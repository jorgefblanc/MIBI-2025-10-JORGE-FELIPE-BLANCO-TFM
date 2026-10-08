"""Carga FOSCAGIB: empresas, sedes, servicios e inventario sin cruzar áreas."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

from server.inventory_enrichment import (
    EMPRESAS_FOSCAGIB,
    FUENTE_FOSCAGIB,
    as_tri_flag,
    ficha_electrica,
    infer_estado,
    infer_fecha_ultimo_pm,
    map_aplicacion_oms,
    map_criticidad_dim,
    map_fallas_oms,
    map_funcion_oms,
    map_requisito_oms,
    parse_any_date,
    parse_vida_util_anios,
    periodicidad_a_freq,
    tiempo_mp_default,
)
from server.inventario_params import freq_anual_to_meses
from server.org_ubicacion import (
    ensure_empresa_by_key,
    ensure_sede,
    ensure_servicio_with_id,
    resolve_servicio_destino,
)
from server.validators import sanitize_string

CSV_CANDIDATES = (
    ROOT_DIR / "data" / "imports" / "foscagib_limpio.csv",
)

INVENTORY_INSERT_COLUMNS = (
    "servicio_id",
    "num_biomedica",
    "registro_invima",
    "equipo",
    "marca",
    "serie",
    "modelo",
    "clasificacion_riesgo",
    "ubicacion",
    "estado",
    "aplica_mp",
    "freq_mp",
    "tiempo_mp",
    "aplica_cal",
    "freq_cal",
    "tiempo_cal",
    "aplica_val",
    "freq_val",
    "tiempo_val",
    "creation_date",
    "clasificacion_biomedica",
    "tecnologia",
    "forma_adquisicion",
    "vida_util_anios",
    "vida_util_txt",
    "fecha_compra",
    "fecha_operacion",
    "fecha_garantia",
    "fecha_baja",
    "fecha_ultimo_pm",
    "fecha_actualizacion",
    "codigo_activo",
    "codigo_ubicacion",
    "institucion_origen",
    "fuente_import",
    "codigo_origen",
    "novedad_desc",
    "voltaje",
    "corriente",
    "potencia",
    "peso",
    "temperatura_trabajo",
    "presion",
    "fuente_alimentacion",
    "comercializador",
    "manual_operacion",
    "manual_servicio",
    "componente1",
    "componente2",
    "componente3",
    "periodicidad_mp",
    "periodicidad_cal",
    "requiere_calibracion",
)


def resolve_csv_path() -> Path | None:
    dest = CSV_CANDIDATES[0]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    return None


def _blank_to_none(value):
    text = str(value or "").strip()
    if not text or text.upper() in {"NA", "N/A", "NONE", "NULL"}:
        return None
    return text


def _ensure_empresa(conn, key: str) -> int:
    return ensure_empresa_by_key(conn, key)


def _row_to_inventory(csv_row: dict, servicio_id: int, sede_name: str, servicio_name: str) -> tuple:
    equipo = sanitize_string(csv_row.get("equipo")) or "Sin nombre"
    aplica_mp, freq_mp = periodicidad_a_freq(csv_row.get("periodicidaddelMantenimiento"))
    mp_flag = as_tri_flag(csv_row.get("mp"))
    if aplica_mp is None:
        aplica_mp = 1 if mp_flag == 1 else (0 if mp_flag == 0 else None)
    if aplica_mp == 0:
        freq_mp = None
    elif freq_mp is None and mp_flag == 1:
        freq_mp = 1.0

    aplica_cal, freq_cal = periodicidad_a_freq(csv_row.get("periodicidaddelaCalibracion"))
    req_cal = as_tri_flag(csv_row.get("requiereCalibracion"))
    if aplica_cal is None:
        aplica_cal = req_cal
    if aplica_cal == 0:
        freq_cal = None
    elif freq_cal is None and req_cal == 1:
        freq_cal = 1.0

    fecha_baja = parse_any_date(csv_row.get("fechaBaja"))
    novedad = _blank_to_none(csv_row.get("novedaddes"))
    estado = infer_estado(fecha_baja, novedad)
    if fecha_baja:
        aplica_mp = 0
        freq_mp = None
        tiempo_mp = None
    fecha_pm = infer_fecha_ultimo_pm(csv_row)
    bio = _blank_to_none(csv_row.get("clasificacionBiomedica"))
    riesgo = _blank_to_none(csv_row.get("clasificacionporRiesgo"))
    tiempo_mp = tiempo_mp_default(bio, riesgo) if aplica_mp == 1 else None
    tiempo_cal = 1.5 if aplica_cal == 1 else None
    created = parse_any_date(csv_row.get("fechacreacion")) or None
    ubicacion = _blank_to_none(csv_row.get("ubicacionnombre")) or servicio_name

    values = {
        "servicio_id": servicio_id,
        "num_biomedica": _blank_to_none(csv_row.get("inventarioBiomedica")),
        "registro_invima": _blank_to_none(csv_row.get("registrooPermiso")),
        "equipo": equipo,
        "marca": _blank_to_none(csv_row.get("marca")),
        "serie": _blank_to_none(csv_row.get("numerodeSerie")),
        "modelo": _blank_to_none(csv_row.get("modelo")),
        "clasificacion_riesgo": riesgo,
        "ubicacion": ubicacion,
        "estado": estado,
        "aplica_mp": aplica_mp,
        "freq_mp": freq_mp,
        "tiempo_mp": tiempo_mp,
        "aplica_cal": aplica_cal,
        "freq_cal": freq_cal,
        "tiempo_cal": tiempo_cal,
        "aplica_val": 0,
        "freq_val": None,
        "tiempo_val": None,
        "creation_date": created or None,
        "clasificacion_biomedica": bio,
        "tecnologia": _blank_to_none(csv_row.get("tecnologiaPredominante")),
        "forma_adquisicion": _blank_to_none(csv_row.get("formadeAdquisicion")),
        "vida_util_anios": parse_vida_util_anios(csv_row.get("vidaUtil")),
        "vida_util_txt": _blank_to_none(csv_row.get("vidaUtil")),
        "fecha_compra": parse_any_date(csv_row.get("fechadeCompra")),
        "fecha_operacion": parse_any_date(csv_row.get("fechadeOperacion")),
        "fecha_garantia": parse_any_date(csv_row.get("vencimientodeGarantia")),
        "fecha_baja": fecha_baja,
        "fecha_ultimo_pm": fecha_pm,
        "fecha_actualizacion": parse_any_date(csv_row.get("fechaactualizacion")),
        "codigo_activo": _blank_to_none(csv_row.get("codigodeActivo")),
        "codigo_ubicacion": _blank_to_none(csv_row.get("ubicacion")),
        "institucion_origen": _blank_to_none(csv_row.get("institucion")),
        "fuente_import": FUENTE_FOSCAGIB,
        "codigo_origen": _blank_to_none(csv_row.get("id")),
        "novedad_desc": novedad,
        "voltaje": _blank_to_none(csv_row.get("voltaje")),
        "corriente": _blank_to_none(csv_row.get("corriente")),
        "potencia": _blank_to_none(csv_row.get("potencia")),
        "peso": _blank_to_none(csv_row.get("peso")),
        "temperatura_trabajo": _blank_to_none(csv_row.get("temperaturadeTrabajo")),
        "presion": _blank_to_none(csv_row.get("presion")),
        "fuente_alimentacion": _blank_to_none(csv_row.get("fuenteAlimentacion")),
        "comercializador": _blank_to_none(csv_row.get("comercializadoroImportador")),
        "manual_operacion": as_tri_flag(csv_row.get("manualdeOperacion")),
        "manual_servicio": as_tri_flag(csv_row.get("manualdeServicio")),
        "componente1": _blank_to_none(csv_row.get("componente1")),
        "componente2": _blank_to_none(csv_row.get("componente2")),
        "componente3": _blank_to_none(csv_row.get("componente3")),
        "periodicidad_mp": _blank_to_none(csv_row.get("periodicidaddelMantenimiento")),
        "periodicidad_cal": _blank_to_none(csv_row.get("periodicidaddelaCalibracion")),
        "requiere_calibracion": req_cal,
        "_sede": sede_name,
        "_servicio": servicio_name,
        "_ficha": ficha_electrica(
            {
                "voltaje": csv_row.get("voltaje"),
                "corriente": csv_row.get("corriente"),
                "potencia": csv_row.get("potencia"),
                "peso": csv_row.get("peso"),
                "temperatura_trabajo": csv_row.get("temperaturadeTrabajo"),
                "presion": csv_row.get("presion"),
                "fuente_alimentacion": csv_row.get("fuenteAlimentacion"),
            }
        ),
    }
    bind = [values.get(col) for col in INVENTORY_INSERT_COLUMNS]
    return values, bind


def _insert_sql() -> str:
    cols = ", ".join(INVENTORY_INSERT_COLUMNS)
    placeholders = []
    for col in INVENTORY_INSERT_COLUMNS:
        if col == "creation_date":
            placeholders.append("COALESCE(?, datetime('now'))")
        else:
            placeholders.append("?")
    return (
        f"INSERT INTO inventario_equipos ({cols}) VALUES ({', '.join(placeholders)})"
    )


def _seed_pm_and_dim(conn, equipo_id: int, values: dict, anio: int):
    from server.frecuencia_pm_routes import _map_estado_inventario, _rebuild_equipo

    servicio_id = values["servicio_id"]
    codigo = values["num_biomedica"] or f"EQ-{equipo_id}"
    estado_pm = _map_estado_inventario(values["estado"])
    if values.get("fecha_baja"):
        estado_pm = "Retirado"
    meses = freq_anual_to_meses(values["freq_mp"]) if values.get("aplica_mp") == 1 else None
    funcion = map_funcion_oms(values.get("clasificacion_biomedica"))
    aplicacion = map_aplicacion_oms(values.get("_servicio"))
    requisito = map_requisito_oms(values.get("clasificacion_riesgo"))
    fallas = map_fallas_oms(values.get("novedad_desc"))
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
            equipo_id,
            codigo,
            values["equipo"],
            values.get("marca"),
            values.get("modelo"),
            values.get("serie"),
            estado_pm,
            meses,
            funcion,
            aplicacion,
            requisito,
            fallas,
            values.get("fecha_ultimo_pm"),
        ),
    )
    pm_id = cur.lastrowid
    pm_row = conn.execute("SELECT * FROM pm_inventario WHERE id = ?", (pm_id,)).fetchone()
    _rebuild_equipo(conn, dict(pm_row), anio)

    conn.execute(
        """
        INSERT OR IGNORE INTO dim_actividad_equipo (
            inventario_equipo_id, criticidad,
            aplica_mp, freq_mp, tiempo_mp,
            aplica_cal, freq_cal, tiempo_cal,
            aplica_val, freq_val, tiempo_val,
            observaciones, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, datetime('now'))
        """,
        (
            equipo_id,
            map_criticidad_dim(
                values.get("clasificacion_riesgo"),
                values.get("clasificacion_biomedica"),
            ),
            values.get("aplica_mp") or 0,
            values.get("freq_mp") or 0,
            values.get("tiempo_mp") or 0,
            values.get("aplica_cal") or 0,
            values.get("freq_cal") or 0,
            values.get("tiempo_cal") or 0,
            values.get("novedad_desc") or values.get("_ficha") or None,
        ),
    )


def seed_foscagib_if_needed(emp_conn) -> dict:
    """Crea el árbol orgánico FOSCAGIB e importa el CSV. Idempotente."""
    already = emp_conn.execute(
        """
        SELECT COUNT(*) AS n FROM inventario_equipos
        WHERE fuente_import = ?
        """,
        (FUENTE_FOSCAGIB,),
    ).fetchone()["n"]
    if already >= 4000:
        return {"skipped": True, "equipos": already}

    csv_path = resolve_csv_path()
    if not csv_path:
        print("[foscagib] CSV no encontrado; se omite la carga institucional.")
        return {"skipped": True, "reason": "csv_missing"}

    existing_origen = {
        r["codigo_origen"]
        for r in emp_conn.execute(
            """
            SELECT codigo_origen FROM inventario_equipos
            WHERE fuente_import = ? AND codigo_origen IS NOT NULL
            """,
            (FUENTE_FOSCAGIB,),
        ).fetchall()
    }

    empresa_ids = {key: _ensure_empresa(emp_conn, key) for key in EMPRESAS_FOSCAGIB}
    insert_sql = _insert_sql()
    from datetime import date as date_cls

    anio = date_cls.today().year
    inserted = 0
    skipped = 0
    servicio_ids: set[int] = set()

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for csv_row in reader:
            equipo = sanitize_string(csv_row.get("equipo"))
            if not equipo:
                skipped += 1
                continue
            emp_key, sede_name, servicio_name, codigo_srv = resolve_servicio_destino(
                codigo=csv_row.get("ubicacion"),
                institucion=csv_row.get("institucion"),
                ubicacionnombre=csv_row.get("ubicacionnombre"),
            )
            empresa_id = empresa_ids[emp_key]
            sede_id = ensure_sede(emp_conn, empresa_id, sede_name)
            servicio_id = ensure_servicio_with_id(
                emp_conn, sede_id, servicio_name, codigo_srv
            )
            servicio_ids.add(servicio_id)
            values, bind = _row_to_inventory(csv_row, servicio_id, sede_name, servicio_name)
            origen = values.get("codigo_origen")
            if origen and origen in existing_origen:
                continue
            cur = emp_conn.execute(insert_sql, bind)
            equipo_id = cur.lastrowid
            _seed_pm_and_dim(emp_conn, equipo_id, values, anio)
            if origen:
                existing_origen.add(origen)
            inserted += 1
            if inserted % 400 == 0:
                emp_conn.commit()

    emp_conn.commit()
    sedes_n = emp_conn.execute(
        """
        SELECT COUNT(*) AS n FROM sedes
        WHERE empresa_id IN ({})
        """.format(",".join("?" * len(empresa_ids))),
        list(empresa_ids.values()),
    ).fetchone()["n"]
    servicios_n = emp_conn.execute(
        """
        SELECT COUNT(*) AS n FROM servicios srv
        JOIN sedes s ON s.id = srv.sede_id
        WHERE s.empresa_id IN ({})
        """.format(",".join("?" * len(empresa_ids))),
        list(empresa_ids.values()),
    ).fetchone()["n"]
    summary = {
        "skipped": False,
        "empresas": len(empresa_ids),
        "sedes": sedes_n,
        "servicios": servicios_n,
        "equipos": inserted,
        "filas_sin_equipo": skipped,
        "csv": str(csv_path),
    }
    print(
        f"[foscagib] carga lista: empresas={summary['empresas']} "
        f"sedes={summary['sedes']} servicios={summary['servicios']} "
        f"equipos={summary['equipos']}"
    )
    return summary


def _novedad_describe_mp(desc: str | None) -> bool:
    from server.inventory_enrichment import fold_text
    import re

    folded = fold_text(desc)
    if not folded:
        return False
    return bool(re.search(r"\bMP\b", folded) or "MANTENIMIENTO PREVENTIVO" in folded)


def repair_instrument_coherence(emp_conn) -> dict:
    """Ajusta fechas PM, bajas y cronogramas para que coincidan con cada módulo."""
    from datetime import date as date_cls

    from server.frecuencia_pm_routes import _rebuild_servicio
    from server.inventory_enrichment import FUENTE_FOSCAGIB

    tables = {
        r["name"]
        for r in emp_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "inventario_equipos" not in tables or "pm_inventario" not in tables:
        return {"skipped": True, "reason": "schema"}

    emp_conn.execute(
        """
        DELETE FROM pm_inventario
        WHERE inventario_equipo_id IS NOT NULL
          AND inventario_equipo_id NOT IN (SELECT id FROM inventario_equipos)
        """
    )

    emp_conn.execute(
        """
        UPDATE inventario_equipos
        SET aplica_mp = 0, freq_mp = NULL, tiempo_mp = NULL
        WHERE fecha_baja IS NOT NULL AND TRIM(fecha_baja) != ''
        """
    )

    rows = emp_conn.execute(
        """
        SELECT id, novedad_desc, fecha_ultimo_pm
        FROM inventario_equipos
        WHERE fuente_import = ?
        """,
        (FUENTE_FOSCAGIB,),
    ).fetchall()
    cleared = 0
    kept = 0
    for row in rows:
        if _novedad_describe_mp(row["novedad_desc"]):
            kept += 1
            continue
        if row["fecha_ultimo_pm"]:
            emp_conn.execute(
                "UPDATE inventario_equipos SET fecha_ultimo_pm = NULL WHERE id = ?",
                (row["id"],),
            )
            cleared += 1

    emp_conn.execute(
        """
        UPDATE pm_inventario
        SET fecha_ultimo_pm = (
            SELECT ie.fecha_ultimo_pm
            FROM inventario_equipos ie
            WHERE ie.id = pm_inventario.inventario_equipo_id
        )
        WHERE inventario_equipo_id IS NOT NULL
        """
    )

    servicio_ids = [
        r["servicio_id"]
        for r in emp_conn.execute(
            """
            SELECT DISTINCT servicio_id
            FROM inventario_equipos
            WHERE fuente_import = ?
            """,
            (FUENTE_FOSCAGIB,),
        ).fetchall()
    ]
    anio = date_cls.today().year
    rebuilt = 0
    for sid in servicio_ids:
        rebuilt += _rebuild_servicio(emp_conn, sid, anio)
    emp_conn.commit()
    summary = {
        "fechas_pm_retiradas": cleared,
        "fechas_pm_conservadas": kept,
        "servicios_recalculados": len(servicio_ids),
        "pm_rebuilt": rebuilt,
    }
    print(
        f"[coherencia] PM fechas retiradas={cleared} conservadas={kept} "
        f"servicios={len(servicio_ids)}"
    )
    return summary

