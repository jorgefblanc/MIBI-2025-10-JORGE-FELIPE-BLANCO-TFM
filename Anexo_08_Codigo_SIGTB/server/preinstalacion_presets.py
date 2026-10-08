"""
Presets de preinstalación por tipo de equipo, con exigencias verificables de fabricantes.
Las fuentes se guardan en el campo `fuente` de cada preset.
"""

from __future__ import annotations

PRESETS = [
    {
        "codigo": "VENT_DRAGER_EVITA",
        "nombre": "Ventilador mecánico — Dräger Evita (UCI)",
        "tipo_equipo": "Ventilador mecánico",
        "marca": "Dräger",
        "modelo": "Evita",
        "fabricante": "Drägerwerk AG & Co. KGaA",
        "fuente": (
            "Dräger Evita XL: alimentación 100–240 V, 50/60 Hz, ~125 W; "
            "suministro O2 y aire 2,7–6 bar (30–87 PSI). Soma Technology / ficha Evita XL."
        ),
        "notas": "Ajusta exigencias eléctricas y de gases al rango publicado del Evita XL.",
        "keywords": ["ventilador", "evita", "drager", "dräger", "respirador"],
        "overlays": {
            6: "100–240 VAC, 50/60 Hz (Dräger Evita XL).",
            7: "50/60 Hz.",
            8: "Consumo aprox. 125 W; circuito sin sobrecarga con accesorios.",
            13: "Oxígeno medicinal 2,7–6 bar / 30–87 PSI; conexión compatible (DISS o según país).",
            14: "Aire medicinal 2,7–6 bar / 30–87 PSI.",
            15: "Presión de O2 y aire dentro de 2,7–6 bar, medida y documentada.",
            16: "Vacío/agua/drenaje no requerido para ventilador (No aplica salvo configuración especial).",
            17: "Área climatizada; evitar extremos fuera de uso clínico habitual.",
            20: "Red opcional; no bloquea instalación inicial.",
            21: "PACS/DICOM no aplica a ventilador.",
            24: "Mangueras O2/aire, cable de poder, brazo/carro soporte.",
            25: "Circuito, filtros y sensor de flujo según configuración adquirida.",
        },
        "na_items": [16, 21],
        "crit_boost": {13: "Crítico", 14: "Crítico", 15: "Crítico"},
    },
    {
        "codigo": "MON_GE_CARESCAPE_B650",
        "nombre": "Monitor multiparámetros — GE CARESCAPE B650",
        "tipo_equipo": "Monitor de signos vitales",
        "marca": "GE Healthcare",
        "modelo": "CARESCAPE B650",
        "fabricante": "GE Healthcare",
        "fuente": (
            "GE Healthcare CARESCAPE Monitor B650 site planning / datasheet: "
            "100–240 Vac ±10%, 50/60 Hz, 140 VA máx., Clase I, tierra hospitalaria; "
            "operación 10–35 °C, HR 10–90 % no condensante; Ethernet RJ45 / WLAN opcional IEEE 802.11."
        ),
        "notas": "Gases medicinales no aplican. Red LAN sí es típica.",
        "keywords": ["monitor", "carescape", "b650", "ge healthcare", "multiparametro", "multiparámetro"],
        "overlays": {
            6: "100–240 Vac ±10% (GE CARESCAPE B650).",
            7: "50/60 Hz.",
            8: "Consumo máximo 140 VA; toma hospitalaria Clase I.",
            9: "Puesta a tierra grado hospitalario (Class I / hospital grade).",
            13: "Oxígeno medicinal no requerido para el monitor.",
            14: "Aire medicinal no requerido.",
            15: "Presión de gases no aplica.",
            16: "Vacío/agua/drenaje no aplica.",
            17: "Temperatura de operación 10–35 °C (50–95 °F).",
            18: "Humedad relativa 10–90 % no condensante.",
            20: "Ethernet RJ45 para red de monitores; WLAN IEEE 802.11 opcional.",
            21: "Integración HIS/HL7 vía gateway; PACS no aplica.",
        },
        "na_items": [13, 14, 15, 16],
        "crit_boost": {6: "Crítico", 9: "Crítico", 20: "Mayor"},
    },
    {
        "codigo": "MON_PHILIPS_INTELLIVUE",
        "nombre": "Monitor multiparámetros — Philips IntelliVue",
        "tipo_equipo": "Monitor de signos vitales",
        "marca": "Philips",
        "modelo": "IntelliVue",
        "fabricante": "Philips Healthcare",
        "fuente": (
            "Philips IntelliVue (serie MX/MP): entorno OR/UCI, IEC 60601-1; "
            "conectividad de dispositivos vía IntelliBridge EC10. Fichas técnicas IntelliVue."
        ),
        "notas": "Gases no aplican. Verificar punto de red y compatibilidad IEC 60601-1.",
        "keywords": ["intelliVue", "philips", "monitor"],
        "overlays": {
            6: "Alimentación de red hospitalaria según ficha IntelliVue (típico 100–240 VAC).",
            7: "50/60 Hz.",
            9: "Tierra de protección IEC 60601-1.",
            13: "Oxígeno no requerido.",
            14: "Aire medicinal no requerido.",
            15: "Gases no aplican.",
            16: "Vacío/agua no aplican.",
            20: "Red / IntelliBridge según configuración adquirida.",
            21: "HIS/HL7 según gateway institucional; PACS no aplica.",
        },
        "na_items": [13, 14, 15, 16],
        "crit_boost": {6: "Crítico", 9: "Crítico"},
    },
    {
        "codigo": "BOMBA_INFUSION_IEC",
        "nombre": "Bomba de infusión — requisitos IEC 60601 (genérico)",
        "tipo_equipo": "Bomba de infusión",
        "marca": None,
        "modelo": None,
        "fabricante": "IEC 60601-1 / práctica de sitio hospitalario",
        "fuente": (
            "IEC 60601-1 (equipos electromédicos Clase I): alimentación de red, tierra de protección "
            "y entorno clínico controlado. Gases medicinales no aplican."
        ),
        "keywords": ["bomba", "infusion", "infusión", "syringe", "jeringa"],
        "overlays": {
            6: "100–240 VAC según ficha del fabricante de la bomba.",
            13: "Oxígeno no requerido.",
            14: "Aire no requerido.",
            15: "Gases no aplican.",
            16: "Vacío/agua no aplican.",
            21: "PACS/DICOM no aplica.",
            24: "Cable de poder, soporte/riel y set de infusión inicial.",
            25: "Sets/jeringas compatibles para prueba funcional.",
        },
        "na_items": [13, 14, 15, 16, 21],
        "crit_boost": {6: "Crítico", 10: "Crítico"},
    },
    {
        "codigo": "DESFIBRILADOR_IEC",
        "nombre": "Desfibrilador / DEA — sitio clínico",
        "tipo_equipo": "Desfibrilador",
        "marca": None,
        "modelo": None,
        "fabricante": "IEC 60601-1 / AHA práctica de sitio",
        "fuente": "IEC 60601-1 y recomendaciones de sitio: toma dedicada, tierra, acceso libre y batería/respaldo.",
        "keywords": ["desfibrilador", "dea", "cardioversor"],
        "overlays": {
            6: "Alimentación según ficha (típico 100–240 VAC) + carga de batería.",
            11: "Respaldo por batería interna; toma de carga permanente recomendada.",
            13: "Oxígeno no requerido para el equipo (sí precaución de atmósfera enriquecida).",
            14: "Aire medicinal no requerido.",
            16: "Vacío/agua no aplican.",
            21: "PACS no aplica.",
            22: "Acceso despejado; no obstruir carro de paro.",
        },
        "na_items": [14, 16, 21],
        "crit_boost": {6: "Crítico", 11: "Crítico", 22: "Crítico"},
    },
    {
        "codigo": "RX_SITIO",
        "nombre": "Rayos X / arco en C — sitio (eléctrico y radiación)",
        "tipo_equipo": "Equipo de rayos X",
        "marca": None,
        "modelo": None,
        "fabricante": "IEC 60601-1-3 / práctica de radiología",
        "fuente": (
            "Requisitos típicos de sitio radiológico: circuito dedicado, puesta a tierra, "
            "control de área y, si aplica, integración PACS/DICOM. Verificar ficha del fabricante."
        ),
        "keywords": ["rayos", "rx", "arco", "c-arm", "fluoroscop", "radiologia", "radiología"],
        "overlays": {
            6: "Voltaje y fases según ficha (frecuente 220–240 VAC dedicado).",
            8: "Circuito dedicado; no compartir con cargas no previstas.",
            13: "Oxígeno no requerido salvo sala híbrida.",
            16: "Agua/drenaje no aplican salvo revelado húmedo legado.",
            20: "Red para PACS/DICOM si el equipo es digital.",
            21: "Integración PACS/DICOM/RIS cuando la tecnología lo requiera.",
        },
        "na_items": [13, 14, 15],
        "crit_boost": {6: "Crítico", 8: "Crítico", 21: "Mayor"},
    },
    {
        "codigo": "ANESTESIA_GASES_ISO7396",
        "nombre": "Máquina de anestesia — gases ISO 7396-1",
        "tipo_equipo": "Máquina de anestesia",
        "marca": None,
        "modelo": None,
        "fabricante": "ISO 7396-1 / IEC 60601-1",
        "fuente": (
            "ISO 7396-1 (sistemas de gases medicinales): O2, aire, N2O, vacío y evacuación de gases "
            "anestésicos; pruebas de estanqueidad e identificación de tomas. IEC 60601-1 eléctrica."
        ),
        "keywords": ["anestesia", "fabius", "avance", "aestiva", "workstation"],
        "overlays": {
            6: "100–240 VAC según ficha de la estación de anestesia.",
            13: "O2 medicinal con toma identificada ISO 7396-1.",
            14: "Aire medicinal y, si aplica, N2O; sin conexiones cruzadas.",
            15: "Presión de suministro en rango de ficha; medición documentada.",
            16: "Vacío y sistema de evacuación de gases anestésicos (AGSS) si aplica.",
            21: "PACS no aplica; HIS opcional.",
        },
        "na_items": [21],
        "crit_boost": {13: "Crítico", 14: "Crítico", 15: "Crítico", 16: "Crítico"},
    },
]


def match_preset_codigo(equipo: str | None, marca: str | None = None, modelo: str | None = None) -> str | None:
    blob = " ".join(x for x in (equipo, marca, modelo) if x).casefold()
    if not blob:
        return None
    best = None
    best_hits = 0
    for preset in PRESETS:
        hits = sum(1 for kw in preset["keywords"] if kw.casefold() in blob)
        if hits > best_hits:
            best_hits = hits
            best = preset["codigo"]
    return best if best_hits else None
