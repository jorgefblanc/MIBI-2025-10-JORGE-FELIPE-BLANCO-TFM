"""Catálogo de parámetros MP/Cal/Val por descripción de equipo.

Almacena en base aparte (parametros_equipo.db) los últimos valores ingresados
manualmente por tipo de equipo. Sin histórico: cada guardado reemplaza el anterior.
"""

from __future__ import annotations

from typing import Any

from server.db import get_parametros_equipo_connection
from server.dimensionamiento import normalize_criticidad
from server.inventario_params import ACTIVITIES, _as_tri_bool, _f, _norm_text


def normalize_descripcion(descripcion: str | None) -> str:
    return _norm_text(descripcion)


def _payload_from_row(row) -> dict[str, Any]:
    if not row:
        return {}
    data = dict(row)
    out = {
        "descripcion": data.get("descripcion"),
        "descripcion_norm": data.get("descripcion_norm"),
        "criticidad": normalize_criticidad(data.get("criticidad") or "Medio"),
        "updated_at": data.get("updated_at"),
    }
    for activity in ACTIVITIES:
        aplica = data.get(f"aplica_{activity}")
        out[f"aplica_{activity}"] = None if aplica is None else bool(aplica)
        out[f"freq_{activity}"] = data.get(f"freq_{activity}")
        out[f"tiempo_{activity}"] = data.get(f"tiempo_{activity}")
        out[f"tercerizado_{activity}"] = bool(data.get(f"tercerizado_{activity}") or 0)
    return out


def get_by_descripcion(descripcion: str) -> dict[str, Any] | None:
    key = normalize_descripcion(descripcion)
    if not key:
        return None
    with get_parametros_equipo_connection() as conn:
        row = conn.execute(
            "SELECT * FROM parametros_tipo_equipo WHERE descripcion_norm = ?",
            (key,),
        ).fetchone()
    return _payload_from_row(row) if row else None


def _ensure_catalog_columns(conn) -> None:
    """CREATE TABLE IF NOT EXISTS no agrega columnas a un catálogo ya creado."""
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "parametros_tipo_equipo" not in tables:
        return
    cols = {
        c["name"] for c in conn.execute("PRAGMA table_info(parametros_tipo_equipo)").fetchall()
    }
    additions = {
        "criticidad": "VARCHAR(40)",
        "tercerizado_mp": "INTEGER NOT NULL DEFAULT 0",
        "tercerizado_cal": "INTEGER NOT NULL DEFAULT 0",
        "tercerizado_val": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, typ in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE parametros_tipo_equipo ADD COLUMN {name} {typ}")


def upsert_parametros(descripcion: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Inserta o reemplaza los parámetros del tipo de equipo (último valor)."""
    key = normalize_descripcion(descripcion)
    label = (descripcion or "").strip() or key
    if not key:
        raise ValueError("La descripción del equipo es obligatoria.")

    values = {
        "descripcion_norm": key,
        "descripcion": label,
        "criticidad": normalize_criticidad(fields.get("criticidad") or "Medio"),
    }
    for activity in ACTIVITIES:
        aplica = _as_tri_bool(fields.get(f"aplica_{activity}"))
        terc = _as_tri_bool(fields.get(f"tercerizado_{activity}"))
        values[f"aplica_{activity}"] = None if aplica is None else (1 if aplica else 0)
        values[f"freq_{activity}"] = _f(fields.get(f"freq_{activity}"))
        values[f"tiempo_{activity}"] = _f(fields.get(f"tiempo_{activity}"))
        values[f"tercerizado_{activity}"] = 1 if terc is True else 0

    with get_parametros_equipo_connection() as conn:
        _ensure_catalog_columns(conn)
        conn.execute(
            """
            INSERT INTO parametros_tipo_equipo (
                descripcion_norm, descripcion, criticidad,
                aplica_mp, freq_mp, tiempo_mp, tercerizado_mp,
                aplica_cal, freq_cal, tiempo_cal, tercerizado_cal,
                aplica_val, freq_val, tiempo_val, tercerizado_val,
                updated_at
            ) VALUES (
                :descripcion_norm, :descripcion, :criticidad,
                :aplica_mp, :freq_mp, :tiempo_mp, :tercerizado_mp,
                :aplica_cal, :freq_cal, :tiempo_cal, :tercerizado_cal,
                :aplica_val, :freq_val, :tiempo_val, :tercerizado_val,
                datetime('now')
            )
            ON CONFLICT(descripcion_norm) DO UPDATE SET
                descripcion = excluded.descripcion,
                criticidad = excluded.criticidad,
                aplica_mp = excluded.aplica_mp,
                freq_mp = excluded.freq_mp,
                tiempo_mp = excluded.tiempo_mp,
                tercerizado_mp = excluded.tercerizado_mp,
                aplica_cal = excluded.aplica_cal,
                freq_cal = excluded.freq_cal,
                tiempo_cal = excluded.tiempo_cal,
                tercerizado_cal = excluded.tercerizado_cal,
                aplica_val = excluded.aplica_val,
                freq_val = excluded.freq_val,
                tiempo_val = excluded.tiempo_val,
                tercerizado_val = excluded.tercerizado_val,
                updated_at = datetime('now')
            """,
            values,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM parametros_tipo_equipo WHERE descripcion_norm = ?",
            (key,),
        ).fetchone()
    return _payload_from_row(row)
