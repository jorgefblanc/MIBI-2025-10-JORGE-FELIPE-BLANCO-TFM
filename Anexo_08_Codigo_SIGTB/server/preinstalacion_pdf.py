"""Generación PDF del informe de preinstalación."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from server.pdf_staff import pdf_xml, staff_flowables
from server.pdf_charts import charts_table


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "pre_title",
            parent=base["Heading1"],
            fontSize=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#165e54"),
            spaceAfter=8,
        ),
        "sub": ParagraphStyle(
            "pre_sub", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#5a6b74")
        ),
        "h2": ParagraphStyle(
            "pre_h2",
            parent=base["Heading2"],
            fontSize=10,
            textColor=colors.HexColor("#1f7a6c"),
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "pre_body", parent=base["Normal"], fontSize=8, alignment=TA_JUSTIFY, leading=11
        ),
        "cell": ParagraphStyle("pre_cell", parent=base["Normal"], fontSize=7, leading=9),
    }


def _p(text, st):
    return Paragraph(pdf_xml(text), st)


def build_informe_pdf(evaluacion: dict, generado_por: str = "", staff: dict | None = None) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=1.4 * cm, rightMargin=1.4 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm
    )
    st = _styles()
    pct = float(evaluacion.get("pct_cumplimiento") or 0) * 100
    decision = evaluacion.get("decision") or "—"
    story = [
        Paragraph("SIGTB · Informe de verificación de preinstalación", st["title"]),
        Paragraph(
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"Responsable de exportación: {pdf_xml(generado_por or 'Ingeniería clínica')}",
            st["sub"],
        ),
        Spacer(1, 6),
    ]
    story.extend(staff_flowables(st["body"], staff, cell_style=st["cell"]))
    story += [
        Paragraph("Datos generales", st["h2"]),
    ]
    datos = [
        ["Institución", evaluacion.get("institucion") or "—", "Servicio / Área", evaluacion.get("servicio_area") or "—"],
        ["Tecnología", evaluacion.get("tecnologia") or "—", "Marca / Modelo", evaluacion.get("marca_modelo") or "—"],
        ["Proveedor", evaluacion.get("proveedor") or "—", "Ubicación", evaluacion.get("ubicacion_propuesta") or "—"],
        ["Fecha visita", str(evaluacion.get("fecha_visita") or "—")[:10], "Responsable", evaluacion.get("responsable_verificacion") or "—"],
        ["Serial / código", evaluacion.get("serial_codigo") or "—", "Acompañante", evaluacion.get("acompanante_servicio") or "—"],
    ]
    t = Table([[_p(c, st["cell"]) for c in row] for row in datos], colWidths=[3.2 * cm, 5.3 * cm, 3.4 * cm, 5.3 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d8efe9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#d8efe9")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [t, Paragraph("Resultado automático", st["h2"])]
    kpis = [
        ["Total evaluables", str(evaluacion.get("total_evaluables") or 0),
         "Cumplidos", str(evaluacion.get("cumplidos") or 0)],
        ["No cumplidos", str(evaluacion.get("no_cumplidos") or 0),
         "Pendientes", str(evaluacion.get("pendientes") or 0)],
        ["Críticos abiertos", str(evaluacion.get("criticos_abiertos") or 0),
         "% cumplimiento", f"{pct:.1f} %"],
        ["Decisión", decision, "Estado", evaluacion.get("estado_eval") or "—"],
    ]
    k = Table([[_p(c, st["cell"]) for c in row] for row in kpis], colWidths=[3.2 * cm, 5.3 * cm, 3.4 * cm, 5.3 * cm])
    k.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef6f3")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef6f3")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(k)

    story.append(Paragraph("Gráficas de apoyo", st["h2"]))
    story.append(
        charts_table(
            "Estado de requisitos",
            [
                {"label": "Cumple", "value": evaluacion.get("cumplidos") or 0},
                {"label": "No cumple", "value": evaluacion.get("no_cumplidos") or 0},
                {"label": "Pendiente", "value": evaluacion.get("pendientes") or 0},
            ],
            "% cumplimiento por bloque",
            [
                {
                    "label": b.get("categoria"),
                    "value": round(float(b.get("pct") or 0) * 100, 1),
                }
                for b in evaluacion.get("por_bloque") or []
            ],
        )
    )

    story.append(Paragraph("Requisitos abiertos que deben cerrarse antes de la instalación", st["h2"]))
    abiertos = evaluacion.get("abiertos") or []
    if not abiertos:
        story.append(Paragraph("No hay requisitos abiertos.", st["body"]))
    else:
        rows = [[_p(h, st["cell"]) for h in ("Fuente", "Categoría", "Requisito", "Criticidad", "Estado", "Acción")]]
        for a in abiertos:
            rows.append([
                _p(a.get("fuente"), st["cell"]),
                _p(a.get("categoria"), st["cell"]),
                _p(a.get("requisito"), st["cell"]),
                _p(a.get("criticidad"), st["cell"]),
                _p(a.get("estado"), st["cell"]),
                _p(a.get("observaciones") or a.get("responsable_cierre"), st["cell"]),
            ])
        at = Table(rows, colWidths=[2.2 * cm, 3.2 * cm, 5.2 * cm, 2.0 * cm, 2.0 * cm, 2.6 * cm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#165e54")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(at)

    story.append(Paragraph("Concepto técnico de ingeniería clínica", st["h2"]))
    concepto = evaluacion.get("concepto_tecnico") or (
        "Con base en la visita de preinstalación, la instalación no debe aprobarse hasta cerrar "
        "los requisitos críticos pendientes." if (evaluacion.get("criticos_abiertos") or 0) > 0
        else "Los requisitos evaluables permiten emitir el concepto según la decisión automática."
    )
    story.append(_p(concepto, st["body"]))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Firmas", st["h2"]))
    firmas = [
        ["Firma Ingeniería Clínica", "", "Firma Servicio Usuario", ""],
        ["Nombre:", evaluacion.get("firma_ic_nombre") or "_______________",
         "Nombre:", evaluacion.get("firma_servicio_nombre") or "_______________"],
        ["Cargo:", evaluacion.get("firma_ic_cargo") or "_______________",
         "Cargo:", evaluacion.get("firma_servicio_cargo") or "_______________"],
        ["Fecha:", str(evaluacion.get("firma_ic_fecha") or "_______________")[:10],
         "Fecha:", str(evaluacion.get("firma_servicio_fecha") or "_______________")[:10],
        ],
    ]
    ft = Table([[_p(c, st["cell"]) for c in row] for row in firmas], colWidths=[3.4 * cm, 5.1 * cm, 3.4 * cm, 5.3 * cm])
    ft.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d5d0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef6f3")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ft)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Instrumento SITIO · SIGTB. «No aplica» no entra al porcentaje. "
        "Un requisito Crítico en Pendiente o No cumple bloquea la instalación.",
        st["sub"],
    ))
    doc.build(story)
    buf.seek(0)
    return buf
