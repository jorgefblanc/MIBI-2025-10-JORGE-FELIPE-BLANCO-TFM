"""API de perfil, solicitudes de la bandeja y notificaciones."""

from flask import Blueprint, jsonify, request, session
import json
import bcrypt

from server.adquisicion import (
    TIPO_SOLICITUD as TIPO_ADQUISICION,
    aplicar_forma_adquisicion,
    can_completar_solicitud_adquisicion,
    extra_solicitudes_adquisicion,
)
from server.authz import (
    assigned_sede_ids,
    can_access_sede,
    can_assign_job_to_target,
    can_review_onboarding_notifications,
    clear_sede_assignments_outside_empresa,
    current_user,
    is_direccion_job,
    is_global_scope,
    login_required,
    permission_required,
    recipient_for_solicitud,
    refresh_session_user,
    user_has_permission,
)
from server.db import (
    get_empresas_connection,
    get_solicitudes_connection,
    get_users_connection,
)
from server.onboarding import JOB_PENDING_TIPO, resolve_job_pending_notifications
from server.org import find_or_create_empresa
from server.event_log import describe_usuario, log_evento
from server.limits import (
    AVISO_VERSION,
    COMMENT,
    MESSAGE,
    META_JSON,
    NAME,
    PHONE,
    QUERY_LIMIT,
    SUBJECT,
    over_limit,
)
from server.presence import (
    item_leido,
    lecturas_set,
    list_online_users,
    mark_leido,
    touch_presence,
)
from server.roles import (
    is_pending_job,
    is_valid_managed_job,
    normalize_job,
    permissions_payload,
)
from server.solicitudes_workflow import (
    ESTADOS_DESTINO_PENDIENTE,
    ESTADOS_ENVIADAS_PENDIENTE,
    ESTADOS_OCULTABLES,
    confirmar_solicitud,
    denegar_solicitud,
    extra_solicitudes_pool,
    flags_for_solicitud,
    mark_resuelta,
    take_solicitud,
)
from server.validators import is_letters_only, sanitize_string, validate_password

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/me")
@login_required
def me():
    user = current_user()
    touch_presence(user["id_usuario"])
    with get_users_connection() as conn:
        row = refresh_session_user(conn, user["id_usuario"])
        if not row:
            return jsonify({"ok": False, "error": "Usuario no encontrado."}), 401
        sede_ids = sorted(assigned_sede_ids(conn, user["id_usuario"]))

    payload = dict(row)
    if row["empresa_id"]:
        with get_empresas_connection() as emp_conn:
            empresa = emp_conn.execute(
                "SELECT ID_Empresa, ID_NIT FROM empresas WHERE id = ?",
                (row["empresa_id"],),
            ).fetchone()
            if empresa:
                payload["ID_Empresa"] = empresa["ID_Empresa"]
                payload["ID_NIT"] = empresa["ID_NIT"]

    expanded = bool(session.get("expanded_permissions"))
    payload.update(permissions_payload(row["ROLL"], row["JOB"], expanded=expanded))
    payload["assigned_sede_ids"] = sede_ids
    payload["global_scope"] = is_global_scope()
    payload["empresa_pendiente"] = row["ROLL"] != "ADMIN" and not row["empresa_id"]
    payload["job_pendiente"] = row["ROLL"] != "ADMIN" and is_pending_job(row["JOB"])
    payload["expanded_permissions"] = expanded
    return jsonify({"ok": True, "user": payload})


@api_bp.get("/online-users")
@login_required
def online_users():
    payload, code = list_online_users(current_user())
    return jsonify(payload), code


@api_bp.get("/bandeja/resumen")
@login_required
def bandeja_resumen():
    """Contadores ligeros para el badge; no serializa el listado completo."""
    user = current_user()
    touch_presence(user["id_usuario"])
    uid = int(user["id_usuario"])
    pendientes_destino = 0
    pendientes_enviadas = 0
    pendientes_notif = 0
    pendientes_fallos = 0
    dest = "','".join(ESTADOS_DESTINO_PENDIENTE)
    enviadas = "','".join(ESTADOS_ENVIADAS_PENDIENTE)
    with get_solicitudes_connection() as sol_conn:
        pendientes_destino = int(
            sol_conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM solicitudes s
                WHERE s.estado IN ('{dest}')
                  AND (s.destinatario_id = ? OR s.asignado_a = ?)
                  AND NOT EXISTS (
                    SELECT 1 FROM solicitudes_ocultas o
                    WHERE o.solicitud_id = s.id AND o.usuario_id = ?
                  )
                """,
                (uid, uid, uid),
            ).fetchone()["n"]
            or 0
        )
        pendientes_enviadas = int(
            sol_conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM solicitudes s
                WHERE s.estado IN ('{enviadas}')
                  AND s.solicitante_id = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM solicitudes_ocultas o
                    WHERE o.solicitud_id = s.id AND o.usuario_id = ?
                  )
                """,
                (uid, uid),
            ).fetchone()["n"]
            or 0
        )
    if can_review_onboarding_notifications(user):
        with get_users_connection() as conn:
            pendientes_notif = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM notificaciones_admin n
                    WHERE n.estado = 'PENDIENTE'
                      AND NOT EXISTS (
                        SELECT 1 FROM notificaciones_ocultas o
                        WHERE o.notificacion_id = n.id AND o.usuario_id = ?
                      )
                    """,
                    (uid,),
                ).fetchone()["n"]
                or 0
            )
            if is_global_scope(user):
                try:
                    pendientes_fallos = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) AS n FROM reportes_fallos r
                            WHERE r.estado = 'PENDIENTE'
                              AND NOT EXISTS (
                                SELECT 1 FROM reportes_fallos_ocultos o
                                WHERE o.reporte_id = r.id AND o.usuario_id = ?
                              )
                            """,
                            (uid,),
                        ).fetchone()["n"]
                        or 0
                    )
                except Exception:
                    pendientes_fallos = 0
    return jsonify(
        {
            "ok": True,
            "pendientes_destino": pendientes_destino,
            "pendientes_enviadas": pendientes_enviadas,
            "pendientes_notif": pendientes_notif,
            "pendientes_fallos": pendientes_fallos,
            "pendientes": pendientes_destino + pendientes_notif + pendientes_fallos,
        }
    )


@api_bp.post("/bandeja/leer")
@login_required
def bandeja_marcar_leido():
    user = current_user()
    body = request.get_json(silent=True) or {}
    kind = sanitize_string(body.get("kind") or "", 20).lower()
    try:
        item_id = int(body.get("id") or 0)
    except (TypeError, ValueError):
        item_id = 0
    if kind not in {"solicitud", "notif", "fallo"} or item_id < 1:
        return jsonify({"ok": False, "error": "Mensaje no válido."}), 400
    with get_users_connection() as conn:
        mark_leido(conn, user["id_usuario"], kind, item_id)
        conn.commit()
    return jsonify({"ok": True, "kind": kind, "id": item_id})


@api_bp.put("/me/perfil")
@login_required
def update_my_profile():
    user = current_user()
    body = request.get_json(silent=True) or {}
    name = sanitize_string(body.get("NAME_USER"), NAME)
    last_name = sanitize_string(body.get("LAST_NAME_USER"), NAME)
    telefono = sanitize_string(body.get("telefono") or "", PHONE)
    password = body.get("password") if isinstance(body.get("password"), str) else ""
    aviso_aceptado = body.get("aviso_aceptado") is True

    field_errors = {}
    if not name or not is_letters_only(name):
        field_errors["NAME_USER"] = "Solo se admiten letras y espacios."
    if not last_name or not is_letters_only(last_name):
        field_errors["LAST_NAME_USER"] = "Solo se admiten letras y espacios."
    if telefono and (len(telefono) < 7 or len(telefono) > PHONE):
        field_errors["telefono"] = "Número de contacto inválido."
    if password:
        password_check = validate_password(password)
        if not password_check["valid"]:
            field_errors["password"] = " ".join(password_check["errors"])
    if field_errors:
        return jsonify({"ok": False, "error": "Datos inválidos.", "fieldErrors": field_errors}), 400

    with get_users_connection() as conn:
        current = conn.execute(
            "SELECT aviso_aceptado_en FROM usuarios WHERE id_usuario = ?",
            (user["id_usuario"],),
        ).fetchone()
        ya_autorizo = bool(current and current["aviso_aceptado_en"])
        if not ya_autorizo and not aviso_aceptado:
            return jsonify(
                {
                    "ok": False,
                    "error": "Debe autorizar el tratamiento de sus datos personales.",
                    "fieldErrors": {"aviso_aceptado": "Autorización pendiente."},
                }
            ), 400
        aviso_sql = ""
        aviso_params = []
        if not ya_autorizo and aviso_aceptado:
            aviso_sql = ", aviso_version = ?, aviso_aceptado_en = datetime('now')"
            aviso_params = [AVISO_VERSION]
        if password:
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            ).decode("utf-8")
            conn.execute(
                f"""
                UPDATE usuarios
                SET NAME_USER = ?, LAST_NAME_USER = ?, telefono = ?, password_hash = ?
                    {aviso_sql}
                WHERE id_usuario = ?
                """,
                (name, last_name, telefono or None, password_hash, *aviso_params, user["id_usuario"]),
            )
        else:
            conn.execute(
                f"""
                UPDATE usuarios
                SET NAME_USER = ?, LAST_NAME_USER = ?, telefono = ?
                    {aviso_sql}
                WHERE id_usuario = ?
                """,
                (name, last_name, telefono or None, *aviso_params, user["id_usuario"]),
            )
        row = conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER,
                   JOB, ROLL, creation_date, empresa_id, telefono,
                   aviso_version, aviso_aceptado_en
            FROM usuarios WHERE id_usuario = ?
            """,
            (user["id_usuario"],),
        ).fetchone()
        conn.commit()

    session["NAME_USER"] = row["NAME_USER"]
    session["LAST_NAME_USER"] = row["LAST_NAME_USER"]

    payload = dict(row)
    if row["empresa_id"]:
        with get_empresas_connection() as emp_conn:
            empresa = emp_conn.execute(
                "SELECT ID_Empresa, ID_NIT FROM empresas WHERE id = ?",
                (row["empresa_id"],),
            ).fetchone()
            if empresa:
                payload["ID_Empresa"] = empresa["ID_Empresa"]
                payload["ID_NIT"] = empresa["ID_NIT"]
    payload.update(permissions_payload(row["ROLL"], row["JOB"], expanded=bool(session.get("expanded_permissions"))))
    payload["global_scope"] = is_global_scope(user)
    payload["empresa_pendiente"] = row["ROLL"] != "ADMIN" and not row["empresa_id"]
    payload["job_pendiente"] = row["ROLL"] != "ADMIN" and is_pending_job(row["JOB"])
    return jsonify({"ok": True, "message": "Perfil actualizado.", "user": payload})


@api_bp.post("/solicitudes-permiso")
@login_required
def create_permission_request():
    body = request.get_json(silent=True) or {}
    tipo = sanitize_string(body.get("tipo") or "consulta_general", 50).lower()
    asunto = sanitize_string(body.get("asunto"), SUBJECT)
    mensaje = sanitize_string(body.get("mensaje"), MESSAGE)
    destinatario_rol = sanitize_string(body.get("destinatario_rol") or "", 40).lower()
    prioridad = sanitize_string(body.get("prioridad") or "MODERADA", 20).upper()
    raw_asunto = body.get("asunto") if isinstance(body.get("asunto"), str) else ""
    raw_mensaje = body.get("mensaje") if isinstance(body.get("mensaje"), str) else ""
    if over_limit(raw_asunto.strip(), SUBJECT):
        return jsonify(
            {"ok": False, "error": f"El asunto no puede superar {SUBJECT} caracteres."}
        ), 400
    if over_limit(raw_mensaje.strip(), MESSAGE):
        return jsonify(
            {"ok": False, "error": f"El mensaje no puede superar {MESSAGE} caracteres."}
        ), 400
    if asunto:
        mensaje = f"{asunto}\n\n{mensaje}".strip() if mensaje else asunto
    if not mensaje or len(mensaje) < 8:
        return jsonify(
            {"ok": False, "error": "Escribe el asunto y el mensaje (mínimo 8 caracteres)."}
        ), 400
    if prioridad not in ("BAJA", "MODERADA", "ALTA"):
        return jsonify({"ok": False, "error": "prioridad inválida."}), 400

    tipos_ok = (
        "modificar_sede",
        "modificar_empresa",
        "actualizar_datos_suficiencia",
        "consulta_general",
        "permisos_ampliados",
    )
    if tipo == "validar_pm_cronograma":
        # Solo el módulo Frecuencia PM puede crear este tipo (evita ref_id forjado).
        return jsonify(
            {
                "ok": False,
                "error": "Las solicitudes de validación PM solo se generan desde Frecuencia PM.",
            }
        ), 400
    if tipo in ("cerrar_requisitos_preinstalacion", "validar_preinstalacion"):
        return jsonify(
            {
                "ok": False,
                "error": "Las solicitudes de preinstalación solo se generan desde el módulo SITIO.",
            }
        ), 400
    if tipo == TIPO_ADQUISICION:
        return jsonify(
            {
                "ok": False,
                "error": "Las solicitudes de forma de adquisición se generan desde Dimensionamiento.",
            }
        ), 400
    if tipo not in tipos_ok:
        return jsonify({"ok": False, "error": "tipo inválido."}), 400

    user = current_user()
    if is_global_scope(user) and tipo not in (
        "actualizar_datos_suficiencia",
    ):
        # ADMIN no radica solicitudes operativas genéricas por este canal
        return jsonify(
            {"ok": False, "error": "El Administrador no radica solicitudes por este canal."}
        ), 403

    if tipo == "actualizar_datos_suficiencia":
        if not (
            user_has_permission("request_suficiencia_update")
            or user_has_permission("view_suficiencia")
            or is_global_scope()
        ):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        destinatario_rol = "asistencial"
    elif tipo == "permisos_ampliados":
        if not user_has_permission("request_expanded_permissions"):
            return jsonify({"ok": False, "error": "No autorizado a solicitar permisos ampliados."}), 403
        if not destinatario_rol:
            destinatario_rol = "coordinacion"
    elif not destinatario_rol:
        destinatario_rol = "coordinacion"

    roles_ok = {
        "direccion",
        "coordinacion",
        "ingenieria",
        "soporte",
        "administracion",
        "asistencial",
    }
    if destinatario_rol not in roles_ok:
        return jsonify({"ok": False, "error": "destinatario_rol inválido."}), 400

    if destinatario_rol == "administracion":
        if not (is_direccion_job(user.get("JOB")) or is_global_scope(user)):
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo Dirección puede enviar solicitudes a Administración.",
                }
            ), 403

    try:
        sede_id = int(body.get("sede_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "sede_id inválido."}), 400

    servicio_id = None
    if body.get("servicio_id") not in (None, ""):
        try:
            servicio_id = int(body.get("servicio_id"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "servicio_id inválido."}), 400

    ref_tipo = sanitize_string(body.get("ref_tipo") or "") or None
    if body.get("ref_id") not in (None, ""):
        return jsonify(
            {
                "ok": False,
                "error": "Las referencias de módulo no se aceptan en este canal.",
            }
        ), 400
    meta_raw = body.get("meta")
    meta_json = None
    if isinstance(meta_raw, dict):
        meta_json = json.dumps(meta_raw, ensure_ascii=False)
        if len(meta_json) > META_JSON:
            return jsonify({"ok": False, "error": "Los metadatos de la solicitud son demasiado extensos."}), 400
    elif isinstance(meta_raw, str) and meta_raw.strip():
        meta_json = meta_raw.strip()
        if len(meta_json) > META_JSON:
            return jsonify({"ok": False, "error": "Los metadatos de la solicitud son demasiado extensos."}), 400

    with (
        get_empresas_connection() as emp_conn,
        get_users_connection() as users_conn,
        get_solicitudes_connection() as sol_conn,
    ):
        sede = emp_conn.execute(
            """
            SELECT s.id, s.ID_sede, s.name_sede, s.empresa_id, e.ID_Empresa
            FROM sedes s
            JOIN empresas e ON e.id = s.empresa_id
            WHERE s.id = ?
            """,
            (sede_id,),
        ).fetchone()
        if not sede:
            return jsonify({"ok": False, "error": "Sede no encontrada."}), 404
        if not can_access_sede(user, sede_id, users_conn=users_conn):
            return jsonify(
                {"ok": False, "error": "No puedes radicar solicitudes en esta sede."}
            ), 403

        if servicio_id:
            srv = emp_conn.execute(
                """
                SELECT id, name_servicio, ID_servicio, sede_id
                FROM servicios WHERE id = ?
                """,
                (servicio_id,),
            ).fetchone()
            if not srv or int(srv["sede_id"]) != int(sede_id):
                return jsonify(
                    {"ok": False, "error": "El servicio no pertenece a la sede indicada."}
                ), 400
        else:
            srv = None

        meta_obj = {}
        if isinstance(meta_raw, dict):
            meta_obj = dict(meta_raw)
        elif isinstance(meta_json, str) and meta_json.strip():
            try:
                parsed = json.loads(meta_json)
                if isinstance(parsed, dict):
                    meta_obj = parsed
            except Exception:
                meta_obj = {}
        meta_obj["empresa_id"] = sede["empresa_id"]
        meta_obj["empresa"] = sede["ID_Empresa"]
        if srv:
            meta_obj["servicio_id"] = srv["id"]
            meta_obj["servicio"] = srv["name_servicio"]
            if srv["ID_servicio"]:
                meta_obj["ID_servicio"] = srv["ID_servicio"]
        meta_json = json.dumps(meta_obj, ensure_ascii=False)
        if len(meta_json) > META_JSON:
            return jsonify(
                {"ok": False, "error": "Los metadatos de la solicitud son demasiado extensos."}
            ), 400

        solicitante = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, ROLL, JOB
            FROM usuarios WHERE id_usuario = ?
            """,
            (user["id_usuario"],),
        ).fetchone()
        if not solicitante:
            return jsonify({"ok": False, "error": "Usuario no encontrado."}), 404

        dest = recipient_for_solicitud(
            users_conn,
            sede_id=sede_id,
            empresa_id=sede["empresa_id"],
            destinatario_rol=destinatario_rol,
        )
        if not dest:
            labels = {
                "direccion": "Dirección operativa",
                "coordinacion": "Coordinación",
                "ingenieria": "Ingeniería",
                "soporte": "Soporte técnico",
                "administracion": "Administración",
                "asistencial": "rol asistencial",
            }
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        f"No hay destinatario ({labels.get(destinatario_rol, destinatario_rol)}) "
                        "disponible para esta sede/empresa."
                    ),
                }
            ), 400

        cur = sol_conn.execute(
            """
            INSERT INTO solicitudes (
                solicitante_id, solicitante_email, solicitante_nombre,
                solicitante_roll, solicitante_job,
                destinatario_id, destinatario_email, destinatario_nombre, destinatario_rol,
                sede_id, empresa_id, servicio_id, ID_sede, name_sede,
                tipo, mensaje, prioridad, estado,
                ref_tipo, ref_id, meta_json, creation_date
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, 'PENDIENTE',
                ?, ?, ?, datetime('now')
            )
            """,
            (
                solicitante["id_usuario"],
                solicitante["usuario_login"],
                f"{solicitante['NAME_USER']} {solicitante['LAST_NAME_USER']}".strip(),
                solicitante["ROLL"],
                solicitante["JOB"],
                dest["id_usuario"],
                dest["usuario_login"],
                f"{dest['NAME_USER']} {dest['LAST_NAME_USER']}".strip(),
                destinatario_rol,
                sede_id,
                sede["empresa_id"],
                servicio_id,
                sede["ID_sede"],
                sede["name_sede"],
                tipo,
                mensaje,
                prioridad,
                ref_tipo,
                None,
                meta_json,
            ),
        )
        sol_conn.commit()
        request_id = cur.lastrowid

    return jsonify(
        {
            "ok": True,
            "message": "Solicitud radicada y enviada a la bandeja del destinatario.",
            "solicitud": {
                "id": request_id,
                "destinatario": dest["usuario_login"],
                "destinatario_nombre": dest["NAME_USER"],
                "destinatario_rol": destinatario_rol,
                "prioridad": prioridad,
                "tipo": tipo,
                "ref_tipo": ref_tipo,
                "ref_id": None,
            },
        }
    ), 201


def _solicitud_payload(row):
    item = dict(row)
    # Compatibilidad con UI anterior
    item["coordinador_id"] = row["destinatario_id"]
    item["email_destino"] = row["destinatario_email"]
    meta = item.get("meta_json")
    if isinstance(meta, str) and meta.strip():
        try:
            item["meta"] = json.loads(meta)
        except Exception:
            item["meta"] = None
    else:
        item["meta"] = None
    if not item.get("servicio_id") and isinstance(item.get("meta"), dict):
        item["servicio_id"] = item["meta"].get("servicio_id")
    item["es_destinatario"] = False
    item["es_solicitante"] = False
    return item


def _can_validate_pm(user) -> bool:
    """Misma regla que Frecuencia PM: ADMIN o ASISTENCIAL Coordinador/Director/Líder."""
    if is_global_scope(user):
        return True
    if (user.get("ROLL") or "").upper() != "ASISTENCIAL":
        return False
    job_norm = (user.get("JOB") or "").strip().casefold()
    if not job_norm:
        return False
    tokens = ("coordinador", "director", "dirección", "direccion", "líder", "lider")
    return any(token in job_norm for token in tokens)


def _apply_pm_validation_from_solicitud(solicitud, decision_sol, user, body=None):
    """Sincroniza pm_validacion cuando se resuelve validar_pm_cronograma desde bandeja."""
    if (solicitud["tipo"] or "") != "validar_pm_cronograma":
        return None
    ref_id = solicitud["ref_id"] if "ref_id" in solicitud.keys() else None
    body = body or {}
    pm_decision = "APROBADO" if decision_sol == "APROBADA" else "RECHAZADO"
    calificacion = body.get("calificacion")
    comentario = sanitize_string(body.get("comentario") or "", COMMENT)

    with get_empresas_connection() as emp_conn:
        # Vínculo autoritativo: pm_validacion.solicitud_id == esta solicitud.
        val = emp_conn.execute(
            "SELECT * FROM pm_validacion WHERE solicitud_id = ?",
            (solicitud["id"],),
        ).fetchone()
        if not val and ref_id:
            # Compatibilidad con registros antiguos: solo si aún no hay otra solicitud dueña.
            candidate = emp_conn.execute(
                "SELECT * FROM pm_validacion WHERE id = ?", (ref_id,)
            ).fetchone()
            if candidate and (
                candidate["solicitud_id"] is None
                or int(candidate["solicitud_id"]) == int(solicitud["id"])
            ):
                # Misma sede/empresa de la solicitud (anti cross-tenant).
                inv = emp_conn.execute(
                    """
                    SELECT pi.id, srv.sede_id, s.empresa_id
                    FROM pm_inventario pi
                    JOIN servicios srv ON srv.id = pi.servicio_id
                    JOIN sedes s ON s.id = srv.sede_id
                    WHERE pi.id = ?
                    """,
                    (candidate["pm_inventario_id"],),
                ).fetchone()
                same_tenant = bool(
                    inv
                    and int(inv["sede_id"] or 0) == int(solicitud["sede_id"] or 0)
                    and (
                        solicitud["empresa_id"] is None
                        or int(inv["empresa_id"] or 0) == int(solicitud["empresa_id"] or 0)
                    )
                )
                if same_tenant:
                    val = candidate
                    emp_conn.execute(
                        """
                        UPDATE pm_validacion
                        SET solicitud_id = ?
                        WHERE id = ? AND (solicitud_id IS NULL OR solicitud_id = ?)
                        """,
                        (solicitud["id"], candidate["id"], solicitud["id"]),
                    )
        if not val:
            return {
                "ok": False,
                "error": "La solicitud PM no tiene validación vinculada.",
            }
        linked = val["solicitud_id"]
        if linked is not None and int(linked) != int(solicitud["id"]):
            return {
                "ok": False,
                "error": "La validación PM está vinculada a otra solicitud.",
            }
        # No reescribir decisiones ya cerradas (evita flip con solicitudes huérfanas).
        if val["estado"] != "CUMPLIDO":
            return {
                "ok": False,
                "error": (
                    "Solo se puede resolver un PM en estado CUMPLIDO "
                    f"(actual: {val['estado']})."
                ),
            }
        cur = emp_conn.execute(
            """
            UPDATE pm_validacion SET
                estado = ?,
                validado_por = ?,
                validado_por_login = ?,
                calificacion = COALESCE(?, calificacion),
                comentario = CASE WHEN ? != '' THEN ? ELSE comentario END,
                updated_at = datetime('now')
            WHERE id = ? AND estado = 'CUMPLIDO'
            """,
            (
                pm_decision,
                user["id_usuario"],
                user.get("usuario_login"),
                calificacion,
                comentario,
                comentario,
                val["id"],
            ),
        )
        if cur.rowcount < 1:
            return {
                "ok": False,
                "error": "La validación PM cambió de estado; reintenta desde Frecuencia PM.",
            }
        emp_conn.commit()
    return {"ok": True}


@api_bp.get("/solicitudes-permiso")
@login_required
def list_permission_requests():
    user = current_user()
    with get_solicitudes_connection() as sol_conn:
        if is_global_scope(user):
            rows = sol_conn.execute(
                """
                SELECT * FROM solicitudes
                ORDER BY creation_date DESC
                LIMIT ?
                """,
                (QUERY_LIMIT,),
            ).fetchall()
        else:
            rows = sol_conn.execute(
                """
                SELECT * FROM solicitudes
                WHERE solicitante_id = ? OR destinatario_id = ? OR asignado_a = ?
                ORDER BY creation_date DESC
                LIMIT ?
                """,
                (user["id_usuario"], user["id_usuario"], user["id_usuario"], QUERY_LIMIT),
            ).fetchall()
        result = [_solicitud_payload(r) for r in rows]
        uid = int(user["id_usuario"])
        seen = {int(item["id"]) for item in result}
        for extra in extra_solicitudes_adquisicion(user, sol_conn):
            eid = int(extra["id"])
            if eid in seen:
                continue
            seen.add(eid)
            result.append(_solicitud_payload(extra))
        for extra in extra_solicitudes_pool(user, sol_conn):
            eid = int(extra["id"])
            if eid in seen:
                continue
            seen.add(eid)
            result.append(_solicitud_payload(extra))
        with get_users_connection() as users_conn:
            reads = lecturas_set(users_conn, uid)
            for item in result:
                item["es_destinatario"] = int(item.get("destinatario_id") or 0) == uid
                item["es_solicitante"] = int(item.get("solicitante_id") or 0) == uid
                item.update(flags_for_solicitud(user, item, users_conn=users_conn))
                if item.get("es_bandeja_destino"):
                    item["es_destinatario"] = True
                if (item.get("tipo") or "") == TIPO_ADQUISICION:
                    item["es_gestor_adquisicion"] = True
                item["leido"] = item_leido(
                    item.get("estado"), "solicitud", item["id"], reads
                )
        hidden_ids = {
            int(r["solicitud_id"])
            for r in sol_conn.execute(
                "SELECT solicitud_id FROM solicitudes_ocultas WHERE usuario_id = ?",
                (uid,),
            ).fetchall()
        }
        result = [item for item in result if int(item["id"]) not in hidden_ids]
        pendientes_destino = sum(
            1
            for item in result
            if item.get("es_bandeja_destino")
            and (item.get("estado") or "") in ESTADOS_DESTINO_PENDIENTE
        )
        pendientes_enviadas = sum(
            1
            for item in result
            if item.get("es_solicitante")
            and (item.get("estado") or "") in ESTADOS_ENVIADAS_PENDIENTE
        )
    return jsonify(
        {
            "ok": True,
            "solicitudes": result,
            "pendientes_destino": pendientes_destino,
            "pendientes_enviadas": pendientes_enviadas,
        }
    )


def _load_solicitud(conn, solicitud_id):
    return conn.execute(
        "SELECT * FROM solicitudes WHERE id = ?",
        (solicitud_id,),
    ).fetchone()


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/tomar")
@login_required
def take_permission_request(solicitud_id):
    user = current_user()
    with get_solicitudes_connection() as conn:
        solicitud = _load_solicitud(conn, solicitud_id)
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
        err, msg, code = take_solicitud(conn, solicitud, user)
        if err:
            return jsonify(err), code
        refreshed = _load_solicitud(conn, solicitud_id)
    item = _solicitud_payload(refreshed)
    with get_users_connection() as users_conn:
        item.update(flags_for_solicitud(user, item, users_conn=users_conn))
    return jsonify({"ok": True, "message": msg, "solicitud": item})


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/confirmar")
@login_required
def confirm_permission_request(solicitud_id):
    user = current_user()
    with get_solicitudes_connection() as conn:
        solicitud = _load_solicitud(conn, solicitud_id)
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
        err, msg, code = confirmar_solicitud(conn, solicitud, user)
        if err:
            return jsonify(err), code
    return jsonify({"ok": True, "message": msg})


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/denegar")
@login_required
def deny_permission_request(solicitud_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    with get_solicitudes_connection() as conn:
        solicitud = _load_solicitud(conn, solicitud_id)
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
        err, msg, code = denegar_solicitud(
            conn, solicitud, user, body.get("comentario") or body.get("mensaje") or ""
        )
        if err:
            return jsonify(err), code
    return jsonify({"ok": True, "message": msg})


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/resolver")
@login_required
def resolve_permission_request(solicitud_id):
    body = request.get_json(silent=True) or {}
    decision = sanitize_string(body.get("decision")).upper()
    if decision not in ("APROBADA", "RECHAZADA", "RESUELTA"):
        return jsonify({"ok": False, "error": "decision inválida."}), 400

    user = current_user()
    with get_solicitudes_connection() as conn:
        solicitud = _load_solicitud(conn, solicitud_id)
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404

        if decision == "RESUELTA":
            err, msg, code = mark_resuelta(conn, solicitud, user)
            if err:
                return jsonify(err), code
            return jsonify({"ok": True, "message": msg})

        is_dest = solicitud["destinatario_id"] == user["id_usuario"]
        tipo = (solicitud["tipo"] or "").lower()
        estado = (solicitud["estado"] or "").upper()
        asignado = 0
        if "asignado_a" in solicitud.keys() and solicitud["asignado_a"]:
            asignado = int(solicitud["asignado_a"])
        can_resolve = is_global_scope(user) or is_dest or asignado == int(user["id_usuario"])
        if tipo == TIPO_ADQUISICION:
            can_resolve = can_completar_solicitud_adquisicion(user, dict(solicitud))
        if not can_resolve:
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        if tipo == "actualizar_datos_suficiencia":
            return jsonify(
                {
                    "ok": False,
                    "error": "Marque la solicitud como resuelta; el solicitante confirmará o denegará.",
                }
            ), 400
        if estado == "TOMADA":
            if asignado and asignado != int(user["id_usuario"]) and not is_global_scope(user):
                return jsonify({"ok": False, "error": "La solicitud está asignada a otro usuario."}), 403
        elif estado == "PENDIENTE":
            if not is_global_scope(user):
                return jsonify(
                    {"ok": False, "error": "Primero toma la solicitud."}
                ), 400
        else:
            return jsonify({"ok": False, "error": "La solicitud ya fue resuelta."}), 400
        if tipo == "permisos_ampliados" and not (
            is_global_scope(user) or user_has_permission("approve_expanded_permissions")
        ):
            return jsonify(
                {"ok": False, "error": "Se requiere permiso para aprobar permisos ampliados."}
            ), 403
        if tipo == "actualizar_datos_suficiencia" and not (
            is_global_scope(user) or user_has_permission("edit_suficiencia_asistencial")
        ):
            return jsonify(
                {
                    "ok": False,
                    "error": "Se requiere permiso asistencial para resolver esta solicitud.",
                }
            ), 403
        if tipo == "validar_pm_cronograma" and not _can_validate_pm(user):
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Solo ADMIN o ASISTENCIAL (Coordinador/Director/Dirección/Líder) "
                        "pueden validar PM desde bandeja."
                    ),
                }
            ), 403
        if tipo in ("cerrar_requisitos_preinstalacion", "validar_preinstalacion"):
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "La preinstalación se valida en el módulo SITIO, no desde bandeja."
                    ),
                }
            ), 400

        if tipo == "validar_pm_cronograma":
            sync = _apply_pm_validation_from_solicitud(solicitud, decision, user, body)
            if sync and not sync.get("ok"):
                return jsonify(sync), 400

        if tipo == TIPO_ADQUISICION:
            if decision != "APROBADA":
                return jsonify(
                    {
                        "ok": False,
                        "error": "Esta solicitud se cierra al registrar la forma de adquisición, no se rechaza.",
                    }
                ), 400
            try:
                eq_id = int(solicitud["ref_id"] or 0)
            except (TypeError, ValueError):
                eq_id = 0
            if not eq_id:
                return jsonify(
                    {"ok": False, "error": "La solicitud no está vinculada a un equipo."}
                ), 400
            try:
                applied = aplicar_forma_adquisicion(
                    inventario_equipo_id=eq_id,
                    forma=body.get("forma_adquisicion") or "",
                    observacion=body.get("observacion") or body.get("comentario") or "",
                    user=user,
                )
            except ValueError as err:
                return jsonify({"ok": False, "error": str(err)}), 400
            meta_raw = solicitud["meta_json"] if "meta_json" in solicitud.keys() else None
            meta = {}
            if isinstance(meta_raw, str) and meta_raw.strip():
                try:
                    import json as _json

                    meta = _json.loads(meta_raw)
                except Exception:
                    meta = {}
            meta.update(applied)
            import json as _json

            conn.execute(
                """
                UPDATE solicitudes
                SET estado = ?, resolved_at = datetime('now'), meta_json = ?
                WHERE id = ?
                """,
                (decision, _json.dumps(meta, ensure_ascii=False), solicitud_id),
            )
            conn.commit()
            verb = "tercerizado (MP a cargo de tercero)" if applied.get("mp_forzado_tercerizado") else "registrada"
            return jsonify(
                {
                    "ok": True,
                    "message": f"Forma de adquisición {verb}: {applied['forma_adquisicion']}.",
                }
            )

        conn.execute(
            """
            UPDATE solicitudes
            SET estado = ?, resolved_at = datetime('now')
            WHERE id = ?
            """,
            (decision, solicitud_id),
        )
        conn.commit()

    msg = f"Solicitud marcada como {decision}."
    if (solicitud["tipo"] or "") == "validar_pm_cronograma":
        verb = "aprobada" if decision == "APROBADA" else "rechazada"
        msg = f"Validación PM {verb} y solicitud cerrada en bandeja."
    return jsonify({"ok": True, "message": msg})


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/ocultar")
@login_required
def hide_permission_request(solicitud_id):
    """Quita de la bandeja del usuario una solicitud ya resuelta (aprobada o rechazada)."""
    user = current_user()
    uid = int(user["id_usuario"])
    with get_solicitudes_connection() as conn:
        solicitud = conn.execute(
            """
            SELECT id, estado, solicitante_id, destinatario_id, asignado_a
            FROM solicitudes WHERE id = ?
            """,
            (solicitud_id,),
        ).fetchone()
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
        estado = (solicitud["estado"] or "").upper()
        if estado not in ESTADOS_OCULTABLES:
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo se pueden eliminar mensajes de solicitudes ya resueltas.",
                }
            ), 400
        is_party = uid in (
            int(solicitud["solicitante_id"] or 0),
            int(solicitud["destinatario_id"] or 0),
            int(solicitud["asignado_a"] or 0) if "asignado_a" in solicitud.keys() else 0,
        )
        if not is_party and not is_global_scope(user):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        conn.execute(
            """
            INSERT OR IGNORE INTO solicitudes_ocultas (solicitud_id, usuario_id)
            VALUES (?, ?)
            """,
            (solicitud_id, uid),
        )
        conn.commit()
    return jsonify({"ok": True, "message": "Mensaje eliminado de tu bandeja."})


@api_bp.post("/solicitudes-permiso/<int:solicitud_id>/calificar")
@login_required
def rate_permission_request(solicitud_id):
    body = request.get_json(silent=True) or {}
    calificacion = sanitize_string(body.get("calificacion")).lower().replace(" ", "_")
    allowed = {
        "muy_satisfecho": "Muy satisfecho",
        "satisfecho": "Satisfecho",
        "insatisfecho": "Insatisfecho",
        "muy_insatisfecho": "Muy insatisfecho",
    }
    label_map = {v.lower(): k for k, v in allowed.items()}
    if calificacion in label_map:
        calificacion = label_map[calificacion]
    if calificacion not in allowed:
        return jsonify({"ok": False, "error": "calificacion inválida."}), 400

    user = current_user()
    with get_solicitudes_connection() as conn:
        solicitud = conn.execute(
            "SELECT * FROM solicitudes WHERE id = ?",
            (solicitud_id,),
        ).fetchone()
        if not solicitud:
            return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
        if solicitud["solicitante_id"] != user["id_usuario"]:
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo quien radicó la solicitud puede calificarla.",
                }
            ), 403
        if solicitud["estado"] not in ("APROBADA", "RECHAZADA"):
            return jsonify(
                {
                    "ok": False,
                    "error": "La solicitud debe estar resuelta para calificar.",
                }
            ), 400
        existing = (solicitud["calificacion"] or "").strip()
        if existing in allowed.values():
            return jsonify({"ok": False, "error": "La solicitud ya fue calificada."}), 400
        conn.execute(
            """
            UPDATE solicitudes
            SET calificacion = ?, calificado_at = datetime('now')
            WHERE id = ?
            """,
            (allowed[calificacion], solicitud_id),
        )
        conn.commit()
    return jsonify(
        {
            "ok": True,
            "message": f"Calificación registrada: {allowed[calificacion]}.",
            "calificacion": allowed[calificacion],
        }
    )


@api_bp.post("/permisos-ampliados/activar")
@login_required
@permission_required("request_expanded_permissions")
def activate_expanded_permissions():
    user = current_user()
    with get_solicitudes_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM solicitudes
            WHERE solicitante_id = ?
              AND estado = 'APROBADA'
              AND tipo = 'permisos_ampliados'
            ORDER BY creation_date DESC LIMIT 1
            """,
            (user["id_usuario"],),
        ).fetchone()
    if not row:
        return jsonify(
            {
                "ok": False,
                "error": "No tienes una solicitud de permisos ampliados APROBADA.",
            }
        ), 400
    session["expanded_permissions"] = True
    return jsonify({"ok": True, "message": "Permisos ampliados activados."})


def _notif_payload(row):
    data = dict(row)
    data["solicitante_roll"] = row["solicitante_roll"] if "solicitante_roll" in row.keys() else None
    data["solicitante_job"] = row["solicitante_job"] if "solicitante_job" in row.keys() else None
    data["solicitante_empresa_id"] = (
        row["solicitante_empresa_id"] if "solicitante_empresa_id" in row.keys() else None
    )
    return data


_NOTIF_SELECT = """
    SELECT n.*,
           u.ROLL AS solicitante_roll,
           u.JOB AS solicitante_job,
           u.empresa_id AS solicitante_empresa_id
    FROM notificaciones_admin n
    LEFT JOIN usuarios u ON u.id_usuario = n.solicitante_id
"""


def _notif_visible_to(user, row) -> bool:
    if is_global_scope(user):
        return True
    if (row["tipo"] or "") != JOB_PENDING_TIPO:
        return False
    target = {
        "ROLL": row["solicitante_roll"] if "solicitante_roll" in row.keys() else None,
        "empresa_id": (
            row["solicitante_empresa_id"] if "solicitante_empresa_id" in row.keys() else None
        ),
        "JOB": row["solicitante_job"] if "solicitante_job" in row.keys() else None,
    }
    return can_assign_job_to_target(user, target)


@api_bp.get("/admin/notificaciones")
@login_required
def list_admin_notifications():
    user = current_user()
    if not can_review_onboarding_notifications(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    estado = sanitize_string(request.args.get("estado") or "")
    with get_users_connection() as conn:
        if estado:
            rows = conn.execute(
                _NOTIF_SELECT
                + """
                WHERE n.estado = ? ORDER BY n.creation_date DESC
                """,
                (estado.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                _NOTIF_SELECT
                + """
                ORDER BY CASE n.estado WHEN 'PENDIENTE' THEN 0 ELSE 1 END,
                         n.creation_date DESC
                """
            ).fetchall()
        uid = int(user["id_usuario"])
        hidden_ids = {
            int(r["notificacion_id"])
            for r in conn.execute(
                "SELECT notificacion_id FROM notificaciones_ocultas WHERE usuario_id = ?",
                (uid,),
            ).fetchall()
        }
        visible = [
            r
            for r in rows
            if _notif_visible_to(user, r) and int(r["id"]) not in hidden_ids
        ]
        reads = lecturas_set(conn, uid)
        pending = sum(1 for r in visible if r["estado"] == "PENDIENTE")
        notifs = []
        for r in visible[:QUERY_LIMIT]:
            payload = _notif_payload(r)
            payload["leido"] = item_leido(payload.get("estado"), "notif", payload["id"], reads)
            notifs.append(payload)
    return jsonify(
        {
            "ok": True,
            "notificaciones": notifs,
            "pendientes": pending,
        }
    )


@api_bp.post("/admin/notificaciones/<int:notif_id>/ocultar")
@login_required
def hide_admin_notification(notif_id):
    """Quita de la bandeja del usuario una notificación ya resuelta o descartada."""
    user = current_user()
    if not can_review_onboarding_notifications(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    uid = int(user["id_usuario"])
    with get_users_connection() as conn:
        notif = _load_pending_notif(conn, notif_id)
        if not notif:
            return jsonify({"ok": False, "error": "No encontrada."}), 404
        if not _notif_visible_to(user, notif):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        estado = (notif["estado"] or "").upper()
        if estado not in ("RESUELTA", "DESCARTADA"):
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo se pueden eliminar mensajes de solicitudes ya resueltas.",
                }
            ), 400
        conn.execute(
            """
            INSERT OR IGNORE INTO notificaciones_ocultas (notificacion_id, usuario_id)
            VALUES (?, ?)
            """,
            (notif_id, uid),
        )
        conn.commit()
    return jsonify({"ok": True, "message": "Mensaje eliminado de tu bandeja."})


@api_bp.post("/admin/notificaciones/<int:notif_id>/asignar-job")
@login_required
def assign_job_from_notification(notif_id):
    user = current_user()
    if not can_review_onboarding_notifications(user):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    body = request.get_json(silent=True) or {}
    job = sanitize_string(body.get("JOB"))
    with get_users_connection() as conn:
        notif = _load_pending_notif(conn, notif_id)
        if not notif:
            return jsonify({"ok": False, "error": "No encontrada."}), 404
        if (notif["tipo"] or "") != JOB_PENDING_TIPO:
            return jsonify({"ok": False, "error": "Esta solicitud no es de asignación de JOB."}), 400
        if notif["estado"] != "PENDIENTE":
            return jsonify({"ok": False, "error": "Esta solicitud ya fue resuelta."}), 409
        target = conn.execute(
            """
            SELECT id_usuario, ROLL, JOB, empresa_id
            FROM usuarios WHERE id_usuario = ?
            """,
            (notif["solicitante_id"],),
        ).fetchone()
        if not target:
            return jsonify({"ok": False, "error": "El usuario ya no existe."}), 404
        if not can_assign_job_to_target(user, target):
            return jsonify(
                {"ok": False, "error": "No puedes asignar JOB a este usuario."}
            ), 403
        roll = target["ROLL"]
        job = normalize_job(roll, job)
        if not is_valid_managed_job(roll, job):
            return jsonify(
                {"ok": False, "error": f"JOB no válido para el rol {roll}."}
            ), 400
        conn.execute(
            "UPDATE usuarios SET JOB = ? WHERE id_usuario = ?",
            (job, target["id_usuario"]),
        )
        resolve_job_pending_notifications(conn, target["id_usuario"])
        conn.commit()
    return jsonify(
        {
            "ok": True,
            "message": f"JOB «{job}» asignado. La solicitud quedó resuelta.",
            "JOB": job,
        }
    )


@api_bp.post("/admin/notificaciones/<int:notif_id>/descartar")
@login_required
def discard_admin_notification(notif_id):
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo ADMIN."}), 403
    with get_users_connection() as conn:
        row = conn.execute(
            "SELECT id FROM notificaciones_admin WHERE id = ?", (notif_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "No encontrada."}), 404
        conn.execute(
            "UPDATE notificaciones_admin SET estado = 'DESCARTADA' WHERE id = ?",
            (notif_id,),
        )
        conn.commit()
    return jsonify({"ok": True, "message": "Notificación descartada."})


def _load_pending_notif(conn, notif_id):
    return conn.execute(
        _NOTIF_SELECT + " WHERE n.id = ?",
        (notif_id,),
    ).fetchone()


@api_bp.post("/admin/notificaciones/<int:notif_id>/aprobar")
@login_required
def approve_admin_notification(notif_id):
    """Crea (o reutiliza) la empresa sugerida y la asigna al solicitante."""
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo ADMIN."}), 403
    body = request.get_json(silent=True) or {}
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        notif = _load_pending_notif(users_conn, notif_id)
        if not notif:
            return jsonify({"ok": False, "error": "No encontrada."}), 404
        if notif["estado"] != "PENDIENTE":
            return jsonify(
                {"ok": False, "error": "Esta solicitud ya fue resuelta."}
            ), 409

        id_empresa = sanitize_string(body.get("ID_Empresa") or notif["empresa_sugerida"])
        id_nit = sanitize_string(body.get("ID_NIT") or notif["nit_sugerido"] or "").upper()
        if not id_empresa:
            return jsonify({"ok": False, "error": "El nombre de la empresa es obligatorio."}), 400
        if not id_nit:
            return jsonify({"ok": False, "error": "El NIT es obligatorio."}), 400

        empresa_id, created = find_or_create_empresa(emp_conn, id_empresa, id_nit)
        solicitante_id = notif["solicitante_id"]
        solicitante = None
        if solicitante_id:
            users_conn.execute(
                "UPDATE usuarios SET empresa_id = ? WHERE id_usuario = ?",
                (empresa_id, solicitante_id),
            )
            clear_sede_assignments_outside_empresa(
                users_conn, solicitante_id, empresa_id
            )
            solicitante = users_conn.execute(
                """
                SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER,
                       JOB, ROLL
                FROM usuarios WHERE id_usuario = ?
                """,
                (solicitante_id,),
            ).fetchone()
        try:
            users_conn.execute(
                """
                UPDATE notificaciones_admin
                SET estado = 'RESUELTA', empresa_creada_id = ?
                WHERE id = ?
                """,
                (empresa_id, notif_id),
            )
        except Exception:
            users_conn.execute(
                "UPDATE notificaciones_admin SET estado = 'RESUELTA' WHERE id = ?",
                (notif_id,),
            )
        emp_conn.commit()
        users_conn.commit()

    if created:
        log_evento(
            empresa_id=empresa_id,
            accion=f"Alta de empresa «{id_empresa}» (NIT {id_nit}) por aprobación de solicitud.",
            user=user,
        )
        message = "Empresa creada y asignada al usuario que hizo la solicitud."
    else:
        message = (
            "El NIT ya existía. Se asignó esa empresa al usuario que hizo la solicitud."
        )
    if solicitante_id:
        log_evento(
            empresa_id=empresa_id,
            accion=f"Alta de usuario {describe_usuario(solicitante)}.",
            user=user,
        )
    return jsonify(
        {
            "ok": True,
            "message": message,
            "empresa_id": empresa_id,
            "created": created,
        }
    )


@api_bp.post("/admin/notificaciones/<int:notif_id>/rechazar")
@login_required
def reject_admin_notification(notif_id):
    """Rechaza la creación: el usuario queda sin empresa hasta una asignación posterior."""
    user = current_user()
    if not is_global_scope(user):
        return jsonify({"ok": False, "error": "Solo ADMIN."}), 403
    with get_users_connection() as conn:
        row = conn.execute(
            "SELECT id, estado FROM notificaciones_admin WHERE id = ?",
            (notif_id,),
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "No encontrada."}), 404
        if row["estado"] != "PENDIENTE":
            return jsonify(
                {"ok": False, "error": "Esta solicitud ya fue resuelta."}
            ), 409
        conn.execute(
            "UPDATE notificaciones_admin SET estado = 'DESCARTADA' WHERE id = ?",
            (notif_id,),
        )
        conn.commit()
    return jsonify(
        {
            "ok": True,
            "message": (
                "Solicitud rechazada. La empresa del usuario queda en blanco "
                "hasta que un rol con permisos de asignación de empresa y sede "
                "realice la asignación."
            ),
        }
    )
