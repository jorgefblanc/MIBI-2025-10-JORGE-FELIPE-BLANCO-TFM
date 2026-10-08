"""Forma de adquisición: MP tercerizado y solicitudes de completar dato.

Regla TFM:
  - Compra directa / propio: carga interna de ingeniería clínica.
  - Comodato / Leasing: no aportan Hparque ni plantilla por criticidad.
  - Vacío / No especifica → solicitud en bandeja (PENDIENTE = pendiente de validación).
  - Sin este campo el dimensionamiento no se considera definitivo.
"""

from __future__ import annotations

import json
from typing import Any

from server.authz import assigned_sede_ids, is_global_scope, recipient_for_solicitud
from server.db import get_empresas_connection, get_solicitudes_connection, get_users_connection
from server.roles import is_operativo_director_job, normalize_job
from server.limits import COMMENT
from server.validators import sanitize_string

TIPO_SOLICITUD = "completar_forma_adquisicion"
REF_TIPO = "inventario_equipo"

CATALOGO_FORMA_ADQUISICION = [
    "Compra directa",
    "Leasing",
    "Comodato",
    "No Aplica",
    "No especifica",
]

CATALOGO_FORMA_COMPLETABLE = [
    "Compra directa",
    "Leasing",
    "Comodato",
    "No Aplica",
]

JOB_TABLERO = "Tablero de forma de adquisición"

_ALIASES = {
    "compra directa": "Compra directa",
    "compra": "Compra directa",
    "leasing": "Leasing",
    "arrendamiento": "Leasing",
    "comodato": "Comodato",
    "no aplica": "No Aplica",
    "no aplicable": "No Aplica",
    "n/a": "No Aplica",
    "na": "No Aplica",
    "no especifica": "No especifica",
    "no especificado": "No especifica",
    "no especificada": "No especifica",
    "sin especificar": "No especifica",
}

_MISSING_RAW = {
    "",
    "none",
    "null",
    "sin dato",
    "s/d",
    "sd",
    "no registra",
    "-",
    ".",
}


def canon_forma_adquisicion(value) -> str | None:
    """Normaliza el texto de inventario al catálogo, o None si está vacío."""
    raw = str(value or "").strip()
    if not raw or raw.casefold() in _MISSING_RAW:
        return None
    mapped = _ALIASES.get(raw.casefold())
    if mapped:
        return mapped
    for item in CATALOGO_FORMA_ADQUISICION:
        if item.casefold() == raw.casefold():
            return item
    return raw


def clasificar_forma(value) -> str:
    """terceriza_mp | conocida | faltante."""
    canon = canon_forma_adquisicion(value)
    if canon is None or canon == "No especifica":
        return "faltante"
    if canon in ("Comodato", "Leasing"):
        return "terceriza_mp"
    return "conocida"


def mp_forzado_por_adquisicion(value) -> bool:
    return clasificar_forma(value) == "terceriza_mp"


def forma_es_completable(value) -> bool:
    canon = canon_forma_adquisicion(value)
    return canon in CATALOGO_FORMA_COMPLETABLE


def aplicar_mp_por_adquisicion(payload: dict[str, Any]) -> dict[str, Any]:
    """Fuerza aplica_mp + tercerizado_mp cuando la adquisición lo exige."""
    if not mp_forzado_por_adquisicion(payload.get("forma_adquisicion")):
        return payload
    payload["aplica_mp"] = True
    payload["tercerizado_mp"] = True
    payload["mp_forzado_tercerizado"] = True
    return payload


def _job_puede_completar_adquisicion(user) -> bool:
    if is_global_scope(user):
        return True
    if (user.get("ROLL") or "").upper() != "OPERATIVO":
        return False
    job = normalize_job("OPERATIVO", user.get("JOB"))
    return job in ("Coordinador", "Director Operativo", "Ingeniero") or is_operativo_director_job(
        user.get("JOB")
    )


def user_puede_completar_adquisicion(user) -> bool:
    return _job_puede_completar_adquisicion(user)


def _job_ve_tablero(user) -> bool:
    """Solo Coordinador y Director operativo (más ADMIN por alcance global)."""
    if is_global_scope(user):
        return True
    if (user.get("ROLL") or "").upper() != "OPERATIVO":
        return False
    job = normalize_job("OPERATIVO", user.get("JOB"))
    return job in ("Coordinador", "Director Operativo") or is_operativo_director_job(user.get("JOB"))


def recipient_for_adquisicion(users_conn, *, sede_id, empresa_id):
    """Cargos de la sede: Coordinador → Dirección → Ingeniería."""
    for rol in ("coordinacion", "direccion", "ingenieria"):
        dest = recipient_for_solicitud(
            users_conn,
            sede_id=sede_id,
            empresa_id=empresa_id,
            destinatario_rol=rol,
        )
        if dest:
            return dest, rol
    return None, None


def _pending_ref_ids(sol_conn, sede_id: int) -> set[int]:
    rows = sol_conn.execute(
        """
        SELECT ref_id FROM solicitudes
        WHERE tipo = ? AND ref_tipo = ? AND estado = 'PENDIENTE'
          AND sede_id = ? AND ref_id IS NOT NULL
        """,
        (TIPO_SOLICITUD, REF_TIPO, sede_id),
    ).fetchall()
    return {int(r["ref_id"]) for r in rows if r["ref_id"] is not None}


def ensure_solicitudes_adquisicion(
    *,
    user,
    sede: dict,
    equipos: list[dict],
) -> dict[str, Any]:
    """Crea una solicitud PENDIENTE por equipo en dotación sin forma de adquisición."""
    created = 0
    skipped = 0
    already = 0
    warning = None
    faltantes = [
        eq
        for eq in equipos
        if eq.get("en_dotacion", True) and clasificar_forma(eq.get("forma_adquisicion")) == "faltante"
    ]
    if not faltantes:
        return {"created": 0, "skipped": 0, "already": 0, "faltantes": 0, "warning": None}

    with get_users_connection() as users_conn, get_solicitudes_connection() as sol_conn:
        dest, dest_rol = recipient_for_adquisicion(
            users_conn,
            sede_id=int(sede["id"]),
            empresa_id=int(sede["empresa_id"]),
        )
        if not dest:
            warning = (
                "Hay equipos sin forma de adquisición, pero no hay Coordinador, "
                "Director operativo ni Ingeniero destinatario en esta sede/empresa."
            )
            return {
                "created": 0,
                "skipped": len(faltantes),
                "already": 0,
                "faltantes": len(faltantes),
                "warning": warning,
            }

        solicitante = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, ROLL, JOB
            FROM usuarios WHERE id_usuario = ?
            """,
            (user["id_usuario"],),
        ).fetchone()
        if not solicitante:
            return {
                "created": 0,
                "skipped": len(faltantes),
                "already": 0,
                "faltantes": len(faltantes),
                "warning": "No se pudo identificar al usuario que carga el dimensionamiento.",
            }

        pending = _pending_ref_ids(sol_conn, int(sede["id"]))
        dest_nombre = f"{dest['NAME_USER']} {dest['LAST_NAME_USER']}".strip()
        sol_nombre = f"{solicitante['NAME_USER']} {solicitante['LAST_NAME_USER']}".strip()

        for eq in faltantes:
            eq_id = int(eq["inventario_equipo_id"])
            if eq_id in pending:
                already += 1
                continue
            meta = {
                "empresa_id": sede.get("empresa_id"),
                "empresa": sede.get("ID_Empresa"),
                "sede_id": sede.get("id"),
                "ID_sede": sede.get("ID_sede"),
                "name_sede": sede.get("name_sede"),
                "servicio_id": eq.get("servicio_id"),
                "servicio": eq.get("servicio"),
                "inventario_equipo_id": eq_id,
                "equipo": eq.get("equipo"),
                "codigo": eq.get("codigo"),
                "catalogo": CATALOGO_FORMA_COMPLETABLE,
                "alerta_sin_datos_anio": bool(eq.get("alerta_sin_datos_anio")),
                "alerta_mensaje": eq.get("alerta_mensaje") or "",
            }
            mensaje = (
                f"Completar forma de adquisición del equipo «{eq.get('equipo') or '—'}» "
                f"({eq.get('codigo') or eq_id}).\n"
                f"Empresa: {sede.get('ID_Empresa') or '—'}\n"
                f"Sede: {sede.get('ID_sede') or '—'} · {sede.get('name_sede') or '—'}\n"
                f"Servicio: {eq.get('servicio') or '—'}\n"
                "Seleccione la modalidad (Compra directa, Leasing, Comodato o No Aplica) "
                "y deje una observación."
            )
            sol_conn.execute(
                """
                INSERT INTO solicitudes (
                    solicitante_id, solicitante_email, solicitante_nombre,
                    solicitante_roll, solicitante_job,
                    destinatario_id, destinatario_email, destinatario_nombre, destinatario_rol,
                    sede_id, empresa_id, servicio_id, ID_sede, name_sede,
                    tipo, mensaje, prioridad, estado,
                    ref_tipo, ref_id, meta_json, creation_date
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, 'ALTA', 'PENDIENTE',
                    ?, ?, ?, datetime('now')
                )
                """,
                (
                    solicitante["id_usuario"],
                    solicitante["usuario_login"],
                    sol_nombre,
                    solicitante["ROLL"],
                    solicitante["JOB"],
                    dest["id_usuario"],
                    dest["usuario_login"],
                    dest_nombre,
                    dest_rol,
                    int(sede["id"]),
                    int(sede["empresa_id"]),
                    int(eq.get("servicio_id") or 0) or None,
                    sede.get("ID_sede"),
                    sede.get("name_sede"),
                    TIPO_SOLICITUD,
                    mensaje,
                    REF_TIPO,
                    eq_id,
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            created += 1
            pending.add(eq_id)
        sol_conn.commit()

    return {
        "created": created,
        "skipped": skipped,
        "already": already,
        "faltantes": len(faltantes),
        "warning": warning,
        "destinatario": dest["usuario_login"] if dest else None,
    }


def user_sede_scope_ids(user) -> set[int] | None:
    """Sedes visibles para solicitudes de adquisición. None = todas (ADMIN)."""
    if is_global_scope(user):
        return None
    with get_users_connection() as users_conn:
        assigned = assigned_sede_ids(users_conn, user["id_usuario"])
    empresa_id = user.get("empresa_id")
    job = normalize_job((user.get("ROLL") or ""), user.get("JOB"))
    if is_operativo_director_job(user.get("JOB")) or job == "Director Operativo":
        if empresa_id:
            with get_empresas_connection() as emp_conn:
                rows = emp_conn.execute(
                    "SELECT id FROM sedes WHERE empresa_id = ?", (empresa_id,)
                ).fetchall()
            return assigned | {int(r["id"]) for r in rows}
    return assigned


def solicitud_adquisicion_visible(user, solicitud) -> bool:
    if int(solicitud.get("solicitante_id") or 0) == int(user["id_usuario"]):
        return True
    if int(solicitud.get("destinatario_id") or 0) == int(user["id_usuario"]):
        return True
    if (solicitud.get("tipo") or "") != TIPO_SOLICITUD:
        return False
    if not _job_puede_completar_adquisicion(user):
        return False
    scope = user_sede_scope_ids(user)
    if scope is None:
        return True
    return int(solicitud.get("sede_id") or 0) in scope


def can_completar_solicitud_adquisicion(user, solicitud) -> bool:
    if (solicitud.get("tipo") or "") != TIPO_SOLICITUD:
        return False
    if not solicitud_adquisicion_visible(user, solicitud):
        return False
    if not _job_puede_completar_adquisicion(user):
        return False
    estado = str(solicitud.get("estado") or "").upper()
    uid = int(user["id_usuario"])
    asignado = int(solicitud.get("asignado_a") or 0)
    if estado == "TOMADA":
        return is_global_scope(user) or asignado == uid
    if estado == "PENDIENTE":
        return is_global_scope(user)
    return False


def extra_solicitudes_adquisicion(user, sol_conn=None) -> list[dict]:
    """Pendientes de adquisición visibles por sede/cargo, no solo destinatario."""
    if not _job_puede_completar_adquisicion(user):
        return []
    scope = user_sede_scope_ids(user)

    def _fetch(conn):
        if scope is None:
            rows = conn.execute(
                """
                SELECT * FROM solicitudes
                WHERE tipo = ?
                ORDER BY creation_date DESC
                """,
                (TIPO_SOLICITUD,),
            ).fetchall()
        elif not scope:
            return []
        else:
            placeholders = ",".join("?" * len(scope))
            rows = conn.execute(
                f"""
                SELECT * FROM solicitudes
                WHERE tipo = ? AND sede_id IN ({placeholders})
                ORDER BY creation_date DESC
                """,
                (TIPO_SOLICITUD, *scope),
            ).fetchall()
        uid = int(user["id_usuario"])
        out = []
        for row in rows:
            item = dict(row)
            if int(item.get("solicitante_id") or 0) == uid or int(
                item.get("destinatario_id") or 0
            ) == uid:
                continue
            estado = str(item.get("estado") or "").upper()
            asignado = int(item.get("asignado_a") or 0)
            if asignado and asignado != uid:
                continue
            if estado not in ("PENDIENTE", "REENVIADA"):
                continue
            out.append(item)
        return out

    if sol_conn is not None:
        return _fetch(sol_conn)
    with get_solicitudes_connection() as conn:
        return _fetch(conn)


def aplicar_forma_adquisicion(
    *,
    inventario_equipo_id: int,
    forma: str,
    observacion: str,
    user,
) -> dict[str, Any]:
    """Persiste la modalidad y, si hay texto, la observación. Si aplica, fuerza MP tercerizado."""
    canon = canon_forma_adquisicion(forma)
    if canon not in CATALOGO_FORMA_COMPLETABLE:
        raise ValueError(
            "Seleccione Compra directa, Leasing, Comodato o No Aplica. "
            "No especifica no cierra la solicitud."
        )
    nota = sanitize_string(observacion, COMMENT) or ""

    with get_empresas_connection() as emp_conn:
        inv = emp_conn.execute(
            """
            SELECT ie.id, ie.equipo, ie.servicio_id, srv.sede_id, srv.name_servicio,
                   s.empresa_id
            FROM inventario_equipos ie
            JOIN servicios srv ON srv.id = ie.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            WHERE ie.id = ?
            """,
            (inventario_equipo_id,),
        ).fetchone()
        if not inv:
            raise ValueError("Equipo no encontrado.")

        cols = {
            c["name"]
            for c in emp_conn.execute("PRAGMA table_info(inventario_equipos)").fetchall()
        }
        if "adquisicion_observacion" in cols:
            emp_conn.execute(
                """
                UPDATE inventario_equipos
                SET forma_adquisicion = ?, adquisicion_observacion = ?
                WHERE id = ?
                """,
                (canon, nota, inventario_equipo_id),
            )
        else:
            emp_conn.execute(
                "UPDATE inventario_equipos SET forma_adquisicion = ? WHERE id = ?",
                (canon, inventario_equipo_id),
            )

        if mp_forzado_por_adquisicion(canon):
            emp_conn.execute(
                """
                INSERT INTO dim_actividad_equipo (
                    inventario_equipo_id, criticidad,
                    aplica_mp, freq_mp, tiempo_mp,
                    aplica_cal, freq_cal, tiempo_cal,
                    aplica_val, freq_val, tiempo_val,
                    tercerizado_mp, tercerizado_cal, tercerizado_val,
                    aplica_cap, freq_cap, tiempo_cap,
                    tiene_historico_correctivo, historico_correctivo_h,
                    gestion_documental_h, acompanamiento_h, otras_tareas_h,
                    observaciones, updated_at
                ) VALUES (?, 'Medio', 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, NULL, 0, 0, 0, ?, datetime('now'))
                ON CONFLICT(inventario_equipo_id) DO UPDATE SET
                    aplica_mp = 1,
                    tercerizado_mp = 1,
                    observaciones = CASE
                        WHEN excluded.observaciones != '' THEN excluded.observaciones
                        ELSE dim_actividad_equipo.observaciones
                    END,
                    updated_at = datetime('now')
                """,
                (inventario_equipo_id, nota),
            )
            emp_conn.execute(
                "UPDATE inventario_equipos SET aplica_mp = 1 WHERE id = ?",
                (inventario_equipo_id,),
            )
        emp_conn.commit()

    return {
        "forma_adquisicion": canon,
        "observacion": nota,
        "mp_forzado_tercerizado": mp_forzado_por_adquisicion(canon),
        "resuelto_por": user.get("usuario_login"),
    }


def cerrar_solicitudes_equipo(inventario_equipo_id: int, meta_extra: dict | None = None):
    extra = meta_extra or {}
    with get_solicitudes_connection() as sol_conn:
        rows = sol_conn.execute(
            """
            SELECT id, meta_json FROM solicitudes
            WHERE tipo = ? AND ref_tipo = ? AND ref_id = ? AND estado = 'PENDIENTE'
            """,
            (TIPO_SOLICITUD, REF_TIPO, int(inventario_equipo_id)),
        ).fetchall()
        for row in rows:
            meta = {}
            raw = row["meta_json"]
            if isinstance(raw, str) and raw.strip():
                try:
                    meta = json.loads(raw)
                except Exception:
                    meta = {}
            meta.update(extra)
            sol_conn.execute(
                """
                UPDATE solicitudes
                SET estado = 'APROBADA', resolved_at = datetime('now'), meta_json = ?
                WHERE id = ?
                """,
                (json.dumps(meta, ensure_ascii=False), row["id"]),
            )
        sol_conn.commit()
    return len(rows)


def tablero_adquisicion(user) -> dict[str, Any]:
    """Resumen ejecutivo para Coordinador y Director operativo."""
    scope = user_sede_scope_ids(user)
    sede_filter = ""
    params: list[Any] = []
    if scope is not None:
        if not scope:
            return {
                "totales": {
                    "equipos_dotacion": 0,
                    "terceriza_mp": 0,
                    "conocida": 0,
                    "faltante": 0,
                    "pendientes_bandeja": 0,
                    "resueltas": 0,
                },
                "por_empresa": [],
                "por_sede": [],
                "por_servicio": [],
                "pendientes": [],
                "catalogo": CATALOGO_FORMA_ADQUISICION,
            }
        placeholders = ",".join("?" * len(scope))
        sede_filter = f"AND s.id IN ({placeholders})"
        params = list(scope)

    with get_empresas_connection() as emp_conn:
        rows = emp_conn.execute(
            f"""
            SELECT
                e.id AS empresa_id,
                e.ID_Empresa AS empresa,
                s.id AS sede_id,
                s.ID_sede,
                s.name_sede,
                srv.id AS servicio_id,
                srv.name_servicio,
                ie.id AS inventario_equipo_id,
                ie.equipo,
                ie.num_biomedica,
                ie.forma_adquisicion,
                ie.estado,
                ie.fecha_baja
            FROM inventario_equipos ie
            JOIN servicios srv ON srv.id = ie.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            JOIN empresas e ON e.id = s.empresa_id
            WHERE 1=1 {sede_filter}
            ORDER BY e.ID_Empresa COLLATE NOCASE, s.name_sede COLLATE NOCASE,
                     srv.name_servicio COLLATE NOCASE, ie.equipo COLLATE NOCASE
            """,
            params,
        ).fetchall()

    equipos = []
    for r in rows:
        estado = str(r["estado"] or "").strip().upper()
        if estado in {"FUERA DE SERVICIO", "BAJA"} or r["fecha_baja"]:
            continue
        clase = clasificar_forma(r["forma_adquisicion"])
        equipos.append(
            {
                "empresa_id": r["empresa_id"],
                "empresa": r["empresa"],
                "sede_id": r["sede_id"],
                "ID_sede": r["ID_sede"],
                "name_sede": r["name_sede"],
                "servicio_id": r["servicio_id"],
                "servicio": r["name_servicio"],
                "inventario_equipo_id": r["inventario_equipo_id"],
                "equipo": r["equipo"],
                "codigo": r["num_biomedica"] or f"EQ-{r['inventario_equipo_id']}",
                "forma_adquisicion": r["forma_adquisicion"] or "",
                "clase": clase,
            }
        )

    def _bucket(items, key_fn, label_fn):
        acc: dict[tuple, dict] = {}
        for item in items:
            key = key_fn(item)
            if key not in acc:
                acc[key] = {
                    **label_fn(item),
                    "total": 0,
                    "terceriza_mp": 0,
                    "conocida": 0,
                    "faltante": 0,
                }
            acc[key]["total"] += 1
            acc[key][item["clase"]] += 1
        return list(acc.values())

    por_empresa = _bucket(
        equipos,
        lambda i: i["empresa_id"],
        lambda i: {"empresa_id": i["empresa_id"], "empresa": i["empresa"]},
    )
    por_sede = _bucket(
        equipos,
        lambda i: i["sede_id"],
        lambda i: {
            "sede_id": i["sede_id"],
            "empresa": i["empresa"],
            "ID_sede": i["ID_sede"],
            "name_sede": i["name_sede"],
        },
    )
    por_servicio = _bucket(
        equipos,
        lambda i: i["servicio_id"],
        lambda i: {
            "servicio_id": i["servicio_id"],
            "empresa": i["empresa"],
            "name_sede": i["name_sede"],
            "servicio": i["servicio"],
        },
    )

    with get_solicitudes_connection() as sol_conn:
        if scope is None:
            sols = sol_conn.execute(
                "SELECT estado, sede_id FROM solicitudes WHERE tipo = ?",
                (TIPO_SOLICITUD,),
            ).fetchall()
        else:
            placeholders = ",".join("?" * len(scope))
            sols = sol_conn.execute(
                f"""
                SELECT estado, sede_id FROM solicitudes
                WHERE tipo = ? AND sede_id IN ({placeholders})
                """,
                (TIPO_SOLICITUD, *scope),
            ).fetchall()

    pendientes_b = sum(1 for s in sols if (s["estado"] or "") == "PENDIENTE")
    resueltas = sum(1 for s in sols if (s["estado"] or "") in ("APROBADA", "RECHAZADA"))

    faltantes = [e for e in equipos if e["clase"] == "faltante"]
    return {
        "totales": {
            "equipos_dotacion": len(equipos),
            "terceriza_mp": sum(1 for e in equipos if e["clase"] == "terceriza_mp"),
            "conocida": sum(1 for e in equipos if e["clase"] == "conocida"),
            "faltante": len(faltantes),
            "pendientes_bandeja": pendientes_b,
            "resueltas": resueltas,
        },
        "por_empresa": por_empresa,
        "por_sede": por_sede,
        "por_servicio": por_servicio,
        "pendientes": faltantes[:200],
        "catalogo": CATALOGO_FORMA_ADQUISICION,
    }
