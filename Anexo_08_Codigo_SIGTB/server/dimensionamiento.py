"""Motor de cálculo: Dimensionamiento de Personal de Ingeniería Clínica.

Réplica fiel de las fórmulas del Excel
Instrumento_Final_Dimensionamiento_Personal_Ingenieria_Clinica_850.xlsx
(hojas Parametros, Inventario_850, Resumen, Dashboard, Informe_Exportable).
"""

from __future__ import annotations

import math
from typing import Any

from server.adquisicion import (
    CATALOGO_FORMA_ADQUISICION,
    canon_forma_adquisicion,
    mp_forzado_por_adquisicion,
)

# —— Catálogos (hoja Catalogos) ——
CATALOGO_SI_NO = ["Sí", "No"]
CATALOGO_CRITICIDAD = ["Bajo", "Medio", "Alto"]
CRITICIDAD_LEGACY_A_ALTO = frozenset(
    {"soporte vital", "soporte-vital", "vital", "especializado", "especializados"}
)

DEFAULT_EQUIPOS_POR_IC = {
    "Bajo": 70.0,
    "Medio": 50.0,
    "Alto": 20.0,
}
CATALOGO_SERVICIOS = [
    "UCI Adulto",
    "Urgencias",
    "Cirugía",
    "Hospitalización",
    "Laboratorio Clínico",
    "Imagenología",
    "Consulta Externa",
    "Esterilización",
    "Farmacia",
    "Neonatos",
    "UCI Pediátrica",
]
CATALOGO_EQUIPOS = [
    "Ventilador mecánico",
    "Monitor multiparámetro",
    "Bomba de infusión",
    "Desfibrilador",
    "Máquina de anestesia",
    "Electrobisturí",
    "Incubadora neonatal",
    "Autoclave",
    "Báscula médica",
    "Tensiómetro digital",
    "Lámpara cialítica",
    "Ecógrafo",
    "Electrocardiógrafo",
    "Aspirador quirúrgico",
    "Cama hospitalaria eléctrica",
    "Termohigrómetro",
    "Cabina bioseguridad",
    "Refrigerador biomédico",
]

DEFAULT_PARAMS = {
    "horas_semana": 42.0,
    "semanas_anio": 52.0,
    "vacaciones_h": 132.0,
    "festivos_h": 88.0,
    "permisos_h": 80.0,
    "productividad": 0.7,
    "correctivo_sin_historico": 0.15,
    "contingencia": 0.15,
    "perfil": "Ingeniero Clínico",
}

# Ayudas contextuales (Instructivo + observaciones Parametros / campos Inventario)
TOOLTIPS = {
    "objetivo": (
        "Calcular la carga anual de trabajo y estimar cuántos Ingenieros Clínicos "
        "se requieren para cubrir actividades programadas, correctivas y adicionales."
    ),
    "parametros": (
        "Estos parámetros afectan directamente la disponibilidad anual del personal."
    ),
    "horas_semana": "Modificar según jornada laboral institucional. Ejemplo: 42 h/semana.",
    "semanas_anio": "Base anual típica: 52 semanas.",
    "vacaciones_h": "Ejemplo: 15 días hábiles × 8,8 h = 132 h/año.",
    "festivos_h": "Puede ajustarse según país/calendario institucional.",
    "permisos_h": "Tiempo no disponible para ejecución técnica (reuniones, permisos, capacitaciones).",
    "productividad": (
        "Fracción del tiempo realmente disponible para actividades del proceso "
        "(ej. 0,70 = 70%)."
    ),
    "correctivo_sin_historico": (
        "Si no existe histórico, el sistema estima correctivos automáticamente "
        "según este parámetro institucional (por defecto 15% de horas de MP)."
    ),
    "contingencia": (
        "Margen para imprevistos, ausencias, reprocesos y picos de carga "
        "(por defecto 15% sobre horas base)."
    ),
    "horas_nominales": "Horas laborales brutas antes de descuentos = horas/semana × semanas/año.",
    "horas_disponibles": "Horas nominales menos vacaciones, festivos y permisos.",
    "horas_efectivas": "Horas disponibles ajustadas × productividad efectiva.",
    "catalogos": (
        "Catálogos institucionales para estandarizar la clasificación de equipos y servicios."
    ),
    "inventario": (
        "Equipos agrupados por descripción. Si un equipo no tiene MP/Cal/Val, "
        "el cálculo reutiliza en memoria los datos de otro con la misma descripción "
        "(sin guardarlos en la BD de los demás). Se muestra la cantidad y el "
        "acumulado de horas/año del grupo."
    ),
    "criticidad": (
        "Clasificación de criticidad del equipo: Bajo, Medio o Alto. "
        "Si marca Alto, indique si es por único equipo en el área, por alta complejidad "
        "(especializado / soporte vital) o por ambos. Solo único en el área usa el ratio "
        "de criticidad media; especializado o ambos usan el de alta."
    ),
    "aplica_mp": "Indique Sí si el equipo tiene mantenimiento preventivo programado.",
    "freq_mp": "Número de veces que se realiza mantenimiento preventivo al equipo en un año.",
    "tiempo_mp": "Tiempo promedio en horas de cada intervención de MP.",
    "horas_mp": "Horas MP/año = frecuencia × tiempo (si aplica MP).",
    "aplica_cal": "Indique Sí si el equipo requiere calibración.",
    "freq_cal": "Frecuencia anual de calibración.",
    "tiempo_cal": "Tiempo promedio en horas de cada calibración.",
    "aplica_val": "Indique Sí si el equipo requiere validación / control de calidad.",
    "freq_val": "Frecuencia anual de validación / control de calidad.",
    "tiempo_val": "Tiempo promedio en horas de cada validación / control de calidad.",
    "tercerizado": (
        "Marque Sí si la ejecución de esta actividad se realiza mediante un "
        "servicio tercerizado. Freq/año y Tiempo pasan a 0 y no suman carga "
        "al personal interno de Ingeniería Clínica. Si el equipo está en "
        "Comodato o Leasing, MP queda forzado como Sí / tercerizado (ejecuta un tercero)."
    ),
    "forma_adquisicion": (
        "Comodato y Leasing: el MP y el correctivo estimado se asumen tercerizados "
        "(no alimentan el IC por carga horaria). Otras actividades y correctivos de "
        "apoyo (histórico) sí pueden sumar. No entran en el IC por criticidad. "
        "Si el dato falta o dice No especifica, se genera una solicitud en bandeja."
    ),
    "aplica_cap": "Indique Sí si se realiza capacitación asociada al equipo.",
    "freq_cap": "Frecuencia anual de capacitación.",
    "tiempo_cap": "Tiempo promedio en horas de cada capacitación.",
    "tiene_historico": (
        "Histórico de correctivos solo con duración verificable "
        "(fecha de cierre − fecha de atención). Si hay MC o visita sin esas fechas, "
        "se mantiene el % institucional sobre horas de MP."
    ),
    "historico_correctivo": (
        "Horas anuales = suma de (cierre − atención) de MC y visitas. "
        "Sin ambas fechas no se asigna hora."
    ),
    "horas_correctivo": (
        "Si hay duración verificable se usa ese histórico; si no, el estimado "
        "institucional sobre horas de MP."
    ),
    "gestion_documental": (
        "Horas/año de hojas de vida, certificados, CMMS y registros. "
        "En esta sección se muestran por lote (mismo tipo de equipo)."
    ),
    "acompanamiento": (
        "Horas/año de entrega/recepción, coordinación, revisión de informes y cierre de evidencias."
    ),
    "otras_tareas": "Proyectos, auditorías, formación y tareas especiales (h/año).",
    "total_equipo": "Carga total anual generada por cada equipo biomédico.",
    "resumen": "Suma de horas por actividad, servicio e institución.",
    "ingenieros_requeridos": (
        "El instrumento calcula cuántos Ingenieros Clínicos se requieren "
        "para cubrir toda la carga anual."
    ),
    "dashboard": "Vista ejecutiva para análisis rápido de carga y necesidades.",
    "dashboard_empresa": (
        "Resumen de todas las sedes: carga horaria consolidada y plantilla por criticidad. "
        "Comodato/Leasing no entran al IC por criticidad; en horas no suman MP ni el "
        "correctivo estimado, pero sí otras actividades o correctivos de apoyo. "
        "El personal actual son ingenieros y técnicos asignados a esas sedes."
    ),
    "alto_unico_area": (
        "Marque si la criticidad alta se debe a que es el único equipo del área "
        "(escasez), no a su complejidad. En la plantilla se aplica el ratio de criticidad media."
    ),
    "alto_especializado": (
        "Marque si es equipo de alta complejidad, soporte vital o especializado. "
        "Usa el ratio de criticidad alta. Si también es único en el área, prevalece este criterio."
    ),
    "equipos_ic_bajo": "Equipos de baja criticidad asignados a 1 ingeniero clínico (por defecto 70).",
    "equipos_ic_medio": "Equipos de criticidad media asignados a 1 ingeniero clínico (por defecto 50).",
    "equipos_ic_alto": (
        "Equipos de alta criticidad, soporte vital o especializados asignados "
        "a 1 ingeniero clínico (por defecto 20)."
    ),
    "informe": "Informe listo para presentar a gerencia.",
    "manual_sin_historico": (
        "Ningún equipo con esta descripción tiene datos históricos. Ingrese la "
        "frecuencia y el tiempo promedio. El sistema usará estos valores en el "
        "cálculo para todas las unidades del grupo (sin copiarlos a la BD de las demás)."
    ),
}


def _f(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool_si(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in ("sí", "si", "yes", "true", "1", "s")


def normalize_criticidad(value) -> str:
    """Unifica el catálogo a Bajo / Medio / Alto. Soporte vital pasa a Alto."""
    raw = str(value or "").strip()
    if not raw:
        return "Medio"
    fold = raw.casefold()
    if fold in CRITICIDAD_LEGACY_A_ALTO or "vital" in fold or "especializ" in fold:
        return "Alto"
    for nivel in CATALOGO_CRITICIDAD:
        if fold == nivel.casefold() or fold.startswith(nivel.casefold()):
            return nivel
    if "alto" in fold or "alta" in fold:
        return "Alto"
    if "bajo" in fold or "baja" in fold:
        return "Bajo"
    if "med" in fold:
        return "Medio"
    return "Medio"


def ratios_desde_params(params: dict[str, Any] | None) -> dict[str, float]:
    src = params or {}
    return {
        "Bajo": max(_f(src.get("equipos_ic_bajo"), DEFAULT_EQUIPOS_POR_IC["Bajo"]), 1.0),
        "Medio": max(_f(src.get("equipos_ic_medio"), DEFAULT_EQUIPOS_POR_IC["Medio"]), 1.0),
        "Alto": max(_f(src.get("equipos_ic_alto"), DEFAULT_EQUIPOS_POR_IC["Alto"]), 1.0),
    }


def criticidad_para_plantilla(fila: dict[str, Any]) -> str:
    """Alto por único en el área usa ratio medio; especializado o ambos usan alto."""
    crit = normalize_criticidad(fila.get("criticidad"))
    if crit != "Alto":
        return crit
    if _as_bool_si(fila.get("alto_especializado")):
        return "Alto"
    if _as_bool_si(fila.get("alto_unico_area")):
        return "Medio"
    return "Alto"


def etiqueta_forma_adquisicion(value) -> str:
    canon = canon_forma_adquisicion(value)
    return canon or "Sin especificar"


def es_parque_tercerizado(fila: dict[str, Any] | None) -> bool:
    """Comodato/Leasing: fuera del campo de acción del IC para plantilla."""
    return mp_forzado_por_adquisicion((fila or {}).get("forma_adquisicion"))


def equipo_en_plantilla(fila: dict[str, Any] | None) -> bool:
    """Dotación propia (no baja, no Comodato/Leasing) que alimenta el IC por criticidad."""
    src = fila or {}
    if not src.get("en_dotacion", True):
        return False
    return not es_parque_tercerizado(src)


def calc_por_adquisicion(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conteo de equipos y horas de carga según forma de adquisición."""
    order = list(CATALOGO_FORMA_ADQUISICION) + ["Sin especificar"]
    buckets: dict[str, dict[str, Any]] = {
        label: {
            "forma_adquisicion": label,
            "equipos": 0,
            "horas": 0.0,
            "en_plantilla": 0,
            "fuera_plantilla": 0,
        }
        for label in order
    }
    for fila in filas:
        if not fila.get("en_dotacion", True):
            continue
        label = etiqueta_forma_adquisicion(fila.get("forma_adquisicion"))
        if label not in buckets:
            buckets[label] = {
                "forma_adquisicion": label,
                "equipos": 0,
                "horas": 0.0,
                "en_plantilla": 0,
                "fuera_plantilla": 0,
            }
        buckets[label]["equipos"] += 1
        buckets[label]["horas"] += _f(fila.get("total_horas"))
        if equipo_en_plantilla(fila):
            buckets[label]["en_plantilla"] += 1
        else:
            buckets[label]["fuera_plantilla"] += 1
    extra = [k for k in buckets if k not in order]
    return [buckets[k] for k in order + extra if buckets[k]["equipos"]]


def calc_ic_por_dotacion(
    filas: list[dict[str, Any]],
    ratios: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Plantilla por criticidad: IC = equipos / (equipos por ingeniero)."""
    ratios = ratios or DEFAULT_EQUIPOS_POR_IC
    counts = {nivel: 0 for nivel in CATALOGO_CRITICIDAD}
    alto_unico_como_medio = 0
    alto_especializado = 0
    for fila in filas:
        if not equipo_en_plantilla(fila):
            continue
        nivel = criticidad_para_plantilla(fila)
        counts[nivel] += 1
        if normalize_criticidad(fila.get("criticidad")) == "Alto":
            if nivel == "Medio":
                alto_unico_como_medio += 1
            else:
                alto_especializado += 1

    detalle = []
    ic_decimal = 0.0
    ic_techo = 0.0
    for nivel in CATALOGO_CRITICIDAD:
        n = counts[nivel]
        ratio = max(_f(ratios.get(nivel), DEFAULT_EQUIPOS_POR_IC[nivel]), 1.0)
        bruto = n / ratio if ratio else 0.0
        techo = float(math.ceil(bruto - 1e-12)) if n else 0.0
        ic_decimal += bruto
        ic_techo += techo
        detalle.append(
            {
                "criticidad": nivel,
                "equipos": n,
                "equipos_por_ic": ratio,
                "ingenieros": bruto,
                "ingenieros_recomendados": techo,
            }
        )

    # TFM: Nc = ⌈Σ(Ek / rk)⌉  (un solo techo sobre la suma, no la suma de techos).
    nc_final = float(math.ceil(ic_decimal - 1e-12)) if ic_decimal > 0 else 0.0

    por_tipo: dict[str, dict[str, Any]] = {}
    for fila in filas:
        if not equipo_en_plantilla(fila):
            continue
        nombre = (fila.get("equipo") or "Sin equipo").strip() or "Sin equipo"
        crit = criticidad_para_plantilla(fila)
        bucket = por_tipo.setdefault(
            nombre,
            {"equipo": nombre, "equipos": 0, "criticidad": crit, "counts": {n: 0 for n in CATALOGO_CRITICIDAD}},
        )
        bucket["equipos"] += 1
        bucket["counts"][crit] += 1

    tipos = []
    for bucket in por_tipo.values():
        crit = max(bucket["counts"], key=lambda k: bucket["counts"][k])
        ratio = max(_f(ratios.get(crit), DEFAULT_EQUIPOS_POR_IC[crit]), 1.0)
        n = bucket["equipos"]
        bruto = n / ratio
        tipos.append(
            {
                "equipo": bucket["equipo"],
                "equipos": n,
                "criticidad": crit,
                "equipos_por_ic": ratio,
                "ingenieros": bruto,
                "ingenieros_recomendados": float(math.ceil(bruto - 1e-12)) if n else 0.0,
            }
        )
    tipos.sort(key=lambda x: (-x["equipos"], x["equipo"]))

    return {
        "por_criticidad_dotacion": detalle,
        "por_tipo_equipo": tipos,
        "total_equipos_dotacion": sum(counts.values()),
        "equipos_fuera_plantilla": sum(
            1 for f in filas if f.get("en_dotacion", True) and es_parque_tercerizado(f)
        ),
        "ingenieros_por_dotacion": ic_decimal,
        "ingenieros_recomendados_dotacion": nc_final,
        "ingenieros_recomendados_dotacion_suma_techos": ic_techo,
        "alto_unico_como_medio": alto_unico_como_medio,
        "alto_especializado": alto_especializado,
    }


def calc_parametros(params: dict[str, Any]) -> dict[str, float | str]:
    """Réplica exacta de Parametros!B11:B13."""
    horas_semana = _f(params.get("horas_semana"), DEFAULT_PARAMS["horas_semana"])
    semanas_anio = _f(params.get("semanas_anio"), DEFAULT_PARAMS["semanas_anio"])
    vacaciones_h = _f(params.get("vacaciones_h"), DEFAULT_PARAMS["vacaciones_h"])
    festivos_h = _f(params.get("festivos_h"), DEFAULT_PARAMS["festivos_h"])
    permisos_h = _f(params.get("permisos_h"), DEFAULT_PARAMS["permisos_h"])
    productividad = _f(params.get("productividad"), DEFAULT_PARAMS["productividad"])
    correctivo_pct = _f(
        params.get("correctivo_sin_historico"),
        DEFAULT_PARAMS["correctivo_sin_historico"],
    )
    contingencia = _f(params.get("contingencia"), DEFAULT_PARAMS["contingencia"])

    horas_nominales = horas_semana * semanas_anio
    horas_disponibles_brutas = horas_nominales - vacaciones_h - festivos_h - permisos_h
    # TFM: Hdisp = (Hnom − Hvac − Hfest − Hperm) · p  ≡ horas_efectivas
    horas_disponibles = horas_disponibles_brutas
    horas_efectivas = horas_disponibles_brutas * productividad

    return {
        "horas_semana": horas_semana,
        "semanas_anio": semanas_anio,
        "vacaciones_h": vacaciones_h,
        "festivos_h": festivos_h,
        "permisos_h": permisos_h,
        "productividad": productividad,
        "correctivo_sin_historico": correctivo_pct,
        "contingencia": contingencia,
        "horas_nominales": horas_nominales,
        "horas_disponibles": horas_disponibles,
        "horas_disponibles_brutas": horas_disponibles_brutas,
        "h_disp": horas_efectivas,
        "horas_efectivas": horas_efectivas,
        "perfil": params.get("perfil") or DEFAULT_PARAMS["perfil"],
    }


def horas_actividad(aplica, frecuencia, tiempo, tercerizado=False) -> float:
    """IF(aplica="Sí", freq*tiempo, 0). Si es servicio tercerizado, no suma carga IC."""
    if not _as_bool_si(aplica):
        return 0.0
    if _as_bool_si(tercerizado):
        return 0.0
    return _f(frecuencia) * _f(tiempo)


def horas_actividad_teorica(aplica, frecuencia, tiempo) -> float:
    """Horas brutas sin descontar tercerización (solo referencia)."""
    if not _as_bool_si(aplica):
        return 0.0
    return _f(frecuencia) * _f(tiempo)


def horas_correctivo(
    tiene_historico,
    historico_h,
    horas_mp: float,
    correctivo_pct: float,
) -> float:
    """
    AA = IF(Y="Sí", IF(Z="",0,Z), L*Parametros!$B$9)
    """
    if _as_bool_si(tiene_historico):
        if historico_h is None or historico_h == "":
            return 0.0
        return _f(historico_h, 0.0)
    return horas_mp * _f(correctivo_pct)


def equipo_excluido_dotacion(row: dict) -> bool:
    """Bajas, fuera de servicio y bodegas no entran a la plantilla de la sede."""
    from server.inventario import is_equipo_baja

    return is_equipo_baja(row)


def _fila_excluida_cero(motivo: str) -> dict[str, float | bool | str]:
    return {
        "horas_mp": 0.0,
        "horas_cal": 0.0,
        "horas_val": 0.0,
        "horas_cap": 0.0,
        "horas_correctivo": 0.0,
        "gestion_documental_h": 0.0,
        "acompanamiento_h": 0.0,
        "otras_tareas_h": 0.0,
        "total_horas": 0.0,
        "en_dotacion": False,
        "en_plantilla": False,
        "motivo_exclusion": motivo,
        "incluye_horas_baja": False,
    }


def _fila_bodega_anio(row: dict[str, Any], correctivo_pct: float, anio: int) -> dict[str, float | bool | str]:
    """Horas especiales de bodega: 0,5 h documentales + otras (estimado sin datos) solo en el año del último evento."""
    from server.inventario import (
        HORAS_GESTION_DOCUMENTAL_BAJA,
        get_horas_otras_tareas,
        get_ultimo_mantenimiento,
        is_en_bodega,
    )

    base = _fila_excluida_cero("bodega_baja" if is_en_bodega(row) else "baja")
    if not is_en_bodega(row):
        return base
    ultimo = get_ultimo_mantenimiento(row)
    if not ultimo or int(ultimo["anio"]) != int(anio):
        return base
    otras = get_horas_otras_tareas(row, correctivo_pct)
    gestion = HORAS_GESTION_DOCUMENTAL_BAJA
    total = round(gestion + otras, 4)
    base.update(
        {
            "gestion_documental_h": gestion,
            "otras_tareas_h": otras,
            "total_horas": total,
            "incluye_horas_baja": total > 0,
            "motivo_exclusion": "bodega_baja",
        }
    )
    return base


def calc_fila_equipo(row: dict[str, Any], correctivo_pct: float, anio: int | None = None) -> dict[str, float]:
    """Calcula horas derivadas de una fila Inventario_850."""
    from server.inventario import clamp_anio, is_en_bodega

    year = clamp_anio(anio if anio is not None else row.get("anio_activo"))
    if equipo_excluido_dotacion(row):
        return _fila_bodega_anio(row, correctivo_pct, year) if is_en_bodega(row) else _fila_excluida_cero("baja")
    terceriza = es_parque_tercerizado(row)
    horas_mp = horas_actividad(
        row.get("aplica_mp"),
        row.get("freq_mp"),
        row.get("tiempo_mp"),
        row.get("tercerizado_mp"),
    )
    if terceriza:
        horas_mp = 0.0
    horas_cal = horas_actividad(
        row.get("aplica_cal"),
        row.get("freq_cal"),
        row.get("tiempo_cal"),
        row.get("tercerizado_cal"),
    )
    horas_val = horas_actividad(
        row.get("aplica_val"),
        row.get("freq_val"),
        row.get("tiempo_val"),
        row.get("tercerizado_val"),
    )
    horas_cap = horas_actividad(row.get("aplica_cap"), row.get("freq_cap"), row.get("tiempo_cap"))
    horas_corr = horas_correctivo(
        row.get("tiene_historico_correctivo"),
        row.get("historico_correctivo_h"),
        horas_mp,
        correctivo_pct,
    )
    gestion = _f(row.get("gestion_documental_h"))
    acomp = _f(row.get("acompanamiento_h"))
    otras = _f(row.get("otras_tareas_h"))
    # AE = SUM(L,P,T,X,AA,AB,AC,AD)
    total = (
        horas_mp
        + horas_cal
        + horas_val
        + horas_cap
        + horas_corr
        + gestion
        + acomp
        + otras
    )
    if terceriza:
        # TFM: comodato/leasing no aportan carga interna (Hparque).
        total = 0.0
    return {
        "horas_mp": horas_mp,
        "horas_cal": horas_cal,
        "horas_val": horas_val,
        "horas_cap": horas_cap,
        "horas_correctivo": horas_corr,
        "gestion_documental_h": gestion,
        "acompanamiento_h": acomp,
        "otras_tareas_h": otras,
        "total_horas": total,
        "en_dotacion": True,
        "en_plantilla": not terceriza,
        "motivo_exclusion": "comodato_leasing" if terceriza else "",
        "incluye_horas_baja": False,
    }


def calc_resumen(filas: list[dict[str, Any]], params_calc: dict[str, Any]) -> dict[str, Any]:
    """Hparque = Σ hi solo de equipos propios activos (no baja, no comodato/leasing)."""
    activos = [f for f in filas if f.get("en_dotacion", True)]
    internos = [
        f
        for f in activos
        if f.get("en_plantilla", not es_parque_tercerizado(f))
    ]
    excluidos = len(filas) - len(activos)
    total_equipos = len(activos)
    sum_mp = sum(_f(f.get("horas_mp")) for f in internos)
    sum_cal = sum(_f(f.get("horas_cal")) for f in internos)
    sum_val = sum(_f(f.get("horas_val")) for f in internos)
    sum_cap = sum(_f(f.get("horas_cap")) for f in internos)
    sum_corr = sum(_f(f.get("horas_correctivo")) for f in internos)
    sum_doc = sum(_f(f.get("gestion_documental_h")) for f in internos)
    sum_acomp = sum(_f(f.get("acompanamiento_h")) for f in internos)
    sum_otras = sum(_f(f.get("otras_tareas_h")) for f in internos)
    extras_baja = [
        f for f in filas if f.get("incluye_horas_baja") and not f.get("en_dotacion", True)
    ]
    sum_doc += sum(_f(f.get("gestion_documental_h")) for f in extras_baja)
    sum_otras += sum(_f(f.get("otras_tareas_h")) for f in extras_baja)
    # B12 = SUM(B4:B11)
    total_base = (
        sum_mp + sum_cal + sum_val + sum_cap + sum_corr + sum_doc + sum_acomp + sum_otras
    )
    # B13 = B12*Parametros!B10
    contingencia_h = total_base * _f(params_calc.get("contingencia"))
    # B14 = B12+B13
    total_ajustado = total_base + contingencia_h
    horas_efectivas = _f(params_calc.get("horas_efectivas"))
    # B16 = B14/B15
    ingenieros_requeridos = (
        (total_ajustado / horas_efectivas) if horas_efectivas > 0 else 0.0
    )
    # B17 = CEILING(B16,1)
    ingenieros_recomendados = (
        float(math.ceil(ingenieros_requeridos - 1e-12)) if ingenieros_requeridos > 0 else 0.0
    )

    por_servicio: dict[str, float] = {}
    por_criticidad: dict[str, float] = {}
    por_equipo_tipo: dict[str, float] = {}
    for f in list(internos) + extras_baja:
        srv = (f.get("servicio") or "Sin servicio").strip() or "Sin servicio"
        crit = normalize_criticidad(f.get("criticidad"))
        eq = (f.get("equipo") or "Sin equipo").strip() or "Sin equipo"
        th = _f(f.get("total_horas"))
        por_servicio[srv] = por_servicio.get(srv, 0.0) + th
        if f in internos:
            por_criticidad[crit] = por_criticidad.get(crit, 0.0) + th
        por_equipo_tipo[eq] = por_equipo_tipo.get(eq, 0.0) + th

    por_actividad = {
        "Mantenimiento preventivo": sum_mp,
        "Calibraciones": sum_cal,
        "Validación / Control de calidad": sum_val,
        "Capacitaciones": sum_cap,
        "Correctivos": sum_corr,
        "Gestión documental": sum_doc,
        "Acompañamiento proveedores": sum_acomp,
        "Otras tareas específicas": sum_otras,
        "Contingencia": contingencia_h,
    }

    return {
        "total_equipos": total_equipos,
        "total_equipos_internos": len(internos),
        "equipos_tercerizados": sum(1 for f in activos if es_parque_tercerizado(f)),
        "equipos_excluidos": excluidos,
        "horas_mp": sum_mp,
        "horas_cal": sum_cal,
        "horas_val": sum_val,
        "horas_cap": sum_cap,
        "horas_correctivo": sum_corr,
        "horas_gestion_documental": sum_doc,
        "horas_acompanamiento": sum_acomp,
        "horas_otras": sum_otras,
        "total_base": total_base,
        "contingencia_h": contingencia_h,
        "total_ajustado": total_ajustado,
        "horas_efectivas": horas_efectivas,
        "ingenieros_requeridos": ingenieros_requeridos,
        "ingenieros_recomendados": ingenieros_recomendados,
        "por_servicio": [
            {"servicio": k, "horas": v}
            for k, v in sorted(por_servicio.items(), key=lambda x: -x[1])
        ],
        "por_actividad": [{"actividad": k, "horas": v} for k, v in por_actividad.items()],
        "por_criticidad": [
            {"criticidad": k, "horas": v}
            for k, v in sorted(por_criticidad.items(), key=lambda x: -x[1])
        ],
        "por_equipo_tipo": [
            {"equipo": k, "horas": v}
            for k, v in sorted(por_equipo_tipo.items(), key=lambda x: -x[1])[:25]
        ],
    }
