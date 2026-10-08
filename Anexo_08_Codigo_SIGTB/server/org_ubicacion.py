"""Catálogo de códigos de ubicación institucionales y reorganización de ID_servicio."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from server.inventory_enrichment import (
    CAMPUS_PRINCIPAL,
    EMPRESAS_FOSCAGIB,
    FUENTE_FOSCAGIB,
    SIN_UBICACION,
    fold_text,
    map_empresa_key,
    safe_org_name,
    split_sede_servicio,
)
from server.sede_ids import (
    looks_like_autogen_id,
    next_id_sede,
    next_id_servicio,
    normalize_external_id,
    prefix_for_id,
)

SANTA_CRUZ_NIT = EMPRESAS_FOSCAGIB["santa_cruz"]["nit"]
SANTA_CRUZ_NOMBRE = EMPRESAS_FOSCAGIB["santa_cruz"]["nombre"]
SANTA_CRUZ_NIT_PREVIO = "900890203-1"
SEDE_SANTA_CRUZ = "Santa Cruz"
SEDE_SAN_GIL_PLAZA = "San Gil Plaza"


@dataclass(frozen=True)
class ServicioCatalogo:
    codigo: str
    sede_name: str
    name_servicio: str
    empresa_key: str = "santa_cruz"


# 3001 es Cirugía General. El 3001 duplicado como Odontología en el listado
# institucional corresponde a 3011 (secuencia 3010 → 3012).
CATALOGO_SANTA_CRUZ: dict[str, ServicioCatalogo] = {
    "3000": ServicioCatalogo("3000", SEDE_SANTA_CRUZ, "Urgencias"),
    "3001": ServicioCatalogo("3001", SEDE_SANTA_CRUZ, "Cirugía General"),
    "3002": ServicioCatalogo("3002", SEDE_SANTA_CRUZ, "Unidad de Esterilización"),
    "3003": ServicioCatalogo("3003", SEDE_SANTA_CRUZ, "SHEC"),
    "3004": ServicioCatalogo("3004", SEDE_SANTA_CRUZ, "Almacen General"),
    "3006": ServicioCatalogo("3006", SEDE_SANTA_CRUZ, "Consulta Externa"),
    "3007": ServicioCatalogo("3007", SEDE_SANTA_CRUZ, "Farmacia General"),
    "3008": ServicioCatalogo("3008", SEDE_SANTA_CRUZ, "Hospitalización"),
    "3009": ServicioCatalogo("3009", SEDE_SANTA_CRUZ, "Imágenes Diagnosticas"),
    "3010": ServicioCatalogo("3010", SEDE_SANTA_CRUZ, "Laboratorio Clínico"),
    "3011": ServicioCatalogo("3011", SEDE_SANTA_CRUZ, "Odontología"),
    "3012": ServicioCatalogo("3012", SEDE_SANTA_CRUZ, "PyP"),
    "3013": ServicioCatalogo("3013", SEDE_SANTA_CRUZ, "Unidad de Gestión Ambiental"),
    "3014": ServicioCatalogo("3014", SEDE_SANTA_CRUZ, "Farmacia Hospitalaria"),
    "3669": ServicioCatalogo("3669", SEDE_SANTA_CRUZ, "UCI"),
    "3999": ServicioCatalogo("3999", SEDE_SANTA_CRUZ, "Bodega de Bajas Santa Cruz"),
    "3015": ServicioCatalogo("3015", SEDE_SAN_GIL_PLAZA, "San Gil Plaza Odontología"),
    "3016": ServicioCatalogo("3016", SEDE_SAN_GIL_PLAZA, "San Gil Plaza - Vacunación"),
    "3017": ServicioCatalogo("3017", SEDE_SAN_GIL_PLAZA, "San Gil Plaza Consulta Externa"),
}

CATCHALL_CODES = {
    "199999": "Bodega de bajas",
    "299999": "Bodega de bajas",
    "499999": "Bodega de bajas",
}


def normalize_ubicacion_code(value) -> str | None:
    return normalize_external_id(value)


def resolve_catalog_code(
    codigo: str | None,
    *,
    institucion: str | None = None,
    ubicacionnombre: str | None = None,
    id_nit: str | None = None,
) -> str | None:
    """Devuelve el código canónico (p. ej. 399999 de Santa Cruz → 3999)."""
    code = normalize_ubicacion_code(codigo)
    if not code:
        return None
    if code in CATALOGO_SANTA_CRUZ:
        return code
    if code != "399999":
        return code
    folded = fold_text(ubicacionnombre)
    if "AVANZAR" in folded or "SOTOMAYOR" in folded:
        return code
    nit = str(id_nit or "").upper()
    emp_key = map_empresa_key(institucion) if institucion else None
    if nit in {
        EMPRESAS_FOSCAGIB["santa_cruz"]["nit"].upper(),
        EMPRESAS_FOSCAGIB["foscagib"]["nit"].upper(),
    } or emp_key in {"santa_cruz", "foscagib"}:
        return "3999"
    return code


def resolve_servicio_destino(
    *,
    codigo,
    institucion: str | None = None,
    ubicacionnombre: str | None = None,
) -> tuple[str, str, str, str | None]:
    """(empresa_key, sede_name, servicio_name, ID_servicio o None)."""
    raw_code = normalize_ubicacion_code(codigo)
    code = resolve_catalog_code(
        raw_code, institucion=institucion, ubicacionnombre=ubicacionnombre
    )
    if code and code in CATALOGO_SANTA_CRUZ:
        item = CATALOGO_SANTA_CRUZ[code]
        return item.empresa_key, item.sede_name, item.name_servicio, item.codigo

    emp_key = map_empresa_key(institucion)
    sede_name, servicio_name = split_sede_servicio(ubicacionnombre)
    if code and code in CATCHALL_CODES:
        return emp_key, sede_name, CATCHALL_CODES[code], code
    return emp_key, sede_name, servicio_name, code


def relabel_santa_cruz(conn) -> None:
    """Pasa el NIT de carga al de la clínica que usa el acta UAT, sin duplicar la empresa."""
    if SANTA_CRUZ_NIT_PREVIO.casefold() == SANTA_CRUZ_NIT.casefold():
        return
    actual = conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (SANTA_CRUZ_NIT,),
    ).fetchone()
    previo = conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (SANTA_CRUZ_NIT_PREVIO,),
    ).fetchone()
    if previo and not actual:
        conn.execute(
            "UPDATE empresas SET ID_Empresa = ?, ID_NIT = ? WHERE id = ?",
            (SANTA_CRUZ_NOMBRE, SANTA_CRUZ_NIT, previo["id"]),
        )
    elif actual:
        conn.execute(
            "UPDATE empresas SET ID_Empresa = ? WHERE id = ? AND ID_Empresa != ?",
            (SANTA_CRUZ_NOMBRE, actual["id"], SANTA_CRUZ_NOMBRE),
        )


def ensure_empresa_by_key(conn, key: str) -> int:
    if key == "santa_cruz":
        relabel_santa_cruz(conn)
    meta = EMPRESAS_FOSCAGIB[key]
    nombre = SANTA_CRUZ_NOMBRE if key == "santa_cruz" else meta["nombre"]
    row = conn.execute(
        "SELECT id, ID_Empresa FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (meta["nit"],),
    ).fetchone()
    if row:
        if str(row["ID_Empresa"] or "") != nombre:
            conn.execute(
                "UPDATE empresas SET ID_Empresa = ? WHERE id = ?",
                (nombre, row["id"]),
            )
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO empresas (ID_Empresa, ID_NIT, creation_date)
        VALUES (?, ?, datetime('now'))
        """,
        (nombre, meta["nit"]),
    )
    return int(cur.lastrowid)


def ensure_sede(conn, empresa_id: int, name_sede: str, *, rename_from: str | None = None) -> int:
    name = safe_org_name(name_sede, CAMPUS_PRINCIPAL)
    row = conn.execute(
        """
        SELECT id FROM sedes
        WHERE empresa_id = ? AND name_sede = ? COLLATE NOCASE
        """,
        (empresa_id, name),
    ).fetchone()
    if row:
        return int(row["id"])
    if rename_from:
        old = conn.execute(
            """
            SELECT id FROM sedes
            WHERE empresa_id = ? AND name_sede = ? COLLATE NOCASE
            """,
            (empresa_id, rename_from),
        ).fetchone()
        if old:
            conn.execute(
                "UPDATE sedes SET name_sede = ? WHERE id = ?",
                (name, old["id"]),
            )
            return int(old["id"])
    id_sede, prefix = next_id_sede(conn, name, empresa_id)
    cur = conn.execute(
        """
        INSERT INTO sedes (ID_sede, name_sede, prefix, empresa_id, creation_date)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (id_sede, name, prefix, empresa_id),
    )
    return int(cur.lastrowid)


def ensure_servicio_with_id(conn, sede_id: int, name_servicio: str, external_id: str | None = None) -> int:
    """Reutiliza el servicio si ya tiene identificador; autogenera solo si falta."""
    name = safe_org_name(name_servicio, SIN_UBICACION)
    ext = normalize_ubicacion_code(external_id)

    if ext:
        by_id = conn.execute(
            """
            SELECT id, name_servicio FROM servicios
            WHERE sede_id = ? AND ID_servicio = ? COLLATE NOCASE
            """,
            (sede_id, ext),
        ).fetchone()
        if by_id:
            if str(by_id["name_servicio"] or "") != name:
                taken = conn.execute(
                    """
                    SELECT id FROM servicios
                    WHERE sede_id = ? AND name_servicio = ? COLLATE NOCASE AND id != ?
                    """,
                    (sede_id, name, by_id["id"]),
                ).fetchone()
                if not taken:
                    conn.execute(
                        """
                        UPDATE servicios SET name_servicio = ?, prefix = ?
                        WHERE id = ?
                        """,
                        (name, prefix_for_id(name, ext), by_id["id"]),
                    )
            return int(by_id["id"])

    by_name = conn.execute(
        """
        SELECT id, ID_servicio FROM servicios
        WHERE sede_id = ? AND name_servicio = ? COLLATE NOCASE
        """,
        (sede_id, name),
    ).fetchone()
    if by_name:
        current = str(by_name["ID_servicio"] or "")
        if not ext or current.upper() == ext.upper():
            return int(by_name["id"])
        if looks_like_autogen_id(current):
            other = conn.execute(
                """
                SELECT id FROM servicios
                WHERE sede_id = ? AND ID_servicio = ? COLLATE NOCASE AND id != ?
                """,
                (sede_id, ext, by_name["id"]),
            ).fetchone()
            if other:
                return int(other["id"])
            conn.execute(
                """
                UPDATE servicios SET ID_servicio = ?, prefix = ?
                WHERE id = ?
                """,
                (ext, prefix_for_id(name, ext), by_name["id"]),
            )
            return int(by_name["id"])
        name = safe_org_name(f"{name} {ext}", f"{SIN_UBICACION} {ext}")
        existing_disc = conn.execute(
            """
            SELECT id FROM servicios
            WHERE sede_id = ? AND name_servicio = ? COLLATE NOCASE
            """,
            (sede_id, name),
        ).fetchone()
        if existing_disc:
            return int(existing_disc["id"])

    id_srv, prefix = next_id_servicio(conn, name, sede_id, external_id=ext)
    cur = conn.execute(
        """
        INSERT INTO servicios (ID_servicio, name_servicio, prefix, sede_id, creation_date)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (id_srv, name, prefix, sede_id),
    )
    return int(cur.lastrowid)


def _table_names(conn) -> set[str]:
    return {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _chunked(items: list[int], size: int = 400):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _move_equipos(conn, equipo_ids: list[int], dest_servicio_id: int):
    if not equipo_ids:
        return
    tables = _table_names(conn)
    for chunk in _chunked(equipo_ids):
        placeholders = ",".join("?" * len(chunk))
        conn.execute(
            f"UPDATE inventario_equipos SET servicio_id = ? WHERE id IN ({placeholders})",
            [dest_servicio_id, *chunk],
        )
        if "pm_inventario" in tables:
            conn.execute(
                f"""
                UPDATE pm_inventario SET servicio_id = ?
                WHERE inventario_equipo_id IN ({placeholders})
                """,
                [dest_servicio_id, *chunk],
            )
        if "pre_evaluaciones" in tables:
            dest = conn.execute(
                "SELECT ID_servicio, name_servicio, sede_id FROM servicios WHERE id = ?",
                (dest_servicio_id,),
            ).fetchone()
            conn.execute(
                f"""
                UPDATE pre_evaluaciones
                SET servicio_id = ?, ID_servicio = ?, servicio_area = ?, sede_id = ?
                WHERE inventario_equipo_id IN ({placeholders})
                """,
                [
                    dest_servicio_id,
                    dest["ID_servicio"] if dest else None,
                    dest["name_servicio"] if dest else None,
                    dest["sede_id"] if dest else None,
                    *chunk,
                ],
            )


def needs_ubicacion_id_reorg(conn) -> bool:
    tables = _table_names(conn)
    if "inventario_equipos" not in tables or "servicios" not in tables:
        return False
    empresa = conn.execute(
        "SELECT ID_Empresa FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (SANTA_CRUZ_NIT,),
    ).fetchone()
    if empresa and fold_text(empresa["ID_Empresa"]) != fold_text(SANTA_CRUZ_NOMBRE):
        return True
    n = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        WHERE ie.fuente_import = ?
          AND ie.codigo_ubicacion IS NOT NULL
          AND TRIM(ie.codigo_ubicacion) != ''
          AND srv.ID_servicio GLOB '[A-Z]*'
        """,
        (FUENTE_FOSCAGIB,),
    ).fetchone()["n"]
    return int(n) > 0


def _majority_name(counter: Counter, fallback: str) -> str:
    useful = Counter(
        {
            name: n
            for name, n in counter.items()
            if name and fold_text(name) != fold_text(SIN_UBICACION)
        }
    )
    if useful:
        return useful.most_common(1)[0][0]
    if counter:
        return counter.most_common(1)[0][0]
    return fallback


def reorganize_ubicacion_ids(conn) -> dict:
    """Asigna ID_servicio = código de ubicación y reubica Santa Cruz / San Gil Plaza."""
    tables = _table_names(conn)
    if "inventario_equipos" not in tables:
        return {"skipped": True, "reason": "schema"}

    try:
        empresa_ids = {key: ensure_empresa_by_key(conn, key) for key in EMPRESAS_FOSCAGIB}
        santa_id = empresa_ids["santa_cruz"]
        sede_santa = ensure_sede(
            conn, santa_id, SEDE_SANTA_CRUZ, rename_from=CAMPUS_PRINCIPAL
        )
        sede_plaza = ensure_sede(conn, santa_id, SEDE_SAN_GIL_PLAZA)

        catalog_servicios: dict[str, int] = {}
        for item in CATALOGO_SANTA_CRUZ.values():
            sede_id = sede_plaza if item.sede_name == SEDE_SAN_GIL_PLAZA else sede_santa
            catalog_servicios[item.codigo] = ensure_servicio_with_id(
                conn, sede_id, item.name_servicio, item.codigo
            )

        rows = conn.execute(
            """
            SELECT ie.id AS equipo_id, ie.codigo_ubicacion, ie.ubicacion, ie.institucion_origen,
                   srv.id AS servicio_id, srv.ID_servicio, srv.name_servicio,
                   s.id AS sede_id, s.name_sede, s.empresa_id, e.ID_NIT
            FROM inventario_equipos ie
            JOIN servicios srv ON srv.id = ie.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            JOIN empresas e ON e.id = s.empresa_id
            WHERE ie.fuente_import = ?
            """,
            (FUENTE_FOSCAGIB,),
        ).fetchall()

        groups: dict[tuple[int, int, str], list[int]] = defaultdict(list)
        group_names: dict[tuple[int, int, str], Counter] = defaultdict(Counter)
        catalog_moves: dict[int, list[int]] = defaultdict(list)
        moved = 0

        for row in rows:
            code = resolve_catalog_code(
                row["codigo_ubicacion"],
                institucion=row["institucion_origen"],
                ubicacionnombre=row["ubicacion"],
                id_nit=row["ID_NIT"],
            )
            if code and code in catalog_servicios:
                dest_id = catalog_servicios[code]
                if int(row["servicio_id"]) != dest_id:
                    catalog_moves[dest_id].append(int(row["equipo_id"]))
                continue
            if not code:
                continue
            key = (int(row["empresa_id"]), int(row["sede_id"]), code)
            groups[key].append(int(row["equipo_id"]))
            group_names[key][row["name_servicio"]] += 1

        for dest_id, equipo_ids in catalog_moves.items():
            _move_equipos(conn, equipo_ids, dest_id)
            moved += len(equipo_ids)

        created_or_reused = 0
        for (empresa_id, sede_id, code), equipo_ids in sorted(
            groups.items(), key=lambda item: len(item[1]), reverse=True
        ):
            if code in CATCHALL_CODES:
                dest_name = CATCHALL_CODES[code]
            else:
                dest_name = _majority_name(
                    group_names[(empresa_id, sede_id, code)], SIN_UBICACION
                )
            dest_id = ensure_servicio_with_id(conn, sede_id, dest_name, code)
            created_or_reused += 1
            _move_equipos(conn, equipo_ids, dest_id)
            moved += len(equipo_ids)

        deleted_servicios = _delete_empty_foscagib_servicios(conn, empresa_ids)
        deleted_sedes = _delete_empty_foscagib_sedes(conn, empresa_ids)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    summary = {
        "skipped": False,
        "empresa": SANTA_CRUZ_NOMBRE,
        "catalogo_servicios": len(catalog_servicios),
        "grupos_codigo": created_or_reused,
        "equipos_movidos": moved,
        "servicios_vacios_eliminados": deleted_servicios,
        "sedes_vacias_eliminadas": deleted_sedes,
    }
    print(
        f"[ubicacion-ids] {SANTA_CRUZ_NOMBRE}: "
        f"movidos={moved} grupos={created_or_reused} "
        f"servicios_vacíos={deleted_servicios}"
    )
    return summary


def _delete_empty_foscagib_servicios(conn, empresa_ids: dict[str, int]) -> int:
    keep_ids = {item.codigo for item in CATALOGO_SANTA_CRUZ.values()}
    placeholders = ",".join("?" * len(empresa_ids))
    rows = conn.execute(
        f"""
        SELECT srv.id, srv.ID_servicio
        FROM servicios srv
        JOIN sedes s ON s.id = srv.sede_id
        WHERE s.empresa_id IN ({placeholders})
          AND NOT EXISTS (
            SELECT 1 FROM inventario_equipos ie WHERE ie.servicio_id = srv.id
          )
        """,
        list(empresa_ids.values()),
    ).fetchall()
    deleted = 0
    for row in rows:
        code = str(row["ID_servicio"] or "")
        if code in keep_ids:
            continue
        conn.execute("DELETE FROM servicios WHERE id = ?", (row["id"],))
        deleted += 1
    return deleted


def _delete_empty_foscagib_sedes(conn, empresa_ids: dict[str, int]) -> int:
    keep_names = {fold_text(SEDE_SANTA_CRUZ), fold_text(SEDE_SAN_GIL_PLAZA)}
    placeholders = ",".join("?" * len(empresa_ids))
    rows = conn.execute(
        f"""
        SELECT s.id, s.name_sede
        FROM sedes s
        WHERE s.empresa_id IN ({placeholders})
          AND NOT EXISTS (
            SELECT 1 FROM servicios srv WHERE srv.sede_id = s.id
          )
        """,
        list(empresa_ids.values()),
    ).fetchall()
    deleted = 0
    for row in rows:
        if fold_text(row["name_sede"]) in keep_names:
            continue
        conn.execute("DELETE FROM sedes WHERE id = ?", (row["id"],))
        deleted += 1
    return deleted


def sync_catalog_nombres(conn) -> int:
    """Ajusta mayúsculas del catálogo Santa Cruz sin tocar IDs."""
    empresa = conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (SANTA_CRUZ_NIT,),
    ).fetchone()
    if not empresa:
        return 0
    updated = 0
    for item in CATALOGO_SANTA_CRUZ.values():
        cur = conn.execute(
            """
            UPDATE servicios
            SET name_servicio = ?, prefix = ?
            WHERE ID_servicio = ? COLLATE NOCASE
              AND sede_id IN (SELECT id FROM sedes WHERE empresa_id = ?)
              AND name_servicio != ?
            """,
            (
                item.name_servicio,
                prefix_for_id(item.name_servicio, item.codigo),
                item.codigo,
                empresa["id"],
                item.name_servicio,
            ),
        )
        updated += cur.rowcount or 0
    if updated:
        conn.commit()
    return updated


def reorganize_ubicacion_ids_if_needed(conn) -> dict:
    result = {"skipped": True}
    if needs_ubicacion_id_reorg(conn):
        result = reorganize_ubicacion_ids(conn)
    result["nombres_catalogo"] = sync_catalog_nombres(conn)
    return result
