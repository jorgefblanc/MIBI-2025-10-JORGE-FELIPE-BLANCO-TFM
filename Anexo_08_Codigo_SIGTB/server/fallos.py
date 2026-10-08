"""Reporte de fallos (público como Invitado o usuario autenticado)."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from server.authz import current_user, is_global_scope, login_required
from server.db import get_users_connection
from server.limits import COMMENT, DESCRIPTION, QUERY_LIMIT, SOLUTION, over_limit
from server.presence import item_leido, lecturas_set
from server.validators import sanitize_string

fallos_bp = Blueprint("fallos", __name__, url_prefix="/api")

TIPOS_FALLO = ("Funcional", "Estructura", "Diseño", "Modulo")
ESTADOS_FALLO = ("PENDIENTE", "RESUELTO", "IMPLEMENTADO", "DESCARTADO")
ESTADOS_CIERRE = ("RESUELTO", "IMPLEMENTADO", "DESCARTADO")


def ensure_fallos_schema(users_conn) -> None:
    users_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reportes_fallos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo VARCHAR(40) NOT NULL
                CHECK (tipo IN ('Funcional', 'Estructura', 'Diseño', 'Modulo')),
            descripcion TEXT NOT NULL,
            solucion_recomendada TEXT,
            remitente_nombre VARCHAR(255) NOT NULL DEFAULT 'Invitado',
            remitente_id INTEGER,
            remitente_email VARCHAR(255),
            estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                CHECK (estado IN ('PENDIENTE', 'RESUELTO', 'IMPLEMENTADO', 'DESCARTADO')),
            observacion_admin TEXT,
            creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            resolved_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_reportes_fallos_estado ON reportes_fallos (estado);
        CREATE INDEX IF NOT EXISTS idx_reportes_fallos_fecha ON reportes_fallos (creation_date);
        CREATE TABLE IF NOT EXISTS reportes_fallos_ocultos (
            reporte_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            hidden_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (reporte_id, usuario_id)
        );
        """
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_payload(row) -> dict:
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "descripcion": row["descripcion"],
        "solucion_recomendada": row["solucion_recomendada"] or "",
        "remitente_nombre": row["remitente_nombre"] or "Invitado",
        "remitente_id": row["remitente_id"],
        "remitente_email": row["remitente_email"] or "",
        "estado": row["estado"],
        "observacion_admin": row["observacion_admin"] or "",
        "creation_date": row["creation_date"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
    }


def create_reporte_from_request():
    body = request.get_json(silent=True) or {}
    tipo = sanitize_string(body.get("tipo"), 40)
    descripcion = sanitize_string(body.get("descripcion") or body.get("novedad"), DESCRIPTION)
    solucion = sanitize_string(body.get("solucion_recomendada") or "", SOLUTION)
    if tipo not in TIPOS_FALLO:
        return jsonify(
            {
                "ok": False,
                "error": "Seleccione el tipo de falla: Funcional, Estructura, Diseño o Modulo.",
            }
        ), 400
    if not descripcion or len(descripcion) < 8:
        return jsonify(
            {"ok": False, "error": "Describa la novedad detectada (mínimo 8 caracteres)."}
        ), 400
    raw_desc = body.get("descripcion") or body.get("novedad") or ""
    raw_sol = body.get("solucion_recomendada") or ""
    if isinstance(raw_desc, str) and over_limit(raw_desc.strip(), DESCRIPTION):
        return jsonify(
            {"ok": False, "error": f"La descripción no puede superar {DESCRIPTION} caracteres."}
        ), 400
    if isinstance(raw_sol, str) and over_limit(raw_sol.strip(), SOLUTION):
        return jsonify(
            {"ok": False, "error": f"La solución recomendada no puede superar {SOLUTION} caracteres."}
        ), 400

    user = current_user()
    if user:
        with get_users_connection() as conn:
            row = conn.execute(
                "SELECT NAME_USER, LAST_NAME_USER, usuario_login FROM usuarios WHERE id_usuario = ?",
                (user["id_usuario"],),
            ).fetchone()
        if row:
            nombre = f"{row['NAME_USER']} {row['LAST_NAME_USER']}".strip()
            email = row["usuario_login"]
        else:
            nombre = user.get("NAME_USER") or ""
            email = user.get("usuario_login")
        remitente_id = int(user["id_usuario"])
        remitente_nombre = nombre or "Usuario"
        remitente_email = email
    else:
        remitente_id = None
        remitente_nombre = "Invitado"
        remitente_email = None

    stamped = _now()
    with get_users_connection() as conn:
        ensure_fallos_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO reportes_fallos (
                tipo, descripcion, solucion_recomendada, remitente_nombre,
                remitente_id, remitente_email, estado, creation_date
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
            """,
            (
                tipo,
                descripcion,
                solucion or None,
                remitente_nombre,
                remitente_id,
                remitente_email,
                stamped,
            ),
        )
        conn.commit()
        reporte_id = cur.lastrowid
    return jsonify(
        {
            "ok": True,
            "message": "Reporte de fallos radicado. El administrador lo recibirá en bandeja.",
            "id": reporte_id,
            "creation_date": stamped,
            "remitente_nombre": remitente_nombre,
        }
    ), 201


@fallos_bp.get("/reportes-fallos")
@login_required
def list_reportes_fallos():
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo el administrador puede ver los reportes."}), 403
    with get_users_connection() as conn:
        ensure_fallos_schema(conn)
        uid = int(user["id_usuario"])
        hidden = {
            int(r["reporte_id"])
            for r in conn.execute(
                "SELECT reporte_id FROM reportes_fallos_ocultos WHERE usuario_id = ?",
                (uid,),
            ).fetchall()
        }
        rows = conn.execute(
            """
            SELECT * FROM reportes_fallos
            ORDER BY CASE estado WHEN 'PENDIENTE' THEN 0 ELSE 1 END,
                     creation_date DESC
            LIMIT ?
            """,
            (QUERY_LIMIT,),
        ).fetchall()
        reads = lecturas_set(conn, uid)
        items = []
        for r in rows:
            if int(r["id"]) in hidden:
                continue
            payload = _row_payload(r)
            payload["leido"] = item_leido(payload.get("estado"), "fallo", payload["id"], reads)
            items.append(payload)
        pendientes = sum(1 for it in items if it["estado"] == "PENDIENTE")
    return jsonify({"ok": True, "reportes": items, "pendientes": pendientes})


@fallos_bp.post("/reportes-fallos/<int:reporte_id>/resolver")
@login_required
def resolver_reporte_fallo(reporte_id: int):
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo el administrador puede resolver reportes."}), 403
    body = request.get_json(silent=True) or {}
    estado = sanitize_string(body.get("estado"), 20).upper()
    observacion = sanitize_string(
        body.get("observacion") or body.get("observacion_admin") or "", COMMENT
    )
    raw_obs = body.get("observacion") or body.get("observacion_admin") or ""
    if isinstance(raw_obs, str) and over_limit(raw_obs.strip(), COMMENT):
        return jsonify(
            {"ok": False, "error": f"La observación no puede superar {COMMENT} caracteres."}
        ), 400
    if estado not in ESTADOS_CIERRE:
        return jsonify(
            {
                "ok": False,
                "error": "Indique Resuelto, Implementado o Descartado.",
            }
        ), 400
    with get_users_connection() as conn:
        ensure_fallos_schema(conn)
        row = conn.execute(
            "SELECT * FROM reportes_fallos WHERE id = ?", (reporte_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Reporte no encontrado."}), 404
        conn.execute(
            """
            UPDATE reportes_fallos
            SET estado = ?, observacion_admin = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ?
            """,
            (estado, observacion or None, _now(), int(user["id_usuario"]), reporte_id),
        )
        conn.commit()
        refreshed = conn.execute(
            "SELECT * FROM reportes_fallos WHERE id = ?", (reporte_id,)
        ).fetchone()
    labels = {
        "RESUELTO": "resuelto",
        "IMPLEMENTADO": "implementado",
        "DESCARTADO": "descartado",
    }
    return jsonify(
        {
            "ok": True,
            "message": f"Reporte marcado como {labels[estado]}.",
            "reporte": _row_payload(refreshed),
        }
    )


@fallos_bp.post("/reportes-fallos/<int:reporte_id>/ocultar")
@login_required
def ocultar_reporte_fallo(reporte_id: int):
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    with get_users_connection() as conn:
        ensure_fallos_schema(conn)
        row = conn.execute(
            "SELECT id, estado FROM reportes_fallos WHERE id = ?", (reporte_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Reporte no encontrado."}), 404
        if (row["estado"] or "").upper() not in ESTADOS_CIERRE:
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo se pueden eliminar mensajes de reportes ya cerrados.",
                }
            ), 400
        conn.execute(
            """
            INSERT OR IGNORE INTO reportes_fallos_ocultos (reporte_id, usuario_id)
            VALUES (?, ?)
            """,
            (reporte_id, int(user["id_usuario"])),
        )
        conn.commit()
    return jsonify({"ok": True, "message": "Mensaje eliminado de tu bandeja."})


@fallos_bp.get("/reportes-fallos/dashboard")
@login_required
def dashboard_reportes_fallos():
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo el administrador puede ver este tablero."}), 403
    with get_users_connection() as conn:
        ensure_fallos_schema(conn)
        total = conn.execute("SELECT COUNT(*) AS n FROM reportes_fallos").fetchone()["n"]
        by_estado = {
            r["estado"]: r["n"]
            for r in conn.execute(
                "SELECT estado, COUNT(*) AS n FROM reportes_fallos GROUP BY estado"
            ).fetchall()
        }
        by_tipo = {
            r["tipo"]: r["n"]
            for r in conn.execute(
                "SELECT tipo, COUNT(*) AS n FROM reportes_fallos GROUP BY tipo"
            ).fetchall()
        }
    pendientes = int(by_estado.get("PENDIENTE") or 0)
    atendidos = total - pendientes
    return jsonify(
        {
            "ok": True,
            "total": total,
            "pendientes": pendientes,
            "atendidos": atendidos,
            "por_estado": {k: int(by_estado.get(k) or 0) for k in ESTADOS_FALLO},
            "por_tipo": {k: int(by_tipo.get(k) or 0) for k in TIPOS_FALLO},
        }
    )
