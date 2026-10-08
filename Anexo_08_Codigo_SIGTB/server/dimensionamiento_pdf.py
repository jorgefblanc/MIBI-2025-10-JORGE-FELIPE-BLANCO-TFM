"""Generación PDF del Informe exportable de Dimensionamiento de Personal."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
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
from server.pdf_charts import charts_table


def _fmt(value, digits=2) -> str:
    if value is None or value == "":
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.{digits}f}"


def build_informe_pdf(
    *,
    sede: dict,
    params_calc: dict,
    resumen: dict,
    disponibles: int,
    grupos: list[dict] | None = None,
    staff: dict | None = None,
) -> bytes:
    """Construye el PDF del informe final exportable."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="Informe Dimensionamiento de Personal IC",
        author="SIGTB",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DimTitle",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=8,
        textColor=colors.HexColor("#1f4f46"),
    )
    h2 = ParagraphStyle(
        "DimH2",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#1f4f46"),
    )
    body = ParagraphStyle(
        "DimBody",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "DimMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#445552"),
    )
    small = ParagraphStyle(
        "DimSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#667774"),
    )

    story = []
    story.append(Paragraph("SIGTB · Ingeniería Clínica", meta))
    story.append(
        Paragraph("Informe final — Dimensionamiento de Personal", title)
    )
    story.append(
        Paragraph(
            f"Sede: <b>{pdf_xml(sede.get('name_sede'))}</b> "
            f"({pdf_xml(sede.get('ID_sede'))}) · Empresa: "
            f"<b>{pdf_xml(sede.get('ID_Empresa'))}</b> · "
            f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
            meta,
        )
    )
    story.append(Spacer(1, 0.35 * cm))
    story.extend(staff_flowables(body, staff, cell_style=small))
    story.append(Paragraph("1. Objetivo", h2))
    story.append(
        Paragraph(
            "Calcular la carga anual de trabajo y estimar cuántos Ingenieros "
            "Clínicos se requieren para cubrir actividades programadas, "
            "correctivas y adicionales en el parque biomédico evaluado.",
            body,
        )
    )

    story.append(Paragraph("2. Perfil evaluado", h2))
    story.append(
        Paragraph(
            f"Perfil institucional: <b>{pdf_xml(params_calc.get('perfil') or 'Ingeniero Clínico')}</b>. "
            f"Horas efectivas por IC/año: <b>{_fmt(resumen.get('horas_efectivas'))}</b>.",
            body,
        )
    )

    story.append(Paragraph("3. Resultado general", h2))
    kpi_data = [
        ["Indicador", "Valor"],
        ["Total equipos evaluados", _fmt(resumen.get("total_equipos"), 0)],
        ["Total horas base / año", _fmt(resumen.get("total_base"))],
        ["Contingencia (h/año)", _fmt(resumen.get("contingencia_h"))],
        ["Total horas ajustadas / año", _fmt(resumen.get("total_ajustado"))],
        ["Horas efectivas por IC / año", _fmt(resumen.get("horas_efectivas"))],
        ["IC requeridos", _fmt(resumen.get("ingenieros_requeridos"))],
        ["IC recomendados (CEILING)", _fmt(resumen.get("ingenieros_recomendados"), 0)],
        ["IC disponibles (personal)", _fmt(disponibles, 0)],
    ]
    kpi_table = Table(kpi_data, colWidths=[10.5 * cm, 5.5 * cm])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f7a6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d9d5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f8f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ]
        )
    )
    story.append(kpi_table)

    story.append(Paragraph("Gráficas de apoyo", h2))
    story.append(
        charts_table(
            "Criticidad (horas/año)",
            [
                {"label": item.get("criticidad"), "value": item.get("horas")}
                for item in resumen.get("por_criticidad") or []
            ],
            "Número de horas por actividad",
            [
                {"label": item.get("actividad"), "value": item.get("horas")}
                for item in resumen.get("por_actividad") or []
            ],
        )
    )

    story.append(Paragraph("4. Resumen por servicio", h2))
    srv_rows = [["Servicio", "Horas/año"]]
    for item in resumen.get("por_servicio") or []:
        srv_rows.append([item.get("servicio") or "—", _fmt(item.get("horas"))])
    if len(srv_rows) == 1:
        srv_rows.append(["Sin datos", "—"])
    srv_table = Table(srv_rows, colWidths=[10.5 * cm, 5.5 * cm])
    srv_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a6f65")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d9d5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7faf9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ]
        )
    )
    story.append(srv_table)

    if grupos:
        story.append(Paragraph("5. Inventario agrupado por tipo de equipo", h2))
        g_rows = [["Cant.", "Equipo", "Horas/año acumuladas"]]
        for g in grupos[:40]:
            g_rows.append(
                [
                    str(g.get("cantidad") or 0),
                    str(g.get("equipo") or "—")[:48],
                    _fmt(g.get("total_horas")),
                ]
            )
        g_table = Table(g_rows, colWidths=[1.6 * cm, 10.4 * cm, 4 * cm])
        g_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d7a70")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0ddd9")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f9f8")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ]
            )
        )
        story.append(g_table)
        if len(grupos) > 40:
            story.append(
                Paragraph(
                    f"Se muestran 40 de {len(grupos)} grupos de equipos.",
                    small,
                )
            )

    story.append(Paragraph("6. Interpretación", h2))
    story.append(
        Paragraph(
            "Si la carga total ajustada supera la capacidad efectiva del equipo "
            "actual, se genera riesgo de incumplimiento del mantenimiento "
            "programado, retrasos en correctivos, debilidad documental y menor "
            "capacidad para auditorías.",
            body,
        )
    )

    story.append(Paragraph("7. Recomendación", h2))
    story.append(
        Paragraph(
            "Usar este resultado como soporte técnico para justificar "
            "contratación, redistribución de funciones, tercerización controlada "
            "o fortalecimiento del área de Ingeniería Clínica.",
            body,
        )
    )

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            "Documento generado automáticamente por SIGTB. Uso institucional.",
            small,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _style_kpi_table():
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f7a6c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d9d5")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f8f6")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ]
    )


def build_informe_empresa_pdf(payload: dict) -> bytes:
    """Informe consolidado de dimensionamiento empresarial."""
    empresa = payload.get("empresa") or {}
    dash = payload.get("dashboard") or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="Informe Dimensionamiento Empresarial IC",
        author="SIGTB",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DimEmpTitle",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=8,
        textColor=colors.HexColor("#1f4f46"),
    )
    h2 = ParagraphStyle(
        "DimEmpH2",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#1f4f46"),
    )
    body = ParagraphStyle(
        "DimEmpBody",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "DimEmpMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#445552"),
    )
    small = ParagraphStyle(
        "DimEmpSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#667774"),
    )

    story = []
    story.append(Paragraph("SIGTB · Ingeniería Clínica", meta))
    story.append(Paragraph("Informe empresarial — Dimensionamiento de Personal", title))
    nit = empresa.get("ID_NIT") or "—"
    story.append(
        Paragraph(
            f"Empresa: <b>{pdf_xml(empresa.get('ID_Empresa'))}</b> · NIT: <b>{pdf_xml(nit)}</b> · "
            f"Sedes: <b>{_fmt(dash.get('sedes'), 0)}</b> · "
            f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
            meta,
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.extend(staff_flowables(body, payload.get("staff"), cell_style=small))

    story.append(Paragraph("1. Alcance del cálculo", h2))
    story.append(
        Paragraph(
            "El IC por carga horaria incluye equipos operativos. En Comodato o Leasing el "
            "mantenimiento preventivo y el correctivo estimado se asumen tercerizados "
            "(no suman horas). Sí pueden alimentar la carga otras actividades o "
            "correctivos de apoyo con histórico. El IC por criticidad no incluye "
            "Comodato/Leasing: quedan fuera del campo de acción del ingeniero clínico.",
            body,
        )
    )

    story.append(Paragraph("2. Resultado general", h2))
    kpi_data = [
        ["Indicador", "Valor"],
        ["Equipos en carga horaria", _fmt(dash.get("total_equipos"), 0)],
        ["Equipos en plantilla (criticidad)", _fmt(dash.get("total_equipos_dotacion"), 0)],
        ["Comodato/Leasing (fuera de plantilla)", _fmt(dash.get("equipos_comodato_leasing"), 0)],
        ["Horas ajustadas / año", _fmt(dash.get("total_ajustado"))],
        ["IC por carga horaria", f"{_fmt(dash.get('ingenieros_requeridos'))} → {_fmt(dash.get('ingenieros_recomendados'), 0)}"],
        ["IC por criticidad", f"{_fmt(dash.get('ingenieros_por_dotacion'))} → {_fmt(dash.get('ingenieros_recomendados_dotacion'), 0)}"],
        ["IC/técnicos asignados a las sedes", _fmt(dash.get("ingenieros_disponibles"), 0)],
        ["Altos únicos con ratio medio", _fmt(dash.get("alto_unico_como_medio"), 0)],
    ]
    kpi_table = Table(kpi_data, colWidths=[10.5 * cm, 5.5 * cm])
    kpi_table.setStyle(_style_kpi_table())
    story.append(kpi_table)

    story.append(Paragraph("Gráficas de apoyo", h2))
    story.append(
        charts_table(
            "Plantilla por criticidad",
            [
                {"label": item.get("criticidad"), "value": item.get("equipos")}
                for item in (payload.get("dotacion") or {}).get("por_criticidad_dotacion") or []
            ],
            "Horas por actividad",
            [
                {"label": item.get("actividad"), "value": item.get("horas")}
                for item in (payload.get("resumen") or {}).get("por_actividad") or []
            ],
        )
    )

    story.append(Paragraph("3. Equipos por forma de adquisición", h2))
    adq_rows = [["Forma", "Equipos", "En plantilla", "Horas carga"]]
    for item in payload.get("por_adquisicion") or []:
        adq_rows.append(
            [
                str(item.get("forma_adquisicion") or "—"),
                _fmt(item.get("equipos"), 0),
                _fmt(item.get("en_plantilla"), 0),
                _fmt(item.get("horas")),
            ]
        )
    if len(adq_rows) == 1:
        adq_rows.append(["Sin datos", "—", "—", "—"])
    adq_table = Table(adq_rows, colWidths=[5.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
    adq_table.setStyle(_style_kpi_table())
    story.append(adq_table)

    story.append(Paragraph("4. Plantilla por criticidad", h2))
    crit_rows = [["Criticidad", "Equipos", "Equipos / IC", "IC rec."]]
    for item in (payload.get("dotacion") or {}).get("por_criticidad_dotacion") or []:
        crit_rows.append(
            [
                str(item.get("criticidad") or "—"),
                _fmt(item.get("equipos"), 0),
                _fmt(item.get("equipos_por_ic"), 0),
                _fmt(item.get("ingenieros_recomendados"), 0),
            ]
        )
    crit_table = Table(crit_rows, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm])
    crit_table.setStyle(_style_kpi_table())
    story.append(crit_table)

    story.append(Paragraph("5. Carga horaria por actividad", h2))
    act_rows = [["Actividad", "Horas/año"]]
    for item in (payload.get("resumen") or {}).get("por_actividad") or []:
        act_rows.append([str(item.get("actividad") or "—"), _fmt(item.get("horas"))])
    if len(act_rows) == 1:
        act_rows.append(["Sin datos", "—"])
    act_table = Table(act_rows, colWidths=[10.5 * cm, 5.5 * cm])
    act_table.setStyle(_style_kpi_table())
    story.append(act_table)

    story.append(Paragraph("6. Consolidado por sede", h2))
    sede_rows = [["Sede", "Carga", "Plantilla", "C/L", "IC horas", "IC crit."]]
    for item in payload.get("por_sede") or []:
        sede_rows.append(
            [
                Paragraph(pdf_xml(str(item.get("name_sede") or item.get("ID_sede") or "—")[:40]), small),
                _fmt(item.get("total_equipos"), 0),
                _fmt(item.get("equipos_plantilla"), 0),
                _fmt(item.get("equipos_comodato_leasing"), 0),
                _fmt(item.get("ingenieros_recomendados"), 0),
                _fmt(item.get("ingenieros_recomendados_dotacion"), 0),
            ]
        )
    if len(sede_rows) == 1:
        sede_rows.append(["Sin sedes", "—", "—", "—", "—", "—"])
    sede_table = Table(
        sede_rows,
        colWidths=[5.4 * cm, 2.1 * cm, 2.2 * cm, 1.6 * cm, 2.4 * cm, 2.3 * cm],
    )
    sede_table.setStyle(_style_kpi_table())
    story.append(sede_table)

    story.append(Paragraph("7. Recomendación", h2))
    story.append(
        Paragraph(
            "Contrastar el IC por horas (carga real, incluyendo apoyo en equipos "
            "tercerizados) con el IC por criticidad (solo parque propio). La brecha "
            "respecto al personal asignado a las sedes sirve de soporte para contratación, "
            "redistribución o tercerización controlada.",
            body,
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph("Documento generado automáticamente por SIGTB. Uso institucional.", small)
    )
    doc.build(story)
    return buffer.getvalue()

