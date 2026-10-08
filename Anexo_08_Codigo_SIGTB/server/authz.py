"""Autorización: sesión Flask, decoradores de login/permiso y alcance por empresa o sede."""

from functools import wraps

from flask import jsonify, session

from server.db import get_empresas_connection, get_users_connection
from server.roles import get_permissions


def current_user():
    user_id = session.get("id_usuario")
    if not user_id:
        return None
    return {
        "id_usuario": user_id,
        "usuario_login": session.get("usuario_login"),
        "NAME_USER": session.get("NAME_USER"),
        "ROLL": session.get("ROLL"),
        "JOB": session.get("JOB"),
        "empresa_id": session.get("empresa_id"),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify({"ok": False, "error": "Debes iniciar sesión."}), 401
        return view(*args, **kwargs)

    return wrapped


def permission_required(*permission_names):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"ok": False, "error": "Debes iniciar sesión."}), 401
            perms = get_permissions(
                user["ROLL"], user["JOB"], expanded=bool(session.get("expanded_permissions"))
            )
            if not any(name in perms for name in permission_names):
                return jsonify(
                    {
                        "ok": False,
                        "error": "No tienes permisos para esta acción.",
                        "required": list(permission_names),
                    }
                ), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def user_has_permission(permission_name):
    user = current_user()
    if not user:
        return False
    return permission_name in get_permissions(
        user["ROLL"], user["JOB"], expanded=bool(session.get("expanded_permissions"))
    )


def is_global_scope(user=None):
    user = user or current_user()
    return bool(user and user["ROLL"] == "ADMIN")


def is_direccion(user=None):
    """Director Operativo (alias histórico: Dirección)."""
    from server.roles import is_operativo_director_job

    user = user or current_user()
    return bool(
        user and user["ROLL"] == "OPERATIVO" and is_operativo_director_job(user["JOB"])
    )


def is_asistencial_director(user=None):
    """Director del rol ASISTENCIAL."""
    user = user or current_user()
    return bool(
        user
        and user["ROLL"] == "ASISTENCIAL"
        and user.get("JOB") in ("Director", "Dirección")
    )


def can_review_onboarding_notifications(user=None):
    """ADMIN, Director Operativo o Director asistencial: ven solicitudes de JOB."""
    user = user or current_user()
    return bool(
        user
        and (is_global_scope(user) or is_direccion(user) or is_asistencial_director(user))
    )


def can_assign_job_to_target(actor, target) -> bool:
    """Quién puede asignar JOB a un usuario recién creado."""
    if not actor or not target:
        return False

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return obj[key]
        except Exception:
            return default

    target_roll = (_get(target, "ROLL") or "").upper()
    if target_roll == "ADMIN":
        return is_global_scope(actor)
    if is_global_scope(actor):
        return True
    actor_emp = assigned_empresa_id(actor)
    target_emp = _get(target, "empresa_id")
    if not target_emp or not actor_emp:
        return False
    if int(actor_emp) != int(target_emp):
        return False
    if is_direccion(actor) and target_roll == "OPERATIVO":
        return True
    if is_asistencial_director(actor) and target_roll == "ASISTENCIAL":
        return True
    return False


def can_purge_inventory(user=None):
    """ADMIN o Director Operativo: borrar inventario cargado y restaurar el reciclo de 30 min."""
    user = user or current_user()
    return bool(user and (is_global_scope(user) or is_direccion(user)))


def assigned_empresa_id(user=None):
    user = user or current_user()
    if not user:
        return None
    raw = user.get("empresa_id")
    try:
        return int(raw) if raw is not None and str(raw).strip() != "" else None
    except (TypeError, ValueError):
        return None


def assigned_sede_ids(conn, usuario_id):
    rows = conn.execute(
        "SELECT sede_id FROM usuario_sedes WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchall()
    return {row["sede_id"] for row in rows}


def sede_ids_for_empresa(empresa_id):
    """IDs de sedes que pertenecen a la empresa (empresas.db)."""
    if not empresa_id:
        return set()
    with get_empresas_connection() as emp_conn:
        rows = emp_conn.execute(
            "SELECT id FROM sedes WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchall()
    return {row["id"] for row in rows}


def clear_sede_assignments_outside_empresa(users_conn, usuario_id, empresa_id):
    """
    Elimina asignaciones usuario↔sede que no pertenecen a la empresa actual.
    Si empresa_id es None, elimina todas las asignaciones del usuario.
    """
    if not usuario_id:
        return 0
    allowed = sede_ids_for_empresa(empresa_id)
    if not allowed:
        cur = users_conn.execute(
            "DELETE FROM usuario_sedes WHERE usuario_id = ?",
            (usuario_id,),
        )
        return cur.rowcount
    placeholders = ",".join("?" * len(allowed))
    cur = users_conn.execute(
        f"""
        DELETE FROM usuario_sedes
        WHERE usuario_id = ?
          AND sede_id NOT IN ({placeholders})
        """,
        (usuario_id, *sorted(allowed)),
    )
    return cur.rowcount


def user_belongs_to_sede_empresa(user_row, sede_empresa_id) -> tuple[bool, str | None]:
    """
    Valida que el usuario pueda asignarse a una sede de sede_empresa_id.
    Si ya tiene empresa asignada, debe coincidir exactamente.
    """
    if not user_row:
        return False, "Usuario no encontrado."
    user_empresa = user_row["empresa_id"] if "empresa_id" in user_row.keys() else None
    if user_empresa is None:
        return (
            False,
            "El usuario no tiene empresa asignada; asígnale una empresa antes de vincularlo a una sede.",
        )
    if int(user_empresa) != int(sede_empresa_id):
        return (
            False,
            "El usuario ya pertenece a otra empresa y no puede asignarse a sedes de esta.",
        )
    return True, None


def can_access_empresa(_emp_conn, user, empresa_id):
    if is_global_scope(user):
        return True
    assigned = assigned_empresa_id(user)
    try:
        target = int(empresa_id)
    except (TypeError, ValueError):
        return False
    return assigned is not None and assigned == target


def can_access_sede(user, sede_id, users_conn=None):
    if is_global_scope(user):
        return True
    try:
        sede_id = int(sede_id)
    except (TypeError, ValueError):
        return False

    with get_empresas_connection() as emp_conn:
        sede = emp_conn.execute(
            "SELECT id, empresa_id FROM sedes WHERE id = ?",
            (sede_id,),
        ).fetchone()
    if not sede:
        return False

    if assigned_empresa_id(user) != int(sede["empresa_id"]):
        return False

    # Si el usuario tiene sedes asignadas, solo esas (de su misma empresa).
    if users_conn is not None:
        assigned = assigned_sede_ids(users_conn, user["id_usuario"])
        if assigned:
            return sede_id in {int(x) for x in assigned}
        return True

    with get_users_connection() as conn:
        assigned = assigned_sede_ids(conn, user["id_usuario"])
        if assigned:
            return sede_id in {int(x) for x in assigned}
    return True


def can_access_servicio(user, servicio_id, users_conn=None):
    if is_global_scope(user):
        return True
    with get_empresas_connection() as emp_conn:
        row = emp_conn.execute(
            """
            SELECT s.id AS sede_id, s.empresa_id
            FROM servicios srv
            JOIN sedes s ON s.id = srv.sede_id
            WHERE srv.id = ?
            """,
            (servicio_id,),
        ).fetchone()
    if not row:
        return False
    return can_access_sede(user, row["sede_id"], users_conn=users_conn)


def coordinator_for_sede(users_conn, sede_id):
    with get_empresas_connection() as emp_conn:
        sede = emp_conn.execute(
            "SELECT empresa_id FROM sedes WHERE id = ?",
            (sede_id,),
        ).fetchone()
    if not sede:
        return None
    row = users_conn.execute(
        """
        SELECT u.id_usuario, u.usuario_login, u.NAME_USER, u.LAST_NAME_USER, u.JOB, u.ROLL
        FROM usuario_sedes us
        JOIN usuarios u ON u.id_usuario = us.usuario_id
        WHERE us.sede_id = ?
          AND u.empresa_id = ?
          AND u.ROLL = 'OPERATIVO'
          AND u.JOB = 'Coordinador'
        ORDER BY us.assigned_at ASC
        LIMIT 1
        """,
        (sede_id, sede["empresa_id"]),
    ).fetchone()
    if row:
        return row
    # Fallback: coordinador de la empresa sin vínculo sede explícito
    return users_conn.execute(
        """
        SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
        FROM usuarios
        WHERE empresa_id = ?
          AND ROLL = 'OPERATIVO'
          AND JOB = 'Coordinador'
        ORDER BY id_usuario ASC
        LIMIT 1
        """,
        (sede["empresa_id"],),
    ).fetchone()


def is_direccion_job(job: str | None) -> bool:
    return job in ("Director Operativo", "Dirección", "Director")


def asistencial_for_empresa(users_conn, empresa_id, sede_id=None):
    """
    Receptor asistencial para solicitudes (suficiencia, validación PM, etc.).
    Preferencia: sede asignada → Director/Dirección → Líder → Coordinador → cualquier ASISTENCIAL.
    """
    if not empresa_id:
        return None

    jobs = ("Director", "Dirección", "Líder", "Coordinador")
    placeholders = ",".join("?" * len(jobs))
    order_sql = """
      CASE JOB
        WHEN 'Director' THEN 0
        WHEN 'Dirección' THEN 0
        WHEN 'Líder' THEN 1
        WHEN 'Coordinador' THEN 2
        ELSE 3
      END,
      id_usuario ASC
    """

    if sede_id:
        preferred_sede = users_conn.execute(
            f"""
            SELECT u.id_usuario, u.usuario_login, u.NAME_USER, u.LAST_NAME_USER, u.JOB, u.ROLL
            FROM usuario_sedes us
            JOIN usuarios u ON u.id_usuario = us.usuario_id
            WHERE us.sede_id = ?
              AND u.empresa_id = ?
              AND u.ROLL = 'ASISTENCIAL'
              AND u.JOB IN ({placeholders})
            ORDER BY
              CASE u.JOB
                WHEN 'Director' THEN 0
                WHEN 'Dirección' THEN 0
                WHEN 'Líder' THEN 1
                WHEN 'Coordinador' THEN 2
                ELSE 3
              END,
              us.assigned_at ASC,
              u.id_usuario ASC
            LIMIT 1
            """,
            (sede_id, empresa_id, *jobs),
        ).fetchone()
        if preferred_sede:
            return preferred_sede

    preferred = users_conn.execute(
        f"""
        SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
        FROM usuarios
        WHERE ROLL = 'ASISTENCIAL'
          AND empresa_id = ?
          AND JOB IN ({placeholders})
        ORDER BY {order_sql}
        LIMIT 1
        """,
        (empresa_id, *jobs),
    ).fetchone()
    if preferred:
        return preferred
    return users_conn.execute(
        """
        SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
        FROM usuarios
        WHERE ROLL = 'ASISTENCIAL' AND empresa_id = ?
        ORDER BY id_usuario ASC
        LIMIT 1
        """,
        (empresa_id,),
    ).fetchone()


def recipient_for_solicitud(users_conn, *, sede_id, empresa_id, destinatario_rol):
    """
    Resuelve el usuario destino según el rol solicitado.
    destinatario_rol: direccion|coordinacion|ingenieria|soporte|administracion|asistencial
    """
    rol = (destinatario_rol or "").strip().lower()
    if rol == "administracion":
        return users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
            FROM usuarios
            WHERE ROLL = 'ADMIN'
            ORDER BY id_usuario ASC
            LIMIT 1
            """
        ).fetchone()

    if rol == "asistencial":
        return asistencial_for_empresa(users_conn, empresa_id, sede_id=sede_id)

    if rol == "coordinacion":
        return coordinator_for_sede(users_conn, sede_id)

    job_map = {
        "direccion": ("OPERATIVO", ("Director Operativo", "Dirección")),
        "ingenieria": ("OPERATIVO", ("Ingeniero",)),
        "soporte": ("OPERATIVO", ("Técnico",)),
    }
    if rol not in job_map:
        return None
    roll, jobs = job_map[rol]
    placeholders = ",".join("?" * len(jobs))
    return users_conn.execute(
        f"""
        SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
        FROM usuarios
        WHERE empresa_id = ?
          AND ROLL = ?
          AND JOB IN ({placeholders})
        ORDER BY id_usuario ASC
        LIMIT 1
        """,
        (empresa_id, roll, *jobs),
    ).fetchone()


def refresh_session_user(conn, usuario_id):
    row = conn.execute(
        """
        SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER,
               JOB, ROLL, empresa_id, creation_date, telefono,
               aviso_version, aviso_aceptado_en
        FROM usuarios WHERE id_usuario = ?
        """,
        (usuario_id,),
    ).fetchone()
    if not row:
        return None
    session["id_usuario"] = row["id_usuario"]
    session["usuario_login"] = row["usuario_login"]
    session["NAME_USER"] = row["NAME_USER"]
    session["JOB"] = row["JOB"]
    session["ROLL"] = row["ROLL"]
    session["empresa_id"] = row["empresa_id"]
    return row
