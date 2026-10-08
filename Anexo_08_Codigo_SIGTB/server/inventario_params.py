"""Parámetros estandarizados MP/Cal/Val del inventario biomédico.

En Dimensionamiento, si un equipo no tiene MP/Cal/Val, se reutilizan en memoria
los datos de otro equipo con la misma descripción (EQUIPO). No se propagan ni
persisten esos valores en la base de datos.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

ACTIVITIES = ("mp", "cal", "val")

TIP_MANUAL_SIN_HISTORICO = (
    "Este equipo no tiene datos históricos. Ingrese la frecuencia y el tiempo "
    "promedio para esta actividad. El sistema usará estos valores en el cálculo "
    "del dimensionamiento para todos los equipos con la misma descripción "
    "(sin copiarlos a la base de datos de los demás)."
)


def _norm_text(value: Any) -> str:
    text = str(value or "").strip().upper()
    for src, dst in (
        ("Á", "A"),
        ("É", "E"),
        ("Í", "I"),
        ("Ó", "O"),
        ("Ú", "U"),
        ("Ü", "U"),
        ("Ñ", "N"),
    ):
        text = text.replace(src, dst)
    return " ".join(text.split())


def _f(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_tri_bool(value):
    """None = en blanco, True/False = Sí/No."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if int(value) == 1:
            return True
        if int(value) == 0:
            return False
        return None
    text = str(value).strip().lower()
    if text in ("sí", "si", "yes", "true", "1", "s"):
        return True
    if text in ("no", "false", "0", "n"):
        return False
    return None


def descripcion_key(row: dict[str, Any]) -> str:
    """Clave de similitud: misma descripción (campo EQUIPO)."""
    return _norm_text(row.get("equipo"))


def same_descripcion(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ka, kb = descripcion_key(a), descripcion_key(b)
    return bool(ka) and ka == kb


def has_complete_activity(row: dict[str, Any], activity: str) -> bool:
    """Datos completos: aplica Sí (o implícito) + frecuencia y tiempo > 0."""
    aplica = _as_tri_bool(row.get(f"aplica_{activity}"))
    freq = _f(row.get(f"freq_{activity}"))
    tiempo = _f(row.get(f"tiempo_{activity}"))
    if freq is None or tiempo is None:
        return False
    if freq <= 0 or tiempo <= 0:
        return False
    if aplica is False:
        return False
    return True


def is_activity_blank(row: dict[str, Any], activity: str) -> bool:
    """Campos en blanco: sin frecuencia ni tiempo útiles (y no marcado explícitamente No)."""
    aplica = _as_tri_bool(row.get(f"aplica_{activity}"))
    if aplica is False:
        return False
    freq = _f(row.get(f"freq_{activity}"))
    tiempo = _f(row.get(f"tiempo_{activity}"))
    freq_blank = freq is None or freq == 0
    tiempo_blank = tiempo is None or tiempo == 0
    return freq_blank and tiempo_blank


def activity_has_usable_data(row: dict[str, Any], activity: str) -> bool:
    """True si el equipo tiene decisión propia: No explícito o Sí con freq/tiempo."""
    return not is_activity_blank(row, activity)


def find_reference_for_activity(
    row: dict[str, Any],
    all_rows: list[dict[str, Any]],
    activity: str,
) -> dict[str, Any] | None:
    """
    Busca un equipo con la misma descripción que sí tenga datos de la actividad.
    Prioriza mismo servicio; no incluye al propio row.
    """
    peers = [
        r
        for r in all_rows
        if r.get("id") != row.get("id")
        and same_descripcion(r, row)
        and activity_has_usable_data(r, activity)
    ]
    if not peers:
        return None
    same_srv = [r for r in peers if r.get("servicio_id") == row.get("servicio_id")]
    if not same_srv:
        return None
    pool = same_srv
    # Preferir el que tenga datos completos (Sí+freq+tiempo) sobre solo No
    complete = [r for r in pool if has_complete_activity(r, activity)]
    return (complete or pool)[0]


def resolve_activity_for_calc(
    row: dict[str, Any],
    all_rows: list[dict[str, Any]],
    activity: str,
    *,
    dim_fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resuelve aplica/freq/tiempo para cálculo en memoria.
    No modifica la base de datos.
    """
    if activity_has_usable_data(row, activity):
        aplica = _as_tri_bool(row.get(f"aplica_{activity}"))
        return {
            "aplica": False if aplica is False else True,
            "freq": _f(row.get(f"freq_{activity}"), 0) or 0,
            "tiempo": _f(row.get(f"tiempo_{activity}"), 0) or 0,
            "needs_manual": False,
            "fuente": "inventario",
            "referencia_id": row.get("id"),
        }

    if dim_fallback and has_complete_activity(dim_fallback, activity):
        return {
            "aplica": bool(dim_fallback.get(f"aplica_{activity}")),
            "freq": _f(dim_fallback.get(f"freq_{activity}"), 0) or 0,
            "tiempo": _f(dim_fallback.get(f"tiempo_{activity}"), 0) or 0,
            "needs_manual": False,
            "fuente": "dimensionamiento",
            "referencia_id": row.get("id"),
        }

    ref = find_reference_for_activity(row, all_rows, activity)
    if ref is not None:
        aplica = _as_tri_bool(ref.get(f"aplica_{activity}"))
        return {
            "aplica": False if aplica is False else True,
            "freq": _f(ref.get(f"freq_{activity}"), 0) or 0,
            "tiempo": _f(ref.get(f"tiempo_{activity}"), 0) or 0,
            "needs_manual": False,
            "fuente": "equipo_similar",
            "referencia_id": ref.get("id"),
        }

    return {
        "aplica": True if activity == "mp" else False,
        "freq": "",
        "tiempo": "",
        "needs_manual": True,
        "fuente": "manual",
        "referencia_id": row.get("id"),
    }


def build_grupos_por_descripcion(equipos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Agrupa equipos por descripción (EQUIPO) para la UI de Dimensionamiento.
    Acumula horas/año del grupo completo.
    """
    buckets: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for eq in equipos:
        key = descripcion_key(eq) or f"SIN-NOMBRE-{eq.get('inventario_equipo_id')}"
        buckets.setdefault(key, []).append(eq)

    grupos = []
    for key, members in buckets.items():
        first = members[0]
        cantidad = len(members)
        # Referencia editable: equipo del grupo con datos propios en inventario.
        # Nunca usar referencia_mp del peer (evitar editar la fila incorrecta).
        ref_id = None
        for m in members:
            if any(m.get(f"fuente_{a}") == "inventario" for a in ACTIVITIES):
                ref_id = m.get("inventario_equipo_id")
                break
        if ref_id is None:
            for m in members:
                if any(not m.get(f"needs_manual_{a}") for a in ACTIVITIES):
                    ref_id = m.get("inventario_equipo_id")
                    break
        if ref_id is None:
            ref_id = first.get("inventario_equipo_id")

        sample = first
        for m in members:
            if any(m.get(f"fuente_{a}") == "inventario" for a in ACTIVITIES):
                sample = m
                break

        def _sum(field: str) -> float:
            return sum(float(m.get(field) or 0) for m in members)

        servicios = sorted(
            {str(m.get("servicio") or "").strip() for m in members if m.get("servicio")}
        )
        codigos = [m.get("codigo") for m in members if m.get("codigo")]
        en_dotacion = [m for m in members if m.get("en_dotacion", True)]
        forced = [m for m in members if m.get("mp_forzado_tercerizado") or m.get("adquisicion_clase") == "terceriza_mp"]
        faltantes = [
            m for m in members if m.get("adquisicion_clase") == "faltante" and m.get("en_dotacion", True)
        ]
        formas = sorted(
            {
                str(m.get("forma_adquisicion") or "").strip()
                for m in members
                if str(m.get("forma_adquisicion") or "").strip()
            }
        )
        all_forced = bool(members) and len(forced) == len(members)
        if all_forced:
            sample["aplica_mp"] = True
            sample["tercerizado_mp"] = True

        grupos.append(
            {
                "grupo_key": key,
                "equipo": first.get("equipo") or key,
                "cantidad": cantidad,
                "cantidad_calculo": len(en_dotacion),
                "cantidad_comodato_leasing": len(forced),
                "servicios": servicios,
                "codigos": codigos,
                "miembros": [
                    {
                        "inventario_equipo_id": m.get("inventario_equipo_id"),
                        "codigo": m.get("codigo"),
                        "servicio": m.get("servicio"),
                        "total_horas": m.get("total_horas"),
                        "forma_adquisicion": m.get("forma_adquisicion") or "",
                        "adquisicion_clase": m.get("adquisicion_clase"),
                        "mp_forzado_tercerizado": bool(m.get("mp_forzado_tercerizado")),
                        "alerta_sin_datos_anio": bool(m.get("alerta_sin_datos_anio")),
                        "en_bodega": bool(m.get("en_bodega")),
                    }
                    for m in members
                ],
                "referencia_inventario_equipo_id": ref_id,
                "criticidad": sample.get("criticidad"),
                "alto_unico_area": bool(sample.get("alto_unico_area")),
                "alto_especializado": bool(sample.get("alto_especializado")),
                "aplica_mp": sample.get("aplica_mp"),
                "freq_mp": sample.get("freq_mp"),
                "tiempo_mp": sample.get("tiempo_mp"),
                "needs_manual_mp": all(m.get("needs_manual_mp") for m in members)
                and not all_forced,
                "fuente_mp": sample.get("fuente_mp"),
                "aplica_cal": sample.get("aplica_cal"),
                "freq_cal": sample.get("freq_cal"),
                "tiempo_cal": sample.get("tiempo_cal"),
                "needs_manual_cal": all(m.get("needs_manual_cal") for m in members),
                "fuente_cal": sample.get("fuente_cal"),
                "aplica_val": sample.get("aplica_val"),
                "freq_val": sample.get("freq_val"),
                "tiempo_val": sample.get("tiempo_val"),
                "needs_manual_val": all(m.get("needs_manual_val") for m in members),
                "fuente_val": sample.get("fuente_val"),
                "tercerizado_mp": bool(sample.get("tercerizado_mp")) or all_forced,
                "tercerizado_cal": bool(sample.get("tercerizado_cal")),
                "tercerizado_val": bool(sample.get("tercerizado_val")),
                "mp_forzado_tercerizado": all_forced,
                "mp_forzado_count": len(forced),
                "adquisicion_faltante_count": len(faltantes),
                "formas_adquisicion": formas,
                "aplica_cap": sample.get("aplica_cap"),
                "freq_cap": sample.get("freq_cap"),
                "tiempo_cap": sample.get("tiempo_cap"),
                "tiene_historico_correctivo": any(
                    m.get("tiene_historico_correctivo") for m in members
                ),
                "historico_correctivo_h": _sum("historico_correctivo_h")
                if any(m.get("tiene_historico_correctivo") for m in members)
                else None,
                "gestion_documental_h": _sum("gestion_documental_h"),
                "acompanamiento_h": _sum("acompanamiento_h"),
                "otras_tareas_h": _sum("otras_tareas_h"),
                "observaciones": sample.get("observaciones") or "",
                "horas_mp": _sum("horas_mp"),
                "horas_cal": _sum("horas_cal"),
                "horas_val": _sum("horas_val"),
                "horas_cap": _sum("horas_cap"),
                "horas_correctivo": _sum("horas_correctivo"),
                "total_horas": _sum("total_horas"),
                "alerta_sin_datos_anio": any(m.get("alerta_sin_datos_anio") for m in members),
                "en_bodega": any(m.get("en_bodega") for m in members),
                "alerta_mensaje": next(
                    (m.get("alerta_mensaje") for m in members if m.get("alerta_sin_datos_anio")),
                    "",
                ),
            }
        )
    return grupos


def parse_activity_fields(body: dict) -> dict:
    """Extrae campos MP/Cal/Val desde un body JSON."""
    out = {}
    for activity in ACTIVITIES:
        aplica_key = f"aplica_{activity}"
        freq_key = f"freq_{activity}"
        tiempo_key = f"tiempo_{activity}"
        if aplica_key in body or freq_key in body or tiempo_key in body:
            aplica = _as_tri_bool(body.get(aplica_key))
            freq = _f(body.get(freq_key))
            tiempo = _f(body.get(tiempo_key))
            out[aplica_key] = None if aplica is None else (1 if aplica else 0)
            out[freq_key] = freq
            out[tiempo_key] = tiempo
    return out


def freq_anual_to_meses(freq_anual) -> float | None:
    """Convierte frecuencia anual (veces/año) al intervalo en meses del fabricante."""
    freq = _f(freq_anual)
    if freq is None or freq <= 0:
        return None
    meses = round(12.0 / freq, 2)
    if meses < 1:
        return 1.0
    if meses > 24:
        return 24.0
    return meses


def row_activity_payload(row) -> dict:
    def get(name, default=None):
        if hasattr(row, "keys"):
            return row[name] if name in row.keys() else default
        return row.get(name, default)

    payload = {}
    for activity in ACTIVITIES:
        aplica = get(f"aplica_{activity}")
        payload[f"aplica_{activity}"] = None if aplica is None else bool(aplica)
        payload[f"freq_{activity}"] = get(f"freq_{activity}")
        payload[f"tiempo_{activity}"] = get(f"tiempo_{activity}")
        payload[f"needs_manual_{activity}"] = is_activity_blank(
            {
                f"aplica_{activity}": aplica,
                f"freq_{activity}": get(f"freq_{activity}"),
                f"tiempo_{activity}": get(f"tiempo_{activity}"),
            },
            activity,
        )
    return payload
