"""Generación PDF del plan de frecuencia de mantenimiento preventivo."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from server.pdf_charts import charts_table
from server.pdf_staff import pdf_xml, staff_flowables

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _p(text, st):
    return Paragraph(pdf_xml(text), st)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "pm_title",
            parent=base["Heading1"],
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#165e54"),
            spaceAfter=8,
        ),
        "sub": ParagraphStyle(
            "pm_sub", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#5a6b74")
        ),
        "h2": ParagraphStyle(
            "pm_h2",
            parent=base["Heading2"],
            fontSize=11,
            textColor=colors.HexColor("#1f7a6c"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "pm_body", parent=base["Normal"], fontSize=9, alignment=TA_JUSTIFY, leading=12
        ),
        "cell": ParagraphStyle("pm_cell", parent=base["Normal"], fontSize=7, leading=9),
    }


def build_informe_resumen_pdf(
    *,
    institucion: str,
    responsable: str,
    stats: dict,
    conclusion: str | None = None,
    staff: dict | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    st = _styles()
    story = [
        Paragraph("SIGTB · Informe exportable — Plan de mantenimiento preventivo", st["title"]),
        Paragraph(
            f"Institución: {pdf_xml(institucion)} · Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"Responsable: {pdf_xml(responsable or 'Ingeniería clínica')}",
            st["sub"],
        ),
        Spacer(1, 8),
    ]
    story.extend(staff_flowables(st["body"], staff, cell_style=st["cell"] if "cell" in st else st["body"]))
    story += [
        Paragraph("Criterio: GE = Función + Aplicación + Requisito + Antecedentes de fallas", st["body"]),
        Paragraph(
            "Ajuste: si GE≥12, TPM = min(TGE, Tfab). Si GE<12 prevalece el fabricante cuando exige PM.",
            st["body"],
        ),
        Spacer(1, 6),
        Paragraph(f"Total equipos evaluados: <b>{stats.get('total_equipos', 0)}</b>", st["body"]),
        Paragraph("Distribución por frecuencia definitiva", st["h2"]),
    ]
    total = max(int(stats.get("total_equipos") or 0), 1)
    freq = stats.get("frecuencias") or {}
    rows = [["Frecuencia", "Cantidad", "%", "Acción recomendada"]]
    acciones = {
        "Cada 4 meses": "Inspecciones de rendimiento y seguridad",
        "Cada 6 meses": "PM/inspección semestral",
        "Anual": "Inspección preventiva básica",
        "Correctivo bajo demanda": "Atender bajo demanda y monitorear fallas",
        "Otro": "Revisar criterio institucional",
    }
    for key in ("Cada 4 meses", "Cada 6 meses", "Anual", "Correctivo bajo demanda", "Otro"):
        n = int(freq.get(key) or 0)
        if key == "Otro" and n == 0:
            continue
        rows.append([key, str(n), f"{(100.0 * n / total):.1f}%", acciones.get(key, "—")])
    table = Table(rows, colWidths=[4.2 * cm, 2.2 * cm, 2 * cm, 7.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5dee3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    story.append(Paragraph("Gráficas de apoyo", st["h2"]))
    ge_items = [
        {"label": "GE ≥ 19", "value": stats.get("ge_ge_19") or 0},
        {"label": "15 ≤ GE < 19", "value": stats.get("ge_15_19") or 0},
        {"label": "12 ≤ GE < 15", "value": stats.get("ge_12_15") or 0},
        {"label": "GE < 12", "value": stats.get("ge_lt_12") or 0},
    ]
    freq_items = [
        {"label": key, "value": n}
        for key, n in (stats.get("frecuencias") or {}).items()
    ]
    story.append(
        charts_table(
            "Equipos por criticidad GE",
            ge_items,
            "Frecuencias definitivas",
            freq_items,
        )
    )
    story.append(Paragraph("Conclusión técnica", st["h2"]))
    story.append(
        Paragraph(
            conclusion
            or (
                "El plan de mantenimiento preventivo se asigna según el grado de evaluación GE. "
                "Los equipos con mayor criticidad clínica, mayor complejidad de mantenimiento, uso en "
                "áreas críticas o antecedentes de fallas reciben intervalos más cortos. El cronograma "
                "debe cargarse al CMMS institucional y actualizarse cuando cambien las condiciones de "
                "uso, fallas o recomendaciones del fabricante."
            ),
            st["body"],
        )
    )
    story.append(Paragraph("Nota sobre cronograma", st["h2"]))
    story.append(
        Paragraph(
            "El cronograma se genera automáticamente tomando como punto de partida la fecha del "
            "último mantenimiento de cada equipo.",
            st["body"],
        )
    )
    doc.build(story)
    return buf.getvalue()


def build_cronograma_pdf(
    *,
    institucion: str,
    servicio: str,
    anio: int,
    rows: list[dict],
    empresa: str | None = None,
    sede: str | None = None,
    staff: dict | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm
    )
    st = _styles()
    empresa_txt = empresa or ""
    sede_txt = sede or ""
    header_org = institucion or "—"
    if empresa_txt or sede_txt:
        header_org = " · ".join(part for part in (empresa_txt, sede_txt) if part) or header_org
    story = [
        Paragraph(f"SIGTB · Cronograma PM {anio} — {pdf_xml(servicio or 'Servicio')}", st["title"]),
        Paragraph(
            f"Empresa / sede: {pdf_xml(header_org)} · Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            st["sub"],
        ),
        Spacer(1, 6),
    ]
    story.extend(staff_flowables(st["sub"], staff, cell_style=st["cell"]))
    header = ["Equipo", "Área", "Último PM", "Frecuencia", *MESES, "Obs."]
    data = [header]
    for r in rows:
        meses = [r.get(f"mes_{i:02d}") for i in range(1, 13)]
        marks = ["PM" if m else "" for m in meses]
        data.append(
            [
                _p(str(r.get("equipo") or "—")[:40], st["cell"]),
                _p(str(r.get("servicio_nombre") or "—")[:24], st["cell"]),
                str(r.get("fecha_ultimo_pm") or "—")[:10],
                _p(str(r.get("frecuencia_definitiva") or "—")[:28], st["cell"]),
                *marks,
                _p(str(r.get("observacion") or "—")[:40], st["cell"]),
            ]
        )
    widths = [3.5 * cm, 2.4 * cm, 2 * cm, 2.6 * cm] + [1.1 * cm] * 12 + [3.2 * cm]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5dee3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("ALIGN", (4, 1), (15, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
