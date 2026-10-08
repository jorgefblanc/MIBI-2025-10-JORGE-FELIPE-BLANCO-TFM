"""Flujo de bandeja: tomar, resolver, confirmar o denegar solicitudes.

Estados: PENDIENTE → TOMADA → RESUELTA → CERRADA
                          ↘ DENEGAR → nueva fila REENVIADA (vuelve al pool).
APROBADA / RECHAZADA se conservan para permisos, PM y adquisición.
"""

from __future__ import annotations

import json
from datetime import datetime

from server.adquisicion import TIPO_SOLICITUD as TIPO_ADQUISICION
from server.adquisicion import user_puede_completar_adquisicion
from server.authz import (
    assigned_sede_ids,
    can_access_sede,
    is_global_scope,
    recipient_for_solicitud,
    sede_ids_for_empresa,
)
from server.db import get_empresas_connection, get_users_connection
from server.event_log import log_evento
from server.limits import COMMENT, META_JSON, over_limit
from server.mailer import send_email
from server.roles import get_permissions
from server.validators import sanitize_string

ESTADOS_CHECK = (
    "PENDIENTE",
    "TOMADA",
    "RESUELTA",
    "REENVIADA",
    "CERRADA",
    "APROBADA",
    "RECHAZADA",
)
ESTADOS_POOL = ("PENDIENTE", "REENVIADA")
ESTADOS_OCULTABLES = ("APROBADA", "RECHAZADA", "CERRADA")
ESTADOS_DESTINO_PENDIENTE = ("PENDIENTE", "REENVIADA", "TOMADA")
ESTADOS_ENVIADAS_PENDIENTE = ("PENDIENTE", "REENVIADA", "TOMADA", "RESUELTA")

TIPO_SUFICIENCIA = "actualizar_datos_suficiencia"
TIPOS_POOL = (
    TIPO_SUFICIENCIA,
    "permisos_ampliados",
    "validar_pm_cronograma",
    TIPO_ADQUISICION,
)
TIPOS_SIN_TOMAR = (
    "cerrar_requisitos_preinstalacion",
    "validar_preinstalacion",
)
TIPOS_DESTINO_EXCLUSIVO = (
    "consulta_general",
    "modificar_sede",
    "modificar_empresa",
)
TIPOS_APROBAR = (
    "permisos_ampliados",
    "consulta_general",
    "modificar_sede",
    "modificar_empresa",
    "validar_pm_cronograma",
)
EVENTO_TOMADA = "solicitud_tomada"
EVENTO_RESUELTA = "solicitud_resuelta"
EVENTO_CONFIRMADA = "solicitud_confirmada"
EVENTO_DENEGADA = "solicitud_denegada"

SOLICITUDES_COPY_COLS = (
    "id",
    "solicitante_id",
    "solicitante_email",
    "solicitante_nombre",
    "solicitante_roll",
    "solicitante_job",
    "destinatario_id",
    "destinatario_email",
    "destinatario_nombre",
    "destinatario_rol",
    "sede_id",
    "empresa_id",
    "servicio_id",
    "ID_sede",
    "name_sede",
    "tipo",
    "mensaje",
    "prioridad",
    "estado",
    "asignado_a",
    "asignado_nombre",
    "comentario",
    "fecha_tomada",
    "fecha_resuelta",
    "parent_id",
    "calificacion",
    "calificado_at",
    "resolved_at",
    "ref_tipo",
    "ref_id",
    "meta_json",
    "creation_date",
)


def now_sql() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_meta(row_or_dict) -> dict:
    raw = None
    if row_or_dict is None:
        return {}
    if hasattr(row_or_dict, "keys"):
        raw = row_or_dict["meta_json"] if "meta_json" in row_or_dict.keys() else None
    elif isinstance(row_or_dict, dict):
        raw = row_or_dict.get("meta_json")
        if row_or_dict.get("meta") and isinstance(row_or_dict.get("meta"), dict):
            return dict(row_or_dict["meta"])
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def dump_meta(meta: dict) -> str | None:
    if not meta:
        return None
    hist = meta.get("historial")
    if isinstance(hist, list) and len(hist) > 12:
        meta = dict(meta)
        meta["historial"] = hist[-12:]
    blob = json.dumps(meta, ensure_ascii=False)
    while len(blob) > META_JSON and isinstance(meta.get("historial"), list) and meta["historial"]:
        meta = dict(meta)
        meta["historial"] = meta["historial"][1:]
        blob = json.dumps(meta, ensure_ascii=False)
    if len(blob) > META_JSON:
        meta = {k: v for k, v in meta.items() if k != "historial"}
        blob = json.dumps(meta, ensure_ascii=False)[:META_JSON]
    return blob


def actor_nombre(user, users_conn=None) -> str:
    first = (user.get("NAME_USER") or "").strip()
    last = (user.get("LAST_NAME_USER") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    uid = int(user.get("id_usuario") or 0)
    if uid and users_conn is not None:
        row = users_conn.execute(
            "SELECT NAME_USER, LAST_NAME_USER, usuario_login FROM usuarios WHERE id_usuario = ?",
            (uid,),
        ).fetchone()
        if row:
            name = f"{row['NAME_USER']} {row['LAST_NAME_USER']}".strip()
            return name or (row["usuario_login"] or "Usuario")
    return (user.get("usuario_login") or "Usuario").strip()


def append_historial(meta: dict, evento: str, user, extra=None, users_conn=None) -> dict:
    out = dict(meta or {})
    hist = list(out.get("historial") or [])
    entry = {
        "evento": evento,
        "usuario_id": int(user.get("id_usuario") or 0) or None,
        "nombre": actor_nombre(user, users_conn),
        "fecha": now_sql(),
    }
    if extra:
        entry.update(extra)
    hist.append(entry)
    out["historial"] = hist[-12:]
    return out


def col(row, name, default=None):
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and name in row.keys():
            val = row[name]
            return default if val is None else val
    except Exception:
        pass
    if isinstance(row, dict):
        val = row.get(name, default)
        return default if val is None else val
    return default


def _user_can_validate_pm(user) -> bool:
    if is_global_scope(user):
        return True
    if (user.get("ROLL") or "").upper() != "ASISTENCIAL":
        return False
    job_norm = (user.get("JOB") or "").strip().casefold()
    if not job_norm:
        return False
    tokens = ("coordinador", "director", "dirección", "direccion", "líder", "lider")
    return any(token in job_norm for token in tokens)


def _has_perm(user, permission_name: str) -> bool:
    if is_global_scope(user):
        return True
    expanded = False
    try:
        from flask import has_request_context, session

        if has_request_context():
            expanded = bool(session.get("expanded_permissions"))
    except Exception:
        pass
    return permission_name in get_permissions(
        user.get("ROLL"), user.get("JOB"), expanded=expanded
    )


def can_tomar_tipo(user, tipo: str) -> bool:
    tipo = (tipo or "").lower()
    if tipo in TIPOS_SIN_TOMAR:
        return False
    if is_global_scope(user):
        return True
    if tipo == TIPO_SUFICIENCIA:
        return _has_perm(user, "edit_suficiencia_asistencial")
    if tipo == "permisos_ampliados":
        return _has_perm(user, "approve_expanded_permissions")
    if tipo == TIPO_ADQUISICION:
        return user_puede_completar_adquisicion(user)
    if tipo == "validar_pm_cronograma":
        return _user_can_validate_pm(user)
    if tipo in TIPOS_DESTINO_EXCLUSIVO:
        return True
    return True


def can_tomar(user, solicitud, users_conn=None) -> bool:
    estado = str(col(solicitud, "estado") or "").upper()
    if estado not in ESTADOS_POOL:
        return False
    if int(col(solicitud, "solicitante_id") or 0) == int(user["id_usuario"]) and not is_global_scope(
        user
    ):
        return False
    if col(solicitud, "asignado_a"):
        return False
    tipo = str(col(solicitud, "tipo") or "").lower()
    if not can_tomar_tipo(user, tipo):
        return False
    if not can_access_sede(user, col(solicitud, "sede_id"), users_conn=users_conn):
        return False
    if tipo in TIPOS_DESTINO_EXCLUSIVO and not is_global_scope(user):
        return int(col(solicitud, "destinatario_id") or 0) == int(user["id_usuario"])
    return True


def _es_asignado(user, solicitud) -> bool:
    uid = int(user["id_usuario"])
    asignado = int(col(solicitud, "asignado_a") or 0)
    return asignado == uid


def can_marcar_resuelta(user, solicitud) -> bool:
    tipo = str(col(solicitud, "tipo") or "").lower()
    if tipo != TIPO_SUFICIENCIA:
        return False
    if str(col(solicitud, "estado") or "").upper() != "TOMADA":
        return False
    if not (
        is_global_scope(user) or _has_perm(user, "edit_suficiencia_asistencial")
    ):
        return False
    return is_global_scope(user) or _es_asignado(user, solicitud)


def can_confirmar_o_denegar(user, solicitud) -> bool:
    tipo = str(col(solicitud, "tipo") or "").lower()
    if tipo != TIPO_SUFICIENCIA:
        return False
    if str(col(solicitud, "estado") or "").upper() != "RESUELTA":
        return False
    return int(col(solicitud, "solicitante_id") or 0) == int(user["id_usuario"])


def can_aprobar_tipo(user, solicitud) -> bool:
    tipo = str(col(solicitud, "tipo") or "").lower()
    if tipo not in TIPOS_APROBAR:
        return False
    estado = str(col(solicitud, "estado") or "").upper()
    if estado == "TOMADA":
        ok = is_global_scope(user) or _es_asignado(user, solicitud)
    elif estado == "PENDIENTE" and is_global_scope(user):
        ok = True
    else:
        return False
    if not ok:
        return False
    if tipo == "permisos_ampliados" and not (
        is_global_scope(user) or _has_perm(user, "approve_expanded_permissions")
    ):
        return False
    if tipo == "validar_pm_cronograma" and not _user_can_validate_pm(user):
        return False
    return True


def flags_for_solicitud(user, item: dict, users_conn=None) -> dict:
    uid = int(user["id_usuario"])
    estado = str(item.get("estado") or "").upper()
    tipo = str(item.get("tipo") or "").lower()
    dest = int(item.get("destinatario_id") or 0)
    asignado = int(item.get("asignado_a") or 0)
    es_asignado = asignado == uid
    en_pool = can_tomar(user, item, users_conn=users_conn)
    puede_adq = False
    if tipo == TIPO_ADQUISICION and user_puede_completar_adquisicion(user):
        if estado == "TOMADA" and (es_asignado or is_global_scope(user)):
            puede_adq = True
        elif estado == "PENDIENTE" and is_global_scope(user):
            puede_adq = True
    return {
        "es_asignado": es_asignado,
        "en_pool": bool(en_pool and dest != uid),
        "puede_tomar": bool(en_pool),
        "puede_marcar_resuelta": can_marcar_resuelta(user, item),
        "puede_confirmar": can_confirmar_o_denegar(user, item),
        "puede_denegar": can_confirmar_o_denegar(user, item),
        "puede_aprobar": can_aprobar_tipo(user, item),
        "puede_completar_adq": puede_adq,
        "es_bandeja_destino": dest == uid or es_asignado or bool(en_pool),
    }


def extra_solicitudes_pool(user, sol_conn) -> list[dict]:
    """Pendientes/reenviadas visibles por sede y permiso, no solo destinatario."""
    if is_global_scope(user):
        return []
    tipos = [t for t in TIPOS_POOL if t != TIPO_ADQUISICION and can_tomar_tipo(user, t)]
    if not tipos:
        return []
    empresa_id = user.get("empresa_id")
    with get_users_connection() as users_conn:
        assigned = assigned_sede_ids(users_conn, user["id_usuario"])
        if assigned:
            sedes = {int(x) for x in assigned}
        elif empresa_id:
            sedes = {int(x) for x in sede_ids_for_empresa(empresa_id)}
        else:
            return []
        if not sedes:
            return []
        t_ph = ",".join("?" * len(tipos))
        s_ph = ",".join("?" * len(sedes))
        rows = sol_conn.execute(
            f"""
            SELECT * FROM solicitudes
            WHERE estado IN ('PENDIENTE', 'REENVIADA')
              AND asignado_a IS NULL
              AND tipo IN ({t_ph})
              AND sede_id IN ({s_ph})
            ORDER BY creation_date DESC
            """,
            (*tipos, *sorted(sedes)),
        ).fetchall()
        uid = int(user["id_usuario"])
        out = []
        for row in rows:
            item = dict(row)
            if int(item.get("solicitante_id") or 0) == uid:
                continue
            if int(item.get("destinatario_id") or 0) == uid:
                continue
            if can_tomar(user, item, users_conn=users_conn):
                out.append(item)
        return out


def _log_solicitud(solicitud, evento: str, user, detalle: str = "") -> None:
    empresa_id = col(solicitud, "empresa_id")
    sid = col(solicitud, "id")
    accion = f"{evento} #{sid}"
    if detalle:
        accion = f"{accion} {detalle}"
    log_evento(empresa_id=empresa_id, accion=accion[:500], user=user)


def _notify_resuelta(solicitud) -> None:
    email = col(solicitud, "solicitante_email") or ""
    sid = col(solicitud, "id")
    sede = (col(solicitud, "name_sede") or col(solicitud, "ID_sede") or "").strip()
    body = (
        f"Tu solicitud #{sid} ha sido resuelta.\n\n"
        f"Sede: {sede or '—'}\n"
        "Abre la bandeja de SIGTB para Confirmar o Denegar la atención.\n"
        "Confirmar archiva la solicitud. Denegar permite reenviarla con un comentario.\n"
    )
    try:
        send_email(email, f"Tu solicitud #{sid} ha sido resuelta.", body)
    except Exception as exc:
        print(f"[solicitudes] no se pudo notificar al solicitante: {exc}")


def take_solicitud(sol_conn, solicitud, user) -> tuple[dict | None, str, int]:
    """Asigna en exclusiva. Retorna (payload_error, mensaje, http)."""
    with get_users_connection() as users_conn:
        if not can_tomar(user, solicitud, users_conn=users_conn):
            return {"ok": False, "error": "No autorizado a tomar esta solicitud."}, "", 403
        dest = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER
            FROM usuarios WHERE id_usuario = ?
            """,
            (user["id_usuario"],),
        ).fetchone()
        nombre = actor_nombre(user, users_conn)
        email = dest["usuario_login"] if dest else user.get("usuario_login")
        meta = append_historial(parse_meta(solicitud), EVENTO_TOMADA, user, users_conn=users_conn)
        sid = int(solicitud["id"])
        cur = sol_conn.execute(
            """
            UPDATE solicitudes
            SET estado = 'TOMADA',
                asignado_a = ?,
                asignado_nombre = ?,
                destinatario_id = ?,
                destinatario_email = ?,
                destinatario_nombre = ?,
                fecha_tomada = datetime('now'),
                meta_json = ?
            WHERE id = ?
              AND estado IN ('PENDIENTE', 'REENVIADA')
              AND asignado_a IS NULL
            """,
            (
                int(user["id_usuario"]),
                nombre[:255],
                int(user["id_usuario"]),
                email,
                nombre[:255],
                dump_meta(meta),
                sid,
            ),
        )
        if cur.rowcount < 1:
            return (
                {"ok": False, "error": "La solicitud ya fue tomada por otro usuario."},
                "",
                409,
            )
        sol_conn.commit()
        refreshed = sol_conn.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    _log_solicitud(refreshed, EVENTO_TOMADA, user, f"por {nombre}")
    return None, f"Solicitud tomada por {nombre}.", 200


def mark_resuelta(sol_conn, solicitud, user) -> tuple[dict | None, str, int]:
    if not can_marcar_resuelta(user, solicitud):
        return {"ok": False, "error": "No autorizado a marcar esta solicitud como resuelta."}, "", 403
    with get_users_connection() as users_conn:
        meta = append_historial(
            parse_meta(solicitud), EVENTO_RESUELTA, user, users_conn=users_conn
        )
        sid = int(solicitud["id"])
        cur = sol_conn.execute(
            """
            UPDATE solicitudes
            SET estado = 'RESUELTA',
                fecha_resuelta = datetime('now'),
                resolved_at = datetime('now'),
                meta_json = ?
            WHERE id = ? AND estado = 'TOMADA'
            """,
            (dump_meta(meta), sid),
        )
        if cur.rowcount < 1:
            return {"ok": False, "error": "La solicitud ya no está tomada."}, "", 400
        sol_conn.commit()
        refreshed = sol_conn.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    _log_solicitud(refreshed, EVENTO_RESUELTA, user)
    _notify_resuelta(refreshed)
    return None, f"Solicitud #{sid} marcada como resuelta. Se notificó al solicitante.", 200


def confirmar_solicitud(sol_conn, solicitud, user) -> tuple[dict | None, str, int]:
    if not can_confirmar_o_denegar(user, solicitud):
        return {"ok": False, "error": "Solo el solicitante puede confirmar esta atención."}, "", 403
    with get_users_connection() as users_conn:
        meta = append_historial(
            parse_meta(solicitud), EVENTO_CONFIRMADA, user, users_conn=users_conn
        )
        sid = int(solicitud["id"])
        cur = sol_conn.execute(
            """
            UPDATE solicitudes
            SET estado = 'CERRADA',
                meta_json = ?
            WHERE id = ? AND estado = 'RESUELTA'
            """,
            (dump_meta(meta), sid),
        )
        if cur.rowcount < 1:
            return {"ok": False, "error": "La solicitud ya no está pendiente de confirmación."}, "", 400
        sol_conn.commit()
        refreshed = sol_conn.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    _log_solicitud(refreshed, EVENTO_CONFIRMADA, user)
    return None, f"Solicitud #{sid} confirmada y archivada.", 200


def denegar_solicitud(sol_conn, solicitud, user, comentario: str) -> tuple[dict | None, str, int]:
    if not can_confirmar_o_denegar(user, solicitud):
        return {"ok": False, "error": "Solo el solicitante puede denegar esta atención."}, "", 403
    raw = comentario if isinstance(comentario, str) else ""
    if over_limit(raw.strip(), COMMENT):
        return (
            {"ok": False, "error": f"El comentario no puede superar {COMMENT} caracteres."},
            "",
            400,
        )
    texto = sanitize_string(raw, COMMENT)
    if not texto or len(texto) < 8:
        return (
            {"ok": False, "error": "Escribe un comentario explicativo (mínimo 8 caracteres)."},
            "",
            400,
        )
    sid = int(solicitud["id"])
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        meta = append_historial(
            parse_meta(solicitud),
            EVENTO_DENEGADA,
            user,
            extra={"comentario": texto},
            users_conn=users_conn,
        )
        dest = recipient_for_solicitud(
            users_conn,
            sede_id=col(solicitud, "sede_id"),
            empresa_id=col(solicitud, "empresa_id"),
            destinatario_rol=col(solicitud, "destinatario_rol") or "asistencial",
        )
        if dest:
            dest_id = dest["id_usuario"]
            dest_email = dest["usuario_login"]
            dest_nombre = f"{dest['NAME_USER']} {dest['LAST_NAME_USER']}".strip()
        else:
            dest_id = col(solicitud, "destinatario_id")
            dest_email = col(solicitud, "destinatario_email")
            dest_nombre = col(solicitud, "destinatario_nombre")
        servicio_id = col(solicitud, "servicio_id")
        if servicio_id:
            srv = emp_conn.execute(
                "SELECT id, name_servicio FROM servicios WHERE id = ?",
                (servicio_id,),
            ).fetchone()
            if srv:
                meta["servicio_id"] = srv["id"]
                meta["servicio"] = srv["name_servicio"]
        cur = sol_conn.execute(
            """
            UPDATE solicitudes
            SET estado = 'CERRADA',
                comentario = ?,
                meta_json = ?
            WHERE id = ? AND estado = 'RESUELTA'
            """,
            (texto, dump_meta(meta), sid),
        )
        if cur.rowcount < 1:
            return {"ok": False, "error": "La solicitud ya no está pendiente de confirmación."}, "", 400
        child_meta = dict(meta)
        child_meta["parent_id"] = sid
        ins = sol_conn.execute(
            """
            INSERT INTO solicitudes (
                solicitante_id, solicitante_email, solicitante_nombre,
                solicitante_roll, solicitante_job,
                destinatario_id, destinatario_email, destinatario_nombre, destinatario_rol,
                sede_id, empresa_id, servicio_id, ID_sede, name_sede,
                tipo, mensaje, prioridad, estado,
                comentario, parent_id, ref_tipo, ref_id, meta_json, creation_date
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, 'REENVIADA',
                ?, ?, ?, ?, ?, datetime('now')
            )
            """,
            (
                col(solicitud, "solicitante_id"),
                col(solicitud, "solicitante_email"),
                col(solicitud, "solicitante_nombre"),
                col(solicitud, "solicitante_roll"),
                col(solicitud, "solicitante_job"),
                dest_id,
                dest_email,
                dest_nombre,
                col(solicitud, "destinatario_rol"),
                col(solicitud, "sede_id"),
                col(solicitud, "empresa_id"),
                col(solicitud, "servicio_id"),
                col(solicitud, "ID_sede"),
                col(solicitud, "name_sede"),
                col(solicitud, "tipo"),
                col(solicitud, "mensaje"),
                col(solicitud, "prioridad") or "MODERADA",
                texto,
                sid,
                col(solicitud, "ref_tipo"),
                col(solicitud, "ref_id"),
                dump_meta(child_meta),
            ),
        )
        new_id = int(ins.lastrowid)
        sol_conn.commit()
        refreshed = sol_conn.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    _log_solicitud(refreshed, EVENTO_DENEGADA, user, f"reenvío #{new_id}")
    return None, f"Solicitud reenviada con comentario (#{new_id}).", 200
