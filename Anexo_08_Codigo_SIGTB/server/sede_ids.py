"""Generación de ID_sede / ID_servicio. Autogenera solo si no hay identificador."""

import re
import unicodedata

KNOWN_PREFIXES = {
    "cirugia": "CI",
    "consulta externa": "CE",
    "urgencias": "UR",
    "urgencia": "UR",
}

AUTOGEN_ID_RE = re.compile(r"^[A-Z]{1,6}\d{5}$")
EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9._\-/]{1,20}$")
SPEC_ID_RE = re.compile(
    r"^(\d{3,10}|[A-Z]{1,6}\d{2,8})\s*[:\-–]?\s+(.+)$",
    re.IGNORECASE,
)

SERVICIO_ORDER_SQL = """
    CASE WHEN ID_servicio GLOB '[0-9]*' THEN 0 ELSE 1 END,
    CAST(ID_servicio AS INTEGER),
    ID_servicio COLLATE NOCASE,
    name_servicio COLLATE NOCASE
"""


def _strip_accents(text):
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text_name(name):
    text = (name or "").strip()
    return re.sub(r"\s+", " ", text)


def is_letters_only_name(name):
    """Nombre de sede/servicio: letras, números, espacios y separadores habituales."""
    text = normalize_text_name(name)
    return bool(text) and bool(
        re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s.\-_/(),]+", text)
    )


def derive_prefix(name):
    normalized = _strip_accents(normalize_text_name(name)).lower()
    if normalized in KNOWN_PREFIXES:
        return KNOWN_PREFIXES[normalized]

    words = [w for w in re.split(r"\s+", normalized) if w]
    if not words:
        return "XX"

    if len(words) == 1:
        word = re.sub(r"[^a-z]", "", words[0])
        return (word[:2] or "XX").upper()

    initials = "".join(re.sub(r"[^a-z]", "", w)[:1] for w in words[:2])
    return (initials[:2] or "XX").upper()


def looks_like_autogen_id(value) -> bool:
    """True para IDs internos tipo AG00001 / UR00001."""
    text = str(value or "").strip().upper()
    return bool(AUTOGEN_ID_RE.fullmatch(text))


def normalize_external_id(value) -> str | None:
    """Devuelve el identificador institucional si existe; si no, None (hay que autogenerar)."""
    text = str(value or "").strip()
    if not text or text.upper() in {"NA", "N/A", "NONE", "NULL", "-"}:
        return None
    text = re.sub(r"\s+", "", text)
    if not EXTERNAL_ID_RE.fullmatch(text):
        return None
    if text.isdigit():
        return text
    return text.upper()


def parse_servicio_spec(raw) -> tuple[str | None, str]:
    """
    Interpreta '3000 Urgencias', '3000: Cirugía General' o un dict.
    Devuelve (ID_servicio o None, nombre).
    """
    if isinstance(raw, dict):
        name = normalize_text_name(
            raw.get("name_servicio") or raw.get("name") or raw.get("nombre") or ""
        )
        ext = normalize_external_id(
            raw.get("ID_servicio")
            or raw.get("id_servicio")
            or raw.get("codigo")
            or raw.get("id")
        )
        if not ext:
            parsed_id, parsed_name = parse_servicio_spec(name)
            return parsed_id, parsed_name or name
        return ext, name

    text = normalize_text_name(str(raw or ""))
    if not text:
        return None, ""
    match = SPEC_ID_RE.match(text)
    if match:
        return normalize_external_id(match.group(1)), normalize_text_name(match.group(2))
    only_id = normalize_external_id(text)
    if only_id and text.replace(" ", "") == only_id:
        return only_id, ""
    return None, text


def prefix_for_id(name: str, external_id: str | None) -> str:
    if external_id and str(external_id).isdigit():
        return "ID"
    prefix = derive_prefix(name)
    return (prefix[:10] or "XX")


def next_scoped_id(conn, *, scope_type, scope_key, name):
    """
    Asigna el siguiente ID autogenerado para sede o servicio.
    scope_type: 'sede' | 'servicio'
    scope_key: empresa_id (sede) o sede_id (servicio)
    """
    prefix = derive_prefix(name)
    key = str(scope_key)
    row = conn.execute(
        """
        SELECT last_number FROM id_counters
        WHERE scope_type = ? AND scope_key = ? AND prefix = ?
        """,
        (scope_type, key, prefix),
    ).fetchone()

    if row is None:
        next_number = 1
        conn.execute(
            """
            INSERT INTO id_counters (scope_type, scope_key, prefix, last_number)
            VALUES (?, ?, ?, ?)
            """,
            (scope_type, key, prefix, next_number),
        )
    else:
        next_number = int(row["last_number"]) + 1
        conn.execute(
            """
            UPDATE id_counters SET last_number = ?
            WHERE scope_type = ? AND scope_key = ? AND prefix = ?
            """,
            (next_number, scope_type, key, prefix),
        )

    return f"{prefix}{next_number:05d}", prefix


def next_id_sede(conn, name_sede, empresa_id, external_id=None):
    ext = normalize_external_id(external_id)
    if ext:
        return ext, prefix_for_id(name_sede, ext)
    return next_scoped_id(
        conn, scope_type="sede", scope_key=empresa_id, name=name_sede
    )


def next_id_servicio(conn, name_servicio, sede_id, external_id=None):
    ext = normalize_external_id(external_id)
    if ext:
        return ext, prefix_for_id(name_servicio, ext)
    return next_scoped_id(
        conn, scope_type="servicio", scope_key=sede_id, name=name_servicio
    )
