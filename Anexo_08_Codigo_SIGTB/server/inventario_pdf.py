"""Plantilla PDF del inventario biomédico (servicio o sede)."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from server.pdf_staff import pdf_xml, staff_flowables

# Ficha operativa: datos básicos del equipo en la sede/servicio.
PDF_COLUMNS = (
    ("EQUIPO", "equipo", 5.2),
    ("MARCA", "marca", 3.0),
    ("MODELO", "modelo", 3.0),
    ("SERIE", "serie", 3.0),
    ("Nº ACTIVO", "activo", 3.2),
    ("UBICACIÓN", "ubicacion", 4.4),
    ("SERVICIO", "servicio", 4.4),
)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "inv_title",
            parent=base["Heading1"],
            fontSize=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#165e54"),
            spaceAfter=4,
        ),
        "sub": ParagraphStyle(
            "inv_sub",
            parent=base["Normal"],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#5a6b74"),
        ),
        "meta": ParagraphStyle(
            "inv_meta",
            parent=base["Normal"],
            fontSize=8,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1f2a2e"),
            leading=11,
        ),
        "cell": ParagraphStyle(
            "inv_cell",
            parent=base["Normal"],
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
        ),
        "head": ParagraphStyle(
            "inv_head",
            parent=base["Normal"],
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "empty": ParagraphStyle(
            "inv_empty",
            parent=base["Normal"],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#5a6b74"),
            spaceBefore=16,
            leading=14,
        ),
    }


def _p(text, st):
    return Paragraph(pdf_xml(text), st)


def _cell_value(row, field):
    try:
        return row[field]
    except (KeyError, IndexError, TypeError):
        if hasattr(row, "keys") and field in row.keys():
            return row[field]
        return ""


def ficha_row(row) -> dict:
    """Normaliza una fila de inventario para la ficha PDF."""
    if hasattr(row, "keys"):
        data = {key: row[key] for key in row.keys()}
    else:
        data = dict(row or {})
    activo = data.get("codigo_activo") or data.get("num_biomedica") or ""
    id_srv = data.get("ID_servicio") or ""
    name_srv = data.get("name_servicio") or ""
    servicio = " · ".join(part for part in (str(id_srv).strip(), str(name_srv).strip()) if part)
    data["activo"] = activo
    data["servicio"] = servicio
    return data


def build_inventario_pdf(meta: dict, rows, generado_por: str = "", staff: dict | None = None) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=1.1 * cm,
        bottomMargin=1.2 * cm,
        title="Ficha de inventario biomédico",
    )
    st = _styles()
    alcance = (meta.get("alcance") or "servicio").lower()
    empresa = meta.get("ID_Empresa") or "—"
    nit = meta.get("ID_NIT") or "—"
    sede = f"{meta.get('ID_sede') or '—'} · {meta.get('name_sede') or '—'}"
    servicio = f"{meta.get('ID_servicio') or '—'} · {meta.get('name_servicio') or '—'}"
    filtro = meta.get("equipo_filtro")
    if alcance == "sede":
        titulo = "SIGTB · Ficha de inventario de la sede"
        alcance_txt = "Todos los servicios de la sede"
        empty_txt = "No hay equipos cargados en esta sede."
        footer_txt = (
            "SIGTB — inventario biomédico por sede. Documento de consulta "
            "(equipo, marca, modelo, serie, número de activo y ubicación)."
        )
    else:
        titulo = "SIGTB · Ficha de inventario del servicio"
        alcance_txt = "Todos los equipos del servicio"
        empty_txt = "No hay equipos cargados al servicio."
        footer_txt = (
            "SIGTB — inventario biomédico por servicio. Documento de consulta "
            "(equipo, marca, modelo, serie, número de activo y ubicación)."
        )
    if filtro:
        alcance_txt = f"Filtro de equipo: {filtro}"

    story = [
        Paragraph(titulo, st["title"]),
        Paragraph(
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"Responsable: {generado_por or '—'}",
            st["sub"],
        ),
        Spacer(1, 8),
    ]
    story.extend(staff_flowables(st["meta"], staff, cell_style=st["cell"]))
    datos = [
        ["Empresa", empresa, "NIT", nit],
        ["Sede", sede, "Servicio" if alcance != "sede" else "Alcance", servicio if alcance != "sede" else alcance_txt],
        ["Equipos", str(len(rows)), "Alcance" if alcance != "sede" else "Servicios", alcance_txt if alcance != "sede" else str(meta.get("servicios_n") or "—")],
    ]
    meta_table = Table(
        [[_p(c, st["cell"]) for c in row] for row in datos],
        colWidths=[2.6 * cm, 10.4 * cm, 2.4 * cm, 10.8 * cm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d8efe9")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#d8efe9")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [meta_table, Spacer(1, 10)]

    ficha_rows = [ficha_row(row) for row in rows]
    if not ficha_rows:
        story.append(Paragraph(empty_txt, st["empty"]))
    else:
        header = [_p(col[0], st["head"]) for col in PDF_COLUMNS]
        data = [header]
        for row in ficha_rows:
            data.append([_p(_cell_value(row, col[1]), st["cell"]) for col in PDF_COLUMNS])
        col_widths = [col[2] * cm for col in PDF_COLUMNS]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f7a6c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7fbfa")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7fbfa"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#5a6b74"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.1 * cm, 0.6 * cm, footer_txt)
        canvas.drawRightString(
            landscape(A4)[0] - 1.1 * cm,
            0.6 * cm,
            f"Página {doc_.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf
