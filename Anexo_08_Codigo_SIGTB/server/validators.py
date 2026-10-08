"""Saneamiento y validación de entradas (correo, contraseña, nombres y textos con tope OWASP)."""

import re

from server.limits import DEFAULT_STRING, EMAIL, PASSWORD_MAX, PASSWORD_MIN, clip

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LETTERS_ONLY_REGEX = re.compile(r"^[A-Za-z\u00C0-\u017F\s]+$")

PASSWORD_MIN_LENGTH = PASSWORD_MIN
PASSWORD_MAX_LENGTH = PASSWORD_MAX


def sanitize_string(value, max_len=DEFAULT_STRING):
    if not isinstance(value, str):
        return ""
    text = value.replace("\x00", "").strip()
    if max_len is None:
        return text
    return clip(text, int(max_len))


def normalize_email(email):
    return sanitize_string(email, EMAIL).lower()


def is_valid_email(email):
    normalized = normalize_email(email)
    return bool(normalized) and bool(EMAIL_REGEX.match(normalized))


def is_letters_only(value):
    text = sanitize_string(value)
    return bool(text) and bool(LETTERS_ONLY_REGEX.match(text))


def validate_password(password):
    errors = []
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"La contraseña debe tener mínimo {PASSWORD_MIN_LENGTH} caracteres.")
    elif len(password) > PASSWORD_MAX_LENGTH:
        errors.append(f"La contraseña no puede superar {PASSWORD_MAX_LENGTH} caracteres.")
    return {"valid": len(errors) == 0, "errors": errors}
