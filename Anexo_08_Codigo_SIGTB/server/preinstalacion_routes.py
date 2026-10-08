"""API HTTP de preinstalación de tecnología biomédica (SITIO)."""

from __future__ import annotations

import json
from datetime import date, datetime

from flask import Blueprint, jsonify, request, send_file, session

from server.authz import (
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
from server.preinstalacion import (
    ALCANCE,
    CRITICIDADES,
    ESTADOS,
    FUENTE_DEFAULT,
    OBJETIVO_DEFAULT,
    calc_resultado,
    catalogs_payload,
    default_items_payload,
)
from server.preinstalacion_pdf import build_informe_pdf
from server.pdf_staff import collect_org_staff
from server.preinstalacion_presets import PRESETS, match_preset_codigo
from server.formula_versions import formula_meta, registrar_calculo
from server.limits import COMMENT, LABEL, LONG_TEXT
from server.validators import sanitize_string

pre_bp = Blueprint("preinstalacion", __name__, url_prefix="/api/preinstalacion")

_VALIDATE_JOBS = ("Coordinador", "Director", "Dirección", "Líder")


def _role_caps(user) -> dict:
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
        "can_view": bool(is_admin or is_operativo or is_asistencial),
        "can_edit": bool(is_admin or is_operativo),
        "can_presets": bool(is_admin or is_operativo),
        "can_pdf": bool(is_admin or is_operativo or is_asistencial),
        "can_validate": bool(is_admin or (is_asistencial and can_validate_job)),
        "can_edit_catalogs": bool(is_admin),
    }


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


def _row_dict(row) -> dict:
    if row is None:
        return {}
    item = dict(row)
    for key, val in list(item.items()):
        if hasattr(val, "isoformat"):
            item[key] = val.isoformat()[:19] if "T" in str(val) or " " in str(val) else str(val)[:10]
    return item


def _items_of(conn, evaluacion_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM pre_items
        WHERE evaluacion_id = ?
        ORDER BY seccion, orden, item_id
        """,
        (evaluacion_id,),
    ).fetchall()
    return [_row_dict(r) for r in rows]


def _persist_resultado(conn, evaluacion_id: int, stats: dict):
    conn.execute(
        """
        UPDATE pre_evaluaciones SET
            evaluables_fab = ?, evaluables_doc = ?, total_evaluables = ?,
            cumplidos = ?, no_cumplidos = ?, pendientes = ?, no_aplica = ?,
            criticos_abiertos = ?, pct_cumplimiento = ?, decision = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            stats["evaluables_fab"],
            stats["evaluables_doc"],
            stats["total_evaluables"],
            stats["cumplidos"],
            stats["no_cumplidos"],
            stats["pendientes"],
            stats["no_aplica"],
            stats["criticos_abiertos"],
            stats["pct_cumplimiento"],
            stats["decision"],
            evaluacion_id,
        ),
    )


def _eval_payload(conn, row) -> dict:
    items = _items_of(conn, row["id"])
    stats = calc_resultado(items)
    payload = _row_dict(row)
    payload.update(stats)
    payload["items"] = items
    payload["items_fabricante"] = [i for i in items if i.get("seccion") == "fabricante"]
    payload["items_documentacion"] = [i for i in items if i.get("seccion") == "documentacion"]
    fmeta = formula_meta("preinstalacion")
    payload.update(fmeta)
    payload["formula"] = fmeta
    return payload


def _seed_presets(conn):
    for preset in PRESETS:
        exists = conn.execute(
            "SELECT id FROM pre_presets WHERE codigo = ?", (preset["codigo"],)
        ).fetchone()
        if exists:
            continue
        cur = conn.execute(
            """
            INSERT INTO pre_presets (
                codigo, nombre, tipo_equipo, marca, modelo, fabricante,
                fuente, notas, es_global, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
            """,
            (
                preset["codigo"],
                preset["nombre"],
                preset.get("tipo_equipo"),
                preset.get("marca"),
                preset.get("modelo"),
                preset.get("fabricante"),
                preset.get("fuente"),
                preset.get("notas"),
            ),
        )
        pid = cur.lastrowid
        base = default_items_payload()
        overlays = preset.get("overlays") or {}
        na_items = set(preset.get("na_items") or [])
        crit_boost = preset.get("crit_boost") or {}
        for it in base:
            if it["seccion"] != "fabricante":
                exig = it["exigencia"]
                estado = it["estado"]
                crit = it["criticidad"]
            else:
                exig = overlays.get(it["item_id"], it["exigencia"])
                estado = "No aplica" if it["item_id"] in na_items else "Pendiente"
                crit = crit_boost.get(it["item_id"], it["criticidad"])
            conn.execute(
                """
                INSERT INTO pre_preset_items (
                    preset_id, seccion, item_id, categoria, requisito, exigencia,
                    criticidad, estado_inicial, orden
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    it["seccion"],
                    it["item_id"],
                    it["categoria"],
                    it["requisito"],
                    exig,
                    crit,
                    estado if it["seccion"] == "fabricante" else "Pendiente",
                    it["orden"],
                ),
            )


def _insert_default_items(conn, evaluacion_id: int):
    for it in default_items_payload():
        conn.execute(
            """
            INSERT INTO pre_items (
                evaluacion_id, seccion, item_id, categoria, requisito, exigencia,
                evidencia, criticidad, estado, responsable_cierre, fecha_compromiso,
                observaciones, orden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluacion_id,
                it["seccion"],
                it["item_id"],
                it["categoria"],
                it["requisito"],
                it["exigencia"],
                "",
                it["criticidad"],
                it["estado"],
                "",
                None,
                "",
                it["orden"],
            ),
        )


def _apply_preset_to_eval(conn, evaluacion_id: int, preset_id: int):
    preset = conn.execute("SELECT * FROM pre_presets WHERE id = ?", (preset_id,)).fetchone()
    if not preset:
        raise ValueError("Preset no encontrado.")
    pitems = conn.execute(
        "SELECT * FROM pre_preset_items WHERE preset_id = ? ORDER BY seccion, orden",
        (preset_id,),
    ).fetchall()
    if not pitems:
        raise ValueError("El preset no tiene ítems.")
    conn.execute("DELETE FROM pre_items WHERE evaluacion_id = ?", (evaluacion_id,))
    for it in pitems:
        conn.execute(
            """
            INSERT INTO pre_items (
                evaluacion_id, seccion, item_id, categoria, requisito, exigencia,
                evidencia, criticidad, estado, responsable_cierre, observaciones, orden
            ) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, '', '', ?)
            """,
            (
                evaluacion_id,
                it["seccion"],
                it["item_id"],
                it["categoria"],
                it["requisito"],
                it["exigencia"],
                it["criticidad"],
                it["estado_inicial"] or "Pendiente",
                it["orden"],
            ),
        )
    conn.execute(
        """
        UPDATE pre_evaluaciones SET
            preset_id = ?, preset_nombre = ?, fuente_requisitos = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (preset_id, preset["nombre"], preset["fuente"] or FUENTE_DEFAULT, evaluacion_id),
    )


def _integration(conn, servicio_id: int, inventario_id: int | None) -> dict:
    payload = {"inventario": None, "suficiencia": None, "dimensionamiento": None, "frecuencia_pm": None}
    if not inventario_id:
        return payload
    inv = conn.execute(
        "SELECT * FROM inventario_equipos WHERE id = ? AND servicio_id = ?",
        (inventario_id, servicio_id),
    ).fetchone()
    if not inv:
        return payload
    payload["inventario"] = _row_dict(inv)
    suf = conn.execute(
        """
        SELECT equipo, resultado, suficiencia_pct, brecha
        FROM suficiencia_evaluaciones
        WHERE servicio_id = ? AND equipo = ? COLLATE NOCASE
        """,
        (servicio_id, inv["equipo"]),
    ).fetchone()
    if suf:
        payload["suficiencia"] = _row_dict(suf)
    try:
        dim = conn.execute(
            """
            SELECT criticidad, aplica_mp, freq_mp, tiempo_mp
            FROM dim_actividad_equipo WHERE inventario_equipo_id = ?
            """,
            (inventario_id,),
        ).fetchone()
        if dim:
            payload["dimensionamiento"] = _row_dict(dim)
    except Exception:
        pass
    try:
        pm = conn.execute(
            """
            SELECT ge_total, frecuencia_oms, frecuencia_definitiva, pm_fabricante_meses,
                   funcion, aplicacion, estado, fecha_ultimo_pm
            FROM pm_inventario WHERE inventario_equipo_id = ?
            """,
            (inventario_id,),
        ).fetchone()
        if pm:
            payload["frecuencia_pm"] = _row_dict(pm)
    except Exception:
        pass
    return payload


def _create_solicitud(user, meta, evaluacion: dict, tipo: str, mensaje: str) -> int:
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
                "No hay destinatario ASISTENCIAL (Coordinador/Director/Líder) para esta sede."
            )
        meta_json = json.dumps(
            {
                "evaluacion_id": evaluacion.get("id"),
                "tecnologia": evaluacion.get("tecnologia"),
                "servicio_id": meta["id"],
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
                ?, ?, 'ALTA', 'PENDIENTE',
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
                tipo,
                mensaje,
                "pre_evaluacion",
                int(evaluacion["id"]),
                meta_json,
            ),
        )
        sol_conn.commit()
        return int(cur.lastrowid)


@pre_bp.get("/meta")
@login_required
@permission_required("view_preinstalacion")
def pre_meta():
    user = current_user()
    with get_empresas_connection() as conn:
        _seed_presets(conn)
        conn.commit()
        presets = [_row_dict(r) for r in conn.execute(
            "SELECT id, codigo, nombre, tipo_equipo, marca, modelo, fabricante, fuente, notas, es_global "
            "FROM pre_presets ORDER BY nombre COLLATE NOCASE"
        ).fetchall()]
    return jsonify({
        "ok": True,
        "catalogos": catalogs_payload(),
        "caps": _role_caps(user),
        "presets": presets,
        "alcance": ALCANCE,
        "formula": formula_meta("preinstalacion"),
    })


@pre_bp.get("/servicios/<int:servicio_id>/contexto")
@login_required
@permission_required("view_preinstalacion")
def pre_contexto(servicio_id: int):
    user = current_user()
    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        equipos = [
            _row_dict(r)
            for r in conn.execute(
                """
            SELECT id, num_biomedica, codigo_activo, registro_invima, equipo, marca, modelo, serie,
                   clasificacion_riesgo, ubicacion, codigo_ubicacion, estado, fecha_baja,
                   fecha_ultimo_pm,
                   voltaje, corriente, potencia, peso, temperatura_trabajo, presion,
                   fuente_alimentacion, comercializador, clasificacion_biomedica
            FROM inventario_equipos
                WHERE servicio_id = ?
                ORDER BY equipo COLLATE NOCASE, id
                """,
                (servicio_id,),
            ).fetchall()
        ]
        try:
            from server.frecuencia_pm import resumen_ejecucion_por_llaves
            from server.inventario import attach_flags_lista, clamp_anio

            year = clamp_anio(request.args.get("anio"))
            resumen = resumen_ejecucion_por_llaves(conn, int(meta["empresa_id"]), anio=year)
            attach_flags_lista(equipos, resumen, year)
        except Exception:
            year = None
        evals = [
            _row_dict(r)
            for r in conn.execute(
                """
                SELECT id, tecnologia, marca_modelo, serial_codigo, fecha_visita,
                       estado_eval, decision, pct_cumplimiento, criticos_abiertos,
                       inventario_equipo_id, updated_at
                FROM pre_evaluaciones
                WHERE servicio_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (servicio_id,),
            ).fetchall()
        ]
    return jsonify({
        "ok": True,
        "servicio": _row_dict(meta),
        "equipos": equipos,
        "anio": year,
        "evaluaciones": evals,
        "caps": _role_caps(user),
    })


@pre_bp.post("/evaluaciones")
@login_required
@permission_required("view_preinstalacion")
def pre_crear():
    user = current_user()
    caps = _role_caps(user)
    if not caps["can_edit"]:
        return jsonify({"ok": False, "error": "Solo OPERATIVO o ADMIN pueden diligenciar."}), 403
    body = request.get_json(silent=True) or {}
    try:
        servicio_id = int(body.get("servicio_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "servicio_id inválido."}), 400
    inventario_id = body.get("inventario_equipo_id")
    try:
        inventario_id = int(inventario_id) if inventario_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "inventario_equipo_id inválido."}), 400

    with get_empresas_connection() as conn:
        meta, err = _require_servicio(conn, user, servicio_id)
        if err:
            return err
        inv = None
        if inventario_id:
            inv = conn.execute(
                "SELECT * FROM inventario_equipos WHERE id = ? AND servicio_id = ?",
                (inventario_id, servicio_id),
            ).fetchone()
            if not inv:
                return jsonify({"ok": False, "error": "Equipo de inventario no encontrado en el servicio."}), 404
        marca_modelo = ""
        proveedor = sanitize_string(body.get("proveedor")) or ""
        ficha = ""
        if inv:
            marca_modelo = " ".join(x for x in (inv["marca"], inv["modelo"]) if x).strip()
            proveedor = (
                (inv["comercializador"] if "comercializador" in inv.keys() else None)
                or proveedor
            )
            specs = []
            for key, label in (
                ("voltaje", "Tensión"),
                ("corriente", "Corriente"),
                ("potencia", "Potencia"),
                ("peso", "Peso"),
                ("temperatura_trabajo", "Temperatura"),
                ("presion", "Presión"),
                ("fuente_alimentacion", "Fuente"),
            ):
                val = inv[key] if key in inv.keys() else None
                if val:
                    specs.append(f"{label}: {val}")
            if specs:
                ficha = "Ficha inventario: " + "; ".join(specs)
        fuente = FUENTE_DEFAULT if not ficha else f"{FUENTE_DEFAULT} | {ficha}"
        cur = conn.execute(
            """
            INSERT INTO pre_evaluaciones (
                servicio_id, inventario_equipo_id, institucion, sede_id, ID_sede, name_sede,
                ID_servicio, servicio_area, tecnologia, marca_modelo, marca, modelo,
                proveedor, serial_codigo, num_biomedica, registro_invima, ubicacion_propuesta,
                fecha_visita, responsable_verificacion, acompanante_servicio,
                fuente_requisitos, objetivo, estado_eval, created_by, created_by_login, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, 'BORRADOR', ?, ?, datetime('now')
            )
            """,
            (
                servicio_id,
                inventario_id,
                meta["ID_Empresa"],
                meta["sede_id"],
                meta["ID_sede"],
                meta["name_sede"],
                meta["ID_servicio"],
                meta["name_servicio"],
                (inv["equipo"] if inv else sanitize_string(body.get("tecnologia"), LABEL)) or "",
                marca_modelo,
                inv["marca"] if inv else None,
                inv["modelo"] if inv else None,
                proveedor or None,
                (inv["serie"] if inv else None) or (inv["num_biomedica"] if inv else None),
                inv["num_biomedica"] if inv else None,
                inv["registro_invima"] if inv else None,
                inv["ubicacion"] if inv else None,
                date.today().isoformat(),
                f"{user.get('NAME_USER') or ''}".strip() or user.get("usuario_login"),
                "",
                fuente,
                OBJETIVO_DEFAULT,
                user["id_usuario"],
                user.get("usuario_login"),
            ),
        )
        eid = cur.lastrowid
        _insert_default_items(conn, eid)
        suggested = None
        if inv:
            suggested = match_preset_codigo(inv["equipo"], inv["marca"], inv["modelo"])
            if suggested:
                prow = conn.execute(
                    "SELECT id FROM pre_presets WHERE codigo = ?", (suggested,)
                ).fetchone()
                if prow:
                    _apply_preset_to_eval(conn, eid, prow["id"])
        items = _items_of(conn, eid)
        _persist_resultado(conn, eid, calc_resultado(items))
        conn.commit()
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (eid,)).fetchone()
        payload = _eval_payload(conn, row)
        payload["integracion"] = _integration(conn, servicio_id, inventario_id)
        payload["preset_sugerido"] = suggested
    return jsonify({"ok": True, "message": "Evaluación de preinstalación creada.", "evaluacion": payload}), 201


@pre_bp.get("/evaluaciones/<int:evaluacion_id>")
@login_required
@permission_required("view_preinstalacion")
def pre_get(evaluacion_id: int):
    user = current_user()
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        meta, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        payload = _eval_payload(conn, row)
        payload["servicio"] = _row_dict(meta)
        payload["integracion"] = _integration(conn, row["servicio_id"], row["inventario_equipo_id"])
        payload["caps"] = _role_caps(user)
    return jsonify({"ok": True, "evaluacion": payload})


@pre_bp.put("/evaluaciones/<int:evaluacion_id>")
@login_required
@permission_required("view_preinstalacion")
def pre_update(evaluacion_id: int):
    user = current_user()
    if not _role_caps(user)["can_edit"]:
        return jsonify({"ok": False, "error": "Sin permiso para editar."}), 403
    body = request.get_json(silent=True) or {}
    fields = (
        "institucion", "servicio_area", "tecnologia", "marca_modelo", "marca", "modelo",
        "proveedor", "serial_codigo", "ubicacion_propuesta", "fecha_visita",
        "responsable_verificacion", "acompanante_servicio", "fuente_requisitos",
        "objetivo", "concepto_tecnico",
        "firma_ic_nombre", "firma_ic_cargo", "firma_ic_fecha",
        "firma_servicio_nombre", "firma_servicio_cargo", "firma_servicio_fecha",
    )
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        _, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        sets = []
        vals = []
        for f in fields:
            if f in body:
                sets.append(f"{f} = ?")
                vals.append(sanitize_string(body.get(f)) if isinstance(body.get(f), str) else body.get(f))
        if sets:
            vals.append(evaluacion_id)
            conn.execute(
                f"UPDATE pre_evaluaciones SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?",
                vals,
            )
        conn.commit()
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        return jsonify({"ok": True, "message": "Datos generales guardados.", "evaluacion": _eval_payload(conn, row)})


@pre_bp.put("/evaluaciones/<int:evaluacion_id>/items")
@login_required
@permission_required("view_preinstalacion")
def pre_update_items(evaluacion_id: int):
    user = current_user()
    if not _role_caps(user)["can_edit"]:
        return jsonify({"ok": False, "error": "Sin permiso para editar."}), 403
    body = request.get_json(silent=True) or {}
    items = body.get("items") or []
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "items inválido."}), 400
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        meta, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        for it in items:
            try:
                iid = int(it.get("id"))
            except (TypeError, ValueError):
                continue
            estado = sanitize_string(it.get("estado") or "Pendiente")
            if estado not in ESTADOS:
                estado = "Pendiente"
            crit = sanitize_string(it.get("criticidad") or "Mayor")
            if crit not in CRITICIDADES:
                crit = "Mayor"
            conn.execute(
                """
                UPDATE pre_items SET
                    exigencia = COALESCE(?, exigencia),
                    evidencia = ?,
                    criticidad = ?,
                    estado = ?,
                    responsable_cierre = ?,
                    fecha_compromiso = ?,
                    observaciones = ?
                WHERE id = ? AND evaluacion_id = ?
                """,
                (
                    sanitize_string(it.get("exigencia")) if it.get("exigencia") is not None else None,
                    sanitize_string(it.get("evidencia") or "", LONG_TEXT),
                    crit,
                    estado,
                    sanitize_string(it.get("responsable_cierre") or ""),
                    sanitize_string(it.get("fecha_compromiso") or "") or None,
                    sanitize_string(it.get("observaciones") or "", COMMENT),
                    iid,
                    evaluacion_id,
                ),
            )
        items_db = _items_of(conn, evaluacion_id)
        stats = calc_resultado(items_db)
        _persist_resultado(conn, evaluacion_id, stats)
        conn.commit()
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        payload = _eval_payload(conn, row)
    registrar_calculo(
        modulo="preinstalacion",
        empresa_id=meta["empresa_id"] if meta else None,
        sede_id=row["sede_id"] if row else None,
        servicio_id=row["servicio_id"] if row else None,
        usuario_id=user.get("id_usuario"),
        parametros={"evaluacion_id": evaluacion_id, "total_evaluables": stats.get("total_evaluables")},
        resultado={
            "Csitio": stats.get("pct_cumplimiento"),
            "decision": stats.get("decision"),
            "criticos_incumplidos": stats.get("criticos_incumplidos"),
        },
        user=user,
    )
    return jsonify({"ok": True, "message": "Checklist actualizado.", "evaluacion": payload})


@pre_bp.post("/evaluaciones/<int:evaluacion_id>/aplicar-preset")
@login_required
@permission_required("view_preinstalacion")
def pre_aplicar_preset(evaluacion_id: int):
    user = current_user()
    if not _role_caps(user)["can_presets"]:
        return jsonify({"ok": False, "error": "Sin permiso para cargar presets."}), 403
    body = request.get_json(silent=True) or {}
    try:
        preset_id = int(body.get("preset_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "preset_id inválido."}), 400
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        _, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        try:
            _apply_preset_to_eval(conn, evaluacion_id, preset_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        items = _items_of(conn, evaluacion_id)
        _persist_resultado(conn, evaluacion_id, calc_resultado(items))
        conn.commit()
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
    return jsonify({"ok": True, "message": "Preset aplicado.", "evaluacion": _eval_payload(conn, row)})


@pre_bp.post("/presets")
@login_required
@permission_required("view_preinstalacion")
def pre_save_preset():
    user = current_user()
    if not _role_caps(user)["can_presets"]:
        return jsonify({"ok": False, "error": "Sin permiso para guardar presets."}), 403
    body = request.get_json(silent=True) or {}
    nombre = sanitize_string(body.get("nombre") or "", LABEL)
    if not nombre:
        return jsonify({"ok": False, "error": "El nombre del preset es obligatorio."}), 400
    evaluacion_id = body.get("evaluacion_id")
    with get_empresas_connection() as conn:
        _seed_presets(conn)
        codigo = sanitize_string(body.get("codigo") or "") or f"USR_{int(datetime.now().timestamp())}"
        es_global = 1 if _role_caps(user)["can_edit_catalogs"] and body.get("es_global") else 0
        cur = conn.execute(
            """
            INSERT INTO pre_presets (
                codigo, nombre, tipo_equipo, marca, modelo, fabricante, fuente, notas,
                es_global, empresa_id, created_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                codigo,
                nombre,
                sanitize_string(body.get("tipo_equipo") or ""),
                sanitize_string(body.get("marca") or ""),
                sanitize_string(body.get("modelo") or ""),
                sanitize_string(body.get("fabricante") or ""),
                sanitize_string(body.get("fuente") or "Cargue manual del usuario"),
                sanitize_string(body.get("notas") or ""),
                es_global,
                user.get("empresa_id"),
                user["id_usuario"],
            ),
        )
        pid = cur.lastrowid
        items = []
        if evaluacion_id:
            items = _items_of(conn, int(evaluacion_id))
        if not items:
            items = default_items_payload()
        for it in items:
            conn.execute(
                """
                INSERT INTO pre_preset_items (
                    preset_id, seccion, item_id, categoria, requisito, exigencia,
                    criticidad, estado_inicial, orden
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    it["seccion"],
                    it["item_id"],
                    it["categoria"],
                    it["requisito"],
                    it.get("exigencia"),
                    it.get("criticidad") or "Mayor",
                    it.get("estado") or "Pendiente",
                    it.get("orden") or it["item_id"],
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM pre_presets WHERE id = ?", (pid,)).fetchone()
    return jsonify({"ok": True, "message": "Preset guardado.", "preset": _row_dict(row)}), 201


@pre_bp.post("/evaluaciones/<int:evaluacion_id>/solicitar-cierre")
@login_required
@permission_required("view_preinstalacion")
def pre_solicitar_cierre(evaluacion_id: int):
    user = current_user()
    if not _role_caps(user)["can_edit"]:
        return jsonify({"ok": False, "error": "Sin permiso."}), 403
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        meta, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        payload = _eval_payload(conn, row)
        abiertos = payload.get("abiertos") or []
        if not abiertos:
            return jsonify({"ok": False, "error": "No hay requisitos abiertos para solicitar cierre."}), 400
        crit = [a for a in abiertos if a.get("criticidad") == "Crítico"]
        resumen = "; ".join(f"{a['requisito']} ({a['estado']})" for a in (crit or abiertos)[:6])
        mensaje = (
            f"Cierre de requisitos de preinstalación — {row['tecnologia'] or 'equipo'} "
            f"en {meta['name_servicio']}. Abiertos: {resumen}."
        )
        try:
            sid = _create_solicitud(user, meta, dict(row), "cerrar_requisitos_preinstalacion", mensaje)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            conn.execute(
                """
                UPDATE pre_evaluaciones SET solicitud_id = ?, estado_eval = 'EN_REVISION',
                    updated_at = datetime('now') WHERE id = ?
                """,
                (sid, evaluacion_id),
            )
            conn.commit()
        except Exception:
            discard_pending_solicitud(sid)
            raise
    return jsonify({"ok": True, "message": "Solicitud de cierre enviada a bandeja asistencial.", "solicitud_id": sid})


@pre_bp.post("/evaluaciones/<int:evaluacion_id>/validar")
@login_required
@permission_required("view_preinstalacion")
def pre_validar(evaluacion_id: int):
    user = current_user()
    if not _role_caps(user)["can_validate"]:
        return jsonify({
            "ok": False,
            "error": "Solo ADMIN o Coordinador/Director/Líder asistencial pueden aprobar.",
        }), 403
    body = request.get_json(silent=True) or {}
    decision = sanitize_string(body.get("decision") or "").upper()
    if decision not in ("APROBADA", "RECHAZADA"):
        return jsonify({"ok": False, "error": "decision debe ser APROBADA o RECHAZADA."}), 400
    comentario = sanitize_string(body.get("comentario") or "", COMMENT)
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        _, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        stats = calc_resultado(_items_of(conn, evaluacion_id))
        if decision == "APROBADA" and stats["criticos_abiertos"] > 0:
            return jsonify({
                "ok": False,
                "error": "No se puede aprobar: hay requisitos críticos abiertos (regla del Excel).",
            }), 400
        conn.execute(
            """
            UPDATE pre_evaluaciones SET
                estado_eval = ?, comentario_asistencial = ?,
                aprobado_por = ?, aprobado_por_login = ?, aprobado_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (decision, comentario, user["id_usuario"], user.get("usuario_login"), evaluacion_id),
        )
        prev_sol_estado = None
        sid = row["solicitud_id"]
        if sid:
            with get_solicitudes_connection() as sol_conn:
                prev = sol_conn.execute(
                    "SELECT estado FROM solicitudes WHERE id = ?",
                    (sid,),
                ).fetchone()
                prev_sol_estado = (prev["estado"] if prev else "PENDIENTE") or "PENDIENTE"
                sol_conn.execute(
                    """
                    UPDATE solicitudes SET estado = ?, resolved_at = datetime('now')
                    WHERE id = ? AND estado = 'PENDIENTE'
                    """,
                    ("APROBADA" if decision == "APROBADA" else "RECHAZADA", sid),
                )
                sol_conn.commit()
        try:
            conn.commit()
            row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
            payload = _eval_payload(conn, row)
        except Exception:
            if sid and prev_sol_estado:
                revert_solicitud_estado(sid, prev_sol_estado)
            raise
    return jsonify({"ok": True, "message": f"Preinstalación {decision.lower()}.", "evaluacion": payload})


@pre_bp.get("/evaluaciones/<int:evaluacion_id>/pdf")
@login_required
@permission_required("view_preinstalacion")
def pre_pdf(evaluacion_id: int):
    user = current_user()
    with get_empresas_connection() as conn:
        row = conn.execute("SELECT * FROM pre_evaluaciones WHERE id = ?", (evaluacion_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        meta, err = _require_servicio(conn, user, row["servicio_id"])
        if err:
            return err
        payload = _eval_payload(conn, row)
        payload["servicio"] = _row_dict(meta)
    staff = collect_org_staff(empresa_id=meta["empresa_id"], sede_id=meta["sede_id"])
    pdf = build_informe_pdf(payload, generado_por=user.get("usuario_login") or "", staff=staff)
    filename = f"preinstalacion_{evaluacion_id}.pdf"
    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
