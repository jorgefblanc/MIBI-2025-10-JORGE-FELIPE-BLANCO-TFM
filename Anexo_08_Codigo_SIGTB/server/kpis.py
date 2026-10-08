"""Motor de KPIs de ingeniería clínica (réplica de Instrumento_KPIs_...xlsx)."""

from __future__ import annotations

import calendar
import json
from datetime import date

from pathlib import Path

from server.inventory_enrichment import map_criticidad_dim
from server.limits import COMMENT, JSON_SMALL, SHORT

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema_kpis.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8")


def ensure_kpis_schema(emp_conn) -> None:
    emp_conn.executescript(SCHEMA_SQL)


MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)

MAX_PAYLOAD_BYTES = JSON_SMALL
MAX_OBS_CHARS = COMMENT
MAX_TEXT_CHARS = SHORT
ESTADOS_DECISION = ("Pendiente", "En curso", "Cerrado")

# Campos que escribe el ingeniero/coordinador. El resto se calcula.
INPUT_FIELDS = (
    ("equipos_totales", "Equipos totales", "Parque", "Conteo del inventario (sin baja)."),
    ("equipos_criticos", "Equipos críticos", "Parque", "Riesgo III / IIB o criticidad Alta."),
    ("tecnicos", "Técnicos biomédicos", "Parque", "Personal operativo de ingeniería en la empresa."),
    ("horas_fuera_total", "Horas fuera de servicio total", "Parque", "Carga el ingeniero: no está en el inventario."),
    ("horas_fuera_criticos", "Horas fuera de servicio críticos", "Parque", "Carga el ingeniero."),
    ("mp_programados", "MP programados", "Mantenimiento", "Órdenes de preventivo programadas en el mes."),
    ("mp_ejecutados", "MP ejecutados", "Mantenimiento", "Órdenes de preventivo ejecutadas."),
    ("cal_programadas", "Cal/val programadas", "Mantenimiento", "Calibraciones/validaciones programadas."),
    ("cal_ejecutadas", "Cal/val ejecutadas", "Mantenimiento", "Calibraciones/validaciones ejecutadas."),
    ("correctivos", "Correctivos totales", "Mantenimiento", "OT correctivas y visitas de verificación del mes (la visita cuenta como correctivo)."),
    ("correctivos_criticos", "Correctivos críticos", "Mantenimiento", "Correctivos sobre equipos críticos."),
    ("fallas_repetidas", "Fallas repetidas", "Mantenimiento", "Reincidencias en el mes."),
    ("tiempo_reparacion_h", "Tiempo total reparación correctivos (h)", "Mantenimiento", "Suma de (fecha de cierre − fecha de atención) en MC y visitas. Sin ambas fechas no se sugiere hora."),
    ("tiempo_primera_respuesta_h", "Tiempo total primera respuesta correctivos (h)", "Mantenimiento", "Suma de horas hasta primera respuesta."),
    ("solicitudes", "Solicitudes totales", "Productividad", "Solicitudes atendidas en el mes."),
    ("tiempo_respuesta_solicitudes_h", "Tiempo total respuesta solicitudes (h)", "Productividad", "Suma de horas de respuesta."),
    ("ot_cerradas", "OT cerradas", "Productividad", "Órdenes cerradas en el mes."),
    ("ot_cerradas_tiempo", "OT cerradas a tiempo", "Productividad", "Cerradas dentro del SLA."),
    ("backlog", "OT pendientes/backlog", "Productividad", "Carga pendiente al corte."),
    ("horas_efectivas_trabajadas", "Horas efectivas trabajadas", "Productividad", "Horas productivas del equipo de IC."),
    ("costo_preventivo", "Costo preventivo", "Costos", "COP del mes."),
    ("costo_correctivo", "Costo correctivo", "Costos", "COP del mes."),
    ("costo_cal_val", "Costo cal/val", "Costos", "COP del mes."),
    ("contratos_soporte", "Contratos/soporte", "Costos", "COP del mes."),
    ("repuestos_consumibles", "Repuestos/consumibles", "Costos", "COP del mes."),
    ("capacitaciones", "Capacitaciones", "Costos", "COP del mes."),
    ("otros_opex", "Otros costos OPEX", "Costos", "COP del mes."),
    ("presupuesto_asignado", "Presupuesto asignado", "Costos", "Presupuesto OPEX del mes."),
    ("valor_reposicion_parque", "Valor reposición parque", "Costos", "Valor de reposición del parque."),
    ("dias_fuera_servicio", "Días fuera de servicio", "Inactividad", "Días-parque fuera de servicio."),
    ("costo_diario_inactividad", "Costo diario inactividad", "Inactividad", "Si vacío, se usa el parámetro institucional."),
    ("factor_mitigacion", "Factor mitigación", "Inactividad", "Reducción por respaldo/contingencia (0–1)."),
    ("equipos_fuera_soporte", "Equipos fuera de soporte", "Riesgo", "Garantía vencida o sin soporte."),
    ("equipos_candidatos_capex", "Equipos candidatos CAPEX", "Riesgo", "Vida útil agotada o renovación."),
    ("equipos_documentacion_completa", "Equipos con documentación completa", "Riesgo", "Manual de operación y de servicio."),
    ("tiempo_repuestos_dias", "Tiempo total consecución repuestos (días)", "Proveedores", "Suma de días de espera."),
    ("solicitudes_repuestos", "Número solicitudes repuestos", "Proveedores", "Solicitudes de repuesto del mes."),
    ("correctivos_retrasados_repuestos", "Correctivos retrasados por repuestos", "Proveedores", "OT frenadas por logística."),
    ("servicios_proveedor_programados", "Servicios proveedor programados", "Proveedores", "Visitas/contratos programados."),
    ("servicios_proveedor_cumplidos", "Servicios proveedor cumplidos", "Proveedores", "Visitas/contratos cumplidos."),
    ("eventos_adversos", "Eventos adversos tecnología", "Seguridad", "Tecnovigilancia: eventos adversos."),
    ("incidentes", "Incidentes tecnología", "Seguridad", "Incidentes asociados a tecnología."),
    ("factor_criticidad_inactividad", "Factor criticidad inactividad", "Inactividad", "Ponderación clínica de la parada crítica."),
)

INPUT_KEYS = tuple(k for k, *_ in INPUT_FIELDS)

# direction: higher / lower / budget / saving
INDICATORS = (
    {"key": "cumplimiento_mp", "tipo": "Cumplimiento y seguridad", "nombre": "Cumplimiento plan MP", "meta": 0.95, "unidad": "%", "verde": "≥ 95%", "amarillo": "90% a 94.9%", "rojo": "< 90%", "frecuencia": "Mensual", "lectura": "Control de prevención y riesgo", "direction": "higher"},
    {"key": "cumplimiento_cal", "tipo": "Cumplimiento y seguridad", "nombre": "Cumplimiento calibración/validación", "meta": 0.95, "unidad": "%", "verde": "≥ 95%", "amarillo": "90% a 94.9%", "rojo": "< 90%", "frecuencia": "Mensual", "lectura": "Cumplimiento metrológico y normativo", "direction": "higher"},
    {"key": "cumplimiento_doc", "tipo": "Cumplimiento y seguridad", "nombre": "Cumplimiento documental/normativo", "meta": 0.95, "unidad": "%", "verde": "≥ 95%", "amarillo": "90% a 94.9%", "rojo": "< 90%", "frecuencia": "Mensual", "lectura": "Auditoría, habilitación y trazabilidad", "direction": "higher"},
    {"key": "disponibilidad_total", "tipo": "Continuidad operativa", "nombre": "Disponibilidad de equipos biomédicos", "meta": 0.97, "unidad": "%", "verde": "≥ 97%", "amarillo": "95% a 96.9%", "rojo": "< 95%", "frecuencia": "Mensual", "lectura": "Continuidad operativa del parque", "direction": "higher"},
    {"key": "disponibilidad_criticos", "tipo": "Continuidad operativa", "nombre": "Disponibilidad de equipos críticos", "meta": 0.98, "unidad": "%", "verde": "≥ 98%", "amarillo": "95% a 97.9%", "rojo": "< 95%", "frecuencia": "Mensual", "lectura": "Continuidad de servicios críticos", "direction": "higher"},
    {"key": "impacto_inactividad_opex", "tipo": "Continuidad operativa", "nombre": "Impacto económico de inactividad sobre OPEX", "meta": 0.05, "unidad": "%", "verde": "≤ 5%", "amarillo": "5% a 10%", "rojo": "> 10%", "frecuencia": "Mensual", "lectura": "Peso de la inactividad frente al OPEX biomédico", "direction": "lower"},
    {"key": "costo_evitado_inactividad", "tipo": "Continuidad operativa", "nombre": "Costo evitado por reducción de inactividad", "meta": 0, "unidad": "COP", "verde": "Ahorro positivo", "amarillo": "Ahorro neutro", "rojo": "Sin ahorro", "frecuencia": "Mensual", "lectura": "Valor generado por reducir paradas", "direction": "saving"},
    {"key": "inactividad_critica_ponderada", "tipo": "Continuidad operativa", "nombre": "Inactividad crítica ponderada", "meta": 50, "unidad": "puntos", "verde": "≤ 50", "amarillo": "51 a 100", "rojo": "> 100", "frecuencia": "Mensual", "lectura": "Indisponibilidad ponderada por criticidad clínica", "direction": "lower"},
    {"key": "respuesta_correctivos_h", "tipo": "Correctivo y confiabilidad", "nombre": "Oportunidad de respuesta a correctivos", "meta": 4, "unidad": "horas", "verde": "≤ 4 h", "amarillo": "4 a 8 h", "rojo": "> 8 h", "frecuencia": "Mensual", "lectura": "Velocidad de atención inicial", "direction": "lower"},
    {"key": "mttr_h", "tipo": "Correctivo y confiabilidad", "nombre": "Tiempo medio para reparar MTTR", "meta": 24, "unidad": "horas", "verde": "≤ 24 h", "amarillo": "24 a 48 h", "rojo": "> 48 h", "frecuencia": "Mensual", "lectura": "Eficiencia para devolver equipos a operación", "direction": "lower"},
    {"key": "mtbf_h", "tipo": "Correctivo y confiabilidad", "nombre": "Tiempo medio entre fallas MTBF", "meta": 720, "unidad": "horas", "verde": "≥ 720 h", "amarillo": "360 a 719 h", "rojo": "< 360 h", "frecuencia": "Semestral", "lectura": "Confiabilidad del parque tecnológico", "direction": "higher"},
    {"key": "tasa_correctivos", "tipo": "Correctivo y confiabilidad", "nombre": "Tasa de correctivos", "meta": 0.08, "unidad": "%", "verde": "≤ 8%", "amarillo": "8% a 12%", "rojo": "> 12%", "frecuencia": "Mensual", "lectura": "Nivel de fallas del parque", "direction": "lower"},
    {"key": "reincidencia", "tipo": "Correctivo y confiabilidad", "nombre": "Reincidencia de fallas", "meta": 0.1, "unidad": "%", "verde": "≤ 10%", "amarillo": "10% a 15%", "rojo": "> 15%", "frecuencia": "Mensual", "lectura": "Calidad de reparación", "direction": "lower"},
    {"key": "horas_efectivas", "tipo": "Productividad del proceso", "nombre": "Horas efectivas de trabajo", "meta": 0.8, "unidad": "%", "verde": "≥ 80%", "amarillo": "70% a 79.9%", "rojo": "< 70%", "frecuencia": "Mensual", "lectura": "Aprovechamiento del recurso humano", "direction": "higher"},
    {"key": "respuesta_solicitudes_h", "tipo": "Productividad del proceso", "nombre": "Tiempo respuesta promedio a solicitudes", "meta": 8, "unidad": "horas", "verde": "≤ 8 h", "amarillo": "8 a 16 h", "rojo": "> 16 h", "frecuencia": "Mensual", "lectura": "Oportunidad general del proceso", "direction": "lower"},
    {"key": "ot_a_tiempo", "tipo": "Productividad del proceso", "nombre": "OT cerradas a tiempo", "meta": 0.9, "unidad": "%", "verde": "≥ 90%", "amarillo": "80% a 89.9%", "rojo": "< 80%", "frecuencia": "Mensual", "lectura": "Cumplimiento operativo", "direction": "higher"},
    {"key": "backlog", "tipo": "Productividad del proceso", "nombre": "Backlog de mantenimiento", "meta": 30, "unidad": "OT", "verde": "≤ 30", "amarillo": "31 a 60", "rojo": "> 60", "frecuencia": "Mensual", "lectura": "Carga pendiente acumulada", "direction": "lower"},
    {"key": "eficiencia_financiera", "tipo": "Costo-efectividad", "nombre": "Eficiencia financiera programa mantenimiento", "meta": 0.1, "unidad": "%", "verde": "≤ 10%", "amarillo": "10% a 15%", "rojo": "> 15%", "frecuencia": "Trimestral", "lectura": "Costo mantenimiento/valor reposición", "direction": "lower"},
    {"key": "ejecucion_presupuestal", "tipo": "Costo-efectividad", "nombre": "Ejecución presupuestal", "meta": 1, "unidad": "%", "verde": "90% a 100%", "amarillo": "80% a 89.9% o 100% a 110%", "rojo": "<80% o >110%", "frecuencia": "Mensual", "lectura": "Control presupuestal", "direction": "budget"},
    {"key": "correctivos_opex", "tipo": "Costo-efectividad", "nombre": "Correctivos/OPEX total", "meta": 0.3, "unidad": "%", "verde": "≤ 30%", "amarillo": "30% a 45%", "rojo": "> 45%", "frecuencia": "Mensual", "lectura": "Control de gasto reactivo", "direction": "lower"},
    {"key": "ahorro_estimado", "tipo": "Costo-efectividad", "nombre": "Ahorro generado por gestión biomédica", "meta": 0, "unidad": "COP", "verde": "Ahorro positivo", "amarillo": "Ahorro neutro", "rojo": "Sin ahorro", "frecuencia": "Mensual", "lectura": "Valor financiero generado", "direction": "saving"},
    {"key": "pct_fuera_soporte", "tipo": "Riesgo tecnológico y CAPEX", "nombre": "Equipos fuera de soporte", "meta": 0.05, "unidad": "%", "verde": "≤ 5%", "amarillo": "5% a 10%", "rojo": "> 10%", "frecuencia": "Trimestral", "lectura": "Riesgo tecnológico", "direction": "lower"},
    {"key": "pct_candidatos_capex", "tipo": "Riesgo tecnológico y CAPEX", "nombre": "Candidatos a renovación CAPEX", "meta": 0.1, "unidad": "%", "verde": "≤ 10%", "amarillo": "10% a 20%", "rojo": "> 20%", "frecuencia": "Trimestral/Anual", "lectura": "Planeación de inversión", "direction": "lower"},
    {"key": "indice_renovacion", "tipo": "Riesgo tecnológico y CAPEX", "nombre": "Índice de renovación tecnológica", "meta": 0.8, "unidad": "%", "verde": "< 10% críticos", "amarillo": "10% a 20%", "rojo": "> 20%", "frecuencia": "Anual", "lectura": "Prioridad de renovación", "direction": "lower"},
    {"key": "tiempo_repuestos_prom", "tipo": "Repuestos y proveedores", "nombre": "Tiempo consecución de repuestos", "meta": 10, "unidad": "días", "verde": "≤ 10 días", "amarillo": "11 a 20 días", "rojo": "> 20 días", "frecuencia": "Mensual", "lectura": "Riesgo logístico", "direction": "lower"},
    {"key": "pct_correctivos_repuestos", "tipo": "Repuestos y proveedores", "nombre": "Correctivos retrasados por repuestos", "meta": 0.1, "unidad": "%", "verde": "≤ 10%", "amarillo": "10% a 20%", "rojo": "> 20%", "frecuencia": "Mensual", "lectura": "Cuello de botella por repuestos", "direction": "lower"},
    {"key": "cumplimiento_proveedores", "tipo": "Repuestos y proveedores", "nombre": "Cumplimiento proveedores", "meta": 0.9, "unidad": "%", "verde": "≥ 90%", "amarillo": "80% a 89.9%", "rojo": "< 80%", "frecuencia": "Mensual", "lectura": "Desempeño contractual", "direction": "higher"},
    {"key": "eventos_adversos", "tipo": "Seguridad del paciente", "nombre": "Eventos adversos asociados a tecnología", "meta": 0, "unidad": "eventos", "verde": "0", "amarillo": "1", "rojo": "> 1", "frecuencia": "Mensual", "lectura": "Seguridad del paciente", "direction": "lower"},
    {"key": "incidentes", "tipo": "Seguridad del paciente", "nombre": "Incidentes asociados a tecnología", "meta": 2, "unidad": "incidentes", "verde": "≤ 2", "amarillo": "3 a 5", "rojo": "> 5", "frecuencia": "Mensual", "lectura": "Riesgo de uso de tecnología", "direction": "lower"},
)

INDICATOR_BY_KEY = {row["key"]: row for row in INDICATORS}

INTERPRETACION = {
    "impacto_inactividad_opex": {
        "que": "Mide qué porcentaje del OPEX biomédico representa el costo de inactividad.",
        "bajo": "Bajo es positivo: la inactividad tiene bajo impacto frente al costo operativo del proceso.",
        "alto": "Alto indica que la inactividad consume una proporción relevante del OPEX y debe tratarse como pérdida operativa.",
        "analisis": "Identificar equipos y servicios que generan mayor costo de parada y comparar contra OPEX total.",
        "accion": "Priorizar reducción de paradas, respaldos operativos y renovación de equipos con alto impacto económico.",
    },
    "costo_evitado_inactividad": {
        "que": "Mide el ahorro generado al reducir el costo de inactividad frente a periodos anteriores.",
        "bajo": "Bajo o cero indica que no se logró reducir la pérdida por inactividad.",
        "alto": "Alto indica valor económico generado al reducir paradas.",
        "analisis": "Comparar contra meses anteriores e identificar acciones que redujeron paradas.",
        "accion": "Documentar el costo evitado como aporte financiero de ingeniería clínica.",
    },
    "inactividad_critica_ponderada": {
        "que": "Mide la inactividad de equipos críticos ponderada por criticidad clínica.",
        "bajo": "Bajo indica menor exposición operativa de equipos críticos.",
        "alto": "Alto indica que tecnologías de alto impacto clínico estuvieron indisponibles y requieren prioridad.",
        "analisis": "Listar equipos críticos fuera de servicio, causas, respaldo disponible y tiempo de recuperación.",
        "accion": "Priorizar equipos críticos, contingencia, repuestos y renovación según riesgo clínico.",
    },
}

_GENERIC_CUMPLE = {
    "que": "Mide cumplimiento frente a lo programado o requerido.",
    "bajo": "Bajo indica brecha de cumplimiento y riesgo operativo/normativo.",
    "alto": "Alto indica control y disciplina del proceso.",
    "analisis": "Revisar causas de incumplimiento, recursos, programación y responsables.",
    "accion": "Ejecutar plan de cierre de brechas y seguimiento mensual.",
}
_GENERIC_TIEMPO = {
    "que": "Mide oportunidad o tiempo promedio del proceso.",
    "bajo": "Bajo es positivo: mayor oportunidad.",
    "alto": "Alto indica demoras y posible impacto operativo.",
    "analisis": "Analizar cuellos de botella, proveedor, repuestos, personal y priorización.",
    "accion": "Definir SLA y plan de reducción de tiempos.",
}
_GENERIC = {
    "que": "Mide desempeño del proceso de ingeniería clínica.",
    "bajo": "Bajo puede ser positivo o negativo según el tipo de indicador.",
    "alto": "Alto puede indicar buen desempeño o alerta según el indicador.",
    "analisis": "Comparar contra meta, tendencia y causa raíz.",
    "accion": "Definir acción según semáforo y criticidad.",
}
_GENERIC_SEG = {
    "que": "Mide eventos o incidentes relacionados con tecnología biomédica.",
    "bajo": "Bajo/cero es el objetivo.",
    "alto": "Alto indica riesgo para seguridad del paciente.",
    "analisis": "Realizar análisis causa raíz y trazabilidad.",
    "accion": "Activar tecnovigilancia y acciones preventivas/correctivas.",
}

for _ind in INDICATORS:
    if _ind["key"] not in INTERPRETACION:
        if _ind["key"] in ("cumplimiento_mp", "cumplimiento_cal", "cumplimiento_doc", "cumplimiento_proveedores"):
            INTERPRETACION[_ind["key"]] = _GENERIC_CUMPLE
        elif _ind["key"] in ("respuesta_correctivos_h", "mttr_h", "respuesta_solicitudes_h", "tiempo_repuestos_prom"):
            INTERPRETACION[_ind["key"]] = _GENERIC_TIEMPO
        elif _ind["key"] in ("eventos_adversos", "incidentes"):
            INTERPRETACION[_ind["key"]] = _GENERIC_SEG
        else:
            INTERPRETACION[_ind["key"]] = _GENERIC

GUIA = (
    "Actualice metas y datos institucionales en Parámetros.",
    "Ingrese los valores mensuales. Las celdas de inventario se sugieren solas; el resto las carga el ingeniero o coordinador.",
    "Las columnas calculadas obtienen horas de parque, disponibilidad, OPEX e inactividad.",
    "Revise KPIs mensuales y el análisis anual para validar resultados.",
    "Use el dashboard y el informe de alta gerencia para reportar a dirección.",
    "El indicador de inactividad se evalúa como impacto sobre OPEX, costo evitado e inactividad crítica ponderada.",
)

DASHBOARD_KEYS = (
    "cumplimiento_mp",
    "cumplimiento_cal",
    "disponibilidad_criticos",
    "impacto_inactividad_opex",
    "costo_evitado_inactividad",
    "mttr_h",
    "respuesta_solicitudes_h",
    "eficiencia_financiera",
    "ejecucion_presupuestal",
    "correctivos_opex",
    "pct_correctivos_repuestos",
    "eventos_adversos",
)


def _n(value, default=0.0) -> float:
    if value is None or value == "":
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _ratio(num, den) -> float:
    d = _n(den)
    if d == 0:
        return 0.0
    return _n(num) / d


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def dias_del_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(int(anio), int(mes))[1]


def default_params(empresa_nombre: str | None = None) -> dict:
    return {
        "anio": date.today().year,
        "institucion": empresa_nombre or "",
        "proceso": "Ingeniería Clínica",
        "responsable": "Coordinación de Ingeniería Clínica",
        "costo_diario_inactividad": 2_000_000,
        "factor_mitigacion": 0.5,
        "horas_laborales_tecnico_mes": 192,
        "costo_externo_referencia": 0,
        "metas": {row["key"]: row["meta"] for row in INDICATORS},
    }


def merge_params(stored: dict | None, empresa_nombre: str | None = None) -> dict:
    base = default_params(empresa_nombre)
    if not stored:
        return base
    out = dict(base)
    for key in (
        "anio",
        "institucion",
        "proceso",
        "responsable",
        "costo_diario_inactividad",
        "factor_mitigacion",
        "horas_laborales_tecnico_mes",
        "costo_externo_referencia",
    ):
        if stored.get(key) not in (None, ""):
            out[key] = stored[key]
    metas = dict(base["metas"])
    extra = stored.get("metas") or {}
    if isinstance(extra, dict):
        for key, val in extra.items():
            if key in metas:
                metas[key] = _n(val, metas[key])
    out["metas"] = metas
    out["costo_diario_inactividad"] = _n(out["costo_diario_inactividad"], 2_000_000)
    out["factor_mitigacion"] = _clamp(_n(out["factor_mitigacion"], 0.5), 0, 1)
    out["horas_laborales_tecnico_mes"] = _n(out["horas_laborales_tecnico_mes"], 192)
    out["anio"] = int(_n(out["anio"], date.today().year))
    return out


def sanitize_params_payload(body: dict) -> dict:
    cleaned = {
        "anio": int(_clamp(_n(body.get("anio"), date.today().year), 2000, 2100)),
        "institucion": str(body.get("institucion") or "")[:MAX_TEXT_CHARS],
        "proceso": str(body.get("proceso") or "")[:MAX_TEXT_CHARS],
        "responsable": str(body.get("responsable") or "")[:MAX_TEXT_CHARS],
        "costo_diario_inactividad": max(0.0, _n(body.get("costo_diario_inactividad"), 2_000_000)),
        "factor_mitigacion": _clamp(_n(body.get("factor_mitigacion"), 0.5), 0, 1),
        "horas_laborales_tecnico_mes": max(1.0, _n(body.get("horas_laborales_tecnico_mes"), 192)),
        "costo_externo_referencia": max(0.0, _n(body.get("costo_externo_referencia"), 0)),
        "metas": {},
    }
    raw_metas = body.get("metas") or {}
    if isinstance(raw_metas, dict):
        for key in INDICATOR_BY_KEY:
            if key in raw_metas:
                cleaned["metas"][key] = _n(raw_metas[key], INDICATOR_BY_KEY[key]["meta"])
    encoded = json.dumps(cleaned, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Los parámetros superan el tamaño máximo permitido.")
    return cleaned


def sanitize_month_payload(body: dict) -> dict:
    cleaned = {}
    for key in INPUT_KEYS:
        if key not in body:
            continue
        val = body.get(key)
        if val in (None, ""):
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num < 0:
            num = 0.0
        cleaned[key] = num
    encoded = json.dumps(cleaned, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("La entrada mensual supera el tamaño máximo permitido.")
    return cleaned


def sanitize_decision(estado: str | None, observaciones: str | None) -> tuple[str, str]:
    est = (estado or "Pendiente").strip()
    if est not in ESTADOS_DECISION:
        est = "Pendiente"
    obs = str(observaciones or "")[:MAX_OBS_CHARS]
    return est, obs


def semaforo(value, meta, direction: str) -> str:
    v = _n(value)
    m = _n(meta)
    if direction == "saving":
        return "Verde" if v > 0 else "Amarillo"
    if direction == "budget":
        if 0.9 <= v <= 1.1:
            return "Verde"
        if 0.8 <= v <= 1.2:
            return "Amarillo"
        return "Rojo"
    if direction == "higher":
        if v >= m:
            return "Verde"
        if v >= m * 0.95:
            return "Amarillo"
        return "Rojo"
    # lower (Excel: verde <= meta, amarillo <= meta*1.5)
    if v <= m:
        return "Verde"
    if m == 0:
        return "Amarillo" if v <= 1 else "Rojo"
    if v <= m * 1.5:
        return "Amarillo"
    return "Rojo"


def _score_component(value, meta, direction: str) -> float:
    v = _n(value)
    m = _n(meta)
    if direction == "higher":
        if m == 0:
            return 100.0 if v >= 0 else 0.0
        return min(100.0, (v / m) * 100.0)
    if direction == "lower":
        if v == 0:
            return 100.0
        if m == 0:
            return 0.0
        return min(100.0, (m / v) * 100.0)
    if direction == "budget":
        gap = abs(v - 1.0)
        return max(0.0, 100.0 - gap * 200.0)
    return 100.0 if v > 0 else 50.0


def compute_month(inputs: dict, params: dict, *, prev_inactividad: float | None, first_correctivo: float | None) -> dict:
    p = params
    horas_lab = max(_n(p.get("horas_laborales_tecnico_mes"), 192), 1)
    costo_dia_def = _n(p.get("costo_diario_inactividad"), 2_000_000)
    factor_def = _clamp(_n(p.get("factor_mitigacion"), 0.5), 0, 1)
    metas = p.get("metas") or {}

    eq = _n(inputs.get("equipos_totales"))
    crit = _n(inputs.get("equipos_criticos"))
    tec = _n(inputs.get("tecnicos"))
    dias = int(_n(inputs.get("dias_mes"), 30))
    horas_parque = eq * dias * 24
    horas_parque_crit = crit * dias * 24
    horas_fuera = _n(inputs.get("horas_fuera_total"))
    horas_fuera_c = _n(inputs.get("horas_fuera_criticos"))
    horas_disp = max(horas_parque - horas_fuera, 0)
    horas_disp_c = max(horas_parque_crit - horas_fuera_c, 0)
    horas_pers = tec * horas_lab
    opex = sum(
        _n(inputs.get(k))
        for k in (
            "costo_preventivo",
            "costo_correctivo",
            "costo_cal_val",
            "contratos_soporte",
            "repuestos_consumibles",
            "capacitaciones",
            "otros_opex",
        )
    )
    costo_dia = _n(inputs.get("costo_diario_inactividad"), costo_dia_def)
    factor = _clamp(_n(inputs.get("factor_mitigacion"), factor_def), 0, 1)
    costo_inact = _n(inputs.get("dias_fuera_servicio")) * costo_dia * (1 - factor)
    factor_c = _n(inputs.get("factor_criticidad_inactividad"), 4.5)
    inact_pond = (horas_fuera_c / 24.0) * factor_c
    costo_evitado = 0.0
    if prev_inactividad is not None:
        costo_evitado = max(0.0, _n(prev_inactividad) - costo_inact)
    corr = _n(inputs.get("costo_correctivo"))
    ahorro_corr = 0.0
    if first_correctivo is not None:
        ahorro_corr = max(0.0, _n(first_correctivo) - corr)
    ahorro_total = ahorro_corr + costo_evitado

    kpis = {
        "cumplimiento_mp": _ratio(inputs.get("mp_ejecutados"), inputs.get("mp_programados")),
        "cumplimiento_cal": _ratio(inputs.get("cal_ejecutadas"), inputs.get("cal_programadas")),
        "cumplimiento_doc": _ratio(inputs.get("equipos_documentacion_completa"), eq),
        "disponibilidad_total": _ratio(horas_disp, horas_parque),
        "disponibilidad_criticos": _ratio(horas_disp_c, horas_parque_crit),
        "impacto_inactividad_opex": _ratio(costo_inact, opex),
        "costo_evitado_inactividad": costo_evitado,
        "inactividad_critica_ponderada": inact_pond,
        "respuesta_correctivos_h": _ratio(inputs.get("tiempo_primera_respuesta_h"), inputs.get("correctivos")),
        "mttr_h": _ratio(inputs.get("tiempo_reparacion_h"), inputs.get("correctivos")),
        "mtbf_h": _ratio(horas_parque, inputs.get("correctivos")),
        "tasa_correctivos": _ratio(inputs.get("correctivos"), eq),
        "reincidencia": _ratio(inputs.get("fallas_repetidas"), inputs.get("correctivos")),
        "horas_efectivas": _ratio(inputs.get("horas_efectivas_trabajadas"), horas_pers),
        "respuesta_solicitudes_h": _ratio(inputs.get("tiempo_respuesta_solicitudes_h"), inputs.get("solicitudes")),
        "ot_a_tiempo": _ratio(inputs.get("ot_cerradas_tiempo"), inputs.get("ot_cerradas")),
        "backlog": _n(inputs.get("backlog")),
        "eficiencia_financiera": _ratio(opex, inputs.get("valor_reposicion_parque")),
        "ejecucion_presupuestal": _ratio(opex, inputs.get("presupuesto_asignado")),
        "correctivos_opex": _ratio(inputs.get("costo_correctivo"), opex),
        "ahorro_estimado": ahorro_total,
        "equipos_fuera_soporte": _n(inputs.get("equipos_fuera_soporte")),
        "pct_fuera_soporte": _ratio(inputs.get("equipos_fuera_soporte"), eq),
        "equipos_candidatos_capex": _n(inputs.get("equipos_candidatos_capex")),
        "pct_candidatos_capex": _ratio(inputs.get("equipos_candidatos_capex"), eq),
        "indice_renovacion": _ratio(inputs.get("equipos_candidatos_capex"), eq),
        "tiempo_repuestos_prom": _ratio(inputs.get("tiempo_repuestos_dias"), inputs.get("solicitudes_repuestos")),
        "pct_correctivos_repuestos": _ratio(inputs.get("correctivos_retrasados_repuestos"), inputs.get("correctivos")),
        "cumplimiento_proveedores": _ratio(inputs.get("servicios_proveedor_cumplidos"), inputs.get("servicios_proveedor_programados")),
        "eventos_adversos": _n(inputs.get("eventos_adversos")),
        "incidentes": _n(inputs.get("incidentes")),
        "costo_inactividad": costo_inact,
    }
    # Índice gerencial: mismos 15 términos del Excel (AVERAGE de MIN(100, …)).
    idx_terms = [
        _score_component(kpis["cumplimiento_mp"], metas.get("cumplimiento_mp", 0.95), "higher"),
        _score_component(kpis["cumplimiento_cal"], metas.get("cumplimiento_cal", 0.95), "higher"),
        _score_component(kpis["cumplimiento_doc"], metas.get("cumplimiento_doc", 0.95), "higher"),
        _score_component(kpis["disponibilidad_total"], metas.get("disponibilidad_total", 0.97), "higher"),
        _score_component(kpis["disponibilidad_criticos"], metas.get("disponibilidad_criticos", 0.98), "higher"),
        _score_component(kpis["impacto_inactividad_opex"], metas.get("impacto_inactividad_opex", 0.05), "lower"),
        _score_component(kpis["respuesta_correctivos_h"], metas.get("respuesta_correctivos_h", 4), "lower"),
        _score_component(kpis["mttr_h"], metas.get("mttr_h", 24), "lower"),
        _score_component(kpis["mtbf_h"], metas.get("mtbf_h", 720), "higher"),
        _score_component(kpis["tasa_correctivos"], metas.get("tasa_correctivos", 0.08), "lower"),
        _score_component(kpis["reincidencia"], metas.get("reincidencia", 0.1), "lower"),
        _score_component(kpis["horas_efectivas"], metas.get("horas_efectivas", 0.8), "higher"),
        _score_component(kpis["ot_a_tiempo"], metas.get("ot_a_tiempo", 0.9), "higher"),
        # Excel usa C20 (backlog) / Q (eficiencia financiera); se replica a propósito.
        _score_component(kpis["eficiencia_financiera"], metas.get("backlog", 30), "lower"),
        _score_component(kpis["cumplimiento_proveedores"], metas.get("cumplimiento_proveedores", 0.9), "higher"),
    ]
    indice = round(sum(idx_terms) / len(idx_terms), 1) if idx_terms else 0.0
    if indice >= 90:
        sem_global = "Verde"
    elif indice >= 75:
        sem_global = "Amarillo"
    else:
        sem_global = "Rojo"
    kpis["indice_gerencial"] = indice
    kpis["semaforo_global"] = sem_global
    derived = {
        "dias_mes": dias,
        "horas_parque_total": horas_parque,
        "horas_parque_critico": horas_parque_crit,
        "horas_disponibles_total": horas_disp,
        "horas_disponibles_criticos": horas_disp_c,
        "horas_disponibles_personal": horas_pers,
        "opex_total": opex,
        "costo_inactividad": costo_inact,
        "inactividad_critica_ponderada": inact_pond,
        "tiene_datos": any(k in inputs for k in INPUT_KEYS),
    }
    return {"inputs": inputs, "derived": derived, "kpis": kpis}


def _avg(values: list[float]) -> float:
    nums = [v for v in values if v is not None]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


def compute_year(months: list[dict], params: dict) -> dict:
    metas = params.get("metas") or {}
    by_key = {ind["key"]: [] for ind in INDICATORS}
    indices = []
    filled = 0
    for month in months:
        if not month.get("derived", {}).get("tiene_datos"):
            continue
        filled += 1
        kpis = month["kpis"]
        indices.append(kpis.get("indice_gerencial") or 0)
        for ind in INDICATORS:
            by_key[ind["key"]].append(kpis.get(ind["key"], 0))
    anual = []
    for ind in INDICATORS:
        key = ind["key"]
        meta = _n(metas.get(key, ind["meta"]), ind["meta"])
        vals = by_key[key]
        if ind["direction"] == "saving" or key in ("eventos_adversos", "incidentes", "costo_evitado_inactividad", "ahorro_estimado"):
            resultado = sum(vals) if vals else 0.0
        else:
            resultado = _avg(vals)
        sem = semaforo(resultado, meta, ind["direction"])
        interp = INTERPRETACION[key]
        if sem == "Verde":
            analisis = "Resultado controlado. Mantener seguimiento."
            decision = "Mantener control"
            prioridad = "Baja"
            gerencial = f"Indicador bajo control: {ind['nombre']}"
        elif sem == "Amarillo":
            analisis = "Resultado en observación. Revisar causas y ajustar plan."
            decision = "Plan de mejora"
            prioridad = "Media"
            gerencial = f"Requiere seguimiento gerencial: {ind['nombre']}"
        else:
            analisis = "Resultado crítico. Requiere acción prioritaria."
            decision = "Intervención prioritaria"
            prioridad = "Alta"
            gerencial = f"Alta gerencia debe priorizar: {ind['nombre']}"
        anual.append(
            {
                **ind,
                "meta": meta,
                "resultado": resultado,
                "semaforo": sem,
                "analisis": analisis,
                "decision": decision,
                "prioridad": prioridad,
                "mensaje_gerencial": gerencial,
                "que": interp["que"],
                "bajo": interp["bajo"],
                "alto": interp["alto"],
                "analisis_recomendado": interp["analisis"],
                "accion": interp["accion"],
            }
        )
    rojos = sum(1 for r in anual if r["semaforo"] == "Rojo")
    amarillos = sum(1 for r in anual if r["semaforo"] == "Amarillo")
    indice = round(_avg(indices), 1) if indices else 0.0
    impacto = next((r["resultado"] for r in anual if r["key"] == "impacto_inactividad_opex"), 0)
    evitado = next((r["resultado"] for r in anual if r["key"] == "costo_evitado_inactividad"), 0)
    if rojos:
        decision_exec = "Priorizar indicadores en rojo con plan de acción formal, responsable y fecha de cierre."
    elif amarillos:
        decision_exec = "Ejecutar plan de mejora sobre indicadores en amarillo."
    else:
        decision_exec = "Mantener estrategia actual y documentar resultados."
    resumen = (
        f"Índice gerencial promedio: {indice:.1f}/100. "
        f"Indicadores en rojo: {rojos}. Indicadores en amarillo: {amarillos}. "
        f"Impacto inactividad/OPEX: {impacto:.1%}. "
        f"Costo evitado inactividad: {evitado:,.0f}."
    )
    dashboard = [row for row in anual if row["key"] in DASHBOARD_KEYS]
    return {
        "indicadores": anual,
        "meses_con_datos": filled,
        "indice_gerencial": indice,
        "rojos": rojos,
        "amarillos": amarillos,
        "resumen_ejecutivo": resumen,
        "decision_ejecutiva": decision_exec,
        "dashboard": dashboard,
    }


def empty_year(anio: int, params: dict) -> list[dict]:
    months = []
    first_corr = None
    prev_inact = None
    for mes in range(1, 13):
        inputs = {"dias_mes": dias_del_mes(anio, mes)}
        computed = compute_month(inputs, params, prev_inactividad=prev_inact, first_correctivo=first_corr)
        computed["mes"] = mes
        computed["nombre"] = MESES[mes - 1]
        months.append(computed)
    return months


def build_year(anio: int, params: dict, saved_by_month: dict[int, dict]) -> list[dict]:
    months = []
    first_corr = None
    prev_inact = None
    for mes in range(1, 13):
        raw = dict(saved_by_month.get(mes) or {})
        raw["dias_mes"] = dias_del_mes(anio, mes)
        computed = compute_month(raw, params, prev_inactividad=prev_inact, first_correctivo=first_corr)
        if computed["derived"]["tiene_datos"]:
            if first_corr is None:
                first_corr = _n(raw.get("costo_correctivo"))
            prev_inact = computed["kpis"]["costo_inactividad"]
        computed["mes"] = mes
        computed["nombre"] = MESES[mes - 1]
        months.append(computed)
    return months


def is_equipo_critico(clasificacion_riesgo, clasificacion_biomedica) -> bool:
    return map_criticidad_dim(clasificacion_riesgo, clasificacion_biomedica) == "Alto"


def snapshot_inventario(emp_conn, users_conn, empresa_id: int, anio: int | None = None) -> dict:
    """Una sola agregación del parque; no se envía el listado de equipos al cliente."""
    from server.frecuencia_pm import lookup_resumen_llave, resumen_ejecucion_por_llaves
    from server.inventario import (
        MENSAJE_SIN_DATOS_ANIO,
        apply_flags_equipo,
        clamp_anio,
        is_en_bodega,
    )

    year = clamp_anio(anio)
    rows = emp_conn.execute(
        """
        SELECT ie.estado, ie.clasificacion_riesgo, ie.clasificacion_biomedica,
               ie.aplica_mp, ie.aplica_cal, ie.aplica_val,
               ie.manual_operacion, ie.manual_servicio,
               ie.fecha_garantia, ie.fecha_baja, ie.vida_util_anios,
               ie.fecha_compra, ie.fecha_operacion,
               ie.ubicacion, ie.codigo_ubicacion, ie.num_biomedica, ie.codigo_activo,
               ie.fecha_ultimo_pm, srv.ID_servicio, srv.name_servicio
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE s.empresa_id = ?
        """,
        (empresa_id,),
    ).fetchall()
    try:
        resumen = resumen_ejecucion_por_llaves(emp_conn, int(empresa_id), anio=year)
    except Exception:
        resumen = {}
    today = date.today()
    total = 0
    criticos = 0
    fs = 0
    mp = 0
    cal = 0
    docs = 0
    fuera_soporte = 0
    candidatos = 0
    bodega = 0
    sin_datos = 0
    for row in rows:
        item = dict(row)
        stats = lookup_resumen_llave(
            resumen, item.get("num_biomedica"), item.get("codigo_activo")
        )
        apply_flags_equipo(item, stats, year)
        if item.get("alerta_sin_datos_anio"):
            sin_datos += 1
        if is_en_bodega(item) or str(item.get("fecha_baja") or "").strip():
            if is_en_bodega(item):
                bodega += 1
            continue
        total += 1
        if is_equipo_critico(row["clasificacion_riesgo"], row["clasificacion_biomedica"]):
            criticos += 1
        if (row["estado"] or "") == "FUERA DE SERVICIO":
            fs += 1
        if row["aplica_mp"]:
            mp += 1
        if row["aplica_cal"] or row["aplica_val"]:
            cal += 1
        if row["manual_operacion"] and row["manual_servicio"]:
            docs += 1
        garantia = str(row["fecha_garantia"] or "").strip()[:10]
        if garantia:
            try:
                g = date.fromisoformat(garantia)
                if g < today:
                    fuera_soporte += 1
            except ValueError:
                pass
        vu = row["vida_util_anios"]
        start = str(row["fecha_operacion"] or row["fecha_compra"] or "").strip()[:10]
        if vu and start:
            try:
                start_d = date.fromisoformat(start)
                years = (today - start_d).days / 365.25
                if years >= float(vu):
                    candidatos += 1
            except (ValueError, TypeError):
                pass
    tecnicos = 0
    try:
        tecnicos = users_conn.execute(
            """
            SELECT COUNT(*) AS n FROM usuarios
            WHERE empresa_id = ?
              AND UPPER(COALESCE(ROLL,'')) = 'OPERATIVO'
              AND (
                UPPER(COALESCE(JOB,'')) LIKE '%INGENIER%'
                OR UPPER(COALESCE(JOB,'')) LIKE '%TECNIC%'
                OR UPPER(COALESCE(JOB,'')) LIKE '%TÉCNIC%'
              )
            """,
            (empresa_id,),
        ).fetchone()["n"]
    except Exception:
        tecnicos = 0
    return {
        "equipos_totales": total,
        "equipos_criticos": criticos,
        "tecnicos": int(tecnicos or 0),
        "fuera_servicio_unidades": fs,
        "mp_programados": mp,
        "cal_programadas": cal,
        "equipos_documentacion_completa": docs,
        "equipos_fuera_soporte": fuera_soporte,
        "equipos_candidatos_capex": candidatos,
        "equipos_bodega_baja": bodega,
        "equipos_sin_datos_anio": sin_datos,
        "alerta_sin_datos_mensaje": MENSAJE_SIN_DATOS_ANIO,
        "nota": (
            "Horas fuera de servicio, costos y algunos tiempos no están en el inventario. "
            "MP ejecutados, correctivos (incluye visitas de verificación) y horas de "
            "reparación se sugieren desde ejecución de mantenimientos del mes; "
            "el ingeniero puede ajustarlas."
        ),
    }


def snapshot_ejecucion_por_mes(emp_conn, empresa_id: int, anio: int) -> dict[int, dict]:
    """Conteos mensuales de ejecución; no lista eventos al cliente."""
    year = str(int(anio))
    try:
        rows = emp_conn.execute(
            """
            SELECT CAST(strftime('%m', fecha_ejecucion) AS INTEGER) AS mes,
                   SUM(CASE WHEN tipo_mantenimiento = 'preventivo' THEN 1 ELSE 0 END)
                       AS mp_ejecutados,
                   SUM(CASE WHEN tipo_mantenimiento IN ('correctivo', 'visita')
                            THEN 1 ELSE 0 END) AS correctivos,
                   SUM(CASE WHEN tipo_mantenimiento IN ('correctivo', 'visita')
                            THEN COALESCE(duracion_horas, 0) ELSE 0 END)
                       AS tiempo_reparacion_h,
                   SUM(CASE WHEN tipo_mantenimiento = 'visita' THEN 1 ELSE 0 END) AS visitas
            FROM ejecucion_mantenimientos
            WHERE empresa_id = ?
              AND fecha_ejecucion IS NOT NULL
              AND strftime('%Y', fecha_ejecucion) = ?
            GROUP BY mes
            """,
            (int(empresa_id), year),
        ).fetchall()
    except Exception:
        return {}
    out: dict[int, dict] = {}
    for row in rows:
        mes = int(row["mes"] or 0)
        if mes < 1 or mes > 12:
            continue
        n_vis = int(row["visitas"] or 0)
        horas = float(row["tiempo_reparacion_h"] or 0)
        item = {
            "mp_ejecutados": int(row["mp_ejecutados"] or 0),
            "correctivos": int(row["correctivos"] or 0),
            "visitas": n_vis,
        }
        if horas > 0:
            item["tiempo_reparacion_h"] = round(horas, 2)
        out[mes] = item
    return out


def catalogo_payload() -> dict:
    groups = []
    seen = []
    for key, label, group, hint in INPUT_FIELDS:
        if group not in seen:
            seen.append(group)
            groups.append({"grupo": group, "campos": []})
        groups[-1]["campos"].append({"key": key, "label": label, "hint": hint})
    return {
        "meses": list(MESES),
        "indicadores": list(INDICATORS),
        "interpretacion": INTERPRETACION,
        "entrada_grupos": groups,
        "guia": list(GUIA),
        "dashboard_keys": list(DASHBOARD_KEYS),
        "estados_decision": list(ESTADOS_DECISION),
    }
