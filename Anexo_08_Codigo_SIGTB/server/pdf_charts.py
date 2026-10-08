"""Gráficas vectoriales para informes PDF (torta + barras con tendencia)."""

from __future__ import annotations

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Table, TableStyle

PALETTE = [
    colors.HexColor("#0074D9"),
    colors.HexColor("#005BB5"),
    colors.HexColor("#FF851B"),
    colors.HexColor("#10B981"),
    colors.HexColor("#7C3AED"),
    colors.HexColor("#EF4444"),
    colors.HexColor("#0EA5E9"),
]

_TITLE = ParagraphStyle(
    "SigtbChartTitle",
    fontName="Helvetica-Bold",
    fontSize=8.5,
    textColor=colors.HexColor("#1f4f46"),
    leading=11,
    spaceAfter=2,
)


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clean_items(items: list | None, limit: int = 10) -> list[tuple[str, float]]:
    rows = []
    for item in items or []:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or "—")
            value = _num(item.get("value") if "value" in item else item.get("horas"))
        elif isinstance(item, (list, tuple)) and item:
            label = str(item[0] if item[0] is not None else "—")
            value = _num(item[1] if len(item) > 1 else 0)
        else:
            continue
        if value > 0:
            rows.append((label[:28], value))
        if len(rows) >= limit:
            break
    return rows


def _color_for(label: str, idx: int):
    key = (label or "").lower()
    if any(w in key for w in ("ge ≥ 19", "ge >= 19", "≥ 19")):
        return colors.HexColor("#9F1239")
    if "15" in key and "19" in key:
        return colors.HexColor("#EA580C")
    if "12" in key and "15" in key:
        return colors.HexColor("#CA8A04")
    if "ge < 12" in key or "ge <12" in key:
        return colors.HexColor("#0F766E")
    if any(w in key for w in ("alto", "alta", "rojo", "insuf", "no cumple", "crític", "critic")):
        return colors.HexColor("#EF4444")
    if any(w in key for w in ("medio", "amarillo", "alerta", "pendiente")):
        return colors.HexColor("#FF851B")
    if any(w in key for w in ("bajo", "baja", "verde", "suficiente", "aprob", "cumple")):
        return colors.HexColor("#10B981")
    return PALETTE[idx % len(PALETTE)]


def pie_drawing(items: list | None, width: float = 230, height: float = 150) -> Drawing:
    rows = _clean_items(items, 8)
    d = Drawing(width, height)
    cx, cy, r = 62, 78, 48
    total = sum(v for _, v in rows) or 1
    if not rows:
        d.add(Circle(cx, cy, r, fillColor=colors.HexColor("#E5E7EB"), strokeColor=None))
        d.add(String(118, 72, "Sin datos", fontSize=8, fillColor=colors.HexColor("#6b7280")))
        return d
    if len(rows) == 1:
        d.add(Circle(cx, cy, r, fillColor=_color_for(rows[0][0], 0), strokeColor=None))
    else:
        start = 90.0
        for idx, (label, value) in enumerate(rows):
            sweep = 360.0 * value / total
            end = start - sweep
            d.add(
                Wedge(
                    cx,
                    cy,
                    r,
                    end,
                    start,
                    fillColor=_color_for(label, idx),
                    strokeColor=colors.white,
                    strokeWidth=0.6,
                )
            )
            start = end
    legend_x = 118
    legend_y = height - 22
    for idx, (label, value) in enumerate(rows):
        pct = 100.0 * value / total
        y = legend_y - idx * 16
        d.add(Rect(legend_x, y - 2, 8, 8, fillColor=_color_for(label, idx), strokeColor=None))
        d.add(
            String(
                legend_x + 12,
                y,
                f"{label[:18]}  {value:.0f} ({pct:.0f}%)",
                fontSize=7,
                fillColor=colors.HexColor("#1f2a2e"),
            )
        )
    return d


def bar_trend_drawing(items: list | None, width: float = 260, height: float = 150) -> Drawing:
    rows = _clean_items(items, 10)
    d = Drawing(width, height)
    pad_l, pad_r, pad_t, pad_b = 28, 8, 12, 32
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b
    axis = colors.HexColor("#D1D5DB")
    d.add(Line(pad_l, pad_t, pad_l, pad_t + inner_h, strokeColor=axis, strokeWidth=0.7))
    d.add(
        Line(
            pad_l,
            pad_t + inner_h,
            width - pad_r,
            pad_t + inner_h,
            strokeColor=axis,
            strokeWidth=0.7,
        )
    )
    if not rows:
        d.add(String(pad_l + 8, pad_t + inner_h / 2, "Sin datos", fontSize=8, fillColor=colors.HexColor("#6b7280")))
        return d
    vals = [v for _, v in rows]
    vmax = max(vals) or 1
    n = len(rows)
    gap = 5
    bar_w = max(8, (inner_w - gap * (n + 1)) / n)
    xs = []
    ys = []
    for i, (label, value) in enumerate(rows):
        bh = (value / vmax) * inner_h
        x = pad_l + gap + i * (bar_w + gap)
        y = pad_t + inner_h - bh
        d.add(
            Rect(
                x,
                y,
                bar_w,
                max(bh, 1),
                fillColor=_color_for(label, i),
                strokeColor=None,
            )
        )
        d.add(
            String(
                x + bar_w / 2,
                8,
                label[:9],
                fontSize=6,
                textAnchor="middle",
                fillColor=colors.HexColor("#6b7280"),
            )
        )
        xs.append(x + bar_w / 2)
        ys.append(value)
    if n >= 2:
        sum_x = sum(range(n))
        sum_y = sum(ys)
        sum_xy = sum(i * ys[i] for i in range(n))
        sum_x2 = sum(i * i for i in range(n))
        den = n * sum_x2 - sum_x * sum_x
        slope = (n * sum_xy - sum_x * sum_y) / den if den else 0
        intercept = (sum_y - slope * sum_x) / n
        pts = []
        for i in range(n):
            tv = intercept + slope * i
            pts.append((xs[i], pad_t + inner_h - (tv / vmax) * inner_h))
        d.add(
            PolyLine(
                pts,
                strokeColor=colors.HexColor("#111827"),
                strokeWidth=1.4,
                strokeDashArray=[4, 3],
            )
        )
    return d


def charts_table(
    pie_title: str,
    pie_items: list | None,
    bar_title: str,
    bar_items: list | None,
) -> Table:
    """Dos gráficas lado a lado para informes de ingeniería."""
    table = Table(
        [
            [Paragraph(pie_title, _TITLE), Paragraph(bar_title, _TITLE)],
            [pie_drawing(pie_items), bar_trend_drawing(bar_items)],
        ],
        colWidths=[8.3 * cm, 8.3 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fbfa")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5e3de")),
            ]
        )
    )
    return table
