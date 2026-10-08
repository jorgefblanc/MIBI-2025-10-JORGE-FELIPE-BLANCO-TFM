"""
Personal institucional para encabezados de PDF exportables.

Incluye director, coordinador y personas asignadas a la empresa/sede.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from server.db import get_users_connection
from server.roles import normalize_job


def pdf_xml(value, empty: str = "—") -> str:
    """Escapa texto para reportlab Paragraph; evita 500 si hay <, & o >."""
    if value is None:
        text = ""
    else:
        text = str(value)
    text = text.strip()
    if not text:
        text = empty
    return xml_escape(text).replace("\n", "<br/>")


DIRECTOR_JOBS = frozenset({"Director Operativo", "Dirección", "Director"})
COORDINADOR_JOBS = frozenset({"Coordinador"})


def _as_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _person_label(row) -> str:
    if not row:
        return ""
    data = dict(row) if hasattr(row, "keys") else dict(row or {})
    name = " ".join(
        part
        for part in (
            str(data.get("NAME_USER") or "").strip(),
            str(data.get("LAST_NAME_USER") or "").strip(),
        )
        if part
    )
    login = str(data.get("usuario_login") or "").strip()
    job = str(data.get("JOB") or "").strip()
    base = name or login
    if not base:
        return ""
    extras = []
    if job:
        extras.append(job)
    if login and name:
        extras.append(login)
    return f"{base} ({', '.join(extras)})" if extras else base


def _job_bucket(job: str) -> str | None:
    normalized = normalize_job("OPERATIVO", job) if job else job
    if job in DIRECTOR_JOBS or normalized in DIRECTOR_JOBS:
        return "director"
    if job in COORDINADOR_JOBS or normalized in COORDINADOR_JOBS:
        return "coordinador"
    return None


def collect_org_staff(*, empresa_id=None, sede_id=None) -> dict:
    """Director, coordinador y personal asignado (empresa o sede)."""
    emp_id = _as_int(empresa_id)
    sede = _as_int(sede_id)
    empty = {"director": [], "coordinador": [], "asignados": []}
    if not emp_id:
        return empty

    directors: list[str] = []
    coordinators: list[str] = []
    assigned: list[str] = []
    seen: set[str] = set()

    def _push(bucket: list[str], label: str):
        if label and label not in seen:
            seen.add(label)
            bucket.append(label)

    with get_users_connection() as users_conn:
        empresa_rows = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL
            FROM usuarios
            WHERE empresa_id = ? AND ROLL != 'ADMIN'
            ORDER BY LAST_NAME_USER COLLATE NOCASE, NAME_USER COLLATE NOCASE
            """,
            (emp_id,),
        ).fetchall()
        for row in empresa_rows:
            label = _person_label(row)
            bucket = _job_bucket(row["JOB"] or "")
            if bucket == "director":
                _push(directors, label)
            elif bucket == "coordinador":
                _push(coordinators, label)

        if sede:
            sede_rows = users_conn.execute(
                """
                SELECT u.id_usuario, u.usuario_login, u.NAME_USER, u.LAST_NAME_USER,
                       u.JOB, u.ROLL
                FROM usuario_sedes us
                JOIN usuarios u ON u.id_usuario = us.usuario_id
                WHERE us.sede_id = ?
                  AND u.empresa_id = ?
                  AND u.ROLL != 'ADMIN'
                ORDER BY u.LAST_NAME_USER COLLATE NOCASE, u.NAME_USER COLLATE NOCASE
                """,
                (sede, emp_id),
            ).fetchall()
            source = sede_rows
        else:
            source = empresa_rows

        for row in source:
            label = _person_label(row)
            bucket = _job_bucket(row["JOB"] or "")
            if bucket in {"director", "coordinador"}:
                continue
            _push(assigned, label)

    return {
        "director": directors,
        "coordinador": coordinators,
        "asignados": assigned,
    }


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "—"


def staff_flowables(style, staff: dict | None, *, cell_style=None):
    """Bloque de tabla para insertar en un PDF (lista de flowables)."""
    data = staff or {}
    rows = [
        ["Director", _join(data.get("director") or [])],
        ["Coordinador", _join(data.get("coordinador") or [])],
        ["Personal asignado", _join(data.get("asignados") or [])],
    ]
    if cell_style is not None:
        table_data = [
            [Paragraph(pdf_xml(label), cell_style), Paragraph(pdf_xml(value), cell_style)]
            for label, value in rows
        ]
    else:
        table_data = rows
    table = Table(table_data, colWidths=[3.4 * cm, 14.2 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d8efe9")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def staff_lines(staff: dict | None) -> str:
    data = staff or {}
    return (
        f"Director: {_join(data.get('director') or [])} · "
        f"Coordinador: {_join(data.get('coordinador') or [])} · "
        f"Personal asignado: {_join(data.get('asignados') or [])}"
    )
