"""API de administración RBAC (solo ROLL ADMIN)."""

import csv
import io
from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_file, session
from openpyxl import Workbook

from server.db import get_users_connection
from server.rbac import (
    ADMIN_ROLE_NAME,
    EXPORT_MATRIX_COLUMNS,
    _job_payload,
    _role_payload,
    build_matrix_export_rows,
    build_matrix_pivot,
    enforce_admin_full_access,
    ensure_permission_cells,
    ensure_rbac_seed,
    fetch_matrix,
)
from server.validators import sanitize_string

rbac_bp = Blueprint("rbac", __name__, url_prefix="/admin/rbac")


def admin_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("id_usuario"):
            return jsonify({"ok": False, "error": "Debes iniciar sesión."}), 401
        if session.get("ROLL") != "ADMIN":
            return jsonify(
                {
                    "ok": False,
                    "error": "No autorizado. Esta sección es exclusiva del Rol Administrador.",
                    "code": "FORBIDDEN_ADMIN_ONLY",
                }
            ), 403
        return view(*args, **kwargs)

    return wrapped


@rbac_bp.get("/matrix")
@admin_only
def get_matrix():
    with get_users_connection() as conn:
        ensure_rbac_seed(conn)
        ensure_permission_cells(conn)
        enforce_admin_full_access(conn)
        conn.commit()
        data = fetch_matrix(conn)
    return jsonify({"ok": True, **data})


@rbac_bp.get("/matrix/export.csv")
@admin_only
def export_matrix_csv():
    try:
        with get_users_connection() as conn:
            ensure_rbac_seed(conn)
            ensure_permission_cells(conn)
            enforce_admin_full_access(conn)
            conn.commit()
            rows = build_matrix_export_rows(conn)

        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=EXPORT_MATRIX_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)

        data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
        data.seek(0)
        filename = f"rbac_roles_permisos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(
            data,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )
    except Exception:
        current_app.logger.exception("Error al exportar CSV de RBAC")
        return jsonify({"ok": False, "error": "Error interno del servidor."}), 500


@rbac_bp.get("/matrix/export.xlsx")
@admin_only
def export_matrix_xlsx():
    try:
        with get_users_connection() as conn:
            ensure_rbac_seed(conn)
            ensure_permission_cells(conn)
            enforce_admin_full_access(conn)
            conn.commit()
            flat_rows = build_matrix_export_rows(conn)
            pivot_headers, pivot_rows = build_matrix_pivot(conn)

        workbook = Workbook()
        sheet_flat = workbook.active
        sheet_flat.title = "distribucion"
        sheet_flat.append(EXPORT_MATRIX_COLUMNS)
        for row in flat_rows:
            sheet_flat.append([row.get(col, "") for col in EXPORT_MATRIX_COLUMNS])

        sheet_pivot = workbook.create_sheet("matriz")
        sheet_pivot.append(pivot_headers)
        for row in pivot_rows:
            sheet_pivot.append(row)

        data = io.BytesIO()
        workbook.save(data)
        data.seek(0)
        filename = f"rbac_roles_permisos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            data,
            mimetype=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name=filename,
        )
    except Exception:
        current_app.logger.exception("Error al exportar XLSX de RBAC")
        return jsonify({"ok": False, "error": "Error interno del servidor."}), 500


@rbac_bp.put("/matrix")
@admin_only
def save_matrix():
    """
    Body: { permisos: [ { id_rol, id_job, permiso_activo }, ... ] }
    """
    body = request.get_json(silent=True) or {}
    items = body.get("permisos") or []
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "permisos debe ser una lista."}), 400

    with get_users_connection() as conn:
        admin = conn.execute(
            "SELECT id_rol FROM Roles WHERE nombre_rol = ? COLLATE NOCASE",
            (ADMIN_ROLE_NAME,),
        ).fetchone()
        admin_id = admin["id_rol"] if admin else None

        for item in items:
            try:
                id_rol = int(item.get("id_rol"))
                id_job = int(item.get("id_job"))
            except (TypeError, ValueError):
                continue
            activo = 1 if item.get("permiso_activo") else 0
            if admin_id is not None and id_rol == admin_id:
                activo = 1
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, ?)
                ON CONFLICT(id_rol, id_job) DO UPDATE SET permiso_activo = excluded.permiso_activo
                """,
                (id_rol, id_job, activo),
            )
        enforce_admin_full_access(conn)
        conn.commit()
        data = fetch_matrix(conn)

    return jsonify(
        {
            "ok": True,
            "message": "Matriz de permisos guardada. Los cambios aplican al iniciar sesión o al refrescar permisos.",
            **data,
        }
    )


@rbac_bp.post("/roles")
@admin_only
def create_role():
    body = request.get_json(silent=True) or {}
    nombre = sanitize_string(body.get("nombre_rol"))
    if not nombre:
        return jsonify({"ok": False, "error": "nombre_rol es obligatorio."}), 400
    if nombre.lower() == ADMIN_ROLE_NAME.lower():
        return jsonify({"ok": False, "error": "El rol Administrador ya existe y es protegido."}), 400

    with get_users_connection() as conn:
        exists = conn.execute(
            "SELECT id_rol FROM Roles WHERE nombre_rol = ? COLLATE NOCASE",
            (nombre,),
        ).fetchone()
        if exists:
            return jsonify({"ok": False, "error": "Ya existe un rol con ese nombre."}), 409
        cur = conn.execute(
            """
            INSERT INTO Roles (nombre_rol, estado, protegido, creation_date)
            VALUES (?, 'ACTIVO', 0, datetime('now'))
            """,
            (nombre,),
        )
        ensure_permission_cells(conn)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM Roles WHERE id_rol = ?", (cur.lastrowid,)
        ).fetchone()
    return jsonify({"ok": True, "message": "Rol creado.", "rol": _role_payload(row)}), 201


@rbac_bp.put("/roles/<int:id_rol>")
@admin_only
def update_role(id_rol):
    body = request.get_json(silent=True) or {}
    with get_users_connection() as conn:
        role = conn.execute(
            "SELECT * FROM Roles WHERE id_rol = ?", (id_rol,)
        ).fetchone()
        if not role:
            return jsonify({"ok": False, "error": "Rol no encontrado."}), 404

        nombre = sanitize_string(body.get("nombre_rol")) if "nombre_rol" in body else None
        estado = sanitize_string(body.get("estado")).upper() if "estado" in body else None

        if role["protegido"] or role["nombre_rol"].lower() == ADMIN_ROLE_NAME.lower():
            if nombre and nombre.lower() != role["nombre_rol"].lower():
                return jsonify(
                    {"ok": False, "error": "No se puede renombrar el rol Administrador."}
                ), 400
            if estado and estado != "ACTIVO":
                return jsonify(
                    {"ok": False, "error": "No se puede desactivar el rol Administrador."}
                ), 400
            enforce_admin_full_access(conn)
            conn.commit()
            return jsonify(
                {
                    "ok": True,
                    "message": "El Administrador permanece activo con acceso total.",
                    "rol": _role_payload(role),
                }
            )

        if nombre:
            dup = conn.execute(
                """
                SELECT id_rol FROM Roles
                WHERE nombre_rol = ? COLLATE NOCASE AND id_rol != ?
                """,
                (nombre, id_rol),
            ).fetchone()
            if dup:
                return jsonify({"ok": False, "error": "Ya existe un rol con ese nombre."}), 409
            conn.execute(
                "UPDATE Roles SET nombre_rol = ? WHERE id_rol = ?",
                (nombre, id_rol),
            )
        if estado in ("ACTIVO", "INACTIVO"):
            conn.execute(
                "UPDATE Roles SET estado = ? WHERE id_rol = ?",
                (estado, id_rol),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM Roles WHERE id_rol = ?", (id_rol,)
        ).fetchone()
    return jsonify({"ok": True, "message": "Rol actualizado.", "rol": _role_payload(row)})


@rbac_bp.delete("/roles/<int:id_rol>")
@admin_only
def delete_role(id_rol):
    with get_users_connection() as conn:
        role = conn.execute(
            "SELECT * FROM Roles WHERE id_rol = ?", (id_rol,)
        ).fetchone()
        if not role:
            return jsonify({"ok": False, "error": "Rol no encontrado."}), 404
        if role["protegido"] or role["nombre_rol"].lower() == ADMIN_ROLE_NAME.lower():
            return jsonify(
                {"ok": False, "error": "No se puede eliminar el rol Administrador."}
            ), 400

        conn.execute("DELETE FROM Permisos WHERE id_rol = ?", (id_rol,))
        conn.execute("DELETE FROM Roles WHERE id_rol = ?", (id_rol,))
        conn.commit()
        data = fetch_matrix(conn)

    return jsonify(
        {
            "ok": True,
            "message": f"Rol «{role['nombre_rol']}» eliminado.",
            **data,
        }
    )


@rbac_bp.post("/jobs")
@admin_only
def create_job():
    body = request.get_json(silent=True) or {}
    nombre = sanitize_string(body.get("nombre_job"))
    descripcion = sanitize_string(body.get("descripcion"))
    icono = sanitize_string(body.get("icono")) or "module"
    if not nombre:
        return jsonify({"ok": False, "error": "nombre_job es obligatorio."}), 400

    with get_users_connection() as conn:
        exists = conn.execute(
            "SELECT id_job FROM Jobs WHERE nombre_job = ? COLLATE NOCASE",
            (nombre,),
        ).fetchone()
        if exists:
            return jsonify({"ok": False, "error": "Ya existe un JOB con ese nombre."}), 409
        cur = conn.execute(
            """
            INSERT INTO Jobs (nombre_job, descripcion, icono, estado, creation_date)
            VALUES (?, ?, ?, 'ACTIVO', datetime('now'))
            """,
            (nombre, descripcion or None, icono),
        )
        ensure_permission_cells(conn)
        enforce_admin_full_access(conn)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM Jobs WHERE id_job = ?", (cur.lastrowid,)
        ).fetchone()
    return jsonify({"ok": True, "message": "JOB creado.", "job": _job_payload(row)}), 201


@rbac_bp.put("/jobs/<int:id_job>")
@admin_only
def update_job(id_job):
    body = request.get_json(silent=True) or {}
    with get_users_connection() as conn:
        job = conn.execute(
            "SELECT * FROM Jobs WHERE id_job = ?", (id_job,)
        ).fetchone()
        if not job:
            return jsonify({"ok": False, "error": "JOB no encontrado."}), 404

        if "nombre_job" in body:
            nombre = sanitize_string(body.get("nombre_job"))
            if not nombre:
                return jsonify({"ok": False, "error": "nombre_job no puede estar vacío."}), 400
            dup = conn.execute(
                """
                SELECT id_job FROM Jobs
                WHERE nombre_job = ? COLLATE NOCASE AND id_job != ?
                """,
                (nombre, id_job),
            ).fetchone()
            if dup:
                return jsonify({"ok": False, "error": "Ya existe un JOB con ese nombre."}), 409
            conn.execute(
                "UPDATE Jobs SET nombre_job = ? WHERE id_job = ?",
                (nombre, id_job),
            )
        if "descripcion" in body:
            conn.execute(
                "UPDATE Jobs SET descripcion = ? WHERE id_job = ?",
                (sanitize_string(body.get("descripcion")) or None, id_job),
            )
        if "icono" in body:
            conn.execute(
                "UPDATE Jobs SET icono = ? WHERE id_job = ?",
                (sanitize_string(body.get("icono")) or "module", id_job),
            )
        if "estado" in body:
            estado = sanitize_string(body.get("estado")).upper()
            if estado not in ("ACTIVO", "INACTIVO"):
                return jsonify({"ok": False, "error": "estado inválido."}), 400
            conn.execute(
                "UPDATE Jobs SET estado = ? WHERE id_job = ?",
                (estado, id_job),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM Jobs WHERE id_job = ?", (id_job,)
        ).fetchone()
    return jsonify({"ok": True, "message": "JOB actualizado.", "job": _job_payload(row)})
