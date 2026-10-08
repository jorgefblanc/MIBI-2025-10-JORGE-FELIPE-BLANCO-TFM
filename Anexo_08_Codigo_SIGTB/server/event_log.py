"""Log de acciones por empresa (Excel, aviso a 5 días y borrado a 8 días)."""

from __future__ import annotations

import io
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, send_file
from openpyxl import Workbook
from openpyxl.styles import Font

from server.authz import current_user, is_global_scope, login_required
from server.db import get_empresas_connection, get_users_connection
from server.limits import META_JSON, clip
from server.roles import is_operativo_director_job

eventos_bp = Blueprint("eventos", __name__, url_prefix="/api")

TIPO_AVISO = "LOG_EVENTOS_PENDIENTE"
TIPO_BORRADO = "LOG_EVENTOS_BORRADO"
DIAS_AVISO = 5
DIAS_PURGA_TRAS_AVISO = 3


def ensure_eventos_schema(users_conn) -> None:
    users_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS eventos_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            usuario_id INTEGER,
            usuario_nombre VARCHAR(255),
            usuario_login VARCHAR(255),
            accion TEXT NOT NULL,
            modulo VARCHAR(80),
            sede_id INTEGER,
            servicio_id INTEGER,
            parametros_json TEXT,
            resultado_json TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_eventos_log_empresa ON eventos_log (empresa_id, created_at);
        CREATE TABLE IF NOT EXISTS eventos_log_avisos (
            empresa_id INTEGER PRIMARY KEY,
            first_event_at DATETIME NOT NULL,
            aviso_at DATETIME,
            notificacion_id INTEGER
        );
        """
    )
    cols = {c["name"] for c in users_conn.execute("PRAGMA table_info(eventos_log)").fetchall()}
    for name, spec in {
        "modulo": "VARCHAR(80)",
        "sede_id": "INTEGER",
        "servicio_id": "INTEGER",
        "parametros_json": "TEXT",
        "resultado_json": "TEXT",
    }.items():
        if name not in cols:
            users_conn.execute(f"ALTER TABLE eventos_log ADD COLUMN {name} {spec}")


def _now() -> datetime:
    return datetime.now()


def _now_sql() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def can_manage_event_log(user=None) -> bool:
    user = user or current_user()
    if not user:
        return False
    if is_global_scope(user):
        return True
    return (user.get("ROLL") or "").upper() == "OPERATIVO" and is_operativo_director_job(
        user.get("JOB")
    )


def empresa_id_for_sede(emp_conn, sede_id: int) -> int | None:
    row = emp_conn.execute(
        "SELECT empresa_id FROM sedes WHERE id = ?",
        (sede_id,),
    ).fetchone()
    return int(row["empresa_id"]) if row and row["empresa_id"] else None


def empresa_id_for_servicio(emp_conn, servicio_id: int) -> int | None:
    row = emp_conn.execute(
        """
        SELECT s.empresa_id
        FROM servicios srv
        JOIN sedes s ON s.id = srv.sede_id
        WHERE srv.id = ?
        """,
        (servicio_id,),
    ).fetchone()
    return int(row["empresa_id"]) if row and row["empresa_id"] else None


def describe_usuario(row) -> str:
    """Etiqueta compacta de un usuario para el texto de la acción."""
    if not row:
        return "usuario"
    try:
        name = f"{row['NAME_USER'] or ''} {row['LAST_NAME_USER'] or ''}".strip()
    except (KeyError, IndexError, TypeError):
        name = ""
    try:
        login = row["usuario_login"] or ""
    except (KeyError, IndexError, TypeError):
        login = ""
    try:
        roll = row["ROLL"] or ""
    except (KeyError, IndexError, TypeError):
        roll = ""
    try:
        job = row["JOB"] or ""
    except (KeyError, IndexError, TypeError):
        job = ""
    try:
        uid = row["id_usuario"]
    except (KeyError, IndexError, TypeError):
        uid = None
    label = f"«{name or login or (f'id {uid}' if uid else 'usuario')}»"
    bits = [str(x) for x in (login, roll, job) if x]
    if bits:
        label += f" ({'; '.join(bits)})"
    return label


def log_evento(
    *,
    empresa_id,
    accion: str,
    user=None,
    modulo: str | None = None,
    sede_id: int | None = None,
    servicio_id: int | None = None,
    parametros: dict | None = None,
    resultado: dict | None = None,
) -> None:
    if not empresa_id or not accion:
        return
    try:
        import json

        user = user or current_user()
        nombre = ""
        login = ""
        uid = None
        if user:
            uid = int(user.get("id_usuario") or 0) or None
            login = user.get("usuario_login") or ""
            nombre = (user.get("NAME_USER") or "").strip()
            if not nombre and uid:
                with get_users_connection() as conn:
                    row = conn.execute(
                        "SELECT NAME_USER, LAST_NAME_USER, usuario_login FROM usuarios WHERE id_usuario = ?",
                        (uid,),
                    ).fetchone()
                if row:
                    nombre = f"{row['NAME_USER']} {row['LAST_NAME_USER']}".strip()
                    login = row["usuario_login"] or login
        stamped = _now_sql()
        params_txt = clip(json.dumps(parametros or {}, ensure_ascii=False, default=str), META_JSON) if parametros else None
        result_txt = clip(json.dumps(resultado or {}, ensure_ascii=False, default=str), META_JSON) if resultado else None
        with get_users_connection() as conn:
            ensure_eventos_schema(conn)
            conn.execute(
                """
                INSERT INTO eventos_log (
                    empresa_id, usuario_id, usuario_nombre, usuario_login, accion,
                    modulo, sede_id, servicio_id, parametros_json, resultado_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(empresa_id),
                    uid,
                    nombre or "Sistema",
                    login or None,
                    str(accion)[:500],
                    (modulo or None),
                    int(sede_id) if sede_id else None,
                    int(servicio_id) if servicio_id else None,
                    params_txt,
                    result_txt,
                    stamped,
                ),
            )
            existing = conn.execute(
                "SELECT empresa_id FROM eventos_log_avisos WHERE empresa_id = ?",
                (int(empresa_id),),
            ).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO eventos_log_avisos (empresa_id, first_event_at)
                    VALUES (?, ?)
                    """,
                    (int(empresa_id), stamped),
                )
            conn.commit()
    except Exception as exc:
        print(f"[eventos] no se pudo registrar acción: {exc}")


def _empresa_nombre(empresa_id: int) -> str:
    with get_empresas_connection() as emp_conn:
        row = emp_conn.execute(
            "SELECT ID_Empresa, ID_NIT FROM empresas WHERE id = ?",
            (empresa_id,),
        ).fetchone()
    if not row:
        return f"Empresa {empresa_id}"
    return f"{row['ID_Empresa']} · NIT {row['ID_NIT']}"


def _notify_admin(conn, *, tipo: str, mensaje: str, empresa_id: int, empresa_nombre: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO notificaciones_admin (
            tipo, mensaje, empresa_sugerida, empresa_creada_id, estado, creation_date
        ) VALUES (?, ?, ?, ?, 'PENDIENTE', ?)
        """,
        (tipo, mensaje, empresa_nombre, int(empresa_id), _now_sql()),
    )
    return int(cur.lastrowid)


def _rows_for_empresa(conn, empresa_id: int) -> list:
    return conn.execute(
        """
        SELECT * FROM eventos_log
        WHERE empresa_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (int(empresa_id),),
    ).fetchall()


def _delete_empresa_log(conn, empresa_id: int) -> tuple[int, str | None, str | None]:
    rows = _rows_for_empresa(conn, empresa_id)
    if not rows:
        conn.execute("DELETE FROM eventos_log_avisos WHERE empresa_id = ?", (int(empresa_id),))
        return 0, None, None
    first = rows[0]["created_at"]
    last = rows[-1]["created_at"]
    conn.execute("DELETE FROM eventos_log WHERE empresa_id = ?", (int(empresa_id),))
    conn.execute("DELETE FROM eventos_log_avisos WHERE empresa_id = ?", (int(empresa_id),))
    return len(rows), str(first) if first else None, str(last) if last else None


def _build_xlsx(rows, empresa_nombre: str) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Log de eventos"
    ws.append(["Empresa", empresa_nombre])
    ws.append(["Generado", _now_sql()])
    ws.append([])
    headers = ["Usuario", "Correo", "Fecha y hora", "Módulo", "Sede", "Servicio", "Acción", "Parámetros", "Resultado"]
    ws.append(headers)
    for cell in ws[4]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(
            [
                row["usuario_nombre"] or "Sistema",
                row["usuario_login"] or "",
                row["created_at"] or "",
                row["modulo"] if "modulo" in row.keys() else "",
                row["sede_id"] if "sede_id" in row.keys() else "",
                row["servicio_id"] if "servicio_id" in row.keys() else "",
                row["accion"] or "",
                row["parametros_json"] if "parametros_json" in row.keys() else "",
                row["resultado_json"] if "resultado_json" in row.keys() else "",
            ]
        )
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 10
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 70
    ws.column_dimensions["H"].width = 40
    ws.column_dimensions["I"].width = 40
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def download_and_clear_log(empresa_id: int):
    user = current_user()
    if not can_manage_event_log(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    if not is_global_scope(user) and int(user.get("empresa_id") or 0) != int(empresa_id):
        return jsonify({"ok": False, "error": "Solo puedes descargar el log de tu empresa."}), 403

    nombre = _empresa_nombre(empresa_id)
    with get_users_connection() as conn:
        ensure_eventos_schema(conn)
        rows = _rows_for_empresa(conn, empresa_id)
        if not rows:
            return jsonify({"ok": False, "error": "No hay eventos pendientes de descarga."}), 404
        buf = _build_xlsx(rows, nombre)
        _delete_empresa_log(conn, empresa_id)
        conn.execute(
            """
            UPDATE notificaciones_admin
            SET estado = 'RESUELTA'
            WHERE tipo = ? AND empresa_creada_id = ? AND estado = 'PENDIENTE'
            """,
            (TIPO_AVISO, int(empresa_id)),
        )
        conn.commit()

    filename = f"log_eventos_{empresa_id}_{_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def process_event_log_expiry() -> None:
    """Aviso a los 5 días; borrado 3 días después del aviso."""
    now = _now()
    with get_users_connection() as conn:
        ensure_eventos_schema(conn)
        empresas = [
            int(r["empresa_id"])
            for r in conn.execute(
                "SELECT DISTINCT empresa_id FROM eventos_log"
            ).fetchall()
        ]
        for empresa_id in empresas:
            aviso = conn.execute(
                "SELECT * FROM eventos_log_avisos WHERE empresa_id = ?",
                (empresa_id,),
            ).fetchone()
            first_row = conn.execute(
                "SELECT MIN(created_at) AS first_at FROM eventos_log WHERE empresa_id = ?",
                (empresa_id,),
            ).fetchone()
            first_at = _parse_dt(first_row["first_at"] if first_row else None)
            if not first_at:
                continue
            if not aviso:
                conn.execute(
                    "INSERT INTO eventos_log_avisos (empresa_id, first_event_at) VALUES (?, ?)",
                    (empresa_id, first_at.strftime("%Y-%m-%d %H:%M:%S")),
                )
                aviso_at = None
            else:
                aviso_at = _parse_dt(aviso["aviso_at"])

            if aviso_at is None and now - first_at >= timedelta(days=DIAS_AVISO):
                nombre = _empresa_nombre(empresa_id)
                n = conn.execute(
                    "SELECT COUNT(*) AS n FROM eventos_log WHERE empresa_id = ?",
                    (empresa_id,),
                ).fetchone()["n"]
                nid = _notify_admin(
                    conn,
                    tipo=TIPO_AVISO,
                    mensaje=(
                        f"El log de acciones de {nombre} lleva {DIAS_AVISO} días sin descargarse "
                        f"({n} evento(s)). Descárguelo o descártelo. Si no se descarga en "
                        f"{DIAS_PURGA_TRAS_AVISO} días más, se borrará automáticamente."
                    ),
                    empresa_id=empresa_id,
                    empresa_nombre=nombre,
                )
                conn.execute(
                    """
                    INSERT INTO eventos_log_avisos (empresa_id, first_event_at, aviso_at, notificacion_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(empresa_id) DO UPDATE SET
                        aviso_at = excluded.aviso_at,
                        notificacion_id = excluded.notificacion_id
                    """,
                    (
                        empresa_id,
                        first_at.strftime("%Y-%m-%d %H:%M:%S"),
                        _now_sql(),
                        nid,
                    ),
                )
                continue

            if aviso_at is not None and now - aviso_at >= timedelta(days=DIAS_PURGA_TRAS_AVISO):
                count, first, last = _delete_empresa_log(conn, empresa_id)
                if count:
                    nombre = _empresa_nombre(empresa_id)
                    rango = f"{first or '—'} a {last or '—'}"
                    _notify_admin(
                        conn,
                        tipo=TIPO_BORRADO,
                        mensaje=(
                            f"Se borró automáticamente el log de acciones de {nombre} "
                            f"({count} evento(s); rango {rango}) porque no se descargó "
                            f"tras el aviso de {DIAS_AVISO}+{DIAS_PURGA_TRAS_AVISO} días."
                        ),
                        empresa_id=empresa_id,
                        empresa_nombre=nombre,
                    )
                    conn.execute(
                        """
                        UPDATE notificaciones_admin
                        SET estado = 'RESUELTA'
                        WHERE tipo = ? AND empresa_creada_id = ? AND estado = 'PENDIENTE'
                        """,
                        (TIPO_AVISO, empresa_id),
                    )
        conn.commit()


@eventos_bp.get("/empresas/<int:empresa_id>/eventos/resumen")
@login_required
def resumen_eventos(empresa_id: int):
    user = current_user()
    if not can_manage_event_log(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    if not is_global_scope(user) and int(user.get("empresa_id") or 0) != int(empresa_id):
        return jsonify({"ok": False, "error": "Sin acceso a esta empresa."}), 403
    with get_users_connection() as conn:
        ensure_eventos_schema(conn)
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM eventos_log WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()["n"]
        first = conn.execute(
            "SELECT MIN(created_at) AS v FROM eventos_log WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()["v"]
        last = conn.execute(
            "SELECT MAX(created_at) AS v FROM eventos_log WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()["v"]
        aviso = conn.execute(
            "SELECT aviso_at FROM eventos_log_avisos WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()
    return jsonify(
        {
            "ok": True,
            "empresa_id": empresa_id,
            "pendientes": int(n or 0),
            "desde": first,
            "hasta": last,
            "aviso_at": aviso["aviso_at"] if aviso else None,
            "can_download": bool(n),
        }
    )


@eventos_bp.get("/empresas/<int:empresa_id>/eventos.xlsx")
@login_required
def export_eventos_xlsx(empresa_id: int):
    return download_and_clear_log(empresa_id)
