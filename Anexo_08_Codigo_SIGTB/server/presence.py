"""Presencia en línea: last_seen con intervalo mínimo y listado por alcance de empresa."""

from datetime import datetime, timedelta, timezone

from flask import session

from server.authz import assigned_empresa_id, current_user, is_direccion, is_global_scope
from server.db import get_empresas_connection, get_users_connection
from server.limits import NAME, clip
from server.roles import is_operativo_director_job

ONLINE_WINDOW_SEC = 180
TOUCH_EVERY_SEC = 45
CLOSED_ESTADOS = frozenset(
    {
        "APROBADA",
        "RECHAZADA",
        "CERRADA",
        "RESUELTA",
        "RESUELTO",
        "IMPLEMENTADO",
        "DESCARTADO",
        "DESCARTADA",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def can_see_all_empresas_online(user=None) -> bool:
    user = user or current_user()
    if not user:
        return False
    if is_global_scope(user):
        return True
    return is_direccion(user) or is_operativo_director_job(user.get("JOB"))


def mark_offline(usuario_id: int | None) -> None:
    if not usuario_id:
        return
    try:
        with get_users_connection() as conn:
            conn.execute(
                "UPDATE usuarios SET last_seen = NULL WHERE id_usuario = ?",
                (int(usuario_id),),
            )
            conn.commit()
    except Exception:
        pass


def touch_presence(usuario_id: int | None = None, *, force: bool = False) -> None:
    """Actualiza last_seen como máximo cada TOUCH_EVERY_SEC (salvo force)."""
    uid = usuario_id or (current_user() or {}).get("id_usuario")
    if not uid:
        return
    last = session.get("presence_touched_at")
    now = datetime.now(timezone.utc)
    if not force and last:
        try:
            prev = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            if now - prev < timedelta(seconds=TOUCH_EVERY_SEC):
                return
        except ValueError:
            pass
    stamp = _now_iso()
    try:
        with get_users_connection() as conn:
            conn.execute(
                "UPDATE usuarios SET last_seen = ? WHERE id_usuario = ?",
                (stamp, int(uid)),
            )
            conn.commit()
        session["presence_touched_at"] = stamp
    except Exception:
        pass


def lecturas_set(users_conn, usuario_id: int) -> set[tuple[str, int]]:
    rows = users_conn.execute(
        "SELECT kind, item_id FROM bandeja_lecturas WHERE usuario_id = ?",
        (int(usuario_id),),
    ).fetchall()
    return {(str(r["kind"]), int(r["item_id"])) for r in rows}


def mark_leido(users_conn, usuario_id: int, kind: str, item_id: int) -> None:
    stamp = _now_iso()
    users_conn.execute(
        """
        INSERT OR IGNORE INTO bandeja_lecturas (usuario_id, kind, item_id, leido_at)
        VALUES (?, ?, ?, ?)
        """,
        (int(usuario_id), kind, int(item_id), stamp),
    )
    users_conn.execute(
        """
        UPDATE bandeja_lecturas
        SET leido_at = ?
        WHERE usuario_id = ? AND kind = ? AND item_id = ?
        """,
        (stamp, int(usuario_id), kind, int(item_id)),
    )


def item_leido(estado, kind: str, item_id: int, reads: set[tuple[str, int]]) -> bool:
    if (kind, int(item_id)) in reads:
        return True
    return str(estado or "").upper() in CLOSED_ESTADOS


def list_online_users(user) -> dict:
    if not user:
        return {"ok": False, "error": "Debes iniciar sesión."}, 401
    touch_presence(user.get("id_usuario"), force=False)
    see_all = can_see_all_empresas_online(user)
    empresa_id = assigned_empresa_id(user)
    if not see_all and not empresa_id:
        return {"ok": True, "usuarios": [], "see_all_empresas": False, "ventana_seg": ONLINE_WINDOW_SEC}, 200

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ONLINE_WINDOW_SEC)).isoformat()
    params: list = [cutoff]
    sql = """
        SELECT id_usuario, NAME_USER, LAST_NAME_USER, JOB, ROLL, empresa_id, last_seen
        FROM usuarios
        WHERE last_seen IS NOT NULL AND last_seen >= ?
    """
    if not see_all:
        sql += " AND empresa_id = ?"
        params.append(int(empresa_id))
    sql += " ORDER BY NAME_USER COLLATE NOCASE, LAST_NAME_USER COLLATE NOCASE LIMIT 80"

    with get_users_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    empresa_names: dict[int, str] = {}
    if see_all and rows:
        ids = sorted({int(r["empresa_id"]) for r in rows if r["empresa_id"]})
        if ids:
            placeholders = ",".join("?" * len(ids))
            with get_empresas_connection() as emp_conn:
                for erow in emp_conn.execute(
                    f"SELECT id, ID_Empresa FROM empresas WHERE id IN ({placeholders})",
                    ids,
                ).fetchall():
                    empresa_names[int(erow["id"])] = erow["ID_Empresa"]

    usuarios = []
    for row in rows:
        emp_id = int(row["empresa_id"]) if row["empresa_id"] else None
        nombre = clip(
            f"{row['NAME_USER'] or ''} {row['LAST_NAME_USER'] or ''}".strip() or "Usuario",
            NAME * 2,
        )
        item = {
            "id_usuario": row["id_usuario"],
            "nombre": nombre,
            "JOB": row["JOB"],
            "ROLL": row["ROLL"],
            "yo": int(row["id_usuario"]) == int(user["id_usuario"]),
        }
        if see_all:
            item["empresa_id"] = emp_id
            item["empresa"] = empresa_names.get(emp_id) if emp_id else "Sin empresa"
        usuarios.append(item)
    return {
        "ok": True,
        "usuarios": usuarios,
        "see_all_empresas": see_all,
        "ventana_seg": ONLINE_WINDOW_SEC,
    }, 200
