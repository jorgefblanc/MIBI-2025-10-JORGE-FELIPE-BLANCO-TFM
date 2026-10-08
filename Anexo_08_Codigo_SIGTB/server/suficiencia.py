"""Motor de cálculo de suficiencia de equipos (requerido, brecha y resultado)."""

from __future__ import annotations

import math
from typing import Any

from server.formula_versions import formula_meta
from server.inventario import is_en_bodega, is_equipo_baja

TIPOS_CALCULO_TFM = (
    "demanda",
    "concurrencia",
    "minimo",
    "mixto",
)

TIPOS_CALCULO_ALIASES = {
    "por_demanda": "demanda",
    "por_capacidad": "concurrencia",
    "por_sala_equipo": "concurrencia",
    "principal": "concurrencia",
    "minimo_tecnico": "minimo",
    "esterilizacion_rotacion": "demanda",
}

TIPOS_CALCULO = TIPOS_CALCULO_TFM + tuple(TIPOS_CALCULO_ALIASES.keys())

TIPOS_CALCULO_LABELS = {
    "demanda": "Por demanda",
    "concurrencia": "Por concurrencia",
    "minimo": "Mínimo técnico",
    "mixto": "Mixto",
    "por_capacidad": "Por capacidad (legado → concurrencia)",
    "por_demanda": "Por demanda (legado)",
    "minimo_tecnico": "Mínimo técnico (legado)",
    "por_sala_equipo": "Por sala/equipo (legado → concurrencia)",
    "principal": "Principal (legado → concurrencia)",
    "esterilizacion_rotacion": "Esterilización/rotación (legado → demanda)",
}

DEFAULT_PARAMS = {
    "utilizacion_segura": 0.75,
    "respaldo_general": 0.20,
    "umbral_alerta": 0.80,
    "redondeo": "CEIL",
}


def _f(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ceil_if(value: float, redondeo: str = "CEIL") -> float:
    if value is None:
        return 0.0
    if redondeo.upper() == "CEIL":
        return float(math.ceil(value - 1e-12)) if value > 0 else 0.0
    return float(value)


def normalize_estado(estado: str | None) -> str:
    """Estado en blanco ⇒ Operativo por defecto."""
    raw = (estado or "").strip().upper()
    if not raw:
        return "OPERATIVO"
    aliases = {
        "EN REPARACION": "EN REPARACIÓN",
        "EN REPARACIÓN": "EN REPARACIÓN",
        "EN MANTENIMIENTO": "EN MANTENIMIENTO",
        "FUERA DE SERVICIO": "FUERA DE SERVICIO",
        "PRESTADO": "PRESTADO",
        "BAJA": "BAJA",
        "PENDIENTE": "PENDIENTE",
        "OPERATIVO": "OPERATIVO",
    }
    return aliases.get(raw, raw)


def classify_estado(estado: str | None) -> str:
    e = normalize_estado(estado)
    if e == "OPERATIVO":
        return "operativo"
    if e in ("EN MANTENIMIENTO", "EN REPARACIÓN"):
        return "mantenimiento"
    if e in ("PRESTADO", "FUERA DE SERVICIO", "BAJA", "PENDIENTE"):
        return "prestado_nd"
    return "prestado_nd"


def summarize_inventario(rows) -> dict[str, dict[str, int]]:
    """Totales por tipo de equipo en un servicio (no cruza sedes)."""
    by_equipo: dict[str, dict[str, int]] = {}
    for row in rows:
        name = (row["equipo"] if hasattr(row, "keys") else row.get("equipo") or "").strip()
        if not name:
            continue
        bucket = by_equipo.setdefault(
            name,
            {
                "cantidad_total": 0,
                "cantidad_operativa": 0,
                "en_mantenimiento": 0,
                "prestado_nd": 0,
                "disponible_real": 0,
                "alerta_sin_datos_anio": False,
                "en_bodega": 0,
            },
        )
        bucket["cantidad_total"] += 1
        estado_raw = row["estado"] if hasattr(row, "keys") and "estado" in row.keys() else None
        if is_en_bodega(row) or is_equipo_baja(row):
            kind = "prestado_nd"
            bucket["en_bodega"] += 1
        else:
            kind = classify_estado(estado_raw)
        if kind == "operativo":
            bucket["cantidad_operativa"] += 1
        elif kind == "mantenimiento":
            bucket["en_mantenimiento"] += 1
        else:
            bucket["prestado_nd"] += 1
        alerta = False
        if isinstance(row, dict):
            alerta = bool(row.get("alerta_sin_datos_anio"))
        elif hasattr(row, "keys") and "alerta_sin_datos_anio" in row.keys():
            alerta = bool(row["alerta_sin_datos_anio"])
        if alerta:
            bucket["alerta_sin_datos_anio"] = True

    for bucket in by_equipo.values():
        # TFM: D = Σ Ii, Ii = 1 si operativo y del servicio evaluado.
        bucket["disponible_real"] = bucket["cantidad_operativa"]

    return by_equipo


def ocupacion_pct(capacidad_instalada, promedio_ocupado) -> float | None:
    """% ocupación = Promedio ocupado/simultáneo ÷ Capacidad instalada."""
    cap = _f(capacidad_instalada)
    prom = _f(promedio_ocupado)
    if cap is None or cap <= 0 or prom is None:
        return None
    return prom / cap


def concurrencia_pct(pacientes_simultaneos, capacidad_base) -> float | None:
    """
    % concurrencia corregido:
    pacientes/puestos simultáneos ÷ capacidad base del equipo en el servicio
    (cantidad en inventario / capacidad instalada del tipo).

    La fórmula propuesta (simultáneos ÷ suma de demanda+minutos+mínimo+respaldo)
    mezcla unidades incompatibles y se descarta.
    """
    sim = _f(pacientes_simultaneos)
    base = _f(capacidad_base)
    if sim is None or base is None or base <= 0:
        return None
    return sim / base


def acciones_para_resultado(resultado: str, brecha: float | None) -> str:
    if resultado == "Suficiente":
        return "Mantener mantenimiento preventivo y monitorear ocupación/concurrencia."
    if resultado == "Alerta":
        deficit = abs(brecha) if brecha is not None and brecha < 0 else 0
        extra = f" Evaluar {math.ceil(deficit)} unidad(es) adicional(es)." if deficit else ""
        return f"Priorizar disponibilidad y reducir indisponibilidad.{extra}"
    if resultado == "Insuficiente":
        deficit = abs(brecha) if brecha is not None and brecha < 0 else 0
        return (
            "Gap crítico: gestionar adquisición/redistribución"
            f"{f' de {math.ceil(deficit)} equipo(s)' if deficit else ''} "
            "y validar demanda asistencial."
        )
    if resultado == "Revisar":
        return "Verificar consistencia de datos asistenciales e inventario antes de decidir."
    return "Complete datos del servicio y matriz de demanda (rol asistencial) para evaluar."


def clasificar_resultado(
    disponible: float | None,
    requerido_final: float | None,
    umbral_alerta: float = 0.80,
    inconsistente: bool = False,
) -> tuple[str, float | None, float | None]:
    if inconsistente:
        return "Revisar", None, None
    if disponible is None or requerido_final is None:
        return "No evaluado", None, None
    if requerido_final <= 0:
        return "Revisar", None, None

    brecha = disponible - requerido_final
    suf = disponible / requerido_final
    if suf >= 1.0:
        return "Suficiente", brecha, suf
    if suf >= umbral_alerta:
        return "Alerta", brecha, suf
    return "Insuficiente", brecha, suf


def modo_tfm(tipo_calculo: str | None) -> str:
    tipo = (tipo_calculo or "mixto").strip().lower()
    return TIPOS_CALCULO_ALIASES.get(tipo, tipo if tipo in TIPOS_CALCULO_TFM else "mixto")


def calcular_evaluacion(
    *,
    tipo_calculo: str,
    pacientes_simultaneos=None,
    demanda_diaria=None,
    tiempo_uso_min=None,
    tiempo_uso_horas=None,
    minimo_tecnico=None,
    respaldo_especifico=None,
    horas_servicio_dia=None,
    capacidad_instalada=None,
    promedio_ocupado=None,
    inventario: dict[str, int] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = {**DEFAULT_PARAMS, **(params or {})}
    tipo = (tipo_calculo or "mixto").strip().lower()
    if tipo not in TIPOS_CALCULO:
        tipo = "mixto"
    modo = modo_tfm(tipo)

    inv = inventario or {}
    cant_total = int(inv.get("cantidad_total") or 0)
    cant_op = int(inv.get("cantidad_operativa") or 0)
    cant_mant = int(inv.get("en_mantenimiento") or 0)
    cant_prest = int(inv.get("prestado_nd") or inv.get("prestado") or 0)
    # D = Σ Ii (equipos operativos del servicio).
    disponible_real = max(0, cant_op)

    capacidad_base_auto = float(cant_total) if cant_total > 0 else _f(capacidad_instalada)
    ocup = ocupacion_pct(capacidad_instalada, promedio_ocupado)
    puestos_ocupados_auto = _f(promedio_ocupado)

    horas = _f(horas_servicio_dia)
    util = _f(params.get("utilizacion_segura"), 0.75) or 0.75
    umbral = _f(params.get("umbral_alerta"), 0.80) or 0.80
    respaldo_pct = _f(params.get("respaldo_general"), 0.20)
    if respaldo_pct is None:
        respaldo_pct = 0.20
    redondeo = str(params.get("redondeo") or "CEIL")

    pac = _f(pacientes_simultaneos)
    dem = _f(demanda_diaria)
    tmin = _f(tiempo_uso_min)
    th_in = _f(tiempo_uso_horas)
    minimo = _f(minimo_tecnico, 0.0) or 0.0
    respaldo_esp = max(0.0, _f(respaldo_especifico, 0.0) or 0.0)

    conc = concurrencia_pct(pac, capacidad_base_auto)

    motivos: list[str] = []
    inconsistente = False
    if ocup is not None and (ocup < 0 or ocup > 2):
        inconsistente = True
        motivos.append("ocupación fuera de rango")
    if dem is not None and dem < 0:
        inconsistente = True
        motivos.append("demanda negativa")
    if tmin is not None and tmin < 0:
        inconsistente = True
        motivos.append("tiempo de uso negativo")
    if pac is not None and pac < 0:
        inconsistente = True
        motivos.append("concurrencia negativa")

    tiempo_uso_h = None
    if th_in is not None and th_in > 0:
        tiempo_uso_h = th_in
    elif tmin is not None and tmin > 0:
        tiempo_uso_h = tmin / 60.0

    if tiempo_uso_h is not None and horas is not None and tiempo_uso_h > horas:
        inconsistente = True
        motivos.append("unidad incompatible: t > H")

    # Ceq = (H · u) / t
    capacidad_por_equipo = None
    if horas is not None and horas > 0 and tiempo_uso_h and tiempo_uso_h > 0 and util > 0:
        capacidad_por_equipo = (horas * util) / tiempo_uso_h

    req_demanda = None
    if dem is not None and capacidad_por_equipo and capacidad_por_equipo > 0:
        req_demanda = _ceil_if(dem / capacidad_por_equipo, redondeo)

    # Rc = ⌈Q⌉
    req_concurrencia = _ceil_if(pac, redondeo) if pac is not None else None
    req_capacidad = req_concurrencia
    req_min = _ceil_if(minimo, redondeo) if minimo > 0 else None

    if modo == "demanda":
        candidatos = [req_demanda] if req_demanda is not None else []
        if not candidatos:
            inconsistente = True
            motivos.append("faltan H, u, t o P para Rd")
    elif modo == "concurrencia":
        candidatos = [req_concurrencia] if req_concurrencia is not None else []
        if not candidatos:
            inconsistente = True
            motivos.append("falta Q para Rc")
    elif modo == "minimo":
        candidatos = [req_min] if req_min is not None else []
        if not candidatos:
            inconsistente = True
            motivos.append("falta Rm")
    else:
        candidatos = [v for v in (req_demanda, req_concurrencia, req_min) if v is not None]
        if not candidatos:
            inconsistente = True
            motivos.append("ningún requerido parcial aplicable")

    fmeta = formula_meta("suficiencia")
    empty = {
        "tipo_calculo": tipo,
        "modo_tfm": modo,
        "capacidad_base_auto": capacidad_base_auto,
        "ocupacion_pct": ocup,
        "puestos_ocupados_auto": puestos_ocupados_auto,
        "pacientes_simultaneos": pac,
        "concurrencia_pct": conc,
        "demanda_diaria": dem,
        "tiempo_uso_min": tmin,
        "tiempo_uso_horas": tiempo_uso_h,
        "horas_servicio_dia": horas,
        "utilizacion_segura": util,
        "minimo_tecnico": minimo,
        "respaldo_pct": respaldo_pct,
        "cantidad_total": cant_total,
        "cantidad_operativa": cant_op,
        "en_mantenimiento": cant_mant,
        "prestado_nd": cant_prest,
        "disponible_real": disponible_real,
        "inventario_disponible": disponible_real,
        "capacidad_por_equipo": capacidad_por_equipo,
        "req_capacidad": req_capacidad,
        "req_concurrencia": req_concurrencia,
        "req_demanda": req_demanda,
        "req_minimo": req_min,
        "requerido_base": None,
        "respaldo_unidades": respaldo_esp,
        "requerido_final": None,
        "brecha": None,
        "suficiencia_pct": None,
        "resultado": "Revisar" if inconsistente else "No evaluado",
        "motivo_revisar": "; ".join(motivos) if motivos else None,
        "acciones_sugeridas": acciones_para_resultado(
            "Revisar" if inconsistente else "No evaluado", None
        ),
        **fmeta,
    }

    if inconsistente or not candidatos:
        return empty

    # Rb = Rd | Rc | Rm | max(Rd, Rc, Rm)
    requerido_base = _ceil_if(max(candidatos), redondeo)
    # Rfinal = ⌈Rb · (1+b)⌉ + Re
    requerido_final = _ceil_if(requerido_base * (1.0 + respaldo_pct), redondeo) + respaldo_esp
    respaldo_unidades = requerido_final - requerido_base

    resultado, brecha, suf = clasificar_resultado(
        float(disponible_real),
        requerido_final,
        umbral_alerta=umbral,
        inconsistente=False,
    )

    return {
        **empty,
        "req_capacidad": req_capacidad,
        "req_concurrencia": req_concurrencia,
        "req_demanda": req_demanda,
        "requerido_base": requerido_base,
        "respaldo_unidades": respaldo_unidades,
        "requerido_final": requerido_final,
        "brecha": brecha,
        "suficiencia_pct": suf,
        "resultado": resultado,
        "motivo_revisar": None,
        "acciones_sugeridas": acciones_para_resultado(resultado, brecha),
    }
