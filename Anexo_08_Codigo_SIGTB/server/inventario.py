"""Reglas transversales de inventario: bodega/baja y datos del año activo.

No persiste ubicacion_logica: se deriva de codigo_ubicacion, ID_servicio,
name_servicio, ubicacion, estado y fecha_baja.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from server.inventory_enrichment import fold_text
from server.org_ubicacion import CATCHALL_CODES, CATALOGO_SANTA_CRUZ, normalize_ubicacion_code

HORAS_GESTION_DOCUMENTAL_BAJA = 0.5
MENSAJE_SIN_DATOS_ANIO = (
    "Este equipo no cuenta con datos de mantenimiento, visitas u otros "
    "registrados para el año actual."
)

CODIGOS_ALMACEN_GENERAL = frozenset(
    {
        code
        for code, item in CATALOGO_SANTA_CRUZ.items()
        if "ALMACEN" in fold_text(item.name_servicio)
    }
)
CODIGOS_BODEGA_BAJAS = frozenset(CATCHALL_CODES) | frozenset(
    {
        code
        for code, item in CATALOGO_SANTA_CRUZ.items()
        if "BODEGA" in fold_text(item.name_servicio) and "BAJA" in fold_text(item.name_servicio)
    }
) | {"399999"}
CODIGOS_BODEGA = CODIGOS_ALMACEN_GENERAL | CODIGOS_BODEGA_BAJAS

UBICACION_EN_SERVICIO = "en_servicio"
UBICACION_ALMACEN_GENERAL = "almacen_general"
UBICACION_BODEGA_BAJAS = "bodega_bajas"
UBICACION_BAJA = "baja"


def _get(row: Any, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in row.keys():
        return row[key]
    return default


def clamp_anio(value, default: int | None = None) -> int:
    today = date.today().year
    if value in (None, ""):
        return int(default if default is not None else today)
    try:
        anio = int(value)
    except (TypeError, ValueError):
        return int(default if default is not None else today)
    return max(2000, min(2100, anio))


def anio_de_fecha(value) -> int | None:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        if 2000 <= year <= 2100:
            return year
    return None


def _codigos_ubicacion(equipo: Any) -> list[str]:
    raw = [
        _get(equipo, "codigo_ubicacion"),
        _get(equipo, "ID_servicio"),
        _get(equipo, "id_servicio"),
    ]
    out = []
    for item in raw:
        code = normalize_ubicacion_code(item)
        if code:
            out.append(code)
    return out


def _textos_ubicacion(equipo: Any) -> str:
    parts = [
        _get(equipo, "name_servicio"),
        _get(equipo, "servicio"),
        _get(equipo, "ubicacion"),
        _get(equipo, "ubicacion_equipo"),
        _get(equipo, "bodega"),
        _get(equipo, "almacen_general"),
    ]
    return " ".join(str(p or "") for p in parts)


def ubicacion_logica(equipo: Any) -> str:
    """Clasificación derivada para UI y cálculos (no es columna SQL)."""
    folded = fold_text(_textos_ubicacion(equipo))
    codes = set(_codigos_ubicacion(equipo))
    if codes & CODIGOS_BODEGA_BAJAS or ("BODEGA" in folded and "BAJA" in folded):
        return UBICACION_BODEGA_BAJAS
    if codes & CODIGOS_ALMACEN_GENERAL or "ALMACEN GENERAL" in folded:
        return UBICACION_ALMACEN_GENERAL
    if _es_baja_por_estado(equipo):
        return UBICACION_BAJA
    return UBICACION_EN_SERVICIO


def is_en_bodega(equipo: Any) -> bool:
    return ubicacion_logica(equipo) in {UBICACION_BODEGA_BAJAS, UBICACION_ALMACEN_GENERAL}


def _es_baja_por_estado(equipo: Any) -> bool:
    estado = str(
        _get(equipo, "estado")
        or _get(equipo, "estado_equipo")
        or _get(equipo, "estado_inventario")
        or ""
    ).strip().upper().replace("Ó", "O")
    if estado in {"FUERA DE SERVICIO", "BAJA", "RETIRADO"}:
        return True
    if str(_get(equipo, "fecha_baja") or "").strip():
        return True
    return False


def is_equipo_baja(equipo: Any) -> bool:
    """Bodega de bajas / almacén general se asumen dados de baja."""
    if is_en_bodega(equipo):
        return True
    return _es_baja_por_estado(equipo)


def get_ultimo_mantenimiento(equipo: Any) -> dict | None:
    """Último preventivo, correctivo o visita (fecha más reciente conocida)."""
    stats = _get(equipo, "ejecucion_stats") or {}
    fecha = (
        _get(equipo, "ultimo_mantenimiento_fecha")
        or stats.get("ultima_ev")
        or stats.get("ultima_ev_all")
        or _get(equipo, "fecha_ultimo_pm")
    )
    if not fecha:
        return None
    texto = str(fecha).strip()[:19]
    year = anio_de_fecha(texto)
    if not year:
        return None
    return {"fecha": texto[:10], "anio": year}


def has_datos_en_anio(equipo: Any, anio: int, stats: dict | None = None) -> bool:
    """True si hay preventivo, correctivo o visita (o último PM) en ese año."""
    year = clamp_anio(anio)
    blob = stats if stats is not None else (_get(equipo, "ejecucion_stats") or {})
    if blob.get("anio_filtro") is not None:
        if int(blob.get("n_total") or 0) > 0:
            return True
    elif int(blob.get("n_total_anio") or 0) > 0:
        return True
    if anio_de_fecha(_get(equipo, "fecha_ultimo_pm")) == year:
        return True
    return False


def horas_mp_teoricas(equipo: Any) -> float:
    aplica = _get(equipo, "aplica_mp")
    if aplica in (None, "", 0, "0", False, "No", "NO", "no"):
        return 0.0
    if str(aplica).strip() in {"No", "NO", "no"}:
        return 0.0
    try:
        return float(_get(equipo, "freq_mp") or 0) * float(_get(equipo, "tiempo_mp") or 0)
    except (TypeError, ValueError):
        return 0.0


def get_horas_otras_tareas(equipo: Any, correctivo_pct: float | None = None) -> float:
    """Equivale al estimado de correctivo/visita/preventivo sin registros (L × %)."""
    if correctivo_pct is None:
        try:
            pct = float(_get(equipo, "correctivo_sin_historico") or 0.15)
        except (TypeError, ValueError):
            pct = 0.15
    else:
        try:
            pct = float(correctivo_pct)
        except (TypeError, ValueError):
            pct = 0.15
    return round(horas_mp_teoricas(equipo) * pct, 4)


def apply_flags_equipo(equipo: dict, stats: dict | None, anio: int) -> dict:
    """Anota flags de bodega/baja y alerta del año activo. No lanza."""
    year = clamp_anio(anio)
    stats = dict(stats or {})
    view = {**equipo, "ejecucion_stats": stats}
    equipo["anio_activo"] = year
    logica = ubicacion_logica(equipo)
    equipo["ubicacion_logica"] = logica
    equipo["en_bodega"] = logica in {UBICACION_BODEGA_BAJAS, UBICACION_ALMACEN_GENERAL}
    equipo["es_baja"] = is_equipo_baja(equipo)
    ultimo = get_ultimo_mantenimiento(view)
    equipo["ultimo_mantenimiento_fecha"] = ultimo["fecha"] if ultimo else None
    equipo["ultimo_mantenimiento_anio"] = ultimo["anio"] if ultimo else None
    has_year = has_datos_en_anio(view, year, stats)
    equipo["has_datos_anio"] = has_year
    equipo["alerta_sin_datos_anio"] = not has_year
    equipo["alerta_mensaje"] = MENSAJE_SIN_DATOS_ANIO if equipo["alerta_sin_datos_anio"] else ""
    return equipo


def attach_flags_lista(
    equipos: list[dict],
    resumen: dict | None,
    anio: int,
) -> None:
    """Enriquece una lista de equipos con una sola pasada del resumen de ejecución."""
    from server.frecuencia_pm import lookup_resumen_llave

    year = clamp_anio(anio)
    for eq in equipos or []:
        bio = (
            eq.get("num_biomedica")
            or eq.get("inv_num_biomedica")
            or eq.get("codigo_equipo")
            or eq.get("codigo")
        )
        act = eq.get("codigo_activo") or eq.get("inv_codigo_activo") or ""
        stats = lookup_resumen_llave(resumen or {}, bio, act)
        apply_flags_equipo(eq, stats, year)
