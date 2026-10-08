"""Motor de frecuencia de mantenimiento preventivo (GE y fabricante).

GE y bandas TGE siguen el Anexo A.1 OMS (Fennigkoh y Smith, 1989).
Adaptación SIGTB: catálogos F/A/M/Hf y T_PM = min(T_GE, T_fab).
No es el modelo WHO Pi; las claves internas oms_* se conservan por compatibilidad de API.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any


# —— Catálogos (hoja Catalogos) ——
FUNCION_CATALOGO = [
    {
        "label": "Soporte vital",
        "puntaje": 10,
        "descripcion": "Equipo esencial para mantener funciones vitales",
        "ejemplo": "Ventilador mecánico / desfibrilador",
    },
    {
        "label": "Diagnóstico/monitoreo crítico",
        "puntaje": 7,
        "descripcion": "Monitoreo o diagnóstico de alto impacto clínico",
        "ejemplo": "Monitor / rayos X",
    },
    {
        "label": "Terapéutico o infusión",
        "puntaje": 5,
        "descripcion": "Administra tratamiento o soporte terapéutico",
        "ejemplo": "Bomba de infusión / electrobisturí",
    },
    {
        "label": "Apoyo no crítico",
        "puntaje": 3,
        "descripcion": "Apoyo operativo con bajo riesgo directo",
        "ejemplo": "Cama / balanza",
    },
]

APLICACION_CATALOGO = [
    {
        "label": "UCI / quirófano / transporte crítico",
        "puntaje": 9,
        "descripcion": "Uso en áreas críticas o pacientes de alto riesgo",
    },
    {
        "label": "Urgencias / hospitalización",
        "puntaje": 7,
        "descripcion": "Uso frecuente en atención clínica general",
    },
    {
        "label": "Consulta externa / apoyo diagnóstico",
        "puntaje": 5,
        "descripcion": "Uso programado o de menor urgencia",
    },
    {
        "label": "Administrativo / bajo riesgo",
        "puntaje": 3,
        "descripcion": "No interviene directamente en atención crítica",
    },
]

REQUISITO_CATALOGO = [
    {
        "label": "Especializado / complejo",
        "puntaje": 5,
        "descripcion": "Rutinas exhaustivas, pruebas funcionales o repuestos críticos",
    },
    {
        "label": "Importante",
        "puntaje": 4,
        "descripcion": "Checklist completo y verificación de parámetros",
    },
    {
        "label": "Usual / estándar",
        "puntaje": 3,
        "descripcion": "Limpieza, inspección, filtros o verificación básica",
    },
    {
        "label": "Mínimo",
        "puntaje": 1,
        "descripcion": "Rutina sencilla y bajo nivel de trazabilidad técnica",
    },
]

FALLAS_CATALOGO = [
    {
        "label": "Frecuentes",
        "puntaje": 2,
        "descripcion": "MTBF bajo o fallas repetitivas",
    },
    {
        "label": "Moderadas",
        "puntaje": 1,
        "descripcion": "Fallas ocasionales",
    },
    {
        "label": "Raras",
        "puntaje": 0,
        "descripcion": "MTBF alto o pocas fallas reportadas",
    },
]

OMS_REGLAS = [
    {
        "rango": "GE >= 19",
        "intervalo": "Cada 4 meses",
        "meses": 4,
        "accion": "Añadir inspecciones de rendimiento y seguridad",
        "interpretacion": "Alta criticidad",
    },
    {
        "rango": "15 <= GE <= 18",
        "intervalo": "Cada 6 meses",
        "meses": 6,
        "accion": "Programar inspección semestral",
        "interpretacion": "Criticidad media-alta",
    },
    {
        "rango": "12 <= GE <= 14",
        "intervalo": "Anual",
        "meses": 12,
        "accion": "Revisión preventiva anual básica",
        "interpretacion": "Criticidad media o baja",
    },
    {
        "rango": "GE < 12",
        "intervalo": "Sin frecuencia derivada",
        "meses": None,
        "accion": "Correctivo bajo demanda; usar criterio del fabricante si existe Tfab",
        "interpretacion": "Sin TGE; prevalece fabricante si hay PM",
    },
]

ESTADOS_EQUIPO = ["Operativo", "En observación", "Fuera de servicio", "Retirado"]

GUIA_USO = [
    "Pegue o diligencie el inventario en Inventario PM (desde el inventario del servicio).",
    "Seleccione función, aplicación, requisito de mantenimiento y antecedentes de fallas.",
    "Ingrese la frecuencia recomendada por el fabricante en meses.",
    "Revise el GE, el intervalo TGE y la frecuencia definitiva calculada.",
    "Consulte el Dashboard y el Cronograma PM.",
    "Exporte el Informe resumen o el cronograma como PDF.",
    "Actualice puntajes si cambian uso, criticidad, fallas o recomendación del fabricante.",
]

GUIA_NOTA = (
    "Adaptación operativa: GE = F+A+M+Hf. El intervalo TGE sale de bandas de GE "
    "(≥19 → 4 meses; 15–18 → 6; 12–14 → 12; <12 sin TGE). "
    "Si GE≥12, TPM = min(TGE, Tfab). Si GE<12 prevalece el fabricante cuando exige PM. "
    "No equivale al modelo WHO Pi / OMS."
)

TOOLTIPS = {
    "funcion": "Rol clínico del equipo (soporte vital, diagnóstico, terapéutico o apoyo).",
    "aplicacion": "Entorno de uso: determina el riesgo según el área asistencial.",
    "requisito": "Complejidad de la rutina de mantenimiento exigida.",
    "fallas": "Historial de fallas del equipo (frecuentes, moderadas o raras).",
    "pm_fabricante": "Intervalo en meses recomendado por el fabricante.",
    "ge": "GE = F + A + M + Hf. Si falta un componente el resultado es Revisar.",
    "oms": "Intervalo TGE derivado del GE (≥19 → 4 meses; 15–18 → 6; 12–14 → anual; <12 sin TGE).",
    "definitiva": "Si GE≥12: TPM = min(TGE, Tfab). Si GE<12: prevalece fabricante si hay PM.",
    "fecha_ultimo_pm": "Punto de partida del cronograma automático anual.",
    "cronograma": "Marca PM en los meses calculados desde la fecha del último mantenimiento.",
    "validacion": "El operativo marca cumplimiento; el coordinador asistencial aprueba o rechaza.",
    "ejecucion": (
        "Historial de preventivos, correctivos y visitas. Las visitas cuentan como "
        "correctivo solo si hay duración verificable (fecha de cierre − fecha de atención). "
        "Sin esas fechas se conserva el % institucional sobre MP. Llave: "
        "Código Biomédica + Código de Activo."
    ),
    "fdef_historial": (
        "Frecuencia ajustada = (F teórica TPM + F real del historial) / 2. "
        "Si falta historial se conserva la teórica; no bloquea otros módulos."
    ),
}


def _score_map(catalog: list[dict]) -> dict[str, float]:
    return {item["label"]: float(item["puntaje"]) for item in catalog}


FUNCION_SCORES = _score_map(FUNCION_CATALOGO)
APLICACION_SCORES = _score_map(APLICACION_CATALOGO)
REQUISITO_SCORES = _score_map(REQUISITO_CATALOGO)
FALLAS_SCORES = _score_map(FALLAS_CATALOGO)


def lookup_puntaje(catalog_scores: dict[str, float], label: str | None) -> float | None:
    if not label:
        return None
    return catalog_scores.get(str(label).strip())


def calc_ge(
    puntaje_funcion=None,
    puntaje_aplicacion=None,
    puntaje_requisito=None,
    puntaje_fallas=None,
) -> float | None:
    """GE = F + A + M + Hf. Si falta alguno → None (Revisar)."""
    vals = [puntaje_funcion, puntaje_aplicacion, puntaje_requisito, puntaje_fallas]
    if any(v is None or v == "" for v in vals):
        return None
    try:
        return float(vals[0]) + float(vals[1]) + float(vals[2]) + float(vals[3])
    except (TypeError, ValueError):
        return None


def oms_meses_from_ge(ge: float | None) -> int | None:
    if ge is None:
        return None
    if ge >= 19:
        return 4
    if ge >= 15:
        return 6
    if ge >= 12:
        return 12
    return None


def frecuencia_oms_label(ge: float | None) -> str | None:
    if ge is None:
        return None
    meses = oms_meses_from_ge(ge)
    if meses == 4:
        return "Cada 4 meses"
    if meses == 6:
        return "Cada 6 meses"
    if meses == 12:
        return "Anual"
    return "Correctivo bajo demanda"


def frecuencia_label_from_meses(meses: int | None) -> str:
    if meses == 4:
        return "Cada 4 meses"
    if meses == 6:
        return "Cada 6 meses"
    if meses == 12:
        return "Anual"
    if meses and meses > 0:
        return f"PM fabricante cada {int(meses)} meses"
    return "Correctivo bajo demanda"


def parse_frecuencia_meses(label: str | None) -> int | None:
    """Convierte etiqueta de frecuencia a intervalo en meses."""
    if not label:
        return None
    text = str(label)
    if "Correctivo" in text:
        return None
    if "4" in text and "mes" in text.lower():
        return 4
    if "6" in text and "mes" in text.lower():
        return 6
    if "Anual" in text:
        return 12
    # "PM fabricante cada N meses"
    import re

    m = re.search(r"cada\s+(\d+)\s+meses", text, re.I)
    if m:
        return int(m.group(1))
    return None


def equipo_fuera_de_programa_pm(row: dict | None) -> bool:
    """Bajas, bodegas, fuera de servicio o 'no aplica MP' no entran al cronograma anual."""
    data = row or {}
    try:
        from server.inventario import is_equipo_baja

        if is_equipo_baja(data):
            return True
    except Exception:
        pass
    estado = str(data.get("estado") or "").strip().casefold()
    if estado in {"retirado", "fuera de servicio", "baja"}:
        return True
    if data.get("fecha_baja"):
        return True
    aplica = data.get("aplica_mp")
    if aplica in (0, "0", False):
        return True
    inv_estado = str(data.get("estado_inventario") or "").strip().upper()
    if inv_estado in {"FUERA DE SERVICIO", "BAJA"}:
        return True
    return False


def frecuencia_definitiva(ge: float | None, pm_fabricante_meses=None) -> str | None:
    """
    TFM:
    - Componentes faltantes (ge is None) → Revisar
    - GE < 12: Tfab si existe; si no, sin frecuencia derivada
    - GE ≥ 12: TPM = min(TGE, Tfab)
    """
    if ge is None:
        return "Revisar"
    try:
        fab = float(pm_fabricante_meses) if pm_fabricante_meses not in (None, "") else None
    except (TypeError, ValueError):
        fab = None

    if ge < 12:
        if fab and fab > 0:
            return f"PM fabricante cada {int(fab)} meses"
        return "Correctivo bajo demanda"

    oms = oms_meses_from_ge(ge)
    if fab is None:
        return frecuencia_oms_label(ge)
    chosen = min(int(fab), int(oms)) if oms else int(fab)
    return frecuencia_label_from_meses(chosen)


def accion_sugerida(ge: float | None) -> str | None:
    if ge is None:
        return None
    if ge >= 19:
        return "PM fabricante + inspecciones de seguridad y rendimiento cada 4 meses"
    if ge >= 15:
        return "PM/inspección semestral con checklist completo"
    if ge >= 12:
        return "Inspección preventiva anual básica"
    return "Correctivo bajo demanda; evaluar inclusión por criterio institucional"


def add_months(d: date, months: int) -> date:
    """Suma meses conservando día válido (equivalente práctico a EDATE)."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            return datetime.strptime(iso.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    dt = re.search(
        r"datetime\.datetime\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})",
        text,
    )
    if dt:
        try:
            return date(int(dt.group(1)), int(dt.group(2)), int(dt.group(3)))
        except ValueError:
            return None
    return None


def build_cronograma_meses(
    fecha_ultimo_pm,
    frecuencia_label: str | None,
    anio: int,
    max_cycles: int = 30,
) -> dict[str, Any]:
    """
    Marca meses del año con 'PM' según:
    mes = Fecha_ultimo_PM + n × Frecuencia_definitiva  (n = 1..max_cycles)
    Si es Correctivo → no programa.
    """
    meses = {i: 0 for i in range(1, 13)}
    last = parse_date(fecha_ultimo_pm)
    interval = parse_frecuencia_meses(frecuencia_label)
    if not last or not interval:
        obs = (
            "No programar PM; atender correctivo bajo demanda"
            if frecuencia_label and "Correctivo" in str(frecuencia_label)
            else "Sin fecha de último PM u intervalo para programar"
        )
        return {"meses": meses, "observacion": obs, "fechas": []}

    fechas = []
    for n in range(1, max_cycles + 1):
        prog = add_months(last, interval * n)
        if prog.year > anio + 1:
            break
        if prog.year == anio:
            meses[prog.month] = 1
            fechas.append(prog.isoformat())

    return {
        "meses": meses,
        "observacion": "Programado automáticamente desde la fecha del último mantenimiento",
        "fechas": fechas,
    }


def enrich_row(body: dict) -> dict:
    """Completa puntajes, GE, OMS, definitiva y acción a partir de catálogos."""
    funcion = (body.get("funcion") or "").strip() or None
    aplicacion = (body.get("aplicacion") or "").strip() or None
    requisito = (body.get("requisito_mantto") or "").strip() or None
    fallas = (body.get("antecedentes_fallas") or "").strip() or None

    pf = lookup_puntaje(FUNCION_SCORES, funcion)
    pa = lookup_puntaje(APLICACION_SCORES, aplicacion)
    pr = lookup_puntaje(REQUISITO_SCORES, requisito)
    pfa = lookup_puntaje(FALLAS_SCORES, fallas)

    ge = calc_ge(pf, pa, pr, pfa)
    oms = frecuencia_oms_label(ge)
    fab = body.get("pm_fabricante_meses")
    definitiva = frecuencia_definitiva(ge, fab)
    accion = accion_sugerida(ge)
    estado_ge = "Revisar" if ge is None else "Calculado"

    out = {
        **body,
        "funcion": funcion,
        "aplicacion": aplicacion,
        "requisito_mantto": requisito,
        "antecedentes_fallas": fallas,
        "puntaje_funcion": pf,
        "puntaje_aplicacion": pa,
        "puntaje_requisito": pr,
        "puntaje_fallas": pfa,
        "ge_total": ge,
        "estado_ge": estado_ge,
        "frecuencia_oms": oms,
        "frecuencia_definitiva": definitiva,
        "accion_sugerida": accion,
    }
    return out


def dashboard_stats(rows: list[dict]) -> dict:
    evaluated = [r for r in rows if r.get("ge_total") is not None]
    total = len([r for r in rows if r.get("equipo")])
    ge_vals = [float(r["ge_total"]) for r in evaluated]
    buckets = {
        "ge_ge_19": sum(1 for g in ge_vals if g >= 19),
        "ge_15_19": sum(1 for g in ge_vals if 15 <= g < 19),
        "ge_12_15": sum(1 for g in ge_vals if 12 <= g < 15),
        "ge_lt_12": sum(1 for g in ge_vals if 0 < g < 12),
    }
    avg = sum(ge_vals) / len(ge_vals) if ge_vals else 0.0

    freq_counts = {
        "Cada 4 meses": 0,
        "Cada 6 meses": 0,
        "Anual": 0,
        "Correctivo bajo demanda": 0,
        "Otro": 0,
    }
    for r in rows:
        lab = r.get("frecuencia_definitiva") or ""
        if lab == "Cada 4 meses":
            freq_counts["Cada 4 meses"] += 1
        elif lab == "Cada 6 meses":
            freq_counts["Cada 6 meses"] += 1
        elif lab == "Anual":
            freq_counts["Anual"] += 1
        elif "Correctivo" in lab:
            freq_counts["Correctivo bajo demanda"] += 1
        elif lab:
            freq_counts["Otro"] += 1

    by_servicio: dict[str, dict] = {}
    for r in rows:
        srv = r.get("servicio_nombre") or r.get("servicio") or "—"
        bucket = by_servicio.setdefault(
            srv, {"servicio": srv, "alta": 0, "media_alta": 0, "media": 0, "baja": 0, "total": 0}
        )
        bucket["total"] += 1
        g = r.get("ge_total")
        if g is None:
            continue
        g = float(g)
        if g >= 19:
            bucket["alta"] += 1
        elif g >= 15:
            bucket["media_alta"] += 1
        elif g >= 12:
            bucket["media"] += 1
        else:
            bucket["baja"] += 1

    n_prev = n_corr = n_vis = con_hist = 0
    for r in rows:
        ej = r.get("ejecucion") or {}
        real = ej.get("real") or {}
        n_prev += int(real.get("preventivos") or 0)
        n_corr += int(real.get("correctivos") or 0)
        n_vis += int(real.get("visitas") or 0)
        if int(ej.get("n_eventos") or 0) > 0:
            con_hist += 1

    return {
        "total_equipos": total,
        **buckets,
        "promedio_ge": round(avg, 2),
        "frecuencias": freq_counts,
        "ejecucion": {
            "equipos_con_historial": con_hist,
            "preventivos": n_prev,
            "correctivos": n_corr + n_vis,
            "correctivos_mc": n_corr,
            "visitas": n_vis,
        },
        "criticidad_por_servicio": list(by_servicio.values()),
        "ejemplos": [
            {
                "equipo": r.get("equipo"),
                "servicio": r.get("servicio_nombre") or r.get("servicio"),
                "ge_total": r.get("ge_total"),
                "frecuencia_definitiva": r.get("frecuencia_definitiva"),
                "accion_sugerida": r.get("accion_sugerida"),
            }
            for r in rows[:10]
        ],
    }


def catalogs_payload() -> dict:
    return {
        "funcion": FUNCION_CATALOGO,
        "aplicacion": APLICACION_CATALOGO,
        "requisito_mantto": REQUISITO_CATALOGO,
        "antecedentes_fallas": FALLAS_CATALOGO,
        "oms_reglas": OMS_REGLAS,
        "estados": ESTADOS_EQUIPO,
        "guia_uso": GUIA_USO,
        "guia_nota": GUIA_NOTA,
        "tooltips": TOOLTIPS,
    }


# —— Ejecución de mantenimientos: llave compuesta y frecuencia real ——

TIPOS_EJECUCION = ("preventivo", "correctivo", "visita")
FUENTES_EJECUCION = ("manual", "importado", "sincronizado")
_CODIGO_VACIO = {
    "",
    "0",
    "00",
    "NA",
    "N/A",
    "NONE",
    "NULL",
    "-",
    "—",
    "NR",
    "SN",
    "S/N",
    "NOPORTA",
}
_NORM_COLUMNS = {
    "num_biomedica",
    "codigo_activo",
    "codigo_biomedica",
    "codigo_equipo",
    "ie.num_biomedica",
    "ie.codigo_activo",
    "em.codigo_biomedica",
    "em.codigo_activo",
}


def normalize_codigo(codigo) -> str:
    """Normaliza Código Biomédica / Código de Activo para comparar entre sedes."""
    if codigo is None:
        return ""
    text = str(codigo).strip().upper().replace(" ", "").replace("-", "")
    if text in _CODIGO_VACIO:
        return ""
    return text


def sql_norm_expr(column: str) -> str:
    if column not in _NORM_COLUMNS:
        raise ValueError("columna no permitida para normalización")
    raw = f"REPLACE(REPLACE(UPPER(TRIM(COALESCE({column}, ''))), ' ', ''), '-', '')"
    vacios = ",".join("'" + valor.replace("'", "''") + "'" for valor in sorted(_CODIGO_VACIO))
    return f"(CASE WHEN {raw} IN ({vacios}) THEN '' ELSE {raw} END)"


def llave_compuesta(codigo_biomedica, codigo_activo) -> tuple[str, str]:
    return normalize_codigo(codigo_biomedica), normalize_codigo(codigo_activo)


def clasificar_coincidencia(query_bio: str, query_act: str, row_bio: str, row_act: str) -> str | None:
    """exacta | variante | parcial_biomedica | parcial_activo | None."""
    q_bio, q_act = normalize_codigo(query_bio), normalize_codigo(query_act)
    r_bio, r_act = normalize_codigo(row_bio), normalize_codigo(row_act)
    if not q_bio and not q_act:
        return None
    bio_ok = bool(q_bio) and q_bio == r_bio
    act_ok = bool(q_act) and q_act == r_act
    if bio_ok and act_ok:
        return "exacta"
    if bio_ok and act_ok is False and (not q_act or not r_act):
        return "parcial_biomedica"
    if act_ok and bio_ok is False and (not q_bio or not r_bio):
        return "parcial_activo"
    if bio_ok:
        return "parcial_biomedica"
    if act_ok:
        return "parcial_activo"
    return None


def frecuencia_real_desde_fechas(fechas) -> float | None:
    """Intervalo promedio en meses entre preventivos (mínimo 2 fechas distintas)."""
    parsed = []
    seen = set()
    for raw in fechas or []:
        d = parse_date(raw)
        if d and d not in seen:
            seen.add(d)
            parsed.append(d)
    parsed.sort()
    if len(parsed) < 2:
        return None
    span_days = (parsed[-1] - parsed[0]).days
    if span_days <= 0:
        return None
    return round(span_days / 30.437 / (len(parsed) - 1), 2)


def frecuencia_real_desde_resumen(n_preventivos, primera, ultima) -> float | None:
    try:
        n_prev = int(n_preventivos or 0)
    except (TypeError, ValueError):
        n_prev = 0
    first = parse_date(primera)
    last = parse_date(ultima)
    if n_prev < 2 or not first or not last:
        return None
    span_days = (last - first).days
    if span_days <= 0:
        return None
    return round(span_days / 30.437 / (n_prev - 1), 2)


def preventivos_por_anio(n_preventivos, primera, ultima) -> float | None:
    try:
        n_prev = int(n_preventivos or 0)
    except (TypeError, ValueError):
        return None
    if n_prev <= 0:
        return None
    first = parse_date(primera)
    last = parse_date(ultima)
    if not first or not last or last <= first:
        return float(n_prev)
    years = max((last - first).days / 365.25, 1 / 12)
    return round(n_prev / years, 2)


def frecuencia_teorica_componentes(
    *,
    ge=None,
    pm_fabricante_meses=None,
    grupo_meses=None,
    frecuencia_tpm_label=None,
) -> dict:
    oms = oms_meses_from_ge(ge) if ge is not None else None
    try:
        fab = float(pm_fabricante_meses) if pm_fabricante_meses not in (None, "") else None
    except (TypeError, ValueError):
        fab = None
    try:
        grupo = float(grupo_meses) if grupo_meses not in (None, "") else None
    except (TypeError, ValueError):
        grupo = None
    tpm = parse_frecuencia_meses(frecuencia_tpm_label)
    if tpm is None:
        tpm = parse_frecuencia_meses(frecuencia_definitiva(ge, fab))
    return {
        "oms_meses": oms,
        "fabricante_meses": fab,
        "grupo_meses": grupo,
        "tpm_meses": tpm,
    }


def frecuencia_ajustada_historial(f_teorica, f_real) -> dict:
    """Fdef = (Fteórica + Freal) / 2. Si falta un lado, se usa el disponible."""
    try:
        teorica = float(f_teorica) if f_teorica not in (None, "") else None
        if teorica is not None and teorica <= 0:
            teorica = None
    except (TypeError, ValueError):
        teorica = None
    try:
        real = float(f_real) if f_real not in (None, "") else None
        if real is not None and real <= 0:
            real = None
    except (TypeError, ValueError):
        real = None

    if teorica is not None and real is not None:
        meses = round((teorica + real) / 2.0, 2)
        origen = "teorica_real"
    elif teorica is not None:
        meses = round(teorica, 2)
        origen = "teorica"
    elif real is not None:
        meses = round(real, 2)
        origen = "real"
    else:
        return {
            "f_teorica_meses": None,
            "f_real_meses": None,
            "f_def_meses": None,
            "f_def_label": None,
            "origen": "sin_datos",
        }

    label = frecuencia_label_from_meses(int(round(meses)))
    if meses and meses not in (4, 6, 12) and "Correctivo" not in label:
        label = f"Cada {meses:g} meses"
    return {
        "f_teorica_meses": teorica,
        "f_real_meses": real,
        "f_def_meses": meses,
        "f_def_label": label,
        "origen": origen,
    }


def estructura_frecuencia_equipo(
    *,
    ge=None,
    pm_fabricante_meses=None,
    grupo_meses=None,
    frecuencia_tpm_label=None,
    n_preventivos=0,
    n_correctivos=0,
    n_visitas=0,
    primera_prev=None,
    ultima_prev=None,
) -> dict:
    teorica = frecuencia_teorica_componentes(
        ge=ge,
        pm_fabricante_meses=pm_fabricante_meses,
        grupo_meses=grupo_meses,
        frecuencia_tpm_label=frecuencia_tpm_label,
    )
    f_real = frecuencia_real_desde_resumen(n_preventivos, primera_prev, ultima_prev)
    ajustada = frecuencia_ajustada_historial(teorica.get("tpm_meses"), f_real)
    return {
        "teorica": teorica,
        "real": {
            "preventivos": int(n_preventivos or 0),
            "correctivos": int(n_correctivos or 0),
            "visitas": int(n_visitas or 0),
            "intervalo_promedio_meses": f_real,
            "preventivos_por_anio": preventivos_por_anio(n_preventivos, primera_prev, ultima_prev),
            "primera_preventivo": str(primera_prev)[:10] if primera_prev else None,
            "ultima_preventivo": str(ultima_prev)[:10] if ultima_prev else None,
        },
        "definitiva": ajustada,
    }


def _sede_filtro_sql(sede_ids: set[int] | None) -> tuple[str, list]:
    if not sede_ids:
        return "", []
    ids = sorted({int(x) for x in sede_ids})
    placeholders = ",".join("?" * len(ids))
    return f" AND s.id IN ({placeholders}) ", ids


def buscar_semejanzas(
    conn,
    empresa_id: int,
    *,
    codigo_biomedica=None,
    codigo_activo=None,
    q=None,
    sede_ids: set[int] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Coincidencias exactas y parciales de la llave en todas las sedes de la empresa."""
    try:
        limit = max(1, min(int(limit or 50), 50))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    q_bio = normalize_codigo(codigo_biomedica)
    q_act = normalize_codigo(codigo_activo)
    q_free = normalize_codigo(q)
    if not q_bio and not q_act and q_free:
        q_bio = q_free
        q_act = q_free
    if not q_bio and not q_act:
        return {"ok": True, "total": 0, "items": [], "query": {"codigo_biomedica": "", "codigo_activo": ""}}

    bio_expr = sql_norm_expr("ie.num_biomedica")
    act_expr = sql_norm_expr("ie.codigo_activo")
    sede_sql, sede_params = _sede_filtro_sql(sede_ids)
    clauses = ["s.empresa_id = ?"]
    params: list = [int(empresa_id)]
    or_bits = []
    if q_bio:
        or_bits.append(f"{bio_expr} = ?")
        params.append(q_bio)
        or_bits.append(f"{bio_expr} LIKE ?")
        params.append(f"%{q_bio}%")
    if q_act:
        or_bits.append(f"{act_expr} = ?")
        params.append(q_act)
        or_bits.append(f"{act_expr} LIKE ?")
        params.append(f"%{q_act}%")
    clauses.append("(" + " OR ".join(or_bits) + ")")
    where = " AND ".join(clauses) + sede_sql
    params.extend(sede_params)

    total = conn.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE {where}
        """,
        params,
    ).fetchone()["n"]

    rows = conn.execute(
        f"""
        SELECT ie.id, ie.num_biomedica, ie.codigo_activo, ie.equipo, ie.estado,
               ie.servicio_id, srv.name_servicio, srv.ID_servicio,
               s.id AS sede_id, s.name_sede, s.ID_sede, s.empresa_id
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE {where}
        ORDER BY ie.equipo COLLATE NOCASE, ie.id
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()

    items = []
    for row in rows:
        kind = clasificar_coincidencia(q_bio, q_act, row["num_biomedica"], row["codigo_activo"])
        if kind is None and q_free:
            n_bio = normalize_codigo(row["num_biomedica"])
            n_act = normalize_codigo(row["codigo_activo"])
            if q_free in n_bio or q_free in n_act:
                kind = "variante"
        items.append(
            {
                "inventario_id": row["id"],
                "codigo_biomedica": row["num_biomedica"],
                "codigo_activo": row["codigo_activo"],
                "codigo_biomedica_norm": normalize_codigo(row["num_biomedica"]),
                "codigo_activo_norm": normalize_codigo(row["codigo_activo"]),
                "equipo": row["equipo"],
                "estado": row["estado"],
                "servicio_id": row["servicio_id"],
                "name_servicio": row["name_servicio"],
                "sede_id": row["sede_id"],
                "name_sede": row["name_sede"],
                "coincidencia": kind or "variante",
            }
        )
    return {
        "ok": True,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "query": {"codigo_biomedica": q_bio, "codigo_activo": q_act},
        "items": items,
    }


def equipos_duplicados(
    conn,
    empresa_id: int,
    *,
    sede_ids: set[int] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Misma llave normalizada en más de un servicio o sede."""
    try:
        limit = max(1, min(int(limit or 50), 50))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    bio_expr = sql_norm_expr("ie.num_biomedica")
    act_expr = sql_norm_expr("ie.codigo_activo")
    sede_sql, sede_params = _sede_filtro_sql(sede_ids)
    params = [int(empresa_id), *sede_params]
    total = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT {bio_expr} AS bio_norm, {act_expr} AS act_norm
            FROM inventario_equipos ie
            JOIN servicios srv ON srv.id = ie.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            WHERE s.empresa_id = ? {sede_sql}
            GROUP BY bio_norm, act_norm
            HAVING bio_norm != '' AND act_norm != ''
               AND (COUNT(*) > 1 OR COUNT(DISTINCT s.id) > 1)
        )
        """,
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT {bio_expr} AS bio_norm, {act_expr} AS act_norm,
               COUNT(*) AS n_equipos,
               COUNT(DISTINCT s.id) AS n_sedes,
               COUNT(DISTINCT srv.id) AS n_servicios
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE s.empresa_id = ? {sede_sql}
        GROUP BY bio_norm, act_norm
        HAVING bio_norm != '' AND act_norm != ''
           AND (COUNT(*) > 1 OR COUNT(DISTINCT s.id) > 1)
        ORDER BY n_sedes DESC, n_equipos DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    return {
        "ok": True,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


def _sum_int(items: list[dict], key: str) -> int:
    return sum(int(item.get(key) or 0) for item in items)


def _sum_float(items: list[dict], key: str) -> float:
    return sum(float(item.get(key) or 0) for item in items)


def _min_date_key(items: list[dict], key: str):
    vals = [str(item.get(key)) for item in items if item.get(key)]
    return min(vals) if vals else None


def _max_date_key(items: list[dict], key: str):
    vals = [str(item.get(key)) for item in items if item.get(key)]
    return max(vals) if vals else None


def _merge_resumen_stats(items: list[dict]) -> dict:
    if not items:
        return {}
    return {
        "n_total": _sum_int(items, "n_total"),
        "n_preventivos": _sum_int(items, "n_preventivos"),
        "n_correctivos": _sum_int(items, "n_correctivos"),
        "n_visitas": _sum_int(items, "n_visitas"),
        "n_preventivos_12m": _sum_int(items, "n_preventivos_12m"),
        "n_correctivos_12m": _sum_int(items, "n_correctivos_12m"),
        "n_visitas_12m": _sum_int(items, "n_visitas_12m"),
        "h_correctivos": _sum_float(items, "h_correctivos"),
        "h_visitas": _sum_float(items, "h_visitas"),
        "h_correctivos_12m": _sum_float(items, "h_correctivos_12m"),
        "h_visitas_12m": _sum_float(items, "h_visitas_12m"),
        "n_corr_con_horas": _sum_int(items, "n_corr_con_horas"),
        "n_vis_con_horas": _sum_int(items, "n_vis_con_horas"),
        "primera_prev": _min_date_key(items, "primera_prev"),
        "ultima_prev": _max_date_key(items, "ultima_prev"),
        "primera_corr": _min_date_key(items, "primera_corr"),
        "ultima_corr": _max_date_key(items, "ultima_corr"),
        "primera_vis": _min_date_key(items, "primera_vis"),
        "ultima_vis": _max_date_key(items, "ultima_vis"),
        "primera_ev": _min_date_key(items, "primera_ev"),
        "ultima_ev": _max_date_key(items, "ultima_ev"),
    }


def tasa_anual_eventos(n_12m, n_all, primera, ultima, *, today=None) -> float:
    """Conteos anuales: ventana de 12 meses si hay historia larga; si no, anualiza (≥ 60 días)."""
    today = today or date.today()
    n12 = int(n_12m or 0)
    nall = int(n_all or 0)
    if nall <= 0 and n12 <= 0:
        return 0.0
    start = parse_date(primera)
    end = parse_date(ultima)
    if start and (today - start).days >= 365:
        return float(n12 if n12 > 0 else nall)
    if start:
        last = end if end and end > start else today
        span = (last - start).days
        if span >= 60:
            base = nall if nall > 0 else n12
            return round(base * 365.25 / max(span, 1), 2)
        return float(nall or n12)
    return float(nall or n12)


def horas_anuales_desde_resumen(
    h_12m,
    h_all,
    primera,
    ultima,
    n_con_horas,
    *,
    today=None,
) -> float | None:
    """Horas/año de un tipo de evento. None si no hay duraciones registradas."""
    if int(n_con_horas or 0) <= 0:
        return None
    h12 = float(h_12m or 0)
    hall = float(h_all or 0)
    if hall <= 0 and h12 <= 0:
        return None
    today = today or date.today()
    start = parse_date(primera)
    end = parse_date(ultima)
    if start and (today - start).days >= 365:
        return round(h12 if h12 > 0 else hall, 2)
    if start:
        last = end if end and end > start else today
        span = (last - start).days
        if span >= 60:
            return round(hall * 365.25 / max(span, 1), 2)
        return round(hall or h12, 2)
    return round(hall or h12, 2)


def enrich_dim_fila_con_ejecucion(payload: dict, stats: dict | None) -> None:
    """
    Inyecta histórico de correctivos solo con horas verificables
    (fecha de cierre − fecha de atención, persistidas en duracion_horas).
    MC y visitas sin duración no inventan horas: se mantiene el % de MP.
    El overlay manual (Sí + horas) tiene prioridad. No duplica visitas en acompañamiento.
    Si stats trae anio_filtro, solo cuenta eventos de ese año (no anualiza otros años).
    """
    stats = stats or {}
    n_corr = int(stats.get("n_correctivos") or 0)
    n_vis = int(stats.get("n_visitas") or 0)
    payload["ejecucion_preventivos"] = int(stats.get("n_preventivos") or 0)
    payload["ejecucion_correctivos"] = n_corr
    payload["ejecucion_visitas"] = n_vis

    if stats.get("anio_filtro") is not None:
        h_corr = (
            round(float(stats.get("h_correctivos") or 0), 2)
            if n_corr > 0 and int(stats.get("n_corr_con_horas") or 0) > 0
            else None
        )
        h_vis = (
            round(float(stats.get("h_visitas") or 0), 2)
            if n_vis > 0 and int(stats.get("n_vis_con_horas") or 0) > 0
            else None
        )
        if h_corr is not None and h_corr <= 0:
            h_corr = None
        if h_vis is not None and h_vis <= 0:
            h_vis = None
    else:
        h_corr = horas_anuales_desde_resumen(
            stats.get("h_correctivos_12m"),
            stats.get("h_correctivos"),
            stats.get("primera_corr") or stats.get("primera_ev"),
            stats.get("ultima_corr") or stats.get("ultima_ev"),
            stats.get("n_corr_con_horas"),
        )
        h_vis = horas_anuales_desde_resumen(
            stats.get("h_visitas_12m"),
            stats.get("h_visitas"),
            stats.get("primera_vis") or stats.get("primera_ev"),
            stats.get("ultima_vis") or stats.get("ultima_ev"),
            stats.get("n_vis_con_horas"),
        )
    partes = [h for h in (h_corr, h_vis) if h is not None]
    manual_hist = bool(payload.get("tiene_historico_correctivo")) and payload.get(
        "historico_correctivo_h"
    ) not in (None, "")

    if manual_hist:
        payload["fuente_correctivo"] = "manual"
    elif partes:
        payload["tiene_historico_correctivo"] = True
        payload["historico_correctivo_h"] = round(sum(partes), 2)
        payload["fuente_correctivo"] = "ejecucion"
    elif (n_corr + n_vis) > 0:
        payload["fuente_correctivo"] = "estimado_con_eventos"
    else:
        payload["fuente_correctivo"] = "estimado"

    try:
        acomp = float(payload.get("acompanamiento_h") or 0)
    except (TypeError, ValueError):
        acomp = 0.0
    if acomp > 0:
        payload["fuente_visitas"] = "manual"
    elif h_vis is not None:
        payload["fuente_visitas"] = "en_correctivo"
    elif n_vis > 0:
        payload["fuente_visitas"] = "sin_duracion"
    else:
        payload["fuente_visitas"] = "ninguna"


def lookup_resumen_llave(resumen: dict[tuple[str, str], dict], codigo_biomedica, codigo_activo) -> dict:
    """Resuelve historial por par, o por biomédica / activo si un lado está vacío."""
    bio, act = llave_compuesta(codigo_biomedica, codigo_activo)
    if not resumen:
        return {}
    if (bio, act) in resumen and (bio or act):
        return resumen[(bio, act)]
    if bio:
        merged = _merge_resumen_stats([stats for (b, _a), stats in resumen.items() if b == bio])
        if merged:
            return merged
    if act:
        merged = _merge_resumen_stats([stats for (_b, a), stats in resumen.items() if a == act])
        if merged:
            return merged
    return {}


def resumen_ejecucion_por_llaves(
    conn, empresa_id: int, anio: int | None = None
) -> dict[tuple[str, str], dict]:
    """Agregado por llave. Una sola consulta; no carga eventos al cliente.

    Si anio está definido, n_* y horas son solo de ese año. ultima_ev sigue siendo
    la fecha más reciente de todo el historial (para gestión documental de bajas).
    """
    if anio is None:
        return _resumen_ejecucion_all(conn, empresa_id)
    return _resumen_ejecucion_anio(conn, empresa_id, int(anio))


def _resumen_ejecucion_all(conn, empresa_id: int) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        """
        SELECT codigo_biomedica_norm, codigo_activo_norm,
               COUNT(*) AS n_total,
               SUM(CASE WHEN tipo_mantenimiento = 'preventivo' THEN 1 ELSE 0 END) AS n_preventivos,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo' THEN 1 ELSE 0 END) AS n_correctivos,
               SUM(CASE WHEN tipo_mantenimiento = 'visita' THEN 1 ELSE 0 END) AS n_visitas,
               SUM(CASE WHEN tipo_mantenimiento = 'preventivo'
                         AND fecha_ejecucion >= date('now', '-12 months') THEN 1 ELSE 0 END) AS n_preventivos_12m,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND fecha_ejecucion >= date('now', '-12 months') THEN 1 ELSE 0 END) AS n_correctivos_12m,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND fecha_ejecucion >= date('now', '-12 months') THEN 1 ELSE 0 END) AS n_visitas_12m,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_correctivos,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_visitas,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND fecha_ejecucion >= date('now', '-12 months')
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_correctivos_12m,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND fecha_ejecucion >= date('now', '-12 months')
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_visitas_12m,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND duracion_horas IS NOT NULL AND duracion_horas > 0 THEN 1 ELSE 0 END) AS n_corr_con_horas,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND duracion_horas IS NOT NULL AND duracion_horas > 0 THEN 1 ELSE 0 END) AS n_vis_con_horas,
               MIN(CASE WHEN tipo_mantenimiento = 'preventivo' THEN fecha_ejecucion END) AS primera_prev,
               MAX(CASE WHEN tipo_mantenimiento = 'preventivo' THEN fecha_ejecucion END) AS ultima_prev,
               MIN(CASE WHEN tipo_mantenimiento = 'correctivo' THEN fecha_ejecucion END) AS primera_corr,
               MAX(CASE WHEN tipo_mantenimiento = 'correctivo' THEN fecha_ejecucion END) AS ultima_corr,
               MIN(CASE WHEN tipo_mantenimiento = 'visita' THEN fecha_ejecucion END) AS primera_vis,
               MAX(CASE WHEN tipo_mantenimiento = 'visita' THEN fecha_ejecucion END) AS ultima_vis,
               MIN(fecha_ejecucion) AS primera_ev,
               MAX(fecha_ejecucion) AS ultima_ev
        FROM ejecucion_mantenimientos
        WHERE empresa_id = ?
        GROUP BY codigo_biomedica_norm, codigo_activo_norm
        """,
        (int(empresa_id),),
    ).fetchall()
    out = {}
    for row in rows:
        key = (row["codigo_biomedica_norm"] or "", row["codigo_activo_norm"] or "")
        out[key] = dict(row)
    return out


def _resumen_ejecucion_anio(conn, empresa_id: int, anio: int) -> dict[tuple[str, str], dict]:
    year = f"{max(2000, min(2100, int(anio))):04d}"
    rows = conn.execute(
        """
        SELECT codigo_biomedica_norm, codigo_activo_norm,
               COUNT(*) AS n_total_all,
               SUM(CASE WHEN strftime('%Y', fecha_ejecucion) = ? THEN 1 ELSE 0 END) AS n_total,
               SUM(CASE WHEN tipo_mantenimiento = 'preventivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN 1 ELSE 0 END) AS n_preventivos,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN 1 ELSE 0 END) AS n_correctivos,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN 1 ELSE 0 END) AS n_visitas,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND strftime('%Y', fecha_ejecucion) = ?
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_correctivos,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND strftime('%Y', fecha_ejecucion) = ?
                         THEN COALESCE(duracion_horas, 0) ELSE 0 END) AS h_visitas,
               SUM(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND strftime('%Y', fecha_ejecucion) = ?
                         AND duracion_horas IS NOT NULL AND duracion_horas > 0 THEN 1 ELSE 0 END) AS n_corr_con_horas,
               SUM(CASE WHEN tipo_mantenimiento = 'visita'
                         AND strftime('%Y', fecha_ejecucion) = ?
                         AND duracion_horas IS NOT NULL AND duracion_horas > 0 THEN 1 ELSE 0 END) AS n_vis_con_horas,
               MIN(fecha_ejecucion) AS primera_ev_all,
               MAX(fecha_ejecucion) AS ultima_ev,
               MAX(CASE WHEN strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS ultima_ev_anio,
               MIN(CASE WHEN tipo_mantenimiento = 'preventivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS primera_prev,
               MAX(CASE WHEN tipo_mantenimiento = 'preventivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS ultima_prev,
               MIN(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS primera_corr,
               MAX(CASE WHEN tipo_mantenimiento = 'correctivo'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS ultima_corr,
               MIN(CASE WHEN tipo_mantenimiento = 'visita'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS primera_vis,
               MAX(CASE WHEN tipo_mantenimiento = 'visita'
                         AND strftime('%Y', fecha_ejecucion) = ? THEN fecha_ejecucion END) AS ultima_vis
        FROM ejecucion_mantenimientos
        WHERE empresa_id = ?
        GROUP BY codigo_biomedica_norm, codigo_activo_norm
        """,
        (
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            year,
            int(empresa_id),
        ),
    ).fetchall()
    out = {}
    for row in rows:
        key = (row["codigo_biomedica_norm"] or "", row["codigo_activo_norm"] or "")
        item = dict(row)
        item["anio_filtro"] = int(anio)
        item["n_total_anio"] = item.get("n_total") or 0
        item["h_correctivos_12m"] = item.get("h_correctivos") or 0
        item["h_visitas_12m"] = item.get("h_visitas") or 0
        item["primera_ev"] = item.get("primera_corr") or item.get("primera_vis") or item.get("primera_prev")
        out[key] = item
    return out


def reporte_cobertura_sedes(
    conn,
    empresa_id: int,
    *,
    sede_ids: set[int] | None = None,
) -> dict:
    """
    Reporte interno (conteos, sin listar equipos):
    sin historial / parcial (hay eventos pero no preventivo) / completo (hay preventivo).
    """
    bio_expr = sql_norm_expr("ie.num_biomedica")
    act_expr = sql_norm_expr("ie.codigo_activo")
    sede_sql, sede_params = _sede_filtro_sql(sede_ids)
    params = [int(empresa_id), *sede_params, int(empresa_id)]
    rows = conn.execute(
        f"""
        WITH inv AS (
            SELECT ie.id, s.id AS sede_id, s.name_sede, s.ID_sede,
                   {bio_expr} AS bio_norm, {act_expr} AS act_norm
            FROM inventario_equipos ie
            JOIN servicios srv ON srv.id = ie.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            WHERE s.empresa_id = ? {sede_sql}
        ),
        hist AS (
            SELECT codigo_biomedica_norm AS bio_norm,
                   codigo_activo_norm AS act_norm,
                   SUM(CASE WHEN tipo_mantenimiento = 'preventivo' THEN 1 ELSE 0 END) AS n_prev,
                   COUNT(*) AS n_total
            FROM ejecucion_mantenimientos
            WHERE empresa_id = ?
            GROUP BY codigo_biomedica_norm, codigo_activo_norm
        ),
        matched AS (
            SELECT inv.sede_id, inv.name_sede, inv.ID_sede, inv.id,
                   MAX(CASE WHEN hist.n_total IS NULL THEN 0 ELSE hist.n_total END) AS n_total,
                   MAX(CASE WHEN hist.n_prev IS NULL THEN 0 ELSE hist.n_prev END) AS n_prev,
                   MAX(CASE WHEN inv.bio_norm = '' AND inv.act_norm = '' THEN 1 ELSE 0 END) AS sin_llave
            FROM inv
            LEFT JOIN hist
              ON (inv.bio_norm <> '' AND hist.bio_norm = inv.bio_norm)
              OR (inv.act_norm <> '' AND hist.act_norm = inv.act_norm)
            GROUP BY inv.sede_id, inv.name_sede, inv.ID_sede, inv.id
        )
        SELECT sede_id, name_sede, ID_sede,
               COUNT(*) AS equipos,
               SUM(sin_llave) AS sin_llave,
               SUM(CASE WHEN n_total = 0 THEN 1 ELSE 0 END) AS sin_historial,
               SUM(CASE WHEN n_total > 0 AND n_prev = 0 THEN 1 ELSE 0 END) AS parcial,
               SUM(CASE WHEN n_prev > 0 THEN 1 ELSE 0 END) AS completo
        FROM matched
        GROUP BY sede_id, name_sede, ID_sede
        ORDER BY name_sede COLLATE NOCASE
        """,
        params,
    ).fetchall()

    sedes = []
    tot = {"equipos": 0, "sin_llave": 0, "sin_historial": 0, "parcial": 0, "completo": 0, "sedes_sin_info": 0}
    for row in rows:
        item = {
            "sede_id": row["sede_id"],
            "ID_sede": row["ID_sede"],
            "name_sede": row["name_sede"],
            "equipos": int(row["equipos"] or 0),
            "sin_llave": int(row["sin_llave"] or 0),
            "sin_historial": int(row["sin_historial"] or 0),
            "parcial": int(row["parcial"] or 0),
            "completo": int(row["completo"] or 0),
            "sin_informacion": int(row["completo"] or 0) == 0 and int(row["parcial"] or 0) == 0,
        }
        if item["sin_informacion"]:
            tot["sedes_sin_info"] += 1
        for k in ("equipos", "sin_llave", "sin_historial", "parcial", "completo"):
            tot[k] += item[k]
        sedes.append(item)
    return {"empresa_id": int(empresa_id), "sedes": sedes, "totales": tot}


def attach_resumen_ejecucion(equipos: list[dict], resumen: dict[tuple[str, str], dict]) -> None:
    """Añade conteos y Fdef al payload PM sin incluir el historial de eventos."""
    from server.inventario_params import freq_anual_to_meses

    for eq in equipos or []:
        bio = eq.get("inv_num_biomedica") or eq.get("codigo_equipo")
        activo = eq.get("inv_codigo_activo") or ""
        key = llave_compuesta(bio, activo)
        stats = lookup_resumen_llave(resumen, bio, activo)
        grupo = freq_anual_to_meses(eq.get("inv_freq_mp"))
        estructura = estructura_frecuencia_equipo(
            ge=eq.get("ge_total"),
            pm_fabricante_meses=eq.get("pm_fabricante_meses"),
            grupo_meses=grupo,
            frecuencia_tpm_label=eq.get("frecuencia_definitiva"),
            n_preventivos=stats.get("n_preventivos") or 0,
            n_correctivos=stats.get("n_correctivos") or 0,
            n_visitas=stats.get("n_visitas") or 0,
            primera_prev=stats.get("primera_prev"),
            ultima_prev=stats.get("ultima_prev"),
        )
        n_total = int(stats.get("n_total") or 0)
        if n_total <= 0:
            cobertura = "sin_historial"
        elif int(stats.get("n_preventivos") or 0) <= 0:
            cobertura = "parcial"
        else:
            cobertura = "completo"
        eq["llave"] = {"codigo_biomedica": bio, "codigo_activo": activo, "norm": {"bio": key[0], "activo": key[1]}}
        eq["ejecucion"] = {
            "cobertura": cobertura,
            "n_eventos": n_total,
            **estructura,
        }
        real = eq["ejecucion"].setdefault("real", {})
        if stats.get("anio_filtro") is not None:
            h_corr = (
                round(float(stats.get("h_correctivos") or 0), 2)
                if int(stats.get("n_corr_con_horas") or 0) > 0
                else None
            )
            h_vis = (
                round(float(stats.get("h_visitas") or 0), 2)
                if int(stats.get("n_vis_con_horas") or 0) > 0
                else None
            )
            real["h_correctivos_anuales"] = h_corr if h_corr else None
            real["h_visitas_anuales"] = h_vis if h_vis else None
        else:
            real["h_correctivos_anuales"] = horas_anuales_desde_resumen(
                stats.get("h_correctivos_12m"),
                stats.get("h_correctivos"),
                stats.get("primera_corr") or stats.get("primera_ev"),
                stats.get("ultima_corr") or stats.get("ultima_ev"),
                stats.get("n_corr_con_horas"),
            )
            real["h_visitas_anuales"] = horas_anuales_desde_resumen(
                stats.get("h_visitas_12m"),
                stats.get("h_visitas"),
                stats.get("primera_vis") or stats.get("primera_ev"),
                stats.get("ultima_vis") or stats.get("ultima_ev"),
                stats.get("n_vis_con_horas"),
            )
