"""Motor de preinstalación de tecnología biomédica (SITIO).

Réplica de catálogos y listas de chequeo del instrumento Excel institucional.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


ESTADOS = ["Cumple", "No cumple", "Pendiente", "No aplica"]
CRITICIDADES = ["Crítico", "Mayor", "Menor"]
DECISIONES = [
    "Aprobado para instalación",
    "Aprobado con condiciones",
    "No aprobado para instalación",
    "Revisar",
]
CATEGORIAS_FAB = [
    "Área física e ingreso",
    "Eléctrico",
    "Gases medicinales/fluidos",
    "Condiciones ambientales",
    "Redes y conectividad",
    "Seguridad física",
    "Accesorios requeridos",
]
CATEGORIA_DOC = "Documentación"

OBJETIVO_DEFAULT = (
    "Verificar en sitio si el área cumple las condiciones mínimas antes de aprobar la instalación."
)
FUENTE_DEFAULT = "Ficha técnica y guía de preinstalación del fabricante"
ALCANCE = (
    "Este instrumento se usa durante la visita de preinstalación para verificar condiciones "
    "del sitio: área física, ingreso, capacidad eléctrica, gases/fluidos, ambiente, "
    "conectividad, seguridad física, accesorios requeridos y documentación técnica/normativa. "
    "No evalúa entrenamiento del personal ni operación clínica; esas actividades corresponden "
    "a instalación, puesta en marcha o capacitación posterior."
)

GUIA_USO = [
    "Diligencie Datos generales con la información del equipo, proveedor, área y fecha de visita.",
    "En Exigencias del fabricante registre o ajuste los requisitos y verifique en sitio si se cumplen.",
    "En Documentación obligatoria valide documentos técnicos y normativos. Use «No aplica» cuando el requisito no corresponda a la tecnología evaluada.",
    "Este instrumento no evalúa capacitación del personal ni entrenamiento operativo.",
    "Resultado de evaluación calcula automáticamente el porcentaje de cumplimiento y la decisión.",
    "Si existe un requisito crítico en «No cumple» o «Pendiente», la instalación queda No aprobada hasta su cierre.",
    "Use Informe exportable para generar el PDF del concepto de preinstalación.",
]

TOOLTIPS = {
    "institucion": "Nombre de la institución / empresa donde se hará la visita de sitio.",
    "servicio": "Servicio o área asistencial de instalación (UCI, quirófano, urgencias, etc.).",
    "tecnologia": "Nombre de la tecnología biomédica a instalar.",
    "marca_modelo": "Marca y modelo según inventario o ficha técnica.",
    "proveedor": "Casa comercial o proveedor responsable de la entrega.",
    "serial": "Serial de fábrica o código interno institucional.",
    "ubicacion": "Punto exacto propuesto para instalar el equipo.",
    "fecha_visita": "Fecha de la visita de preinstalación en sitio.",
    "responsable": "Quien verifica (Ingeniería Clínica / operativo).",
    "acompanante": "Acompañante del servicio usuario (coordinación asistencial).",
    "fuente": "Origen de los requisitos (ficha técnica, guía de sitio, preset de fabricante).",
    "criticidad": "Crítico bloquea la instalación si queda abierto. Mayor y Menor no bloquean solos.",
    "estado": "Cumple / No cumple / Pendiente / No aplica. «No aplica» no entra al porcentaje.",
    "pct": "Csitio = 100 × Σ(ai·ci) / Σ(ai). No aplica no entra. Σ(ai)=0 → Revisar.",
    "decision": "Aprobado: Csitio≥90, sin críticos incumplidos ni pendientes. Con pendientes: Aprobado con condiciones. Csitio<90 o crítico incumplido: No aprobado.",
    "evidencia": "Lo observado en sitio o el soporte documental cargado.",
}

# (item_id, categoria, requisito, exigencia, criticidad)
DEFAULT_EXIGENCIAS = [
    (1, "Área física e ingreso", "Área disponible para instalar el equipo",
     "Espacio libre mínimo para equipo, soporte y movilidad segura alrededor del paciente", "Crítico"),
    (2, "Área física e ingreso", "Ubicación exacta definida",
     "Debe existir punto definido de instalación que no obstruya circulación ni acceso al paciente", "Mayor"),
    (3, "Área física e ingreso", "Ruta de ingreso del equipo",
     "Puertas, pasillos, ascensor/rampa permiten ingreso sin desmontajes no autorizados", "Mayor"),
    (4, "Área física e ingreso", "Soporte de peso del lugar",
     "Piso o superficie debe soportar peso del equipo y accesorios según fabricante", "Crítico"),
    (5, "Área física e ingreso", "Espacio para mantenimiento y retiro del equipo",
     "Debe quedar acceso para revisión, limpieza, cambio de accesorios y retiro seguro", "Menor"),
    (6, "Eléctrico", "Voltaje de alimentación",
     "Debe cumplir voltaje especificado por fabricante: 100-240 VAC o según ficha técnica", "Crítico"),
    (7, "Eléctrico", "Frecuencia eléctrica",
     "Debe cumplir frecuencia requerida: 50/60 Hz o según ficha técnica", "Mayor"),
    (8, "Eléctrico", "Capacidad de corriente/carga instalada",
     "Circuito debe soportar consumo del equipo y accesorios sin sobrecarga", "Crítico"),
    (9, "Eléctrico", "Puesta a tierra",
     "Debe existir sistema de tierra funcional y verificado", "Crítico"),
    (10, "Eléctrico", "Toma regulada o dedicada",
     "Debe contar con toma regulada/dedicada si lo exige el fabricante o política institucional", "Crítico"),
    (11, "Eléctrico", "Respaldo eléctrico",
     "UPS, planta o respaldo institucional cuando aplique por criticidad del equipo", "Mayor"),
    (12, "Eléctrico", "Protección eléctrica",
     "Protección contra sobretensión o circuito protegido según fabricante", "Mayor"),
    (13, "Gases medicinales/fluidos", "Oxígeno medicinal",
     "Presión y conexión compatibles con especificación del equipo, si aplica", "Crítico"),
    (14, "Gases medicinales/fluidos", "Aire medicinal",
     "Presión y conexión compatibles, si el equipo requiere aire externo", "Crítico"),
    (15, "Gases medicinales/fluidos", "Presión/caudal de gases",
     "Presión de suministro dentro del rango exigido por fabricante", "Crítico"),
    (16, "Gases medicinales/fluidos", "Vacío, agua o drenaje",
     "Disponible solo si aplica según tecnología", "Menor"),
    (17, "Condiciones ambientales", "Temperatura del área",
     "Debe estar dentro del rango recomendado por fabricante", "Mayor"),
    (18, "Condiciones ambientales", "Humedad relativa",
     "Debe estar dentro del rango recomendado por fabricante", "Menor"),
    (19, "Condiciones ambientales", "Ventilación y limpieza del entorno",
     "Área limpia, ventilada, sin exposición a polvo o humedad excesiva", "Mayor"),
    (20, "Redes y conectividad", "Punto de red o conectividad",
     "Disponible si el equipo requiere comunicación, monitoreo o integración", "Menor"),
    (21, "Redes y conectividad", "Integración PACS/RIS/HIS/LIS/DICOM",
     "Solo aplica para tecnologías que intercambian imágenes/datos clínicos", "Menor"),
    (22, "Seguridad física", "Ubicación segura respecto al paciente y operador",
     "No debe generar tropiezos, obstrucciones ni riesgo de desconexión accidental", "Mayor"),
    (23, "Seguridad física", "Sistema de fijación/soporte requerido",
     "Carro, soporte, brazo o base compatible según fabricante", "Mayor"),
    (24, "Accesorios requeridos", "Accesorios mínimos para instalación",
     "Debe contar con cable de poder, soportes y accesorios iniciales según configuración", "Crítico"),
    (25, "Accesorios requeridos", "Consumibles iniciales para prueba de funcionamiento",
     "Consumibles de arranque según configuración adquirida", "Mayor"),
]

DEFAULT_DOCUMENTOS = [
    (1, "Documentación", "Registro sanitario o permiso de comercialización",
     "Documento vigente del equipo o soporte regulatorio aplicable", "Crítico"),
    (2, "Documentación", "Declaración de importación",
     "Aplica para equipo importado cuando corresponda", "Mayor"),
    (3, "Documentación", "Factura, orden de compra o acta de entrega",
     "Soporte administrativo para trazabilidad de adquisición", "Mayor"),
    (4, "Documentación", "Ficha técnica del equipo",
     "Debe incluir especificaciones técnicas y requerimientos de instalación", "Crítico"),
    (5, "Documentación", "Manual de usuario",
     "Debe estar disponible en español o idioma aceptado por la institución", "Crítico"),
    (6, "Documentación", "Manual de servicio o mantenimiento",
     "Debe estar disponible para ingeniería clínica o soporte autorizado", "Mayor"),
    (7, "Documentación", "Certificado de garantía",
     "Debe indicar tiempo, cobertura, exclusiones y responsable del soporte", "Mayor"),
    (8, "Documentación", "Certificados de conformidad/seguridad eléctrica",
     "Certificados IEC, INVIMA u otros aplicables según tecnología", "Mayor"),
    (9, "Documentación", "Certificado de calibración/verificación inicial, si aplica",
     "Aplica cuando la tecnología lo requiera por norma, fabricante o metrología institucional", "Mayor"),
    (10, "Documentación", "Lista de accesorios y consumibles incluidos",
     "Debe permitir verificar que el equipo llegará completo para instalación/prueba", "Mayor"),
    (11, "Documentación", "Plan de mantenimiento recomendado por fabricante",
     "Frecuencias, actividades, repuestos y pruebas recomendadas", "Mayor"),
    (12, "Documentación", "Condiciones de garantía y soporte técnico",
     "Tiempos de respuesta, canales de atención y cobertura geográfica", "Mayor"),
]


def _norm_estado(value: str | None) -> str:
    text = (value or "").strip()
    for opt in ESTADOS:
        if opt.casefold() == text.casefold():
            return opt
    return "Pendiente"


def _norm_crit(value: str | None) -> str:
    text = (value or "").strip()
    aliases = {"Critico": "Crítico", "Crítico": "Crítico", "Alta": "Crítico", "Media": "Mayor", "Baja": "Menor"}
    if text in aliases:
        return aliases[text]
    for opt in CRITICIDADES:
        if opt.casefold() == text.casefold():
            return opt
    return "Mayor"


def _count(items: list[dict], estado: str, seccion: str | None = None, categoria: str | None = None) -> int:
    n = 0
    for it in items:
        if seccion and it.get("seccion") != seccion:
            continue
        if categoria and it.get("categoria") != categoria:
            continue
        if _norm_estado(it.get("estado")) == estado:
            n += 1
    return n


def calc_resultado(items: list[dict]) -> dict[str, Any]:
    """Csitio = 100 · Σ(ai·ci) / Σ(ai). ai=1 si aplica; ci=1 si cumple."""
    evaluables_fab = (
        _count(items, "Cumple", "fabricante")
        + _count(items, "No cumple", "fabricante")
        + _count(items, "Pendiente", "fabricante")
    )
    evaluables_doc = (
        _count(items, "Cumple", "documentacion")
        + _count(items, "No cumple", "documentacion")
        + _count(items, "Pendiente", "documentacion")
    )
    total = evaluables_fab + evaluables_doc
    cumplidos = _count(items, "Cumple")
    no_cumplidos = _count(items, "No cumple")
    pendientes = _count(items, "Pendiente")
    no_aplica = _count(items, "No aplica")

    criticos_incumplidos = 0
    criticos_pendientes = 0
    for it in items:
        if _norm_crit(it.get("criticidad")) != "Crítico":
            continue
        estado = _norm_estado(it.get("estado"))
        if estado == "No cumple":
            criticos_incumplidos += 1
        elif estado == "Pendiente":
            criticos_pendientes += 1
    criticos_abiertos = criticos_incumplidos + criticos_pendientes

    if total == 0:
        pct = None
        decision = "Revisar"
        semaforo = "amarillo"
    else:
        pct = cumplidos / total
        if criticos_incumplidos > 0 or pct < 0.9:
            decision = "No aprobado para instalación"
        elif pendientes == 0:
            decision = "Aprobado para instalación"
        else:
            decision = "Aprobado con condiciones"

        if criticos_incumplidos > 0 or (pct is not None and pct < 0.7):
            semaforo = "rojo"
        elif decision == "Aprobado para instalación":
            semaforo = "verde"
        else:
            semaforo = "amarillo"

    por_bloque = []
    for cat in CATEGORIAS_FAB:
        c = _count(items, "Cumple", "fabricante", cat)
        nc = _count(items, "No cumple", "fabricante", cat)
        p = _count(items, "Pendiente", "fabricante", cat)
        na = _count(items, "No aplica", "fabricante", cat)
        base = c + nc + p
        por_bloque.append({
            "categoria": cat,
            "cumple": c,
            "no_cumple": nc,
            "pendiente": p,
            "no_aplica": na,
            "pct": 0.0 if base == 0 else c / base,
        })
    c = _count(items, "Cumple", "documentacion", CATEGORIA_DOC)
    nc = _count(items, "No cumple", "documentacion", CATEGORIA_DOC)
    p = _count(items, "Pendiente", "documentacion", CATEGORIA_DOC)
    na = _count(items, "No aplica", "documentacion", CATEGORIA_DOC)
    base = c + nc + p
    por_bloque.append({
        "categoria": CATEGORIA_DOC,
        "cumple": c,
        "no_cumple": nc,
        "pendiente": p,
        "no_aplica": na,
        "pct": 0.0 if base == 0 else c / base,
    })

    abiertos = [
        {
            "fuente": "Fabricante" if it.get("seccion") == "fabricante" else "Documentación",
            "categoria": it.get("categoria"),
            "requisito": it.get("requisito"),
            "criticidad": _norm_crit(it.get("criticidad")),
            "estado": _norm_estado(it.get("estado")),
            "observaciones": it.get("observaciones") or "",
            "responsable_cierre": it.get("responsable_cierre") or "",
        }
        for it in items
        if _norm_estado(it.get("estado")) in ("Pendiente", "No cumple")
    ]

    return {
        "evaluables_fab": evaluables_fab,
        "evaluables_doc": evaluables_doc,
        "total_evaluables": total,
        "cumplidos": cumplidos,
        "no_cumplidos": no_cumplidos,
        "pendientes": pendientes,
        "no_aplica": no_aplica,
        "criticos_abiertos": criticos_abiertos,
        "criticos_incumplidos": criticos_incumplidos,
        "criticos_pendientes": criticos_pendientes,
        "pct_cumplimiento": pct,
        "decision": decision,
        "semaforo": semaforo,
        "por_bloque": por_bloque,
        "abiertos": abiertos,
    }


def default_items_payload() -> list[dict]:
    rows = []
    for item_id, cat, req, exig, crit in DEFAULT_EXIGENCIAS:
        rows.append({
            "seccion": "fabricante",
            "item_id": item_id,
            "categoria": cat,
            "requisito": req,
            "exigencia": exig,
            "evidencia": "",
            "criticidad": crit,
            "estado": "Pendiente",
            "responsable_cierre": "",
            "fecha_compromiso": None,
            "observaciones": "",
            "orden": item_id,
        })
    for item_id, cat, req, exig, crit in DEFAULT_DOCUMENTOS:
        rows.append({
            "seccion": "documentacion",
            "item_id": item_id,
            "categoria": cat,
            "requisito": req,
            "exigencia": exig,
            "evidencia": "",
            "criticidad": crit,
            "estado": "Pendiente",
            "responsable_cierre": "",
            "fecha_compromiso": None,
            "observaciones": "",
            "orden": item_id,
        })
    return rows


def catalogs_payload() -> dict:
    return {
        "estados": ESTADOS,
        "criticidades": CRITICIDADES,
        "decisiones": DECISIONES,
        "categorias_fabricante": CATEGORIAS_FAB,
        "categoria_documentacion": CATEGORIA_DOC,
        "guia_uso": GUIA_USO,
        "alcance": ALCANCE,
        "objetivo_default": OBJETIVO_DEFAULT,
        "fuente_default": FUENTE_DEFAULT,
        "tooltips": TOOLTIPS,
    }


def group_items(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        grouped[it.get("categoria") or "Otros"].append(it)
    return dict(grouped)
