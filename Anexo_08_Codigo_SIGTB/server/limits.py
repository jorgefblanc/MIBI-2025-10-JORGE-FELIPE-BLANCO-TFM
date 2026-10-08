"""
Límites de entrada (OWASP Input Validation + API4 Lack of Resources).

Toda cadena y todo payload JSON deben tener máximo. SQLite no recorta VARCHAR.
Servidor = control de seguridad; maxlength en el cliente = UX.
"""

# Identidad (RFC 5321 correo; bcrypt DoS en contraseña)
EMAIL = 254
NAME = 80
PHONE = 40
PASSWORD_MIN = 8
PASSWORD_MAX = 128
# Versión del aviso de tratamiento mostrado en registro y perfil.
AVISO_VERSION = "2026-09-23"
LOGIN = 255

# Catálogo / inventario (alineado a schema_empresas)
LABEL = 255
CODE = 100
NIT = 50
PREFIX = 10
JOB = 150
SHORT = 120

# Mensajería y formularios libres
SUBJECT = 120          # asunto de bandeja
MESSAGE = 2000         # cuerpo de solicitud / descripción operativa
DESCRIPTION = 2000     # reporte de fallos (novedad)
SOLUTION = 1000        # solución recomendada
COMMENT = 500          # observaciones, comentarios de cierre
LONG_TEXT = 4000       # notas técnicas, concepto, ayuda
DEFAULT_STRING = 8000  # red de seguridad para sanitize_string sin tope explícito

# JSON / HTTP (no aplica a multipart de fotos/CSV; esos usan MAX_CONTENT)
JSON_SMALL = 12_000          # KPI mes / params
JSON_BODY = 256 * 1024       # 256 KB: instrumentos y APIs JSON
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB: fotos SITIO (12 MB) + CSV
CSV_BYTES = 8 * 1024 * 1024  # 8 MB por importación
IMPORT_ROWS = 5_000
META_JSON = 4_000

# Listados
QUERY_LIMIT = 500


def clip(text: str, max_len: int) -> str:
    if max_len is None or len(text) <= max_len:
        return text
    return text[:max_len]


def over_limit(text: str, max_len: int) -> bool:
    return len(text or "") > max_len


def public_payload() -> dict:
    return {
        "email": EMAIL,
        "name": NAME,
        "phone": PHONE,
        "passwordMin": PASSWORD_MIN,
        "passwordMax": PASSWORD_MAX,
        "subject": SUBJECT,
        "message": MESSAGE,
        "description": DESCRIPTION,
        "solution": SOLUTION,
        "comment": COMMENT,
        "longText": LONG_TEXT,
        "label": LABEL,
        "code": CODE,
        "nit": NIT,
        "queryLimit": QUERY_LIMIT,
    }
