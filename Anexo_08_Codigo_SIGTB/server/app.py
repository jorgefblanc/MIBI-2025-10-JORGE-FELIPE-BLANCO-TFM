"""Punto de entrada Flask: estáticos de public/, sesión y registro de blueprints.

Arranque: python -m server.app
"""

import hashlib
import logging
import os
import secrets
import subprocess
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import bcrypt
from flask import Flask, jsonify, request, send_from_directory, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from server.admin import admin_bp
from server.api import api_bp
from server.org_routes import org_bp
from server.rbac_routes import rbac_bp
from server.suficiencia_routes import suficiencia_bp
from server.dimensionamiento_routes import dim_bp
from server.frecuencia_pm_routes import pm_bp
from server.preinstalacion_routes import pre_bp
from server.adquisicion_routes import adq_bp
from server.kpis_routes import kpis_bp
from server.event_log import describe_usuario, eventos_bp, log_evento
from server.help_routes import docs_bp, help_bp
from server.fallos import create_reporte_from_request, fallos_bp
from server.backup import start_backup_scheduler
from server.db import DATA_DIR, get_empresas_connection, get_users_connection, init_db
from server.mailer import send_email
from server.onboarding import insert_job_pending_notification
from server.roles import (
    get_roles_catalog,
    is_pending_job,
    is_valid_roll,
    permissions_payload,
)
from server.validators import (
    is_letters_only,
    is_valid_email,
    normalize_email,
    sanitize_string,
    validate_password,
)
from server.limits import (
    AVISO_VERSION,
    JSON_BODY,
    LABEL,
    MAX_CONTENT_LENGTH,
    NAME,
    NIT,
    PASSWORD_MAX,
    public_payload as limits_public_payload,
)
from server.presence import mark_offline, touch_presence

ROOT_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT_DIR / "public"
BCRYPT_ROUNDS = 12

# Marcador: defina SECRET_KEY en el entorno. En producción el arranque se detiene si no se cambia.
DEV_SECRET = "CAMBIAR_ANTES_DE_USAR"
app = Flask(
    __name__,
    static_folder=str(PUBLIC_DIR),
    static_url_path="",
)
app.secret_key = os.environ.get("SECRET_KEY") or DEV_SECRET
app.config["PROPAGATE_EXCEPTIONS"] = False
# Cookie de sesión: compartida entre pestañas/ventanas del mismo origen.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_NAME"] = "sigtb_session"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def _is_production_env() -> bool:
    env = (os.environ.get("SIGTB_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
    if env in {"production", "prod"}:
        return True
    flag = (os.environ.get("SIGTB_PRODUCTION") or "").strip().lower()
    return flag in {"1", "true", "yes"}


def _configure_error_log(flask_app) -> None:
    log_dir = DATA_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "sigtb-errors.log",
            maxBytes=1_048_576,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        flask_app.logger.addHandler(handler)
        flask_app.logger.setLevel(logging.INFO)
    except OSError:
        pass


def _record_http_500(err) -> None:
    """Archivo rotativo (traceback) + event_log sin pila. Nunca al navegador."""
    try:
        empresa_id = session.get("empresa_id")
        if not empresa_id:
            return
        log_evento(
            empresa_id=int(empresa_id),
            accion=f"Error HTTP 500 en {request.method} {request.path}",
            modulo="sistema",
            parametros={
                "exc_type": type(err).__name__,
                "path": (request.path or "")[:120],
                "method": request.method,
            },
        )
    except Exception:
        pass


_configure_error_log(app)
if _is_production_env() and app.secret_key == DEV_SECRET:
    raise SystemExit(
        "SECRET_KEY de producción no puede ser la clave de desarrollo. "
        "Defina SECRET_KEY distinta en el entorno."
    )

app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(org_bp)
app.register_blueprint(rbac_bp)
app.register_blueprint(suficiencia_bp)
app.register_blueprint(dim_bp)
app.register_blueprint(pm_bp)
app.register_blueprint(pre_bp)
app.register_blueprint(adq_bp)
app.register_blueprint(kpis_bp)
app.register_blueprint(fallos_bp)
app.register_blueprint(eventos_bp)
app.register_blueprint(help_bp)
app.register_blueprint(docs_bp)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["400 per minute"],
    storage_uri="memory://",
)


@limiter.request_filter
def _skip_static_rate_limit():
    path = request.path or ""
    return path.startswith("/css/") or path.startswith("/js/") or path.startswith("/img/") or path.startswith("/fonts/")

init_db()
start_backup_scheduler(debug=app.debug)


@app.errorhandler(413)
def _payload_too_large(_err):
    return jsonify(
        {"ok": False, "error": "El archivo o la solicitud supera el tamaño máximo permitido."}
    ), 413


@app.before_request
def _reject_oversized_json():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    length = request.content_length
    if not length:
        return None
    ctype = request.content_type or ""
    if "multipart/form-data" in ctype:
        return None
    if length > JSON_BODY:
        return jsonify(
            {
                "ok": False,
                "error": "La solicitud JSON supera el tamaño máximo permitido (256 KB).",
            }
        ), 413
    return None


@app.get("/api/limits")
def public_input_limits():
    return jsonify({"ok": True, "limits": limits_public_payload()})


def _user_payload(row):
    return {
        "id_usuario": row["id_usuario"],
        "usuario_login": row["usuario_login"],
        "NAME_USER": row["NAME_USER"],
        "LAST_NAME_USER": row["LAST_NAME_USER"],
        "JOB": row["JOB"],
        "ROLL": row["ROLL"],
        "creation_date": row["creation_date"] if "creation_date" in row.keys() else None,
        "empresa_id": row["empresa_id"] if "empresa_id" in row.keys() else None,
        "aviso_version": row["aviso_version"] if "aviso_version" in row.keys() else None,
        "aviso_aceptado_en": row["aviso_aceptado_en"] if "aviso_aceptado_en" in row.keys() else None,
    }


@app.post("/api/reportes-fallos")
@limiter.limit("12 per 15 minutes")
def public_reporte_fallos():
    """Radica un fallo sin exigir sesión (Invitado) o con el usuario autenticado."""
    try:
        return create_reporte_from_request()
    except Exception as err:
        app.logger.exception("POST /api/reportes-fallos: %s", err)
        return jsonify(
            {"ok": False, "error": "No se pudo radicar el reporte. Intente de nuevo."}
        ), 500


@app.post("/login")
@limiter.limit("80 per 15 minutes")
def login():
    try:
        body = request.get_json(silent=True) or {}
        usuario_login = normalize_email(body.get("usuario_login"))
        password = body.get("password") if isinstance(body.get("password"), str) else ""

        if not is_valid_email(usuario_login):
            return jsonify(
                {"ok": False, "error": "El correo (usuario_login) no es válido."}
            ), 400

        if not password:
            return jsonify({"ok": False, "error": "La contraseña es obligatoria."}), 400
        if len(password) > PASSWORD_MAX:
            return jsonify({"ok": False, "error": "Credenciales inválidas."}), 401

        with get_users_connection() as conn:
            user = conn.execute(
                """
                SELECT id_usuario, usuario_login, password_hash, NAME_USER,
                       LAST_NAME_USER, JOB, ROLL, creation_date, empresa_id,
                       aviso_version, aviso_aceptado_en
                FROM usuarios
                WHERE usuario_login = ? COLLATE NOCASE
                """,
                (usuario_login,),
            ).fetchone()

        if user is None:
            return jsonify(
                {
                    "ok": False,
                    "exists": False,
                    "error": "El usuario no existe. Puedes crear una cuenta nueva.",
                    "allowRegister": True,
                }
            ), 404

        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password_hash"].encode("utf-8")
        ):
            return jsonify(
                {"ok": False, "exists": True, "error": "Credenciales incorrectas."}
            ), 401

        session.clear()
        session.permanent = True
        session["id_usuario"] = user["id_usuario"]
        session["usuario_login"] = user["usuario_login"]
        session["ROLL"] = user["ROLL"]
        session["JOB"] = user["JOB"]
        session["NAME_USER"] = user["NAME_USER"]
        session["empresa_id"] = user["empresa_id"]
        session["expanded_permissions"] = False
        touch_presence(user["id_usuario"], force=True)

        user_data = _user_payload(user)
        user_data.update(permissions_payload(user["ROLL"], user["JOB"]))
        user_data["empresa_pendiente"] = (
            user["ROLL"] != "ADMIN" and not user["empresa_id"]
        )
        user_data["job_pendiente"] = user["ROLL"] != "ADMIN" and is_pending_job(
            user["JOB"]
        )

        return jsonify(
            {
                "ok": True,
                "message": "Inicio de sesión correcto.",
                "user": user_data,
            }
        )
    except Exception as err:
        app.logger.exception("POST /login error: %s", err)
        return jsonify({"ok": False, "error": "Error interno al iniciar sesión."}), 500


@app.post("/register")
@limiter.limit("80 per 15 minutes")
def register():
    try:
        body = request.get_json(silent=True) or {}
        usuario_login = normalize_email(body.get("usuario_login"))
        password = body.get("password") if isinstance(body.get("password"), str) else ""
        name_user = sanitize_string(body.get("NAME_USER"), NAME)
        last_name_user = sanitize_string(body.get("LAST_NAME_USER"), NAME)
        roll = sanitize_string(body.get("ROLL"), 20).upper()
        empresa_choice = body.get("empresa_id")
        empresa_no_encontrada = bool(body.get("empresa_no_encontrada"))
        empresa_sugerida = sanitize_string(body.get("empresa_sugerida"), LABEL)
        nit_sugerido = sanitize_string(body.get("nit_sugerido"), NIT).upper()
        aviso_aceptado = body.get("aviso_aceptado") is True
        # El JOB público se ignora: lo asigna ADMIN (o un rol con gestión de usuarios).
        job = ""

        field_errors = {}

        if not is_valid_email(usuario_login):
            field_errors["usuario_login"] = (
                "Debe ser un correo válido (sin distinguir mayúsculas/minúsculas)."
            )

        password_check = validate_password(password)
        if not password_check["valid"]:
            field_errors["password"] = " ".join(password_check["errors"])

        if not is_letters_only(name_user):
            field_errors["NAME_USER"] = (
                "NAME_USER solo admite letras (sin números ni símbolos)."
            )

        if not is_letters_only(last_name_user):
            field_errors["LAST_NAME_USER"] = (
                "LAST_NAME_USER solo admite letras (sin números ni símbolos)."
            )

        if not is_valid_roll(roll):
            field_errors["ROLL"] = "El rol debe ser Operador (OPERATIVO) o Asistencial."

        if not aviso_aceptado:
            field_errors["aviso_aceptado"] = (
                "Debe autorizar el tratamiento de sus datos personales para crear la cuenta."
            )

        empresa_id = None
        if empresa_no_encontrada:
            if not empresa_sugerida:
                field_errors["empresa_sugerida"] = (
                    "Indica el nombre de la empresa no encontrada."
                )
            if not nit_sugerido:
                field_errors["nit_sugerido"] = "El NIT es obligatorio para la solicitud."
        else:
            try:
                empresa_id = int(empresa_choice)
            except (TypeError, ValueError):
                field_errors["empresa_id"] = (
                    "Debes elegir una empresa o la opción «No se encuentra»."
                )

        if field_errors:
            return jsonify(
                {
                    "ok": False,
                    "error": "Validación fallida. Corrige los campos indicados.",
                    "fieldErrors": field_errors,
                }
            ), 400

        with get_users_connection() as conn:
            existing = conn.execute(
                "SELECT id_usuario FROM usuarios WHERE usuario_login = ? COLLATE NOCASE",
                (usuario_login,),
            ).fetchone()

            if existing:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Ya existe un usuario con ese correo.",
                        "fieldErrors": {
                            "usuario_login": "Este correo ya está registrado."
                        },
                    }
                ), 409

            if empresa_id is not None:
                with get_empresas_connection() as emp_conn:
                    empresa = emp_conn.execute(
                        "SELECT id FROM empresas WHERE id = ?",
                        (empresa_id,),
                    ).fetchone()
                if not empresa:
                    return jsonify(
                        {
                            "ok": False,
                            "error": "La empresa seleccionada no existe.",
                            "fieldErrors": {"empresa_id": "Empresa inválida."},
                        }
                    ), 400

            password_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
            ).decode("utf-8")

            cursor = conn.execute(
                """
                INSERT INTO usuarios (
                    usuario_login, password_hash, creation_date,
                    NAME_USER, LAST_NAME_USER, JOB, ROLL, empresa_id,
                    aviso_version, aviso_aceptado_en
                ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    usuario_login,
                    password_hash,
                    name_user,
                    last_name_user,
                    job,
                    roll,
                    empresa_id,
                    AVISO_VERSION,
                ),
            )
            new_id = cursor.lastrowid
            insert_job_pending_notification(
                conn,
                user_id=new_id,
                email=usuario_login,
                nombre=f"{name_user} {last_name_user}".strip(),
                roll=roll,
            )

            if empresa_no_encontrada:
                roll_txt = "Operador" if roll == "OPERATIVO" else "Asistencial"
                conn.execute(
                    """
                    INSERT INTO notificaciones_admin (
                        tipo, mensaje, solicitante_id, solicitante_email,
                        solicitante_nombre, empresa_sugerida, nit_sugerido,
                        estado, creation_date
                    ) VALUES (
                        'EMPRESA_NO_ENCONTRADA', ?, ?, ?, ?, ?, ?, 'PENDIENTE', datetime('now')
                    )
                    """,
                    (
                        (
                            f"Solicitud de creación de empresa. "
                            f"{name_user} {last_name_user} ({usuario_login}, {roll_txt}) "
                            f"indicó que su empresa no está en el catálogo. "
                            f"Si se aprueba, la empresa se asignará a este usuario. "
                            f"El JOB sigue pendiente de asignación."
                        ),
                        new_id,
                        usuario_login,
                        f"{name_user} {last_name_user}",
                        empresa_sugerida,
                        nit_sugerido or None,
                    ),
                )

            conn.commit()

        if empresa_id:
            alta = {
                "id_usuario": new_id,
                "usuario_login": usuario_login,
                "NAME_USER": name_user,
                "LAST_NAME_USER": last_name_user,
                "JOB": job,
                "ROLL": roll,
            }
            log_evento(
                empresa_id=empresa_id,
                accion=f"Alta de usuario {describe_usuario(alta)}.",
                user={
                    "id_usuario": new_id,
                    "usuario_login": usuario_login,
                    "NAME_USER": name_user,
                },
            )

        message = (
            "Usuario creado. Se envió una solicitud al administrador o al director "
            "operativo/asistencial correspondiente para asignar tu JOB."
        )
        if empresa_no_encontrada:
            message = (
                "Usuario creado. Se envió al administrador la solicitud de creación "
                "de la empresa y otra para asignar el JOB. La empresa no se asignará "
                "hasta que se apruebe."
            )

        return jsonify(
            {
                "ok": True,
                "message": message,
                "empresa_pendiente": empresa_no_encontrada,
                "job_pendiente": True,
                "user": {
                    "id_usuario": new_id,
                    "usuario_login": usuario_login,
                    "NAME_USER": name_user,
                    "LAST_NAME_USER": last_name_user,
                    "JOB": job,
                    "ROLL": roll,
                    "empresa_id": empresa_id,
                },
            }
        ), 201
    except Exception as err:
        app.logger.exception("POST /register error: %s", err)
        return jsonify(
            {"ok": False, "error": "Error interno al registrar el usuario."}
        ), 500


@app.get("/empresas/catalog")
def empresas_catalog():
    """Catálogo público para el alta de usuarios (elegir empresa)."""
    with get_empresas_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, ID_Empresa, ID_NIT
            FROM empresas
            ORDER BY ID_Empresa COLLATE NOCASE
            """
        ).fetchall()
    return jsonify(
        {
            "ok": True,
            "empresas": [
                {
                    "id": r["id"],
                    "ID_Empresa": r["ID_Empresa"],
                    "ID_NIT": r["ID_NIT"],
                }
                for r in rows
            ],
        }
    )


@app.get("/roles")
def roles():
    return jsonify({"ok": True, **get_roles_catalog()})


@app.post("/logout")
def logout():
    uid = session.get("id_usuario")
    mark_offline(uid)
    session.clear()
    return jsonify({"ok": True, "message": "Sesión cerrada."})


GENERIC_RESET_MSG = (
    "Si el correo está registrado, te enviaremos instrucciones para restablecer la contraseña."
)


@app.post("/forgot-password")
@limiter.limit("8 per 15 minutes")
def forgot_password():
    body = request.get_json(silent=True) or {}
    usuario_login = normalize_email(body.get("usuario_login"))
    if not is_valid_email(usuario_login):
        return jsonify(
            {"ok": False, "error": "Indica un correo válido.", "fieldErrors": {"usuario_login": "Correo inválido."}}
        ), 400

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    with get_users_connection() as conn:
        user = conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER
            FROM usuarios WHERE usuario_login = ? COLLATE NOCASE
            """,
            (usuario_login,),
        ).fetchone()
        if user:
            conn.execute(
                "DELETE FROM password_reset_tokens WHERE usuario_id = ? AND used_at IS NULL",
                (user["id_usuario"],),
            )
            conn.execute(
                """
                INSERT INTO password_reset_tokens (usuario_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (user["id_usuario"], token_hash, expires_at),
            )
            conn.commit()
            base = (request.host_url or "http://127.0.0.1:3000/").rstrip("/")
            reset_url = f"{base}/?reset={token}"
            nombre = user["NAME_USER"] or "Usuario"
            body_txt = (
                f"Hola {nombre},\n\n"
                "Recibimos una solicitud para restablecer tu contraseña de SIGTB.\n"
                "Abre este enlace (válido 1 hora):\n\n"
                f"{reset_url}\n\n"
                "Si no fuiste tú, ignora este mensaje. Tu contraseña no cambiará.\n"
            )
            ok, detail = send_email(
                user["usuario_login"],
                "SIGTB — restablecer contraseña",
                body_txt,
            )
            if not ok:
                app.logger.warning("forgot-password mail failed for %s: %s", usuario_login, detail)

    return jsonify({"ok": True, "message": GENERIC_RESET_MSG})


@app.post("/reset-password")
@limiter.limit("20 per 15 minutes")
def reset_password():
    body = request.get_json(silent=True) or {}
    token = sanitize_string(body.get("token"))
    password = body.get("password") if isinstance(body.get("password"), str) else ""
    if not token:
        return jsonify({"ok": False, "error": "El enlace de recuperación no es válido."}), 400
    password_check = validate_password(password)
    if not password_check["valid"]:
        return jsonify(
            {
                "ok": False,
                "error": " ".join(password_check["errors"]),
                "fieldErrors": {"password": " ".join(password_check["errors"])},
            }
        ), 400

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_users_connection() as conn:
        row = conn.execute(
            """
            SELECT id, usuario_id FROM password_reset_tokens
            WHERE token_hash = ?
              AND used_at IS NULL
              AND expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if not row:
            return jsonify(
                {"ok": False, "error": "El enlace expiró o ya fue utilizado. Solicita uno nuevo."}
            ), 400
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        ).decode("utf-8")
        conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id_usuario = ?",
            (password_hash, row["usuario_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    return jsonify(
        {"ok": True, "message": "Contraseña actualizada. Ya puedes iniciar sesión."}
    )


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "sistema-usuarios-roles"})


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


def _api_error_path():
    path = request.path or ""
    return path.startswith("/api/") or path.startswith("/admin/")


@app.errorhandler(404)
def handle_404(_error):
    if _api_error_path():
        return jsonify({"ok": False, "error": "Recurso no encontrado."}), 404
    return _error


@app.errorhandler(405)
def handle_405(_error):
    if _api_error_path():
        return jsonify(
            {
                "ok": False,
                "error": "Esta acción no está activa en el servidor. Deténgalo (Ctrl+C) y vuelva a iniciarlo.",
            }
        ), 405
    return _error


@app.errorhandler(429)
def ratelimit_handler(_error):
    return jsonify(
        {
            "ok": False,
            "error": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
        }
    ), 429


@app.errorhandler(Exception)
def handle_unexpected(err):
    """JSON coherente en /api y /admin; evita HTML 500 y traceback al navegador."""
    if isinstance(err, HTTPException):
        return err
    app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
    _record_http_500(err)
    return jsonify({"ok": False, "error": "Error interno del servidor."}), 500


def _lan_urls(port: int) -> list[str]:
    import socket

    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            url = f"http://{ip}:{port}"
            if url not in found:
                found.append(url)
    except OSError:
        pass
    return found


def _ensure_lan_firewall(port: int) -> str:
    """Abre el puerto en el firewall de Windows (red privada)."""
    if os.name != "nt":
        return "ok"
    import subprocess

    name = f"SIGTB LAN {port}"
    try:
        added = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={name}",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localport={port}",
                "profile=private",
                "enable=yes",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        out = (added.stdout or "") + (added.stderr or "")
        if added.returncode == 0:
            return "ok"
        if "already exists" in out.lower() or "ya existe" in out.lower():
            return "ok"
        return "denied"
    except Exception:
        return "denied"


def _pids_listening_on_port(port: int) -> list[int]:
    me = os.getpid()
    found: list[int] = []
    if os.name == "nt":
        try:
            kwargs = {"text": True, "errors": "ignore"}
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], **kwargs)
        except Exception:
            return []
        needle = f":{int(port)}"
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[1] if parts[0].upper() == "TCP" else parts[0]
            if not (local.endswith(needle) or local.endswith("]" + needle)):
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid and pid != me:
                found.append(pid)
        return list(dict.fromkeys(found))
    try:
        out = subprocess.check_output(["lsof", "-ti", f"tcp:{int(port)}"], text=True, errors="ignore")
        for raw in out.split():
            try:
                pid = int(raw)
            except ValueError:
                continue
            if pid and pid != me:
                found.append(pid)
    except Exception:
        return []
    return list(dict.fromkeys(found))


def _free_listen_port(port: int) -> int:
    killed = 0
    for pid in _pids_listening_on_port(port):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    check=False,
                    capture_output=True,
                )
            else:
                os.kill(pid, 15)
            killed += 1
        except Exception:
            pass
    return killed


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    old = _free_listen_port(port)
    if old:
        print("Se detuvieron %s proceso(s) que ocupaban el puerto %s." % (old, port))
    lan = _lan_urls(port)
    fw = _ensure_lan_firewall(port)
    print("Acceso local:     http://127.0.0.1:%s" % port)
    if lan:
        print("Acceso WiFi/LAN:")
        for url in lan:
            print("  %s" % url)
    else:
        print("No se detectó IP de red. Conecte Ethernet o WiFi e intente de nuevo.")
    if fw == "denied":
        print(
            "Firewall: no se pudo abrir el puerto %s. Ejecute PowerShell como "
            "Administrador:\n  netsh advfirewall firewall add rule name=\"SIGTB LAN %s\" "
            "dir=in action=allow protocol=TCP localport=%s profile=private"
            % (port, port, port)
        )
    flask_debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if app.secret_key == DEV_SECRET:
        print("Aviso: SECRET_KEY por defecto (solo entorno de tesis). Defina SECRET_KEY en producción.")
    if flask_debug:
        print("Aviso: FLASK_DEBUG activo (consola de depuración). No usar en red compartida.")
    app.run(host="0.0.0.0", port=port, debug=flask_debug, threaded=True, use_reloader=False)
