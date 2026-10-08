"""API HTTP de frecuencia de mantenimiento preventivo (GE y fabricante)."""

from __future__ import annotations

import io
from calendar import monthrange
from datetime import date, datetime

from flask import Blueprint, jsonify, request, send_file, session

from server.authz import (
    assigned_empresa_id,
    assigned_sede_ids,
    can_access_empresa,
    can_access_sede,
    can_access_servicio,
    current_user,
    is_global_scope,
    login_required,
    permission_required,
    recipient_for_solicitud,
)
from server.db import (
    discard_pending_solicitud,
    get_empresas_connection,
    get_solicitudes_connection,
    get_users_connection,
    revert_solicitud_estado,
)
from server.frecuencia_pm import (
    ESTADOS_EQUIPO,
    buscar_semejanzas,
    build_cronograma_meses,
    catalogs_payload,
    dashboard_stats,
    enrich_row,
    equipo_fuera_de_programa_pm,
    equipos_duplicados,
    parse_date,
    reporte_cobertura_sedes,
)
from server.ejecucion_mantenimientos import (
    attach_pm_ejecucion,
    insert_ejecucion,
    list_ejecucion,
    validate_manual_payload,
)
from server.event_log import log_evento
from server.frecuencia_pm_pdf import build_cronograma_pdf, build_informe_resumen_pdf
from server.pdf_staff import collect_org_staff
from server.inventory_enrichment import (
    map_aplicacion_oms,
    map_fallas_oms,
    map_funcion_oms,
    map_requisito_oms,
)
from server.inventario_params import freq_anual_to_meses
from server.limits import COMMENT, LONG_TEXT
from server.formula_versions import formula_meta, registrar_calculo
from server.validators import sanitize_string

pm_bp = Blueprint("frecuencia_pm", __name__, url_prefix="/api/frecuencia-pm")

_SCORE_FIELDS = ("funcion", "aplicacion", "requisito_mantto", "antecedentes_fallas")
_VALIDATE_JOBS = ("Coordinador", "Director", "Dirección", "Líder")
_MES_COLS = tuple(f"mes_{i:02d}" for i in range(1, 13))


# ---------------------------------------------------------------------------
# Capacidades por rol
# ---------------------------------------------------------------------------


def _role_caps(user) -> dict:
    """Caps de UI/API según ROLL y JOB del usuario autenticado."""
    user = user or {}
    roll = (user.get("ROLL") or session.get("ROLL") or "").upper()
    job = (user.get("JOB") or session.get("JOB") or "").strip()

    is_admin = roll == "ADMIN" or is_global_scope(user)
    is_operativo = roll == "OPERATIVO"
    is_asistencial = roll == "ASISTENCIAL"

    job_norm = job.casefold()
    can_validate_job = any(j.casefold() == job_norm for j in _VALIDATE_JOBS) or any(
        token in job_norm for token in ("coordinador", "director", "dirección", "direccion", "líder", "lider")
    )

    return {
        "can_view_full": bool(is_admin or is_operativo),
        "can_view_cronograma": bool(is_admin or is_operativo or is_asistencial),
        "can_edit_scores": bool(is_admin),
        "can_edit_operational": bool(is_admin or is_operativo),
        "can_execute": bool(is_admin or is_operativo),
        "can_validate": bool(is_admin or (is_asistencial and can_validate_job)),
        "can_edit_catalogs": bool(is_admin),
    }


# ---------------------------------------------------------------------------
# Utilidades de servicio / filas
# ---------------------------------------------------------------------------


def _servicio_meta(conn, servicio_id: int):
    return conn.execute(
        """
        SELECT srv.id, srv.ID_servicio, srv.name_servicio, srv.sede_id,
               s.ID_sede, s.name_sede, s.empresa_id, e.ID_Empresa, e.ID_NIT
        FROM servicios srv
        JOIN sedes s ON s.id = srv.sede_id
        JOIN empresas e ON e.id = s.empresa_id
        WHERE srv.id = ?
        """,
        (servicio_id,),
    ).fetchone()


def _require_servicio(conn, user, servicio_id: int):
    meta = _servicio_meta(conn, servicio_id)
    if not meta:
        return None, (jsonify({"ok": False, "error": "Servicio no encontrado."}), 404)
    if not can_access_servicio(user, servicio_id):
        return None, (jsonify({"ok": False, "error": "No autorizado."}), 403)
    return meta, None


def _anio_from_request(default: int | None = None) -> int:
    raw = request.args.get("anio")
    if raw in (None, "") and request.method in ("POST", "PUT", "PATCH"):
        body = request.get_json(silent=True) or {}
        raw = body.get("anio")
    if raw in (None, ""):
        return int(default or datetime.now().year)
    try:
        anio = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("anio inválido.") from exc
    if anio < 2000 or anio > 2100:
        raise ValueError("anio fuera de rango.")
    return anio


def _map_estado_inventario(estado: str | None) -> str | None:
    if not estado:
        return "Operativo"
    text = str(estado).strip()
    upper = text.upper()
    mapping = {
        "OPERATIVO": "Operativo",
        "EN REPARACIÓN": "En observación",
        "EN REPARACION": "En observación",
        "FUERA DE SERVICIO": "Fuera de servicio",
        "BAJA": "Retirado",
        "RETIRADO": "Retirado",
    }
    if upper in mapping:
        return mapping[upper]
    for item in ESTADOS_EQUIPO:
        if item.casefold() == text.casefold():
            return item
    return text[:80] or "Operativo"


def _as_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fecha_iso(value) -> str | None:
    d = parse_date(value)
    return d.isoformat() if d else None


def _row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def _inventario_payload(row: dict, crono: dict | None = None, validaciones: list | None = None) -> dict:
    payload = dict(row)
    for key in ("fecha_ultimo_pm", "updated_at"):
        if payload.get(key) is not None:
            payload[key] = str(payload[key])[:19] if key == "updated_at" else _fecha_iso(payload[key]) or str(payload[key])[:10]
    if crono:
        c = dict(crono)
        c["fecha_ultimo_pm"] = _fecha_iso(c.get("fecha_ultimo_pm")) or c.get("fecha_ultimo_pm")
        if c.get("updated_at") is not None:
            c["updated_at"] = str(c["updated_at"])[:19]
        payload["cronograma"] = c
        payload["meses"] = {i: int(c.get(f"mes_{i:02d}") or 0) for i in range(1, 13)}
    else:
        payload["cronograma"] = None
        payload["meses"] = {i: 0 for i in range(1, 13)}
    payload["validaciones"] = validaciones or []
    return payload


# ---------------------------------------------------------------------------
# Cronograma + validaciones
# ---------------------------------------------------------------------------


def _fechas_por_mes(fechas: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for raw in fechas or []:
        d = parse_date(raw)
        if d:
            out[d.month] = d.isoformat()
    return out


def _default_fecha_mes(anio: int, mes: int, fecha_ultimo_pm) -> str:
    last = parse_date(fecha_ultimo_pm)
    day = last.day if last else 1
    day = min(day, monthrange(anio, mes)[1])
    return date(anio, mes, day).isoformat()


def _lookup_inventario_pm_flags(conn, pm_row: dict) -> dict:
    flags = {
        "aplica_mp": None,
        "fecha_baja": None,
        "estado_inventario": None,
    }
    inv_id = pm_row.get("inventario_equipo_id")
    if not inv_id:
        return flags
    inv = conn.execute(
        """
        SELECT aplica_mp, fecha_baja, estado, ubicacion, codigo_ubicacion,
               fecha_ultimo_pm, num_biomedica, codigo_activo
        FROM inventario_equipos WHERE id = ?
        """,
        (inv_id,),
    ).fetchone()
    if not inv:
        return flags
    return {
        "aplica_mp": inv["aplica_mp"],
        "fecha_baja": inv["fecha_baja"],
        "estado_inventario": inv["estado"],
        "ubicacion": inv["ubicacion"],
        "codigo_ubicacion": inv["codigo_ubicacion"],
        "fecha_ultimo_pm": inv["fecha_ultimo_pm"],
        "num_biomedica": inv["num_biomedica"],
        "codigo_activo": inv["codigo_activo"],
    }


def _upsert_cronograma(conn, pm_inventario_id: int, anio: int, row: dict) -> dict:
    """Reconstruye marcas mensuales y asegura filas de validación para meses programados."""
    built = build_cronograma_meses(
        row.get("fecha_ultimo_pm"),
        row.get("frecuencia_definitiva"),
        anio,
    )
    meses = built.get("meses") or {i: 0 for i in range(1, 13)}
    observacion = built.get("observacion")
    fechas = built.get("fechas") or []
    fecha_map = _fechas_por_mes(fechas)

    conn.execute(
        f"""
        INSERT INTO pm_cronograma (
            pm_inventario_id, anio, frecuencia_definitiva, fecha_ultimo_pm,
            {", ".join(_MES_COLS)},
            observacion, updated_at
        ) VALUES (
            ?, ?, ?, ?,
            {", ".join("?" for _ in _MES_COLS)},
            ?, datetime('now')
        )
        ON CONFLICT(pm_inventario_id, anio) DO UPDATE SET
            frecuencia_definitiva = excluded.frecuencia_definitiva,
            fecha_ultimo_pm = excluded.fecha_ultimo_pm,
            {", ".join(f"{c} = excluded.{c}" for c in _MES_COLS)},
            observacion = excluded.observacion,
            updated_at = datetime('now')
        """,
        (
            pm_inventario_id,
            anio,
            row.get("frecuencia_definitiva"),
            _fecha_iso(row.get("fecha_ultimo_pm")),
            *[int(meses.get(i) or 0) for i in range(1, 13)],
            observacion,
        ),
    )

    marked = [i for i in range(1, 13) if int(meses.get(i) or 0)]
    for mes in marked:
        fecha_prog = fecha_map.get(mes) or _default_fecha_mes(anio, mes, row.get("fecha_ultimo_pm"))
        conn.execute(
            """
            INSERT INTO pm_validacion (
                pm_inventario_id, anio, mes, fecha_programada, estado, updated_at
            ) VALUES (?, ?, ?, ?, 'PENDIENTE', datetime('now'))
            ON CONFLICT(pm_inventario_id, anio, mes) DO UPDATE SET
                fecha_programada = COALESCE(pm_validacion.fecha_programada, excluded.fecha_programada),
                updated_at = datetime('now')
            """,
            (pm_inventario_id, anio, mes, fecha_prog),
        )

    # Limpia pendientes de meses que ya no están programados (conserva historial ejecutado/validado).
    if marked:
        placeholders = ",".join("?" * len(marked))
        conn.execute(
            f"""
            DELETE FROM pm_validacion
            WHERE pm_inventario_id = ? AND anio = ?
              AND estado = 'PENDIENTE'
              AND mes NOT IN ({placeholders})
            """,
            (pm_inventario_id, anio, *marked),
        )
    else:
        conn.execute(
            """
            DELETE FROM pm_validacion
            WHERE pm_inventario_id = ? AND anio = ? AND estado = 'PENDIENTE'
            """,
            (pm_inventario_id, anio),
        )

    crono = conn.execute(
        "SELECT * FROM pm_cronograma WHERE pm_inventario_id = ? AND anio = ?",
        (pm_inventario_id, anio),
    ).fetchone()
    return _row_dict(crono)


def _rebuild_equipo(conn, pm_row: dict, anio: int) -> dict:
    enriched = enrich_row(dict(pm_row))
    flags = _lookup_inventario_pm_flags(conn, pm_row)
    merged_flags = {**enriched, **flags, "estado": pm_row.get("estado") or enriched.get("estado")}
    if equipo_fuera_de_programa_pm(merged_flags):
        enriched["frecuencia_definitiva"] = "Correctivo bajo demanda"
        if not enriched.get("accion_sugerida"):
            enriched["accion_sugerida"] = "Fuera de programa de PM (baja, fuera de servicio o no aplica)."
    conn.execute(
        """
        UPDATE pm_inventario SET
            funcion = ?, puntaje_funcion = ?,
            aplicacion = ?, puntaje_aplicacion = ?,
            requisito_mantto = ?, puntaje_requisito = ?,
            antecedentes_fallas = ?, puntaje_fallas = ?,
            ge_total = ?, frecuencia_oms = ?, frecuencia_definitiva = ?,
            accion_sugerida = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            enriched.get("funcion"),
            enriched.get("puntaje_funcion"),
            enriched.get("aplicacion"),
            enriched.get("puntaje_aplicacion"),
            enriched.get("requisito_mantto"),
            enriched.get("puntaje_requisito"),
            enriched.get("antecedentes_fallas"),
            enriched.get("puntaje_fallas"),
            enriched.get("ge_total"),
            enriched.get("frecuencia_oms"),
            enriched.get("frecuencia_definitiva"),
            enriched.get("accion_sugerida"),
            pm_row["id"],
        ),
    )
    refreshed = conn.execute(
        "SELECT * FROM pm_inventario WHERE id = ?", (pm_row["id"],)
    ).fetchone()
    crono_row = dict(refreshed)
    crono_row.update(flags)
    if equipo_fuera_de_programa_pm({**crono_row, "estado": crono_row.get("estado")}):
        crono_row["frecuencia_definitiva"] = "Correctivo bajo demanda"
    crono = _upsert_cronograma(conn, pm_row["id"], anio, crono_row)
    if equipo_fuera_de_programa_pm({**crono_row, "estado": crono_row.get("estado")}):
        conn.execute(
            """
            UPDATE pm_cronograma
            SET observacion = ?,
                mes_01=0, mes_02=0, mes_03=0, mes_04=0, mes_05=0, mes_06=0,
                mes_07=0, mes_08=0, mes_09=0, mes_10=0, mes_11=0, mes_12=0,
                updated_at = datetime('now')
            WHERE pm_inventario_id = ? AND anio = ?
            """,
            (
                "Fuera de programa: baja, fuera de servicio o no aplica MP.",
                pm_row["id"],
                anio,
            ),
        )
        crono = conn.execute(
            "SELECT * FROM pm_cronograma WHERE pm_inventario_id = ? AND anio = ?",
            (pm_row["id"], anio),
        ).fetchone()
        crono = _row_dict(crono)
    return {"inventario": dict(refreshed), "cronograma": crono}


def _rebuild_servicio(conn, servicio_id: int, anio: int) -> int:
    rows = conn.execute(
        "SELECT * FROM pm_inventario WHERE servicio_id = ? ORDER BY id",
        (servicio_id,),
    ).fetchall()
    for row in rows:
        _rebuild_equipo(conn, dict(row), anio)
    return len(rows)


def _load_validaciones(conn, pm_inventario_id: int, anio: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM pm_validacion
        WHERE pm_inventario_id = ? AND anio = ?
        ORDER BY mes ASC
        """,
        (pm_inventario_id, anio),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ("fecha_programada", "fecha_ejecucion", "updated_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])[:19] if key == "updated_at" else str(item[key])[:10]
        result.append(item)
    return result


def _load_contexto(conn, servicio_id: int, anio: int, meta) -> dict:
    inv_rows = conn.execute(
        """
        SELECT pi.*,
               ie.num_biomedica AS inv_num_biomedica,
               ie.codigo_activo AS inv_codigo_activo,
               ie.freq_mp AS inv_freq_mp,
               ie.ubicacion AS inv_ubicacion,
               ie.codigo_ubicacion AS inv_codigo_ubicacion,
               ie.fecha_baja AS inv_fecha_baja,
               ie.estado AS inv_estado,
               ie.fecha_ultimo_pm AS inv_fecha_ultimo_pm
        FROM pm_inventario pi
        LEFT JOIN inventario_equipos ie ON ie.id = pi.inventario_equipo_id
        WHERE pi.servicio_id = ?
        ORDER BY pi.equipo COLLATE NOCASE, pi.id
        """,
        (servicio_id,),
    ).fetchall()

    equipos = []
    for row in inv_rows:
        inv = dict(row)
        crono = conn.execute(
            "SELECT * FROM pm_cronograma WHERE pm_inventario_id = ? AND anio = ?",
            (inv["id"], anio),
        ).fetchone()
        vals = _load_validaciones(conn, inv["id"], anio)
        payload = _inventario_payload(inv, _row_dict(crono) if crono else None, vals)
        payload["servicio_nombre"] = meta["name_servicio"]
        payload["servicio"] = meta["name_servicio"]
        flags = _lookup_inventario_pm_flags(conn, inv)
        payload["ubicacion"] = inv.get("inv_ubicacion") or inv.get("ubicacion")
        payload["codigo_ubicacion"] = inv.get("inv_codigo_ubicacion")
        payload["fecha_baja"] = inv.get("inv_fecha_baja") or flags.get("fecha_baja")
        payload["num_biomedica"] = inv.get("inv_num_biomedica")
        payload["codigo_activo"] = inv.get("inv_codigo_activo")
        payload["en_programa_pm"] = not equipo_fuera_de_programa_pm(
            {**inv, **flags, **payload, "estado": inv.get("estado") or flags.get("estado_inventario")}
        )
        equipos.append(payload)

    try:
        attach_pm_ejecucion(conn, equipos, meta["empresa_id"], anio=anio)
    except Exception:
        pass

    stats = dashboard_stats(equipos)
    return {
        "servicio": dict(meta),
        "anio": anio,
        "equipos": equipos,
        "dashboard": stats,
        "total_equipos": len(equipos),
    }


def _create_solicitud_validacion(
    *,
    user,
    meta,
    validacion: dict,
    inventario: dict,
) -> int:
    """Inserta solicitud tipo validar_pm_cronograma vinculada a pm_validacion."""
    import json

    with get_users_connection() as users_conn, get_solicitudes_connection() as sol_conn:
        solicitante = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, ROLL, JOB
            FROM usuarios WHERE id_usuario = ?
            """,
            (user["id_usuario"],),
        ).fetchone()
        if not solicitante:
            raise ValueError("Usuario solicitante no encontrado.")

        dest = recipient_for_solicitud(
            users_conn,
            sede_id=meta["sede_id"],
            empresa_id=meta["empresa_id"],
            destinatario_rol="asistencial",
        )
        if not dest:
            raise ValueError(
                "No hay destinatario ASISTENCIAL (Coordinador/Director/Líder) disponible "
                "para esta sede/empresa."
            )

        mensaje = (
            f"Validar cumplimiento de PM cronograma — equipo «{inventario.get('equipo') or '—'}» "
            f"({inventario.get('codigo_equipo') or inventario.get('id')}), "
            f"servicio {meta['name_servicio']}, año {validacion['anio']} mes {validacion['mes']:02d}."
        )
        meta_json = json.dumps(
            {
                "servicio_id": meta["id"] if "id" in meta.keys() else inventario.get("servicio_id"),
                "anio": validacion.get("anio"),
                "mes": validacion.get("mes"),
                "pm_inventario_id": inventario.get("id"),
                "equipo": inventario.get("equipo"),
                "codigo_equipo": inventario.get("codigo_equipo"),
            },
            ensure_ascii=False,
        )

        cur = sol_conn.execute(
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
                ?, ?, ?, 'PENDIENTE',
                ?, ?, ?, datetime('now')
            )
            """,
            (
                solicitante["id_usuario"],
                solicitante["usuario_login"],
                f"{solicitante['NAME_USER']} {solicitante['LAST_NAME_USER']}".strip(),
                solicitante["ROLL"],
                solicitante["JOB"],
                dest["id_usuario"],
                dest["usuario_login"],
                f"{dest['NAME_USER']} {dest['LAST_NAME_USER']}".strip(),
                "asistencial",
                meta["sede_id"],
                meta["empresa_id"],
                meta["id"] if "id" in meta.keys() else None,
                meta["ID_sede"],
                meta["name_sede"],
                "validar_pm_cronograma",
                mensaje,
                "MODERADA",
                "pm_validacion",
                int(validacion["id"]),
                meta_json,
            ),
        )
        sol_conn.commit()
        return int(cur.lastrowid)


def _pm_defaults_from_inv(inv) -> dict:
    """Deriva intervalo fabricante, función OMS y último PM desde el inventario."""
    def get(name, default=None):
        if hasattr(inv, "keys"):
            return inv[name] if name in inv.keys() else default
        return inv.get(name, default)

    aplica_mp = get("aplica_mp")
    freq_mp = _as_float(get("freq_mp"))
    meses = freq_anual_to_meses(freq_mp) if aplica_mp in (1, True, "1") else None
    servicio = get("name_servicio") or get("ubicacion")
    fecha_baja = get("fecha_baja")
    estado = _map_estado_inventario(get("estado"))
    if fecha_baja:
        estado = "Retirado"
    return {
        "pm_fabricante_meses": meses,
        "funcion": map_funcion_oms(get("clasificacion_biomedica")),
        "aplicacion": map_aplicacion_oms(servicio),
        "requisito_mantto": map_requisito_oms(get("clasificacion_riesgo")),
        "antecedentes_fallas": map_fallas_oms(get("novedad_desc")),
        "fecha_ultimo_pm": _fecha_iso(get("fecha_ultimo_pm")),
        "estado": estado,
    }


def _sync_from_inventario(conn, servicio_id: int, anio: int) -> dict:
    """Upsert de identidad desde inventario_equipos hacia pm_inventario y rebuild."""
    inv_rows = conn.execute(
        """
        SELECT ie.*, srv.name_servicio
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        WHERE ie.servicio_id = ?
        ORDER BY ie.equipo COLLATE NOCASE, ie.id
        """,
        (servicio_id,),
    ).fetchall()

    created = 0
    updated = 0
    for inv in inv_rows:
        existing = conn.execute(
            """
            SELECT * FROM pm_inventario
            WHERE servicio_id = ? AND inventario_equipo_id = ?
            """,
            (servicio_id, inv["id"]),
        ).fetchone()
        if not existing and inv["num_biomedica"]:
            existing = conn.execute(
                """
                SELECT * FROM pm_inventario
                WHERE servicio_id = ? AND codigo_equipo = ? AND inventario_equipo_id IS NULL
                """,
                (servicio_id, inv["num_biomedica"]),
            ).fetchone()

        defaults = _pm_defaults_from_inv(inv)
        codigo = sanitize_string(inv["num_biomedica"]) or f"EQ-{inv['id']}"
        equipo = sanitize_string(inv["equipo"]) or f"Equipo {inv['id']}"

        if existing:
            conn.execute(
                """
                UPDATE pm_inventario SET
                    inventario_equipo_id = ?,
                    codigo_equipo = COALESCE(?, codigo_equipo),
                    equipo = ?,
                    marca = ?,
                    modelo = ?,
                    serie = ?,
                    estado = COALESCE(?, estado),
                    pm_fabricante_meses = COALESCE(pm_fabricante_meses, ?),
                    funcion = COALESCE(funcion, ?),
                    aplicacion = COALESCE(aplicacion, ?),
                    requisito_mantto = COALESCE(requisito_mantto, ?),
                    antecedentes_fallas = COALESCE(antecedentes_fallas, ?),
                    fecha_ultimo_pm = COALESCE(fecha_ultimo_pm, ?),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    inv["id"],
                    codigo,
                    equipo,
                    sanitize_string(inv["marca"]),
                    sanitize_string(inv["modelo"]),
                    sanitize_string(inv["serie"]),
                    defaults["estado"],
                    defaults["pm_fabricante_meses"],
                    defaults["funcion"],
                    defaults["aplicacion"],
                    defaults["requisito_mantto"],
                    defaults["antecedentes_fallas"],
                    defaults["fecha_ultimo_pm"],
                    existing["id"],
                ),
            )
            updated += 1
            pm_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO pm_inventario (
                    servicio_id, inventario_equipo_id, codigo_equipo, equipo,
                    marca, modelo, serie, estado, pm_fabricante_meses,
                    funcion, aplicacion, requisito_mantto, antecedentes_fallas,
                    fecha_ultimo_pm, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    servicio_id,
                    inv["id"],
                    codigo,
                    equipo,
                    sanitize_string(inv["marca"]),
                    sanitize_string(inv["modelo"]),
                    sanitize_string(inv["serie"]),
                    defaults["estado"],
                    defaults["pm_fabricante_meses"],
                    defaults["funcion"],
                    defaults["aplicacion"],
                    defaults["requisito_mantto"],
                    defaults["antecedentes_fallas"],
                    defaults["fecha_ultimo_pm"],
                ),
            )
            created += 1
            pm_id = cur.lastrowid

        pm_row = conn.execute("SELECT * FROM pm_inventario WHERE id = ?", (pm_id,)).fetchone()
        _rebuild_equipo(conn, dict(pm_row), anio)

    return {"created": created, "updated": updated, "source_rows": len(inv_rows)}


def _apply_upsert_body(existing: dict | None, body: dict, caps: dict) -> dict:
    """Fusiona body con fila existente respetando caps de puntajes vs operativos."""
    base = dict(existing or {})
    merged = {
        "inventario_equipo_id": body.get("inventario_equipo_id", base.get("inventario_equipo_id")),
        "codigo_equipo": sanitize_string(body.get("codigo_equipo", base.get("codigo_equipo"))),
        "equipo": sanitize_string(body.get("equipo", base.get("equipo"))),
        "marca": sanitize_string(body.get("marca", base.get("marca"))),
        "modelo": sanitize_string(body.get("modelo", base.get("modelo"))),
        "serie": sanitize_string(body.get("serie", base.get("serie"))),
        "estado": sanitize_string(body.get("estado", base.get("estado"))) or "Operativo",
        "pm_fabricante_meses": (
            _as_float(body["pm_fabricante_meses"])
            if "pm_fabricante_meses" in body
            else base.get("pm_fabricante_meses")
        ),
        "fecha_ultimo_pm": (
            _fecha_iso(body.get("fecha_ultimo_pm"))
            if "fecha_ultimo_pm" in body
            else _fecha_iso(base.get("fecha_ultimo_pm"))
        ),
        "funcion": base.get("funcion"),
        "aplicacion": base.get("aplicacion"),
        "requisito_mantto": base.get("requisito_mantto"),
        "antecedentes_fallas": base.get("antecedentes_fallas"),
    }

    if not merged["equipo"]:
        raise ValueError("equipo es obligatorio.")

    score_incoming = {f: sanitize_string(body.get(f)) for f in _SCORE_FIELDS if f in body}
    if existing and score_incoming and not caps["can_edit_scores"]:
        # OPERATIVO no puede alterar función/aplicación/requisito/fallas de un registro existente.
        blocked = [
            f
            for f, val in score_incoming.items()
            if (val or None) != (sanitize_string(existing.get(f)) or None)
        ]
        if blocked:
            raise PermissionError(
                "El rol operativo no puede modificar función, aplicación, "
                "requisito de mantenimiento ni antecedentes de fallas de un equipo existente."
            )

    if caps["can_edit_scores"] or not existing:
        for f in _SCORE_FIELDS:
            if f in body:
                merged[f] = sanitize_string(body.get(f)) or None
            elif f not in merged or merged.get(f) is None:
                merged[f] = sanitize_string(base.get(f)) or None
    else:
        for f in _SCORE_FIELDS:
            merged[f] = sanitize_string(base.get(f)) or None

    if not caps["can_edit_operational"] and not caps["can_edit_scores"]:
        raise PermissionError("No tienes permisos para editar el inventario PM.")

    if existing and not caps["can_edit_operational"]:
        # Solo ADMIN con can_edit_scores (sin operativo) aún puede tocar puntajes.
        for key in (
            "codigo_equipo",
            "equipo",
            "marca",
            "modelo",
            "serie",
            "estado",
            "pm_fabricante_meses",
            "fecha_ultimo_pm",
            "inventario_equipo_id",
        ):
            merged[key] = base.get(key) if key != "fecha_ultimo_pm" else _fecha_iso(base.get(key))
        for f in _SCORE_FIELDS:
            if f in body:
                merged[f] = sanitize_string(body.get(f)) or None

    if merged.get("estado") and merged["estado"] not in ESTADOS_EQUIPO:
        mapped = _map_estado_inventario(merged["estado"])
        merged["estado"] = mapped

    return enrich_row(merged)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@pm_bp.get("/meta")
@login_required
@permission_required("view_frecuencia_pm")
def pm_meta():
    user = current_user()
    caps = _role_caps(user)
    catalogs = catalogs_payload()
    return jsonify(
        {
            "ok": True,
            "modulo": "frecuencia_pm",
            "titulo": "Frecuencia de mantenimiento preventivo (GE + fabricante)",
            "catalogos": catalogs,
            "estados": catalogs.get("estados") or ESTADOS_EQUIPO,
            "tooltips": catalogs.get("tooltips") or {},
            "guia_uso": catalogs.get("guia_uso") or [],
            "guia_nota": catalogs.get("guia_nota"),
            "caps": caps,
            "permisos_hint": {
                "admin": "Edita catálogos/puntajes, opera el cronograma y valida excepcionalmente.",
                "operativo": "Sincroniza inventario, edita datos operativos, ejecuta PM y solicita validación.",
                "asistencial": "Consulta cronograma; Coordinador/Director/Líder aprueba o rechaza cumplimientos.",
            },
            "anio_default": datetime.now().year,
            "formula": formula_meta("ge"),
        }
    )


@pm_bp.get("/servicios/<int:servicio_id>/contexto")
@login_required
@permission_required("view_frecuencia_pm")
def pm_contexto(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_view_cronograma"] and not caps["can_view_full"]:
        return jsonify({"ok": False, "error": "No autorizado para consultar este módulo."}), 403

    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        # Si no hay cronograma del año, lo materializa al vuelo para equipos existentes.
        missing = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM pm_inventario pi
            LEFT JOIN pm_cronograma pc
              ON pc.pm_inventario_id = pi.id AND pc.anio = ?
            WHERE pi.servicio_id = ? AND pc.id IS NULL
            """,
            (anio, servicio_id),
        ).fetchone()
        if missing and int(missing["n"] or 0) > 0:
            _rebuild_servicio(conn, servicio_id, anio)
            conn.commit()
        ctx = _load_contexto(conn, servicio_id, anio, meta)
        conn.commit()

    if not caps["can_view_full"]:
        # ASISTENCIAL: cronograma + validaciones, sin detalle fino de puntajes si se desea ocultar.
        for eq in ctx["equipos"]:
            for key in (
                "puntaje_funcion",
                "puntaje_aplicacion",
                "puntaje_requisito",
                "puntaje_fallas",
            ):
                eq.pop(key, None)

    return jsonify(
        {
            "ok": True,
            **ctx,
            "caps": caps,
            "catalogos": catalogs_payload() if caps["can_view_full"] or caps["can_edit_scores"] else None,
            "formula": formula_meta("ge"),
        }
    )


@pm_bp.post("/servicios/<int:servicio_id>/sync-inventario")
@login_required
@permission_required("view_frecuencia_pm")
def pm_sync_inventario(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_edit_operational"]:
        return jsonify({"ok": False, "error": "Solo ADMIN u OPERATIVO pueden sincronizar inventario."}), 403

    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        summary = _sync_from_inventario(conn, servicio_id, anio)
        ctx = _load_contexto(conn, servicio_id, anio, meta)
        conn.commit()

    return jsonify(
        {
            "ok": True,
            "message": (
                f"Inventario sincronizado ({summary['created']} nuevos, "
                f"{summary['updated']} actualizados)."
            ),
            "sync": summary,
            **ctx,
            "caps": caps,
        }
    )


@pm_bp.post("/servicios/<int:servicio_id>/equipos")
@login_required
@permission_required("view_frecuencia_pm")
def pm_upsert_equipo(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not (caps["can_edit_operational"] or caps["can_edit_scores"]):
        return jsonify({"ok": False, "error": "No autorizado para editar equipos PM."}), 403

    body = request.get_json(silent=True) or {}
    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err

        existing = None
        pm_id = body.get("id") or body.get("pm_inventario_id")
        if pm_id:
            existing = conn.execute(
                "SELECT * FROM pm_inventario WHERE id = ? AND servicio_id = ?",
                (pm_id, servicio_id),
            ).fetchone()
            if not existing:
                return jsonify({"ok": False, "error": "Equipo PM no encontrado."}), 404
        elif body.get("inventario_equipo_id"):
            existing = conn.execute(
                """
                SELECT * FROM pm_inventario
                WHERE servicio_id = ? AND inventario_equipo_id = ?
                """,
                (servicio_id, body.get("inventario_equipo_id")),
            ).fetchone()
        elif body.get("codigo_equipo"):
            existing = conn.execute(
                """
                SELECT * FROM pm_inventario
                WHERE servicio_id = ? AND codigo_equipo = ?
                """,
                (servicio_id, sanitize_string(body.get("codigo_equipo"))),
            ).fetchone()

        try:
            enriched = _apply_upsert_body(_row_dict(existing) if existing else None, body, caps)
        except PermissionError as err:
            return jsonify({"ok": False, "error": str(err)}), 403
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400

        values = (
            servicio_id,
            enriched.get("inventario_equipo_id"),
            enriched.get("codigo_equipo"),
            enriched.get("equipo"),
            enriched.get("marca"),
            enriched.get("modelo"),
            enriched.get("serie"),
            enriched.get("estado"),
            enriched.get("pm_fabricante_meses"),
            enriched.get("funcion"),
            enriched.get("puntaje_funcion"),
            enriched.get("aplicacion"),
            enriched.get("puntaje_aplicacion"),
            enriched.get("requisito_mantto"),
            enriched.get("puntaje_requisito"),
            enriched.get("antecedentes_fallas"),
            enriched.get("puntaje_fallas"),
            enriched.get("ge_total"),
            enriched.get("frecuencia_oms"),
            enriched.get("frecuencia_definitiva"),
            enriched.get("accion_sugerida"),
            enriched.get("fecha_ultimo_pm"),
        )

        if existing:
            conn.execute(
                """
                UPDATE pm_inventario SET
                    inventario_equipo_id = ?, codigo_equipo = ?, equipo = ?,
                    marca = ?, modelo = ?, serie = ?, estado = ?,
                    pm_fabricante_meses = ?,
                    funcion = ?, puntaje_funcion = ?,
                    aplicacion = ?, puntaje_aplicacion = ?,
                    requisito_mantto = ?, puntaje_requisito = ?,
                    antecedentes_fallas = ?, puntaje_fallas = ?,
                    ge_total = ?, frecuencia_oms = ?, frecuencia_definitiva = ?,
                    accion_sugerida = ?, fecha_ultimo_pm = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (*values[1:], existing["id"]),
            )
            pm_inventario_id = existing["id"]
            message = "Equipo PM actualizado."
        else:
            cur = conn.execute(
                """
                INSERT INTO pm_inventario (
                    servicio_id, inventario_equipo_id, codigo_equipo, equipo,
                    marca, modelo, serie, estado, pm_fabricante_meses,
                    funcion, puntaje_funcion, aplicacion, puntaje_aplicacion,
                    requisito_mantto, puntaje_requisito, antecedentes_fallas, puntaje_fallas,
                    ge_total, frecuencia_oms, frecuencia_definitiva, accion_sugerida,
                    fecha_ultimo_pm, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, datetime('now')
                )
                """,
                values,
            )
            pm_inventario_id = cur.lastrowid
            message = "Equipo PM creado."

        pm_row = conn.execute(
            "SELECT * FROM pm_inventario WHERE id = ?", (pm_inventario_id,)
        ).fetchone()
        crono = _upsert_cronograma(conn, pm_inventario_id, anio, dict(pm_row))
        vals = _load_validaciones(conn, pm_inventario_id, anio)
        conn.commit()

    payload = _inventario_payload(dict(pm_row), crono, vals)
    payload["servicio_nombre"] = meta["name_servicio"]
    return jsonify({"ok": True, "message": message, "equipo": payload, "caps": caps})


@pm_bp.post("/servicios/<int:servicio_id>/recalcular")
@login_required
@permission_required("view_frecuencia_pm")
def pm_recalcular(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_edit_operational"]:
        return jsonify({"ok": False, "error": "Solo ADMIN u OPERATIVO pueden recalcular."}), 403

    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        n = _rebuild_servicio(conn, servicio_id, anio)
        ctx = _load_contexto(conn, servicio_id, anio, meta)
        conn.commit()

    registrar_calculo(
        modulo="ge",
        empresa_id=meta["empresa_id"] if meta else None,
        sede_id=meta["sede_id"] if meta else None,
        servicio_id=servicio_id,
        usuario_id=user.get("id_usuario"),
        parametros={"accion": "recalcular", "anio": anio, "n": n},
        resultado={"equipos": n},
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": f"Recalculados {n} equipos y cronograma {anio}.",
            **ctx,
            "caps": caps,
            "formula": formula_meta("ge"),
        }
    )


@pm_bp.post("/validaciones/<int:validacion_id>/cumplir")
@login_required
@permission_required("view_frecuencia_pm")
def pm_cumplir(validacion_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_execute"]:
        return jsonify({"ok": False, "error": "Solo ADMIN u OPERATIVO pueden marcar cumplimiento."}), 403

    body = request.get_json(silent=True) or {}
    evidencia = sanitize_string(body.get("evidencia"), LONG_TEXT)
    fecha_ejecucion = _fecha_iso(body.get("fecha_ejecucion")) or date.today().isoformat()

    with get_empresas_connection() as conn:
        val = conn.execute(
            "SELECT * FROM pm_validacion WHERE id = ?", (validacion_id,)
        ).fetchone()
        if not val:
            return jsonify({"ok": False, "error": "Validación no encontrada."}), 404

        inv = conn.execute(
            "SELECT * FROM pm_inventario WHERE id = ?", (val["pm_inventario_id"],)
        ).fetchone()
        if not inv:
            return jsonify({"ok": False, "error": "Equipo PM no encontrado."}), 404

        meta, err = _require_servicio(conn, user, inv["servicio_id"])
        if err:
            return err

        if val["estado"] in ("APROBADO",):
            return jsonify({"ok": False, "error": "La validación ya fue aprobada."}), 400
        if val["estado"] == "CUMPLIDO" and val["solicitud_id"]:
            return jsonify(
                {
                    "ok": True,
                    "message": "El cumplimiento ya estaba registrado.",
                    "validacion": _load_validaciones(conn, inv["id"], val["anio"]),
                    "solicitud_id": val["solicitud_id"],
                }
            )

        solicitud_id = None
        try:
            solicitud_id = _create_solicitud_validacion(
                user=user,
                meta=meta,
                validacion=dict(val),
                inventario=dict(inv),
            )
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400

        try:
            conn.execute(
                """
                UPDATE pm_validacion SET
                    estado = 'CUMPLIDO',
                    fecha_ejecucion = ?,
                    ejecutado_por = ?,
                    ejecutado_por_login = ?,
                    evidencia = COALESCE(?, evidencia),
                    solicitud_id = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    fecha_ejecucion,
                    user["id_usuario"],
                    user.get("usuario_login"),
                    evidencia,
                    solicitud_id,
                    validacion_id,
                ),
            )
            # Actualiza fecha_ultimo_pm del equipo con la ejecución más reciente.
            conn.execute(
                """
                UPDATE pm_inventario SET
                    fecha_ultimo_pm = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (fecha_ejecucion, inv["id"]),
            )
            refreshed = conn.execute(
                "SELECT * FROM pm_inventario WHERE id = ?", (inv["id"],)
            ).fetchone()
            _upsert_cronograma(conn, inv["id"], int(val["anio"]), dict(refreshed))
            updated = conn.execute(
                "SELECT * FROM pm_validacion WHERE id = ?", (validacion_id,)
            ).fetchone()
            vals = _load_validaciones(conn, inv["id"], val["anio"])
            conn.commit()
        except Exception:
            discard_pending_solicitud(solicitud_id)
            raise

    item = dict(updated)
    for key in ("fecha_programada", "fecha_ejecucion", "updated_at"):
        if item.get(key) is not None:
            item[key] = str(item[key])[:19] if key == "updated_at" else str(item[key])[:10]

    return jsonify(
        {
            "ok": True,
            "message": "Cumplimiento registrado y solicitud de validación creada.",
            "validacion": item,
            "validaciones": vals,
            "solicitud_id": solicitud_id,
        }
    )


@pm_bp.post("/validaciones/<int:validacion_id>/validar")
@login_required
@permission_required("view_frecuencia_pm")
def pm_validar(validacion_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_validate"]:
        return jsonify(
            {
                "ok": False,
                "error": (
                    "Solo ADMIN o ASISTENCIAL (Coordinador/Director/Dirección/Líder) "
                    "pueden validar."
                ),
            }
        ), 403

    body = request.get_json(silent=True) or {}
    decision = sanitize_string(body.get("estado") or body.get("decision") or "").upper()
    if decision not in ("APROBADO", "RECHAZADO"):
        return jsonify(
            {"ok": False, "error": "estado debe ser APROBADO o RECHAZADO."}
        ), 400

    calificacion = _as_float(body.get("calificacion"))
    if calificacion is not None and (calificacion < 0 or calificacion > 5):
        return jsonify({"ok": False, "error": "calificacion debe estar entre 0 y 5."}), 400
    comentario = sanitize_string(body.get("comentario"), COMMENT)

    with get_empresas_connection() as conn:
        val = conn.execute(
            "SELECT * FROM pm_validacion WHERE id = ?", (validacion_id,)
        ).fetchone()
        if not val:
            return jsonify({"ok": False, "error": "Validación no encontrada."}), 404

        inv = conn.execute(
            "SELECT * FROM pm_inventario WHERE id = ?", (val["pm_inventario_id"],)
        ).fetchone()
        if not inv:
            return jsonify({"ok": False, "error": "Equipo PM no encontrado."}), 404

        meta, err = _require_servicio(conn, user, inv["servicio_id"])
        if err:
            return err

        if val["estado"] not in ("CUMPLIDO", "RECHAZADO", "APROBADO"):
            return jsonify(
                {
                    "ok": False,
                    "error": "Solo se puede validar un PM marcado como CUMPLIDO.",
                }
            ), 400

        conn.execute(
            """
            UPDATE pm_validacion SET
                estado = ?,
                validado_por = ?,
                validado_por_login = ?,
                calificacion = ?,
                comentario = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                decision,
                user["id_usuario"],
                user.get("usuario_login"),
                calificacion,
                comentario,
                validacion_id,
            ),
        )

        prev_sol_estado = None
        if val["solicitud_id"]:
            with get_solicitudes_connection() as sol_conn:
                prev = sol_conn.execute(
                    "SELECT estado FROM solicitudes WHERE id = ?",
                    (val["solicitud_id"],),
                ).fetchone()
                prev_sol_estado = (prev["estado"] if prev else "PENDIENTE") or "PENDIENTE"
                sol_estado = "APROBADA" if decision == "APROBADO" else "RECHAZADA"
                sol_conn.execute(
                    """
                    UPDATE solicitudes SET
                        estado = ?,
                        resolved_at = datetime('now'),
                        ref_tipo = COALESCE(ref_tipo, 'pm_validacion'),
                        ref_id = COALESCE(ref_id, ?)
                    WHERE id = ?
                    """,
                    (sol_estado, validacion_id, val["solicitud_id"]),
                )
                sol_conn.commit()

        try:
            updated = conn.execute(
                "SELECT * FROM pm_validacion WHERE id = ?", (validacion_id,)
            ).fetchone()
            vals = _load_validaciones(conn, inv["id"], val["anio"])
            conn.commit()
        except Exception:
            if val["solicitud_id"] and prev_sol_estado:
                revert_solicitud_estado(val["solicitud_id"], prev_sol_estado)
            raise

    item = dict(updated)
    for key in ("fecha_programada", "fecha_ejecucion", "updated_at"):
        if item.get(key) is not None:
            item[key] = str(item[key])[:19] if key == "updated_at" else str(item[key])[:10]

    return jsonify(
        {
            "ok": True,
            "message": f"Validación {decision.lower()}.",
            "validacion": item,
            "validaciones": vals,
            "servicio": dict(meta),
            "caps": caps,
        }
    )


@pm_bp.get("/servicios/<int:servicio_id>/informe.pdf")
@login_required
@permission_required("view_frecuencia_pm")
def pm_informe_pdf(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_view_full"] and not caps["can_view_cronograma"]:
        return jsonify({"ok": False, "error": "No autorizado."}), 403

    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        ctx = _load_contexto(conn, servicio_id, anio, meta)
        conn.commit()

    institucion = f"{meta['ID_Empresa']} · {meta['name_sede']}"
    responsable = user.get("NAME_USER") or user.get("usuario_login") or "Ingeniería clínica"
    staff = collect_org_staff(empresa_id=meta["empresa_id"], sede_id=meta["sede_id"])
    pdf_bytes = build_informe_resumen_pdf(
        institucion=institucion,
        responsable=responsable,
        stats=ctx["dashboard"],
        conclusion=(
            f"Servicio {meta['name_servicio']} ({meta['ID_servicio']}). "
            f"Año de referencia del cronograma: {anio}. "
            "La frecuencia definitiva aplica el criterio más conservador entre fabricante y OMS."
        ),
        staff=staff,
    )
    data = io.BytesIO(pdf_bytes)
    data.seek(0)
    fname = f"informe_pm_{meta['ID_servicio']}_{anio}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    return send_file(data, mimetype="application/pdf", as_attachment=True, download_name=fname)


@pm_bp.get("/servicios/<int:servicio_id>/cronograma.pdf")
@login_required
@permission_required("view_frecuencia_pm")
def pm_cronograma_pdf(servicio_id: int):
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_view_cronograma"]:
        return jsonify({"ok": False, "error": "No autorizado para ver el cronograma."}), 403

    try:
        anio = _anio_from_request()
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        ctx = _load_contexto(conn, servicio_id, anio, meta)
        conn.commit()

    rows = []
    for eq in ctx["equipos"]:
        crono = eq.get("cronograma") or {}
        rows.append(
            {
                "equipo": eq.get("equipo"),
                "servicio_nombre": meta["name_servicio"],
                "fecha_ultimo_pm": eq.get("fecha_ultimo_pm"),
                "frecuencia_definitiva": eq.get("frecuencia_definitiva"),
                "observacion": crono.get("observacion"),
                **{f"mes_{i:02d}": crono.get(f"mes_{i:02d}", eq.get("meses", {}).get(i, 0)) for i in range(1, 13)},
            }
        )

    institucion = f"{meta['ID_Empresa']} · {meta['name_sede']}"
    staff = collect_org_staff(empresa_id=meta["empresa_id"], sede_id=meta["sede_id"])
    pdf_bytes = build_cronograma_pdf(
        institucion=institucion,
        servicio=meta["name_servicio"],
        anio=anio,
        rows=rows,
        empresa=meta["ID_Empresa"],
        sede=f"{meta['ID_sede']} · {meta['name_sede']}",
        staff=staff,
    )
    data = io.BytesIO(pdf_bytes)
    data.seek(0)
    fname = f"cronograma_pm_{meta['ID_servicio']}_{anio}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    return send_file(data, mimetype="application/pdf", as_attachment=True, download_name=fname)


# ---------------------------------------------------------------------------
# Ejecución de mantenimientos (llave Código Biomédica + Código de Activo)
# ---------------------------------------------------------------------------


def _scope_sede_ids(user):
    if is_global_scope(user):
        return None
    with get_users_connection() as conn:
        assigned = assigned_sede_ids(conn, user["id_usuario"])
    return assigned or None


def _require_empresa_id(user, raw):
    try:
        empresa_id = int(raw) if raw not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None, (jsonify({"ok": False, "error": "empresa_id inválido."}), 400)
    if is_global_scope(user):
        if not empresa_id:
            return None, (jsonify({"ok": False, "error": "Selecciona una empresa."}), 400)
        return empresa_id, None
    assigned = assigned_empresa_id(user)
    if not assigned:
        return None, (jsonify({"ok": False, "error": "Sin empresa asignada."}), 403)
    if empresa_id and int(empresa_id) != int(assigned):
        return None, (jsonify({"ok": False, "error": "Fuera del alcance de su empresa."}), 403)
    return int(assigned), None


def _empresa_desde_filtro(user, conn, args: dict):
    servicio_raw = args.get("servicio_id")
    if servicio_raw not in (None, ""):
        try:
            servicio_id = int(servicio_raw)
        except (TypeError, ValueError):
            return None, None, (jsonify({"ok": False, "error": "servicio_id inválido."}), 400)
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return None, None, err
        return int(meta["empresa_id"]), meta, None
    sede_raw = args.get("sede_id")
    if sede_raw not in (None, ""):
        try:
            sede_id = int(sede_raw)
        except (TypeError, ValueError):
            return None, None, (jsonify({"ok": False, "error": "sede_id inválido."}), 400)
        if not can_access_sede(user, sede_id):
            return None, None, (jsonify({"ok": False, "error": "No autorizado."}), 403)
        sede = conn.execute(
            "SELECT id, empresa_id FROM sedes WHERE id = ?",
            (sede_id,),
        ).fetchone()
        if not sede:
            return None, None, (jsonify({"ok": False, "error": "Sede no encontrada."}), 404)
        return int(sede["empresa_id"]), None, None
    empresa_id, err = _require_empresa_id(user, args.get("empresa_id"))
    if err:
        return None, None, err
    if not can_access_empresa(conn, user, empresa_id):
        return None, None, (jsonify({"ok": False, "error": "No autorizado."}), 403)
    return empresa_id, None, None


@pm_bp.get("/ejecucion")
@login_required
@permission_required("view_frecuencia_pm")
def pm_ejecucion_list():
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_view_cronograma"] and not caps["can_view_full"]:
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    args = request.args
    with get_empresas_connection() as conn:
        empresa_id, meta, err = _empresa_desde_filtro(user, conn, args)
        if err:
            return err
        sede_ids = _scope_sede_ids(user)
        payload = list_ejecucion(
            conn,
            empresa_id,
            sede_id=args.get("sede_id") or (meta["sede_id"] if meta else None),
            servicio_id=args.get("servicio_id"),
            tipo=args.get("tipo"),
            q=args.get("q"),
            sede_ids=sede_ids,
            page=args.get("page") or 1,
            page_size=args.get("page_size") or 25,
        )
    payload["caps"] = {
        "can_create": bool(caps["can_execute"] or caps["can_edit_operational"]),
        "can_view_full": bool(caps["can_view_full"]),
    }
    return jsonify(payload)


@pm_bp.post("/ejecucion")
@login_required
@permission_required("view_frecuencia_pm")
def pm_ejecucion_create():
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_execute"] and not caps["can_edit_operational"]:
        return jsonify({"ok": False, "error": "Solo ADMIN u OPERATIVO pueden registrar ejecución."}), 403
    body = request.get_json(silent=True) or {}
    with get_empresas_connection() as conn:
        empresa_id, meta, err = _empresa_desde_filtro(user, conn, body)
        if err:
            return err
        if meta:
            body.setdefault("empresa_id", meta["empresa_id"])
            body.setdefault("sede_id", meta["sede_id"])
            body.setdefault("servicio_id", meta["id"] if "id" in meta.keys() else body.get("servicio_id"))
        else:
            body["empresa_id"] = empresa_id
        body["fuente"] = "manual"
        payload, error = validate_manual_payload(body)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        if payload.get("sede_id") and not can_access_sede(user, payload["sede_id"]):
            return jsonify({"ok": False, "error": "No autorizado para esta sede."}), 403
        if payload.get("servicio_id"):
            _meta, srv_err = _require_servicio(conn, user, payload["servicio_id"])
            if srv_err:
                return srv_err
        row = insert_ejecucion(conn, payload)
        conn.commit()
    log_evento(
        empresa_id=payload["empresa_id"],
        accion="Registró ejecución de mantenimiento (manual).",
        user=user,
        modulo="frecuencia_pm",
        sede_id=payload.get("sede_id"),
        servicio_id=payload.get("servicio_id"),
        parametros={
            "tipo": payload["tipo_mantenimiento"],
            "codigo_biomedica": payload["codigo_biomedica_norm"],
            "codigo_activo": payload["codigo_activo_norm"],
        },
        resultado={"id": row.get("id")},
    )
    return jsonify({"ok": True, "message": "Ejecución registrada.", "item": row}), 201


@pm_bp.get("/ejecucion/coincidencias")
@login_required
@permission_required("view_frecuencia_pm")
def pm_ejecucion_coincidencias():
    user = current_user()
    args = request.args
    with get_empresas_connection() as conn:
        empresa_id, _meta, err = _empresa_desde_filtro(user, conn, args)
        if err:
            return err
        payload = buscar_semejanzas(
            conn,
            empresa_id,
            codigo_biomedica=args.get("codigo_biomedica"),
            codigo_activo=args.get("codigo_activo"),
            q=args.get("q"),
            sede_ids=_scope_sede_ids(user),
            limit=args.get("limit") or 50,
            offset=args.get("offset") or 0,
        )
    return jsonify(payload)


@pm_bp.get("/ejecucion/duplicados")
@login_required
@permission_required("view_frecuencia_pm")
def pm_ejecucion_duplicados():
    user = current_user()
    args = request.args
    with get_empresas_connection() as conn:
        empresa_id, _meta, err = _empresa_desde_filtro(user, conn, args)
        if err:
            return err
        payload = equipos_duplicados(
            conn,
            empresa_id,
            sede_ids=_scope_sede_ids(user),
            limit=args.get("limit") or 50,
            offset=args.get("offset") or 0,
        )
    return jsonify(payload)


@pm_bp.get("/ejecucion/auditoria")
@login_required
@permission_required("view_frecuencia_pm")
def pm_ejecucion_auditoria():
    """Reporte interno de cobertura por sede. No se muestra en la UI."""
    user = current_user()
    if not is_global_scope(user) and (user.get("ROLL") or "").upper() != "ADMIN":
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    args = request.args
    with get_empresas_connection() as conn:
        empresa_id, _meta, err = _empresa_desde_filtro(user, conn, args)
        if err:
            return err
        payload = reporte_cobertura_sedes(conn, empresa_id, sede_ids=_scope_sede_ids(user))
    return jsonify({"ok": True, **payload})
