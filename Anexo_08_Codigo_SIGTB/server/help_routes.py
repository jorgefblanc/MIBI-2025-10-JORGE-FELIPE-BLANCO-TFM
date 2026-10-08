"""Guías rápidas de instrumentos (/api/help/<modulo>)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file

from server.authz import (
    assigned_empresa_id,
    current_user,
    is_global_scope,
    login_required,
    user_has_permission,
)
from server.db import get_empresas_connection
from server.event_log import log_evento
from server.help_examples import EXAMPLE_FILES, build_example
from server.limits import COMMENT, CSV_BYTES, IMPORT_ROWS, clip
from server.validators import sanitize_string

help_bp = Blueprint("help_api", __name__, url_prefix="/api")
docs_bp = Blueprint("help_docs", __name__)

HELP_DIR = Path(__file__).resolve().parent / "help"
ROOT_DIR = Path(__file__).resolve().parent.parent
PHRASE_MAX = 400
LIST_ITEM_MAX = 220
ALLOWED_LANGS = frozenset({"es", "en"})
IMAGE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
EXAMPLE_HREF_RE = re.compile(
    r"^/api/help/(suficiencia|dimensionamiento|frecuencia-pm|preinstalacion|kpis)/examples/(plantilla\.xlsx|ejemplo\.pdf)$"
)

HELP_MODULES = {
    "suficiencia": {
        "file": "suficiencia",
        "permissions": (
            "view_suficiencia",
            "view_help_suficiencia",
            "edit_suficiencia_asistencial",
            "request_suficiencia_update",
        ),
    },
    "dimensionamiento": {
        "file": "dimensionamiento",
        "permissions": ("view_dimensionamiento", "view_help_dimensionamiento"),
    },
    "frecuencia-pm": {
        "file": "frecuencia-pm",
        "permissions": ("view_frecuencia_pm", "view_help_frecuencia_pm"),
    },
    "preinstalacion": {
        "file": "preinstalacion",
        "permissions": ("view_preinstalacion", "view_help_preinstalacion"),
    },
    "kpis": {
        "file": "kpis",
        "permissions": ("view_kpis", "view_respaldo", "view_help_kpis"),
    },
}

_SLUG_ALIASES = {
    "frecuencia_pm": "frecuencia-pm",
    "frecuenciapm": "frecuencia-pm",
    "preinstalación": "preinstalacion",
}

ALLOWED_DOCS = frozenset(
    {
        "MAPA_MODULOS.md",
        "INFORME_OPERACION_SIGTB.md",
        "ARQUITECTURE_AUDIT.md",
        "SUFICIENCIA.md",
        "DIMENSIONAMIENTO.md",
        "GE.md",
        "PREINSTALACION.md",
        "RBAC.md",
        "ARQUITECTURE.md",
        "RESUMEN_CAMBIOS_TFM.md",
    }
)


def normalize_module(raw) -> str | None:
    slug = sanitize_string(raw, 40).lower().replace(" ", "-")
    slug = _SLUG_ALIASES.get(slug, slug)
    if slug in HELP_MODULES:
        return slug
    return None


def help_permissions(module: str) -> tuple[str, ...]:
    spec = HELP_MODULES.get(module) or {}
    return tuple(spec.get("permissions") or ())


def user_can_view_help(module: str, user=None) -> bool:
    user = user or current_user()
    if not user:
        return False
    return any(user_has_permission(name) for name in help_permissions(module))


def format_help_viewed_accion(module: str, version: str, sede_label="", servicio_label="") -> str:
    parts = ["help_viewed", f"módulo={module}", f"versión={version or '—'}"]
    if sede_label:
        parts.append(f"sede={sede_label}")
    if servicio_label:
        parts.append(f"servicio={servicio_label}")
    return clip(" · ".join(parts), 500)


def _tech_notes(lang: str) -> str:
    mb = CSV_BYTES // (1024 * 1024)
    if lang == "en":
        return (
            f"Inventory files: up to {mb} MB or {IMPORT_ROWS} rows. "
            f"Comments: {COMMENT} characters. The app checks this for you."
        )
    return (
        f"Archivos de inventario: hasta {mb} MB o {IMPORT_ROWS} filas. "
        f"Observaciones: {COMMENT} caracteres. El sistema lo revisa por ti."
    )


def _sanitize_image_name(name) -> str:
    text = sanitize_string(name, 120)
    if not text or "/" in text or "\\" in text or ".." in text:
        return ""
    if not IMAGE_NAME_RE.match(text):
        return ""
    return text


def _string_list(raw, *, limit: int, item_max: int) -> list[str]:
    out = []
    for item in raw or []:
        text = sanitize_string(item, item_max)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _sanitize_example(item, module: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    kind = sanitize_string(item.get("type"), 20).lower()
    if kind not in {"plantilla", "informe", "xlsx", "pdf", "csv"}:
        return None
    href = sanitize_string(item.get("href"), 180)
    if not EXAMPLE_HREF_RE.match(href):
        return None
    if f"/help/{module}/examples/" not in href:
        return None
    label = sanitize_string(item.get("label") or item.get("file"), 80)
    if not label:
        label = "Plantilla de ejemplo" if "plantilla" in href else "Informe de ejemplo"
    return {"type": kind, "label": label, "href": href}


def load_help_document(module: str, lang: str) -> tuple[dict | None, Path | None]:
    spec = HELP_MODULES.get(module)
    if not spec:
        return None, None
    lang = lang if lang in ALLOWED_LANGS else "es"
    path = HELP_DIR / f"{spec['file']}.{lang}.json"
    if not path.is_file() and lang != "es":
        path = HELP_DIR / f"{spec['file']}.es.json"
        lang = "es"
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(raw, dict):
        return None, None

    errors = []
    for item in raw.get("common_errors") or []:
        if not isinstance(item, dict):
            continue
        err = sanitize_string(item.get("error"), LIST_ITEM_MAX)
        fix = sanitize_string(item.get("fix"), PHRASE_MAX)
        if err and fix:
            errors.append({"error": err, "fix": fix})
        if len(errors) >= 5:
            break

    examples = []
    for item in raw.get("examples") or []:
        cleaned = _sanitize_example(item, module)
        if cleaned:
            examples.append(cleaned)
        if len(examples) >= 4:
            break

    images = []
    for name in raw.get("images") or []:
        image = _sanitize_image_name(name)
        if image:
            images.append(image)
        if len(images) >= 4:
            break

    served_lang = lang if (HELP_DIR / f"{spec['file']}.{lang}.json").is_file() else "es"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    contact = sanitize_string(raw.get("contact"), PHRASE_MAX)
    if not contact:
        contact = (
            "If you cannot see your site or people are missing, write to your organisation ADMIN."
            if served_lang == "en"
            else "Si no ves tu sede o faltan personas, escríbele al ADMIN de tu organización."
        )
    payload = {
        "ok": True,
        "module": module,
        "lang": served_lang,
        "version": sanitize_string(raw.get("version"), 40) or mtime.strftime("%Y-%m-%d"),
        "title": sanitize_string(raw.get("title"), 120),
        "what": clip(sanitize_string(raw.get("what") or raw.get("overview"), PHRASE_MAX), PHRASE_MAX),
        "can_do": _string_list(raw.get("can_do"), limit=5, item_max=LIST_ITEM_MAX),
        "steps": _string_list(raw.get("steps"), limit=5, item_max=PHRASE_MAX),
        "common_errors": errors,
        "examples": examples,
        "images": images,
        "tips": _string_list(raw.get("tips"), limit=3, item_max=LIST_ITEM_MAX),
        "contact": contact,
        "tech_notes": _tech_notes(served_lang),
        "last_modified": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return payload, path


def _etag_for(payload: dict, path: Path) -> str:
    stamp = f"{payload.get('module')}|{payload.get('lang')}|{payload.get('version')}|{path.stat().st_mtime_ns}|{path.stat().st_size}"
    digest = hashlib.sha256(stamp.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0 or number > 1_000_000_000:
        return None
    return number


def _can_log_empresa(user, empresa_id: int) -> bool:
    with get_empresas_connection() as conn:
        exists = conn.execute(
            "SELECT id FROM empresas WHERE id = ?", (int(empresa_id),)
        ).fetchone()
    if not exists:
        return False
    if is_global_scope(user):
        return True
    assigned = assigned_empresa_id(user)
    return assigned is not None and int(assigned) == int(empresa_id)


def _scope_labels(empresa_id: int, sede_id, servicio_id) -> tuple[str, str]:
    sede_label = ""
    servicio_label = ""
    with get_empresas_connection() as conn:
        if sede_id:
            row = conn.execute(
                "SELECT name_sede FROM sedes WHERE id = ? AND empresa_id = ?",
                (int(sede_id), int(empresa_id)),
            ).fetchone()
            if row:
                sede_label = sanitize_string(row["name_sede"], 80)
        if servicio_id and sede_id:
            row = conn.execute(
                """
                SELECT s.name_servicio
                FROM servicios s
                JOIN sedes d ON d.id = s.sede_id
                WHERE s.id = ? AND s.sede_id = ? AND d.empresa_id = ?
                """,
                (int(servicio_id), int(sede_id), int(empresa_id)),
            ).fetchone()
            if row:
                servicio_label = sanitize_string(row["name_servicio"], 80)
    return sede_label, servicio_label


def _record_help_viewed(slug: str, version: str, body=None):
    body = body or {}
    user = current_user()
    empresa_id = _optional_int(body.get("empresa_id") or request.args.get("empresa_id")) or assigned_empresa_id(
        user
    )
    if not empresa_id:
        return False
    if not _can_log_empresa(user, int(empresa_id)):
        return False
    sede_id = _optional_int(body.get("sede_id") or request.args.get("sede_id"))
    servicio_id = _optional_int(body.get("servicio_id") or request.args.get("servicio_id"))
    sede_label, servicio_label = _scope_labels(int(empresa_id), sede_id, servicio_id)
    accion = format_help_viewed_accion(slug, version, sede_label, servicio_label)
    log_evento(empresa_id=int(empresa_id), accion=accion, user=user)
    return True


@help_bp.get("/help/<module>")
@login_required
def get_help(module):
    slug = normalize_module(module)
    if not slug:
        return jsonify({"ok": False, "error": "Módulo de guía no encontrado."}), 404
    if not user_can_view_help(slug):
        return jsonify({"ok": False, "error": "No tienes permisos para esta acción."}), 403

    lang = sanitize_string(request.args.get("lang"), 8).lower() or "es"
    if lang not in ALLOWED_LANGS:
        return jsonify({"ok": False, "error": "Idioma no soportado. Use es o en."}), 400

    payload, path = load_help_document(slug, lang)
    if not payload or path is None:
        return jsonify({"ok": False, "error": "La guía de este módulo no está disponible."}), 404

    viewed = sanitize_string(request.args.get("viewed"), 8).lower() in {"1", "true", "si"}
    if viewed:
        _record_help_viewed(slug, payload.get("version") or "")

    etag = _etag_for(payload, path)
    if request.headers.get("If-None-Match") == etag:
        resp = Response(status=304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp

    resp = jsonify(payload)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "private, max-age=86400"
    resp.headers["Last-Modified"] = payload["last_modified"]
    return resp


@help_bp.get("/help/<module>/examples/<filename>")
@login_required
def get_help_example(module, filename):
    slug = normalize_module(module)
    if not slug:
        return jsonify({"ok": False, "error": "Módulo no encontrado."}), 404
    if not user_can_view_help(slug):
        return jsonify({"ok": False, "error": "No tienes permisos para esta acción."}), 403
    name = Path(filename).name.lower()
    if name not in EXAMPLE_FILES:
        return jsonify({"ok": False, "error": "Ejemplo no disponible."}), 404
    buf, mime, download_name = build_example(slug, name)
    inline = name.endswith(".pdf") and request.args.get("download") != "1"
    return send_file(
        buf,
        mimetype=mime,
        as_attachment=not inline,
        download_name=download_name,
        max_age=0,
    )


@help_bp.post("/event_log")
@login_required
def post_event_log():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON inválido."}), 400

    event = sanitize_string(body.get("event"), 40).lower()
    if event != "help_viewed":
        return jsonify({"ok": False, "error": "Evento no permitido."}), 400

    slug = normalize_module(body.get("module"))
    if not slug:
        return jsonify({"ok": False, "error": "Módulo no válido."}), 400
    if not user_can_view_help(slug):
        return jsonify({"ok": False, "error": "No tienes permisos para esta acción."}), 403

    version = sanitize_string(body.get("version"), 40)
    logged = _record_help_viewed(slug, version, body)
    return jsonify({"ok": True, "logged": logged})


@docs_bp.get("/docs/<path:filename>")
@login_required
def get_help_doc(filename):
    name = Path(filename).name
    if name not in ALLOWED_DOCS:
        return jsonify({"ok": False, "error": "Documento no disponible."}), 404
    path = ROOT_DIR / "docs" / name
    if not path.is_file():
        path = ROOT_DIR / name
    if not path.is_file():
        return jsonify({"ok": False, "error": "Documento no disponible."}), 404
    return send_file(path, mimetype="text/markdown; charset=utf-8", max_age=86400)
