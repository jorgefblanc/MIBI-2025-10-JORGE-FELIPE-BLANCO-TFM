"""
Envío de correo (recuperación de contraseña).

Configuración (variables de entorno o data/smtp.json):
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS (1/0)
"""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from server.db import DATA_DIR

SMTP_JSON = DATA_DIR / "smtp.json"
OUTBOX_DIR = DATA_DIR / "mail_outbox"


def _smtp_config() -> dict:
    cfg = {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT") or "587"),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM", "").strip(),
        "tls": os.environ.get("SMTP_TLS", "1").strip() not in ("0", "false", "False"),
    }
    if SMTP_JSON.exists():
        try:
            raw = json.loads(SMTP_JSON.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if raw.get("host"):
                    cfg["host"] = str(raw.get("host") or "").strip()
                if raw.get("port"):
                    cfg["port"] = int(raw.get("port"))
                if raw.get("user") is not None:
                    cfg["user"] = str(raw.get("user") or "").strip()
                if raw.get("password") is not None:
                    cfg["password"] = str(raw.get("password") or "")
                if raw.get("from"):
                    cfg["from_addr"] = str(raw.get("from") or "").strip()
                if "tls" in raw:
                    cfg["tls"] = bool(raw.get("tls"))
        except Exception:
            pass
    if not cfg["from_addr"]:
        cfg["from_addr"] = cfg["user"] or "noreply@sigtb.local"
    return cfg


def _write_outbox(to_addr: str, subject: str, body: str) -> None:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "@._-" else "_" for ch in to_addr)[:80]
    from datetime import datetime

    name = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + f"_{safe}.txt"
    (OUTBOX_DIR / name).write_text(
        f"To: {to_addr}\nSubject: {subject}\n\n{body}\n",
        encoding="utf-8",
    )


def send_email(to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Envía un correo de texto. Si no hay SMTP, deja copia en data/mail_outbox.
    Retorna (ok, detalle).
    """
    if not to_addr:
        return False, "Destinatario vacío."
    cfg = _smtp_config()
    _write_outbox(to_addr, subject, body)
    if not cfg["host"]:
        return True, "Correo registrado en bandeja local (configure SMTP_HOST para envío real)."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        if cfg["tls"]:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        return True, "Correo enviado."
    except Exception as err:
        return False, str(err)
