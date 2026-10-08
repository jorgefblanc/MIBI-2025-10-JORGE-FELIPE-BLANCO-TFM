"""Mapeos del inventario biomédico hacia instrumentos (PM, dimensión, preinstalación)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

from server.frecuencia_pm import APLICACION_CATALOGO, FUNCION_CATALOGO, REQUISITO_CATALOGO


FUNCION_SOPORTE = FUNCION_CATALOGO[0]["label"]
FUNCION_DX = FUNCION_CATALOGO[1]["label"]
FUNCION_TERAP = FUNCION_CATALOGO[2]["label"]
FUNCION_APOYO = FUNCION_CATALOGO[3]["label"]

APLIC_CRITICA = APLICACION_CATALOGO[0]["label"]
APLIC_HOSP = APLICACION_CATALOGO[1]["label"]
APLIC_CE = APLICACION_CATALOGO[2]["label"]
APLIC_ADMIN = APLICACION_CATALOGO[3]["label"]

REQ_ESP = REQUISITO_CATALOGO[0]["label"]
REQ_IMP = REQUISITO_CATALOGO[1]["label"]
REQ_USUAL = REQUISITO_CATALOGO[2]["label"]
REQ_MIN = REQUISITO_CATALOGO[3]["label"]

PERIODICIDAD_A_FREQ_ANUAL = {
    "MENSUAL": 12.0,
    "TRIMESTRAL": 4.0,
    "CUATRIMESTRAL": 3.0,
    "SEMESTRAL": 2.0,
    "ANUAL": 1.0,
    "BIANUAL": 0.5,
    "BIMESTRAL": 6.0,
}

CAMPUS_PRINCIPAL = "Campus principal"
SIN_UBICACION = "Sin ubicación asignada"
FUENTE_FOSCAGIB = "FOSCAGIB"

_ACRONYMS = {
    "UCI",
    "CAA",
    "PYP",
    "TMS",
    "CAL",
    "VIP",
    "NEPS",
    "PGP",
    "SST",
    "SHEC",
    "EPS",
    "FOS",
    "CTA",
    "MP",
    "INVIMA",
}


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def fold_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = strip_accents(text).upper()
    text = re.sub(r"[,;:()\[\]/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fold_location(value: Any) -> str:
    text = fold_text(value)
    text = text.replace(".", " ")
    text = re.sub(r"\s*[-–]+\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_org_name(value: Any, fallback: str = "Sin nombre") -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[,;:()\[\]]+", " ", text)
    text = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s.\-_/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-_/")
    return text or fallback


def title_org(value: str) -> str:
    words = []
    parts = safe_org_name(value).split()
    for i, raw in enumerate(parts):
        folded = strip_accents(raw).upper()
        if folded in _ACRONYMS:
            words.append(folded)
            continue
        if i > 0 and folded in {"Y", "DE", "DEL", "LA", "EL", "EN", "LOS", "LAS"}:
            words.append(folded.lower())
            continue
        words.append(raw[:1].upper() + raw[1:].lower() if raw else raw)
    return " ".join(words) or value


def parse_any_date(value: Any) -> str | None:
    """Normaliza fechas del CSV (ISO, timestamp o dict de Python) a YYYY-MM-DD."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A", "NONE", "NULL"}:
        return None
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            datetime.strptime(iso.group(1), "%Y-%m-%d")
            return iso.group(1)
        except ValueError:
            pass
    dt = re.search(
        r"datetime\.datetime\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})",
        text,
    )
    if dt:
        try:
            return date(int(dt.group(1)), int(dt.group(2)), int(dt.group(3))).isoformat()
        except ValueError:
            return None
    return None


def parse_vida_util_anios(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def periodicidad_a_freq(value: Any) -> tuple[int | None, float | None]:
    """Retorna (aplica 0/1/None, frecuencia anual)."""
    folded = fold_text(value)
    if not folded:
        return None, None
    if folded in {"NO APLICA", "NA", "N A", "NO"}:
        return 0, None
    freq = PERIODICIDAD_A_FREQ_ANUAL.get(folded)
    if freq:
        return 1, freq
    return None, None


def as_tri_flag(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in {"true", "1", "si", "sí", "yes", "s"}:
        return 1
    if text in {"false", "0", "no", "n"}:
        return 0
    return None


def map_funcion_oms(clasificacion_biomedica: str | None) -> str:
    folded = fold_text(clasificacion_biomedica)
    if "SOPORTE" in folded or "VITAL" in folded or "TRATAMIENTO" in folded:
        return FUNCION_SOPORTE
    if "DIAGNOSTICO" in folded or "DIAGNOSTIC" in folded:
        return FUNCION_DX
    if "REHABILIT" in folded:
        return FUNCION_TERAP
    return FUNCION_APOYO


def map_aplicacion_oms(servicio_o_ubicacion: str | None) -> str:
    folded = fold_text(servicio_o_ubicacion)
    criticos = (
        "UCI",
        "CIRUGIA",
        "QUIROFANO",
        "URGENCIA",
        "TRANSPLANTE",
        "PARTOS",
        "HEMODINAMIA",
        "UCIADULTOS",
    )
    if any(token in folded for token in criticos):
        return APLIC_CRITICA
    hospital = (
        "HOSPITALIZ",
        "HOSP ",
        "HEMATO",
        "PISO",
        "TORRE",
        "CLINICENTRO",
    )
    if any(token in folded for token in hospital):
        return APLIC_HOSP
    ce = (
        "CONSULTA",
        "LABORATORIO",
        "IMAGEN",
        "FARMACIA",
        "ODONTO",
        "OPTICA",
        "DIAGNOSTIC",
        "RESONANCIA",
        "ENDOSCOP",
        "PYP",
        "CONSULTORIO",
        "VACUNAC",
    )
    if any(token in folded for token in ce):
        return APLIC_CE
    return APLIC_ADMIN


def map_requisito_oms(clasificacion_riesgo: str | None) -> str:
    folded = fold_text(clasificacion_riesgo).replace(" ", "")
    if folded in {"III", "IIB"}:
        return REQ_ESP
    if folded in {"IIA", "II"}:
        return REQ_IMP
    if folded in {"I"}:
        return REQ_USUAL
    return REQ_MIN


def map_fallas_oms(novedad_desc: str | None) -> str:
    folded = fold_text(novedad_desc)
    if not folded:
        return "Raras"
    if any(tok in folded for tok in ("FALLA", "DAÑO", "DANO", "AVERIA", "CORRECTIVO", "REPAR")):
        if "RECURR" in folded or "FRECUENT" in folded:
            return "Frecuentes"
        return "Moderadas"
    return "Raras"


def tiempo_mp_default(clasificacion_biomedica: str | None, clasificacion_riesgo: str | None) -> float:
    folded = fold_text(clasificacion_biomedica)
    riesgo = fold_text(clasificacion_riesgo).replace(" ", "")
    if "SOPORTE" in folded or "VITAL" in folded or riesgo in {"III", "IIB"}:
        return 3.0
    if "DIAGNOSTICO" in folded or riesgo in {"IIA", "II"}:
        return 2.0
    if "REHABILIT" in folded:
        return 1.5
    return 1.0


def map_criticidad_dim(clasificacion_riesgo: str | None, clasificacion_biomedica: str | None) -> str:
    bio = fold_text(clasificacion_biomedica)
    riesgo = fold_text(clasificacion_riesgo).replace(" ", "")
    if "SOPORTE" in bio or "VITAL" in bio or riesgo in {"III", "IIB"}:
        return "Alto"
    if riesgo in {"IIA", "II"}:
        return "Alto"
    if riesgo == "I":
        return "Bajo"
    return "Medio"


_EMPRESA_MAP = {
    "1000": "foscal",
    "FOSCAL": "foscal",
    "CENTRO DE COSTOS FOSCAL": "foscal",
    "1001": "foscal_internacional",
    "FOSCAL INTERNACIONAL": "foscal_internacional",
    "CENTRO DE COSTOS FOSCAL INTERNACIONAL": "foscal_internacional",
    "1002": "foscagib",
    "1003": "foscagib",
    "FUNDACION AVANZAR FOS": "avanzar",
    "AVANZAR": "avanzar",
    "CENTRO DE COSTOS SANTA CRUZ": "santa_cruz",
    "SANTA CRUZ": "santa_cruz",
}

EMPRESAS_FOSCAGIB = {
    "foscal": {
        "nombre": "FOSCAL",
        "nit": "890207877-1",
    },
    "foscal_internacional": {
        "nombre": "FOSCAL Internacional",
        "nit": "900123001-1",
    },
    "foscagib": {
        "nombre": "FOSCAGIB Red regional",
        "nit": "900890201-1",
    },
    "avanzar": {
        "nombre": "Fundación Avanzar FOS",
        "nit": "900890202-1",
    },
    "santa_cruz": {
        "nombre": "Clínica Santa Cruz de la Loma S.A.",
        "nit": "800.215.758-1",
    },
}


def map_empresa_key(institucion: str | None) -> str:
    folded = fold_text(institucion)
    folded = re.sub(r"\s+", " ", folded)
    if folded in _EMPRESA_MAP:
        return _EMPRESA_MAP[folded]
    for raw, key in _EMPRESA_MAP.items():
        if fold_text(raw) == folded:
            return key
    return "foscagib"


_SEDE_CITY = {
    "BARBOSA": "Barbosa",
    "BARRANCABERMEJA": "Barrancabermeja",
    "BOLARQUI": "Bolarqui",
    "FLORIDABLANCA": "Floridablanca",
    "GIRON": "Girón",
    "GIRON ANTIGUA": "Girón Antigua",
    "MALAGA": "Málaga",
    "PIEDECUESTA": "Piedecuesta",
    "PUENTE NACIONAL": "Puente Nacional",
    "SAN ALONSO": "San Alonso",
    "SAN GIL": "San Gil",
    "SAN GIL PLAZA": "San Gil Plaza",
    "SOCORRO": "Socorro",
    "SOTOMAYOR": "Sotomayor",
    "VELEZ": "Vélez",
    "VELEZ NACIONAL": "Vélez",
    "FOSCAL SUR": "Foscal Sur",
    "CRA.33": "Carrera 33",
    "CRA 33": "Carrera 33",
    "CARRERA 33": "Carrera 33",
    "P CUESTA": "Piedecuesta",
    "PCUESTA": "Piedecuesta",
}


def _sede_from_token(token: str) -> str | None:
    folded = fold_text(token)
    folded = folded.replace("P CUESTA", "PIEDECUESTA").replace("P/CUESTA", "PIEDECUESTA")
    if folded in _SEDE_CITY:
        return _SEDE_CITY[folded]
    for key, name in sorted(_SEDE_CITY.items(), key=lambda kv: len(kv[0]), reverse=True):
        if folded == fold_text(key):
            return name
    return None


def _servicio_canonico(folded: str, original: str) -> str:
    aliases = {
        "UCI ADULTOS": "UCI Adultos",
        "UCI PEDIATRICA": "UCI Pediátrica",
        "LABORATORIO CLINICO": "Laboratorio clínico",
        "HOSPITALIZACION": "Hospitalización",
        "CIRUGIA GENERAL": "Cirugía general",
        "CIRUGIA FOS": "Cirugía FOS",
        "CIRUGIA OFTALMOLOGIA": "Cirugía oftalmología",
        "CONSULTA EXTERNA PREANESTESIA": "Consulta externa preanestesia",
        "IMAGENES DIAGNOSTICAS": "Imágenes diagnósticas",
        "UNIDAD DE ESTERILIZACION": "Unidad de esterilización",
        "UNIDAD DE ENDOSCOPIA": "Unidad de endoscopia",
        "UNIDAD RADIOTERAPIA": "Unidad de radioterapia",
        "UNIDAD QUIMIOTERAPIA": "Unidad de quimioterapia",
        "BANCO MULTITEJIDOS Y CTA": "Banco multitejidos y CTA",
        "DIRECCION DE INVESTIGACIONES": "Dirección de investigaciones",
        "CENTRO DE CANCER": "Centro de cáncer",
        "SALA DE PARTOS": "Sala de partos",
        "URGENCIAS": "Urgencias",
        "URGENCIAS CLINICENTRO": "Urgencias / Clinicentro",
        "FARMACIA CENTRAL": "Farmacia central",
        "CONSULTA OFTALMOLOGICA": "Consulta oftalmológica",
        "CONSULTA EXTERNA": "Consulta externa",
        "CONSULTA EXTERNA CAA": "Consulta externa CAA",
        "TRANSPLANTE MEDULA": "Trasplante de médula",
        "ODONTOLOGIA": "Odontología",
        "PYP": "PyP",
    }
    if folded in aliases:
        return aliases[folded]
    return title_org(original or folded)


def split_sede_servicio(ubicacionnombre: str | None) -> tuple[str, str]:
    """Separa sede y servicio para no mezclar inventarios entre áreas."""
    raw = unicodedata.normalize("NFKC", str(ubicacionnombre or "")).replace("\xa0", " ").strip()
    if not raw:
        return CAMPUS_PRINCIPAL, SIN_UBICACION

    folded = fold_location(raw)

    plaza = re.match(r"^SAN GIL PLAZA\s+(.+)$", folded)
    if plaza:
        rest = plaza.group(1).strip()
        return "San Gil Plaza", _servicio_canonico(rest, rest)

    consultorios = re.match(r"^(.+?)\s+CONSULTORIOS\s+PROCEDIMIENTOS\s+PYP$", folded)
    if consultorios:
        sede = _sede_from_token(consultorios.group(1)) or title_org(consultorios.group(1))
        return sede, "Consultorios procedimientos y PyP"

    odonto = re.match(r"^(.+?)\s+ODONTOLOGIA$", folded)
    if odonto and not folded.startswith("ODONTOLOGIA"):
        sede = _sede_from_token(odonto.group(1)) or title_org(odonto.group(1))
        return sede, "Odontología"

    ce_foscal_sede = re.match(r"^CONSULTA EXTERNA FOSCAL SEDE (.+)$", folded)
    if ce_foscal_sede:
        sede = _sede_from_token(ce_foscal_sede.group(1)) or title_org(ce_foscal_sede.group(1))
        return sede, "Consulta externa"

    ce_sede = re.match(r"^CONSULTA EXTERNA SEDE (.+)$", folded)
    if ce_sede:
        sede = _sede_from_token(ce_sede.group(1)) or title_org(ce_sede.group(1))
        return sede, "Consulta externa"

    if folded == "CONSULTA EXTERNA FOSCAL SUR":
        return "Foscal Sur", "Consulta externa"
    if folded == "CONSULTA EXTERNA NUEVA EPS BOLARQUI":
        return "Bolarqui", "Consulta externa Nueva EPS"
    if folded == "ODONTOLOGIA SEDE BOLARQUI":
        return "Bolarqui", "Odontología"
    if folded == "ODONTOLOGIA NUEVA EPS FOS SUR":
        return "Foscal Sur", "Odontología Nueva EPS"
    if folded == "ODONTOLOGIA PGP SAN ALONSO":
        return "San Alonso", "Odontología PGP"
    if folded == "OPTICA BOLARQUI":
        return "Bolarqui", "Óptica"
    if folded == "PUVATERAPIA BOLARQUI":
        return "Bolarqui", "Puvaterapia"
    if folded == "CIRUGIA CAL":
        return "CAL", "Cirugía"
    if folded in {"FLORIDABLANCA A", "FLORIDABLANCA B"}:
        letra = folded[-1]
        return "Floridablanca", f"Consultorio {letra}"

    if folded.startswith("DISPENSACION NEPS ") or folded.startswith("DISP NEPS "):
        rest = folded.replace("DISPENSACION NEPS ", "", 1).replace("DISP NEPS ", "", 1)
        sede = _sede_from_token(rest) or title_org(rest)
        return sede, "Dispensación NEPS"
    if folded.startswith("DISPENSACION "):
        rest = folded.replace("DISPENSACION ", "", 1)
        sede = _sede_from_token(rest) or title_org(rest)
        return sede, "Dispensación"

    market = re.match(r"^FOSCAL MARKET D (.+)$", folded)
    if market:
        token = market.group(1)
        if token.startswith("BOLAR"):
            return "Bolarqui", "Foscal Market"
        if token.startswith("PIEDE"):
            return "Piedecuesta", "Foscal Market"
        if token.startswith("FOSCAL"):
            return CAMPUS_PRINCIPAL, "Foscal Market"
        return _sede_from_token(token) or CAMPUS_PRINCIPAL, "Foscal Market"

    if folded.startswith("AVANZAR "):
        rest = folded.replace("AVANZAR ", "", 1)
        sede = _sede_from_token(rest) or title_org(rest)
        return sede, "Fundación Avanzar"

    hosp = re.match(r"^HOSP\s*(\d+)\s*PISO\s*(.+)$", folded)
    if hosp:
        piso = hosp.group(1)
        suf = hosp.group(2).strip()
        if "CAL" in suf:
            sede = "CAL"
            extra = "occidente" if "OCCIDENTE" in suf else ""
        elif "TMS" in suf:
            sede = "TMS"
            extra = ""
        elif "VIP" in suf:
            sede = CAMPUS_PRINCIPAL
            extra = "VIP"
        elif "ORIENTE" in suf:
            sede = "Torre A"
            extra = "oriente"
        else:
            sede = CAMPUS_PRINCIPAL
            extra = title_org(suf).lower()
        servicio = f"Hospitalización piso {piso}" + (f" {extra}" if extra else "")
        return sede, servicio.strip()

    torres = re.match(r"^HOSPITALIZACION (\d+).*(TORRE [AB])", folded)
    if torres:
        piso = torres.group(1)
        torre = "Torre A" if "TORRE A" in folded else "Torre B"
        extra = ""
        if "VIP" in folded:
            extra = " VIP"
        elif "HEMATO" in folded:
            extra = " hematología"
        elif "ESTACION" in folded:
            extra = " estaciones B C E"
        elif "TRANSPLANTE" in folded:
            extra = " trasplante de médula"
        return torre, f"Hospitalización piso {piso}{extra}"

    if folded.startswith("HOSPITALIZACION "):
        return CAMPUS_PRINCIPAL, title_org(raw)

    if "CLINICENTRO" in folded and folded != "CLINICENTRO":
        return "Clinicentro", _servicio_canonico(folded.replace("CLINICENTRO", "").strip(), raw)

    if folded.startswith("BODEGA DE BAJAS"):
        return CAMPUS_PRINCIPAL, "Bodega de bajas"

    if folded == "AMBULANCIAS":
        return "Ambulancias", "Ambulancias"

    return CAMPUS_PRINCIPAL, _servicio_canonico(folded, raw)


def infer_estado(fecha_baja: str | None, novedad_desc: str | None) -> str:
    if fecha_baja:
        return "FUERA DE SERVICIO"
    folded = fold_text(novedad_desc)
    if any(tok in folded for tok in ("FALLA", "DAÑO", "DANO", "AVERIA", "REPAR")) and "MP " not in folded:
        return "EN REPARACIÓN"
    return "OPERATIVO"


def infer_fecha_ultimo_pm(row: dict) -> str | None:
    """Solo acepta evidencia de MP en la novedad. No usa fecha de actualización."""
    desc = fold_text(row.get("novedaddes") or row.get("novedad_desc"))
    novedad_fecha = parse_any_date(row.get("fechanovedad"))
    if not novedad_fecha or not desc:
        return None
    if re.search(r"\bMP\b", desc) or "MANTENIMIENTO PREVENTIVO" in desc:
        return novedad_fecha
    return None


def ficha_electrica(row: dict) -> str:
    parts = []
    mapping = (
        ("voltaje", "Tensión"),
        ("corriente", "Corriente"),
        ("potencia", "Potencia"),
        ("peso", "Peso"),
        ("temperatura_trabajo", "Temperatura de trabajo"),
        ("presion", "Presión"),
        ("fuente_alimentacion", "Fuente de alimentación"),
    )
    for key, label in mapping:
        val = str(row.get(key) or "").strip()
        if val and fold_text(val) not in {"NA", "N A", "NO APLICA", "NO"}:
            parts.append(f"{label}: {val}")
    return "; ".join(parts)
