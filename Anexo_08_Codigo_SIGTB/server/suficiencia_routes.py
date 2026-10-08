"""API HTTP de suficiencia: contexto, persistencia y recálculo."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from openpyxl import Workbook

from server.authz import (
    can_access_servicio,
    current_user,
    is_global_scope,
    login_required,
    permission_required,
    user_has_permission,
)
from server.db import get_empresas_connection
from server.frecuencia_pm import resumen_ejecucion_por_llaves
from server.inventario import attach_flags_lista, clamp_anio
from server.suficiencia import (
    DEFAULT_PARAMS,
    TIPOS_CALCULO,
    TIPOS_CALCULO_LABELS,
    TIPOS_CALCULO_TFM,
    calcular_evaluacion,
    ocupacion_pct,
    summarize_inventario,
)
from server.formula_versions import formula_meta, registrar_calculo
from server.limits import COMMENT, LONG_TEXT
from server.validators import sanitize_string

suficiencia_bp = Blueprint("suficiencia", __name__, url_prefix="/api/suficiencia")


def _ensure_params(conn):
    conn.execute("INSERT OR IGNORE INTO suficiencia_parametros (id) VALUES (1)")
    row = conn.execute("SELECT * FROM suficiencia_parametros WHERE id = 1").fetchone()
    return dict(row) if row else dict(DEFAULT_PARAMS)


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


def _inventario_enriquecido(conn, servicio_id: int, anio: int | None = None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT ie.*, srv.ID_servicio, srv.name_servicio, s.empresa_id
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE ie.servicio_id = ?
        ORDER BY ie.equipo COLLATE NOCASE, ie.id
        """,
        (servicio_id,),
    ).fetchall()
    equipos = [dict(r) for r in rows]
    if not equipos:
        return []
    year = clamp_anio(anio)
    try:
        resumen = resumen_ejecucion_por_llaves(conn, int(equipos[0]["empresa_id"]), anio=year)
    except Exception:
        resumen = {}
    attach_flags_lista(equipos, resumen, year)
    return equipos


def _inventario_summary(conn, servicio_id: int, anio: int | None = None):
    return summarize_inventario(_inventario_enriquecido(conn, servicio_id, anio))


def _eval_payload(row):
    return dict(row)


def _recalc_row(conn, servicio_id: int, body: dict, params: dict, datos: dict | None, inv_map: dict):
    equipo = sanitize_string(body.get("equipo"))
    if not equipo:
        raise ValueError("equipo es obligatorio.")
    tipo = sanitize_string(body.get("tipo_calculo") or "mixto").lower()
    if tipo not in TIPOS_CALCULO:
        raise ValueError("tipo_calculo inválido.")

    datos = datos or {}
    inv = inv_map.get(equipo) or {
        "cantidad_total": 0,
        "cantidad_operativa": 0,
        "en_mantenimiento": 0,
        "prestado_nd": 0,
        "disponible_real": 0,
    }
    if equipo not in inv_map:
        for k, v in inv_map.items():
            if k.lower() == equipo.lower():
                inv = v
                equipo = k
                break

    calc = calcular_evaluacion(
        tipo_calculo=tipo,
        pacientes_simultaneos=body.get("pacientes_simultaneos"),
        demanda_diaria=body.get("demanda_diaria"),
        tiempo_uso_min=body.get("tiempo_uso_min"),
        minimo_tecnico=body.get("minimo_tecnico"),
        respaldo_especifico=body.get("respaldo_especifico"),
        horas_servicio_dia=datos.get("horas_servicio_dia"),
        capacidad_instalada=datos.get("capacidad_instalada"),
        promedio_ocupado=datos.get("promedio_ocupado"),
        inventario=inv,
        params=params,
    )

    return {
        "servicio_id": servicio_id,
        "equipo": equipo,
        "tipo_calculo": tipo,
        "pacientes_simultaneos": body.get("pacientes_simultaneos"),
        "demanda_diaria": body.get("demanda_diaria"),
        "tiempo_uso_min": body.get("tiempo_uso_min"),
        "minimo_tecnico": body.get("minimo_tecnico") or 0,
        "respaldo_especifico": body.get("respaldo_especifico") or 0,
        "fuente_dato": sanitize_string(body.get("fuente_dato")),
        "comentario": sanitize_string(body.get("comentario"), COMMENT),
        "ayuda_diligenciar": sanitize_string(body.get("ayuda_diligenciar"), LONG_TEXT),
        **calc,
        # Compat columna histórica `prestado`
        "prestado": calc.get("prestado_nd") or 0,
    }


@suficiencia_bp.get("/meta")
@login_required
@permission_required("view_suficiencia", "edit_suficiencia_asistencial")
def suficiencia_meta():
    return jsonify(
        {
            "ok": True,
            "tipos_calculo": [
                {"id": k, "label": TIPOS_CALCULO_LABELS[k]} for k in TIPOS_CALCULO
            ],
            "modos_tfm": [{"id": k, "label": TIPOS_CALCULO_LABELS[k]} for k in TIPOS_CALCULO_TFM],
            "formula": formula_meta("suficiencia"),
            "resultados": [
                "Suficiente",
                "Alerta",
                "Insuficiente",
                "No evaluado",
                "Revisar",
            ],
            "estados_equipo": [
                "OPERATIVO",
                "EN MANTENIMIENTO",
                "FUERA DE SERVICIO",
                "PRESTADO",
                "BAJA",
                "PENDIENTE",
            ],
            "tooltips": {
                "tipo_calculo": "Modos TFM: demanda, concurrencia, mínimo y mixto. Los tipos legado se mapean a esos cuatro.",
                "disponible": "D = número de equipos operativos del servicio (Ii = 1 si operativo).",
                "resultado": "Resultado automático basado en el porcentaje de suficiencia calculado.",
                "estado_equipo": "Si el estado está vacío, el sistema lo considera Operativo por defecto.",
                "parametros": "Estos parámetros institucionales se aplican automáticamente en los cálculos de suficiencia.",
                "datos_servicio": "Información que debe suministrar el rol asistencial. El área operativa puede solicitar su actualización desde la bandeja.",
                "ocupacion": "Porcentaje de ocupación = Promedio ocupado/simultáneo ÷ Capacidad instalada.",
                "capacidad_instalada": "Capacidad instalada del servicio (camas, camillas, quirófanos, etc.).",
                "promedio_ocupado": "Promedio de puestos/pacientes ocupados de forma simultánea.",
                "inventario": "Inventario del servicio seleccionado (no se combinan sedes). En blanco = Operativo.",
                "disponible_real": "D = equipos operativos del servicio (Ii = 1).",
                "matriz": "Concurrencia y demanda por tipo de equipo. Se guardan y calculan automáticamente al ingresar los datos.",
                "servicio": "Seleccione la sede y el servicio (misma sede; no se mezclan inventarios).",
                "equipo": "Equipos biomédicos del inventario de ese servicio (monitores, camas, etc.).",
                "simultaneos": "Pacientes/puestos que requieren el equipo al mismo tiempo. Ej.: si 5 pacientes pueden requerir monitor, indique 5.",
                "pacientes_simultaneos": "Habilitado si Tipo = Por capacidad (también en Mixto/Principal/Sala). Ej.: 5 pacientes con monitor.",
                "demanda_campos": "Habilitados si Tipo ≠ Por capacidad. Demanda diaria y minutos por atención/procedimiento.",
                "minimo_tecnico": "Mínimo normativo o institucional para brindar la atención.",
                "respaldo_especifico": "Cantidad de equipos de respaldo en el servicio (dejar vacío si no aplica).",
                "concurrencia": "% concurrencia = pacientes/puestos simultáneos ÷ capacidad base (inventario del equipo).",
                "utilizacion_segura": "Tope de utilización segura institucional (p. ej. 75%).",
                "respaldo_pct": "Porcentaje institucional de respaldo sobre el requerido base.",
                "umbral_alerta": "Umbral de suficiencia para marcar Alerta (p. ej. 80%).",
                "req_capacidad": "Necesidad estimada a partir de capacidad, ocupación y concurrencia.",
                "req_demanda": "Necesidad estimada a partir de demanda diaria, tiempo de uso y horas de servicio.",
                "fuente_dato": "Rol + empresa + sede + servicio que respaldan el dato manual.",
                "comentario": "Observaciones para interpretar el cálculo.",
                "evaluacion": "Informe final por servicio: todos los equipos del mismo servicio.",
                "acciones": "Recomendaciones automáticas según Suficiente / Alerta / Insuficiente.",
                "requerido_final": "Rfinal = ⌈Rb·(1+b)⌉ + Re (respaldo institucional b y respaldo específico Re).",
                "brecha": "Brecha = Inventario disponible − Requerido final. Negativo = déficit.",
                "suficiencia": "Suficiencia = Inventario disponible ÷ Requerido final (≥1 Suficiente; 0.80–0.99 Alerta; <0.80 Insuficiente).",
            },
            "permisos_hint": {
                "asistencial": "Ingresa datos del servicio y matriz de concurrencia/demanda.",
                "operativo": "Consulta resultados y puede solicitar actualización asistencial por bandeja.",
            },
        }
    )


@suficiencia_bp.get("/parametros")
@login_required
@permission_required("view_suficiencia", "edit_suficiencia_asistencial")
def get_parametros():
    with get_empresas_connection() as conn:
        row = _ensure_params(conn)
        conn.commit()
    return jsonify({"ok": True, "parametros": row})


def _as_fraction(value, default):
    """Acepta 0–1 o porcentaje 1–100."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n > 1:
        n = n / 100.0
    return n


@suficiencia_bp.put("/parametros")
@login_required
@permission_required("admin_panel", "modify_empresa")
def put_parametros():
    body = request.get_json(silent=True) or {}
    util = _as_fraction(body.get("utilizacion_segura"), 0.75)
    respaldo = _as_fraction(body.get("respaldo_general"), 0.20)
    umbral = _as_fraction(body.get("umbral_alerta"), 0.80)
    redondeo = sanitize_string(body.get("redondeo") or "CEIL").upper()
    if redondeo not in ("CEIL", "ROUND"):
        redondeo = "CEIL"
    if not (0 < util <= 1) or not (0 <= respaldo <= 1) or not (0 < umbral <= 1):
        return jsonify({"ok": False, "error": "Parámetros fuera de rango."}), 400

    with get_empresas_connection() as conn:
        _ensure_params(conn)
        conn.execute(
            """
            UPDATE suficiencia_parametros
            SET utilizacion_segura = ?, respaldo_general = ?, umbral_alerta = ?,
                redondeo = ?, updated_at = datetime('now')
            WHERE id = 1
            """,
            (util, respaldo, umbral, redondeo),
        )
        row = _ensure_params(conn)
        conn.commit()
    return jsonify({"ok": True, "message": "Parámetros actualizados.", "parametros": row})


@suficiencia_bp.get("/servicios/<int:servicio_id>/contexto")
@login_required
@permission_required("view_suficiencia", "edit_suficiencia_asistencial")
def get_contexto(servicio_id):
    user = current_user()
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403

        params = _ensure_params(conn)
        datos = conn.execute(
            "SELECT * FROM suficiencia_datos_servicio WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchone()
        year = clamp_anio(request.args.get("anio"))
        inv_rows = _inventario_enriquecido(conn, servicio_id, year)
        inv_map = summarize_inventario(inv_rows)
        evals = conn.execute(
            """
            SELECT * FROM suficiencia_evaluaciones
            WHERE servicio_id = ?
            ORDER BY equipo COLLATE NOCASE
            """,
            (servicio_id,),
        ).fetchall()
        conn.commit()

    datos_payload = dict(datos) if datos else None
    if datos_payload:
        datos_payload["ocupacion_pct"] = ocupacion_pct(
            datos_payload.get("capacidad_instalada"),
            datos_payload.get("promedio_ocupado"),
        )

    fuente_default = (
        f"{meta['ID_Empresa']} · {meta['name_sede']} · {meta['name_servicio']}"
    )

    return jsonify(
        {
            "ok": True,
            "servicio": dict(meta),
            "parametros": params,
            "datos_servicio": datos_payload,
            "inventario_por_equipo": inv_map,
            "inventario_rows": inv_rows,
            "anio": year,
            "equipos": sorted(inv_map.keys(), key=str.lower),
            "evaluaciones": [
                {
                    **_eval_payload(r),
                    "alerta_sin_datos_anio": bool(
                        (inv_map.get(r["equipo"]) or {}).get("alerta_sin_datos_anio")
                    ),
                }
                for r in evals
            ],
            "fuente_default": fuente_default,
            "can_edit_asistencial": bool(
                is_global_scope(user) or user_has_permission("edit_suficiencia_asistencial")
            ),
            "can_request_update": bool(
                is_global_scope(user) or user_has_permission("request_suficiencia_update")
            ),
        }
    )


@suficiencia_bp.put("/servicios/<int:servicio_id>/datos")
@login_required
@permission_required("edit_suficiencia_asistencial", "admin_panel")
def put_datos_servicio(servicio_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403

        conn.execute(
            """
            INSERT INTO suficiencia_datos_servicio (
                servicio_id, capacidad_instalada, unidad_capacidad, promedio_ocupado,
                horas_servicio_dia, jornadas_dia, fuente_dato, comentario,
                ayuda_diligenciar, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(servicio_id) DO UPDATE SET
                capacidad_instalada = excluded.capacidad_instalada,
                unidad_capacidad = excluded.unidad_capacidad,
                promedio_ocupado = excluded.promedio_ocupado,
                horas_servicio_dia = excluded.horas_servicio_dia,
                jornadas_dia = excluded.jornadas_dia,
                fuente_dato = excluded.fuente_dato,
                comentario = excluded.comentario,
                ayuda_diligenciar = excluded.ayuda_diligenciar,
                updated_at = datetime('now')
            """,
            (
                servicio_id,
                body.get("capacidad_instalada"),
                sanitize_string(body.get("unidad_capacidad")),
                body.get("promedio_ocupado"),
                body.get("horas_servicio_dia"),
                body.get("jornadas_dia") if body.get("jornadas_dia") not in (None, "") else 1,
                sanitize_string(body.get("fuente_dato")),
                sanitize_string(body.get("comentario"), COMMENT),
                sanitize_string(body.get("ayuda_diligenciar"), LONG_TEXT),
            ),
        )
        row = conn.execute(
            "SELECT * FROM suficiencia_datos_servicio WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchone()
        conn.commit()

    payload = dict(row)
    payload["ocupacion_pct"] = ocupacion_pct(
        payload.get("capacidad_instalada"), payload.get("promedio_ocupado")
    )
    return jsonify({"ok": True, "message": "Datos del servicio guardados.", "datos_servicio": payload})


@suficiencia_bp.post("/servicios/<int:servicio_id>/evaluaciones")
@login_required
@permission_required("edit_suficiencia_asistencial", "admin_panel")
def upsert_evaluacion(servicio_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403

        params = _ensure_params(conn)
        datos_row = conn.execute(
            "SELECT * FROM suficiencia_datos_servicio WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchone()
        datos = dict(datos_row) if datos_row else None
        inv_map = _inventario_summary(conn, servicio_id)

        try:
            computed = _recalc_row(conn, servicio_id, body, params, datos, inv_map)
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400

        conn.execute(
            """
            INSERT INTO suficiencia_evaluaciones (
                servicio_id, equipo, tipo_calculo,
                pacientes_simultaneos, demanda_diaria, tiempo_uso_min,
                minimo_tecnico, respaldo_especifico, fuente_dato, comentario,
                cantidad_total, cantidad_operativa, en_mantenimiento, prestado,
                disponible_real, ocupacion_pct, concurrencia_pct, capacidad_base_auto,
                puestos_ocupados_auto, utilizacion_segura, respaldo_pct, horas_servicio_dia,
                req_capacidad, req_demanda, requerido_base, respaldo_unidades, requerido_final,
                brecha, suficiencia_pct, resultado, acciones_sugeridas, ayuda_diligenciar, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, datetime('now')
            )
            ON CONFLICT(servicio_id, equipo) DO UPDATE SET
                tipo_calculo = excluded.tipo_calculo,
                pacientes_simultaneos = excluded.pacientes_simultaneos,
                demanda_diaria = excluded.demanda_diaria,
                tiempo_uso_min = excluded.tiempo_uso_min,
                minimo_tecnico = excluded.minimo_tecnico,
                respaldo_especifico = excluded.respaldo_especifico,
                fuente_dato = excluded.fuente_dato,
                comentario = excluded.comentario,
                cantidad_total = excluded.cantidad_total,
                cantidad_operativa = excluded.cantidad_operativa,
                en_mantenimiento = excluded.en_mantenimiento,
                prestado = excluded.prestado,
                disponible_real = excluded.disponible_real,
                ocupacion_pct = excluded.ocupacion_pct,
                concurrencia_pct = excluded.concurrencia_pct,
                capacidad_base_auto = excluded.capacidad_base_auto,
                puestos_ocupados_auto = excluded.puestos_ocupados_auto,
                utilizacion_segura = excluded.utilizacion_segura,
                respaldo_pct = excluded.respaldo_pct,
                horas_servicio_dia = excluded.horas_servicio_dia,
                req_capacidad = excluded.req_capacidad,
                req_demanda = excluded.req_demanda,
                requerido_base = excluded.requerido_base,
                respaldo_unidades = excluded.respaldo_unidades,
                requerido_final = excluded.requerido_final,
                brecha = excluded.brecha,
                suficiencia_pct = excluded.suficiencia_pct,
                resultado = excluded.resultado,
                acciones_sugeridas = excluded.acciones_sugeridas,
                ayuda_diligenciar = excluded.ayuda_diligenciar,
                updated_at = datetime('now')
            """,
            (
                computed["servicio_id"],
                computed["equipo"],
                computed["tipo_calculo"],
                computed.get("pacientes_simultaneos"),
                computed.get("demanda_diaria"),
                computed.get("tiempo_uso_min"),
                computed.get("minimo_tecnico"),
                computed.get("respaldo_especifico"),
                computed.get("fuente_dato"),
                computed.get("comentario"),
                computed.get("cantidad_total"),
                computed.get("cantidad_operativa"),
                computed.get("en_mantenimiento"),
                computed.get("prestado"),
                computed.get("disponible_real"),
                computed.get("ocupacion_pct"),
                computed.get("concurrencia_pct"),
                computed.get("capacidad_base_auto"),
                computed.get("puestos_ocupados_auto"),
                computed.get("utilizacion_segura"),
                computed.get("respaldo_pct"),
                computed.get("horas_servicio_dia"),
                computed.get("req_capacidad"),
                computed.get("req_demanda"),
                computed.get("requerido_base"),
                computed.get("respaldo_unidades"),
                computed.get("requerido_final"),
                computed.get("brecha"),
                computed.get("suficiencia_pct"),
                computed.get("resultado"),
                computed.get("acciones_sugeridas"),
                computed.get("ayuda_diligenciar"),
            ),
        )
        row = conn.execute(
            """
            SELECT * FROM suficiencia_evaluaciones
            WHERE servicio_id = ? AND equipo = ? COLLATE NOCASE
            """,
            (servicio_id, computed["equipo"]),
        ).fetchone()
        conn.commit()

    registrar_calculo(
        modulo="suficiencia",
        empresa_id=meta["empresa_id"],
        sede_id=meta["sede_id"],
        servicio_id=servicio_id,
        usuario_id=user.get("id_usuario"),
        parametros={
            "equipo": computed.get("equipo"),
            "tipo_calculo": computed.get("tipo_calculo"),
            "modo_tfm": computed.get("modo_tfm"),
        },
        resultado={
            "S": computed.get("suficiencia_pct"),
            "resultado": computed.get("resultado"),
            "Rfinal": computed.get("requerido_final"),
            "D": computed.get("disponible_real"),
            "version": computed.get("formula_version"),
        },
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": "Evaluación calculada y guardada.",
            "evaluacion": _eval_payload(row),
        }
    ), 201


@suficiencia_bp.post("/servicios/<int:servicio_id>/recalcular")
@login_required
@permission_required(
    "edit_suficiencia_asistencial",
    "view_suficiencia",
    "admin_panel",
)
def recalcular_todo(servicio_id):
    user = current_user()
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403

        params = _ensure_params(conn)
        datos_row = conn.execute(
            "SELECT * FROM suficiencia_datos_servicio WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchone()
        datos = dict(datos_row) if datos_row else None
        inv_map = _inventario_summary(conn, servicio_id)
        existing = conn.execute(
            "SELECT * FROM suficiencia_evaluaciones WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchall()

        updated = []
        for row in existing:
            body = dict(row)
            computed = _recalc_row(conn, servicio_id, body, params, datos, inv_map)
            conn.execute(
                """
                UPDATE suficiencia_evaluaciones SET
                    cantidad_total = ?, cantidad_operativa = ?, en_mantenimiento = ?,
                    prestado = ?, disponible_real = ?, ocupacion_pct = ?,
                    concurrencia_pct = ?, capacidad_base_auto = ?, puestos_ocupados_auto = ?,
                    utilizacion_segura = ?, respaldo_pct = ?, horas_servicio_dia = ?,
                    req_capacidad = ?, req_demanda = ?, requerido_base = ?,
                    respaldo_unidades = ?, requerido_final = ?, brecha = ?,
                    suficiencia_pct = ?, resultado = ?, acciones_sugeridas = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    computed.get("cantidad_total"),
                    computed.get("cantidad_operativa"),
                    computed.get("en_mantenimiento"),
                    computed.get("prestado"),
                    computed.get("disponible_real"),
                    computed.get("ocupacion_pct"),
                    computed.get("concurrencia_pct"),
                    computed.get("capacidad_base_auto"),
                    computed.get("puestos_ocupados_auto"),
                    computed.get("utilizacion_segura"),
                    computed.get("respaldo_pct"),
                    computed.get("horas_servicio_dia"),
                    computed.get("req_capacidad"),
                    computed.get("req_demanda"),
                    computed.get("requerido_base"),
                    computed.get("respaldo_unidades"),
                    computed.get("requerido_final"),
                    computed.get("brecha"),
                    computed.get("suficiencia_pct"),
                    computed.get("resultado"),
                    computed.get("acciones_sugeridas"),
                    row["id"],
                ),
            )
            updated.append(row["id"])

        rows = conn.execute(
            """
            SELECT * FROM suficiencia_evaluaciones
            WHERE servicio_id = ? ORDER BY equipo COLLATE NOCASE
            """,
            (servicio_id,),
        ).fetchall()
        conn.commit()

    registrar_calculo(
        modulo="suficiencia",
        empresa_id=meta["empresa_id"],
        sede_id=meta["sede_id"],
        servicio_id=servicio_id,
        usuario_id=user.get("id_usuario"),
        parametros={"accion": "recalcular", "n": len(updated)},
        resultado={"n": len(updated)},
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": f"Recalculadas {len(updated)} evaluación(es).",
            "evaluaciones": [_eval_payload(r) for r in rows],
        }
    )


@suficiencia_bp.delete("/evaluaciones/<int:eval_id>")
@login_required
@permission_required("edit_suficiencia_asistencial", "admin_panel")
def delete_evaluacion(eval_id):
    user = current_user()
    with get_empresas_connection() as conn:
        row = conn.execute(
            "SELECT * FROM suficiencia_evaluaciones WHERE id = ?", (eval_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Evaluación no encontrada."}), 404
        if not can_access_servicio(user, row["servicio_id"]):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        conn.execute("DELETE FROM suficiencia_evaluaciones WHERE id = ?", (eval_id,))
        conn.commit()
    return jsonify({"ok": True, "message": "Evaluación eliminada."})


@suficiencia_bp.get("/servicios/<int:servicio_id>/export.csv")
@login_required
@permission_required("view_suficiencia", "edit_suficiencia_asistencial")
def export_csv(servicio_id):
    user = current_user()
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        rows = conn.execute(
            """
            SELECT * FROM suficiencia_evaluaciones
            WHERE servicio_id = ? ORDER BY equipo COLLATE NOCASE
            """,
            (servicio_id,),
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Equipo",
            "Tipo cálculo",
            "Disponible real",
            "Req. capacidad",
            "Req. demanda",
            "Requerido base",
            "Respaldo",
            "Requerido final",
            "Brecha",
            "Suficiencia",
            "Resultado",
            "Acciones",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["equipo"],
                r["tipo_calculo"],
                r["disponible_real"],
                r["req_capacidad"],
                r["req_demanda"],
                r["requerido_base"],
                r["respaldo_unidades"],
                r["requerido_final"],
                r["brecha"],
                r["suficiencia_pct"],
                r["resultado"],
                r["acciones_sugeridas"],
            ]
        )
    data = buf.getvalue().encode("utf-8-sig")
    filename = f"suficiencia_{meta['ID_servicio']}_{datetime.now():%Y%m%d}.csv"
    return send_file(
        io.BytesIO(data),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@suficiencia_bp.get("/servicios/<int:servicio_id>/export.xlsx")
@login_required
@permission_required("view_suficiencia", "edit_suficiencia_asistencial")
def export_xlsx(servicio_id):
    user = current_user()
    with get_empresas_connection() as conn:
        meta = _servicio_meta(conn, servicio_id)
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id):
            return jsonify({"ok": False, "error": "No autorizado."}), 403
        rows = conn.execute(
            """
            SELECT * FROM suficiencia_evaluaciones
            WHERE servicio_id = ? ORDER BY equipo COLLATE NOCASE
            """,
            (servicio_id,),
        ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Suficiencia"
    headers = [
        "Equipo",
        "Tipo cálculo",
        "Disponible real",
        "Req. capacidad",
        "Req. demanda",
        "Requerido base",
        "Respaldo",
        "Requerido final",
        "Brecha",
        "Suficiencia",
        "Resultado",
        "Acciones",
    ]
    ws.append(headers)
    for r in rows:
        ws.append(
            [
                r["equipo"],
                r["tipo_calculo"],
                r["disponible_real"],
                r["req_capacidad"],
                r["req_demanda"],
                r["requerido_base"],
                r["respaldo_unidades"],
                r["requerido_final"],
                r["brecha"],
                r["suficiencia_pct"],
                r["resultado"],
                r["acciones_sugeridas"],
            ]
        )
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"suficiencia_{meta['ID_servicio']}_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        out,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )
