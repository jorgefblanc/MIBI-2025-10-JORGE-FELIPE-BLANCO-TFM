"""
Reciclo de inventario biomédico (30 minutos).

Independiente del auto-backup de las 4 bases (`data/backups/`):
  - Solo guarda filas de inventario del servicio (y dim_actividad ligada).
  - No escribe en BACKUP_DIR ni altera snapshots periódicos.
  - Tras TTL el JSON se borra; el inventario en vivo ya se había vaciado.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from server.db import DATA_DIR, get_empresas_connection

TTL_SECONDS = 30 * 60
RECYCLE_DIR = DATA_DIR / "inventory_recycle"
INVENTORY_TABLE = "inventario_equipos"
CHILD_TABLE = "dim_actividad_equipo"


def _now() -> datetime:
    return datetime.now()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _recycle_path(servicio_id: int) -> Path:
    return RECYCLE_DIR / f"servicio-{int(servicio_id)}.json"


def _row_dict(row: sqlite3.Row) -> dict:
    item = {}
    for key in row.keys():
        value = row[key]
        if hasattr(value, "isoformat"):
            value = str(value)
        item[key] = value
    return item


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return bool(row)


def _read_payload(servicio_id: int) -> dict | None:
    path = _recycle_path(servicio_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None
    if int(data.get("servicio_id") or 0) != int(servicio_id):
        path.unlink(missing_ok=True)
        return None
    return data


def _is_expired(payload: dict, now: datetime | None = None) -> bool:
    now = now or _now()
    expires = _parse_iso(payload.get("expires_at"))
    if expires is None:
        return True
    return now >= expires


def purge_expired() -> int:
    """Elimina reciclos vencidos. No toca data/backups/."""
    if not RECYCLE_DIR.exists():
        return 0
    removed = 0
    now = _now()
    for path in RECYCLE_DIR.glob("servicio-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if _is_expired(data, now):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def status_for_servicio(servicio_id: int) -> dict:
    purge_expired()
    payload = _read_payload(servicio_id)
    if not payload:
        return {"pending": False, "can_restore": False}
    remaining = max(
        0,
        int((_parse_iso(payload["expires_at"]) - _now()).total_seconds()),
    )
    return {
        "pending": True,
        "can_restore": remaining > 0,
        "expires_at": payload.get("expires_at"),
        "created_at": payload.get("created_at"),
        "remaining_seconds": remaining,
        "equipos": int(payload.get("equipos") or 0),
        "deleted_by": payload.get("deleted_by") or "",
    }


def snapshot_and_delete(conn, *, servicio_id: int, user: dict) -> dict:
    """
    Copia inventario del servicio a reciclo (TTL 30 min) y lo borra en vivo.
    Reemplaza un reciclo previo del mismo servicio (último backup).
    """
    purge_expired()
    if not _table_exists(conn, INVENTORY_TABLE):
        raise ValueError("No existe la tabla de inventario.")

    equipos = conn.execute(
        f"SELECT * FROM {INVENTORY_TABLE} WHERE servicio_id = ? ORDER BY id",
        (servicio_id,),
    ).fetchall()
    if not equipos:
        raise ValueError("No hay inventario cargado en este servicio.")

    ids = [int(row["id"]) for row in equipos]
    dim_rows = []
    if _table_exists(conn, CHILD_TABLE) and ids:
        placeholders = ",".join("?" * len(ids))
        dim_rows = conn.execute(
            f"SELECT * FROM {CHILD_TABLE} WHERE inventario_equipo_id IN ({placeholders}) ORDER BY id",
            ids,
        ).fetchall()

    now = _now()
    expires = now + timedelta(seconds=TTL_SECONDS)
    payload = {
        "servicio_id": int(servicio_id),
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": expires.isoformat(timespec="seconds"),
        "deleted_by": (user or {}).get("usuario_login") or "",
        "equipos": len(equipos),
        "tables": {
            INVENTORY_TABLE: [_row_dict(r) for r in equipos],
            CHILD_TABLE: [_row_dict(r) for r in dim_rows],
        },
    }
    RECYCLE_DIR.mkdir(parents=True, exist_ok=True)
    path = _recycle_path(servicio_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

    try:
        if _table_exists(conn, CHILD_TABLE) and ids:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM {CHILD_TABLE} WHERE inventario_equipo_id IN ({placeholders})",
                ids,
            )
        conn.execute(f"DELETE FROM {INVENTORY_TABLE} WHERE servicio_id = ?", (servicio_id,))
        conn.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return status_for_servicio(servicio_id)


def _insert_rows(conn, table: str, rows: list[dict]) -> None:
    if not rows or not _table_exists(conn, table):
        return
    for row in rows:
        cols = list(row.keys())
        placeholders = ",".join("?" * len(cols))
        quoted = ",".join(cols)
        conn.execute(
            f"INSERT INTO {table} ({quoted}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )


def _bump_sequence(conn, table: str) -> None:
    if not _table_exists(conn, table):
        return
    row = conn.execute(f"SELECT MAX(id) AS m FROM {table}").fetchone()
    maximum = row["m"] if row else None
    if maximum is None:
        return
    seq = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
    ).fetchone()
    if not seq:
        return
    exists = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?",
            (int(maximum), table),
        )
    else:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
            (table, int(maximum)),
        )


def restore_last(conn, *, servicio_id: int) -> dict:
    """Restaura el último reciclo vigente. Sustituye el inventario actual del servicio."""
    purge_expired()
    payload = _read_payload(servicio_id)
    if not payload or _is_expired(payload):
        _recycle_path(servicio_id).unlink(missing_ok=True)
        raise ValueError(
            "No hay un backup de inventario vigente. La ventana de 30 minutos ya venció."
        )

    tables = payload.get("tables") or {}
    equipos = tables.get(INVENTORY_TABLE) or []
    if not equipos:
        _recycle_path(servicio_id).unlink(missing_ok=True)
        raise ValueError("El backup de inventario está vacío.")

    live_ids = [
        int(r["id"])
        for r in conn.execute(
            f"SELECT id FROM {INVENTORY_TABLE} WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchall()
    ]
    if live_ids and _table_exists(conn, CHILD_TABLE):
        placeholders = ",".join("?" * len(live_ids))
        conn.execute(
            f"DELETE FROM {CHILD_TABLE} WHERE inventario_equipo_id IN ({placeholders})",
            live_ids,
        )
    conn.execute(f"DELETE FROM {INVENTORY_TABLE} WHERE servicio_id = ?", (servicio_id,))
    _insert_rows(conn, INVENTORY_TABLE, equipos)
    _insert_rows(conn, CHILD_TABLE, tables.get(CHILD_TABLE) or [])
    _bump_sequence(conn, INVENTORY_TABLE)
    _bump_sequence(conn, CHILD_TABLE)
    conn.commit()
    _recycle_path(servicio_id).unlink(missing_ok=True)
    return {
        "restored": len(equipos),
        "servicio_id": int(servicio_id),
    }
