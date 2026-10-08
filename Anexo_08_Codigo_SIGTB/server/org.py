"""Helpers de organización Empresa → Sede → Servicio."""

from server.db import get_empresas_connection
from server.sede_ids import (
    is_letters_only_name,
    next_id_sede,
    next_id_servicio,
    normalize_text_name,
    parse_servicio_spec,
    SERVICIO_ORDER_SQL,
)


def find_or_create_empresa(emp_conn, id_empresa, id_nit):
    """
    Localiza empresa por NIT o la crea.
    Retorna (empresa_id, created).
    """
    existing = emp_conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        (id_nit,),
    ).fetchone()
    if existing:
        return int(existing["id"]), False
    cur = emp_conn.execute(
        """
        INSERT INTO empresas (ID_Empresa, ID_NIT, creation_date)
        VALUES (?, ?, datetime('now'))
        """,
        (id_empresa, id_nit),
    )
    return int(cur.lastrowid), True


def empresa_payload(row):
    return {
        "id": row["id"],
        "ID_Empresa": row["ID_Empresa"],
        "ID_NIT": row["ID_NIT"],
        "creation_date": row["creation_date"],
    }


def sede_payload(row):
    return {
        "id": row["id"],
        "ID_sede": row["ID_sede"],
        "name_sede": row["name_sede"],
        "prefix": row["prefix"],
        "empresa_id": row["empresa_id"],
        "ID_Empresa": row["ID_Empresa"] if "ID_Empresa" in row.keys() else None,
        "ID_NIT": row["ID_NIT"] if "ID_NIT" in row.keys() else None,
        "creation_date": row["creation_date"],
    }


def servicio_payload(row):
    return {
        "id": row["id"],
        "ID_servicio": row["ID_servicio"],
        "name_servicio": row["name_servicio"],
        "prefix": row["prefix"],
        "sede_id": row["sede_id"],
        "ID_sede": row["ID_sede"] if "ID_sede" in row.keys() else None,
        "name_sede": row["name_sede"] if "name_sede" in row.keys() else None,
        "empresa_id": row["empresa_id"] if "empresa_id" in row.keys() else None,
        "ID_Empresa": row["ID_Empresa"] if "ID_Empresa" in row.keys() else None,
        "creation_date": row["creation_date"],
    }


def create_sede_with_servicios(
    emp_conn, empresa_id, name_sede, servicios_names, ID_sede=None
):
    name_sede = normalize_text_name(name_sede)
    if not is_letters_only_name(name_sede):
        raise ValueError(
            "name_sede admite letras, números, espacios y separadores (. - _ /)."
        )

    dup = emp_conn.execute(
        """
        SELECT id FROM sedes
        WHERE empresa_id = ? AND name_sede = ? COLLATE NOCASE
        """,
        (empresa_id, name_sede),
    ).fetchone()
    if dup:
        raise ValueError(f"La sede '{name_sede}' ya existe en esta empresa.")

    id_sede, prefix = next_id_sede(emp_conn, name_sede, empresa_id, external_id=ID_sede)
    if ID_sede:
        taken = emp_conn.execute(
            """
            SELECT id FROM sedes
            WHERE empresa_id = ? AND ID_sede = ? COLLATE NOCASE
            """,
            (empresa_id, id_sede),
        ).fetchone()
        if taken:
            raise ValueError(f"El ID_sede '{id_sede}' ya existe en esta empresa.")

    cur = emp_conn.execute(
        """
        INSERT INTO sedes (ID_sede, name_sede, prefix, empresa_id, creation_date)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (id_sede, name_sede, prefix, empresa_id),
    )
    sede_id = cur.lastrowid
    servicios = []
    seen_ids = set()
    for raw in servicios_names or []:
        ext_id, name_servicio = parse_servicio_spec(raw)
        name_servicio = normalize_text_name(name_servicio)
        if not name_servicio:
            continue
        if not is_letters_only_name(name_servicio):
            raise ValueError(
                f"Servicio '{name_servicio}' admite letras, números, espacios y separadores (. - _ /)."
            )
        id_srv, srv_prefix = next_id_servicio(
            emp_conn, name_servicio, sede_id, external_id=ext_id
        )
        if id_srv in seen_ids:
            raise ValueError(f"ID_servicio duplicado en la sede: {id_srv}.")
        seen_ids.add(id_srv)
        taken = emp_conn.execute(
            """
            SELECT id FROM servicios
            WHERE sede_id = ? AND ID_servicio = ? COLLATE NOCASE
            """,
            (sede_id, id_srv),
        ).fetchone()
        if taken:
            raise ValueError(f"El ID_servicio '{id_srv}' ya existe en esta sede.")
        srv_cur = emp_conn.execute(
            """
            INSERT INTO servicios (ID_servicio, name_servicio, prefix, sede_id, creation_date)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (id_srv, name_servicio, srv_prefix, sede_id),
        )
        servicios.append(
            {
                "id": srv_cur.lastrowid,
                "ID_servicio": id_srv,
                "name_servicio": name_servicio,
            }
        )

    return {
        "id": sede_id,
        "ID_sede": id_sede,
        "name_sede": name_sede,
        "servicios": servicios,
    }


def fetch_empresa_tree(emp_conn, empresa_id=None):
    if empresa_id is None:
        empresas = emp_conn.execute(
            "SELECT * FROM empresas ORDER BY ID_Empresa COLLATE NOCASE"
        ).fetchall()
    else:
        empresas = emp_conn.execute(
            "SELECT * FROM empresas WHERE id = ?",
            (empresa_id,),
        ).fetchall()

    tree = []
    for empresa in empresas:
        sedes_rows = emp_conn.execute(
            """
            SELECT * FROM sedes
            WHERE empresa_id = ?
            ORDER BY name_sede COLLATE NOCASE
            """,
            (empresa["id"],),
        ).fetchall()
        sedes = []
        for sede in sedes_rows:
            servicios = emp_conn.execute(
                f"""
                SELECT * FROM servicios
                WHERE sede_id = ?
                ORDER BY {SERVICIO_ORDER_SQL}
                """,
                (sede["id"],),
            ).fetchall()
            sedes.append(
                {
                    **sede_payload({**dict(sede), "ID_Empresa": empresa["ID_Empresa"], "ID_NIT": empresa["ID_NIT"]}),
                    "servicios": [servicio_payload(dict(s)) for s in servicios],
                }
            )
        tree.append({**empresa_payload(empresa), "sedes": sedes})
    return tree


def _cleanup_id_counters(emp_conn, *, empresa_id=None, sede_id=None):
    tables = {
        r["name"]
        for r in emp_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "id_counters" not in tables:
        return
    if sede_id is not None:
        emp_conn.execute(
            "DELETE FROM id_counters WHERE scope_type = 'servicio' AND scope_key = ?",
            (str(sede_id),),
        )
    if empresa_id is not None:
        emp_conn.execute(
            "DELETE FROM id_counters WHERE scope_type = 'sede' AND scope_key = ?",
            (str(empresa_id),),
        )


def delete_sede_with_inventory(emp_conn, users_conn, sede_id: int) -> dict:
    """Elimina la sede, sus servicios e inventario. Quita asignaciones de personal."""
    sede = emp_conn.execute(
        """
        SELECT s.id, s.ID_sede, s.name_sede, s.empresa_id, e.ID_Empresa
        FROM sedes s
        JOIN empresas e ON e.id = s.empresa_id
        WHERE s.id = ?
        """,
        (sede_id,),
    ).fetchone()
    if not sede:
        raise ValueError("La sede no existe.")

    n_servicios = emp_conn.execute(
        "SELECT COUNT(*) AS n FROM servicios WHERE sede_id = ?",
        (sede_id,),
    ).fetchone()["n"]
    servicios_detalle = [
        f"{r['name_servicio']} ({r['ID_servicio']})"
        for r in emp_conn.execute(
            "SELECT name_servicio, ID_servicio FROM servicios WHERE sede_id = ?",
            (sede_id,),
        ).fetchall()
    ]
    n_equipos = emp_conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        WHERE srv.sede_id = ?
        """,
        (sede_id,),
    ).fetchone()["n"]

    users_conn.execute("DELETE FROM usuario_sedes WHERE sede_id = ?", (sede_id,))
    _cleanup_id_counters(emp_conn, sede_id=sede_id)
    emp_conn.execute("DELETE FROM sedes WHERE id = ?", (sede_id,))

    return {
        "id": sede_id,
        "ID_sede": sede["ID_sede"],
        "name_sede": sede["name_sede"],
        "empresa_id": sede["empresa_id"],
        "ID_Empresa": sede["ID_Empresa"],
        "servicios": int(n_servicios),
        "servicios_detalle": servicios_detalle,
        "equipos": int(n_equipos),
    }


def delete_empresa_with_inventory(emp_conn, users_conn, empresa_id: int) -> dict:
    """Elimina la empresa, sedes, servicios e inventario. Desvincula personal."""
    empresa = emp_conn.execute(
        "SELECT id, ID_Empresa, ID_NIT FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()
    if not empresa:
        raise ValueError("La empresa no existe.")

    sede_ids = [
        int(r["id"])
        for r in emp_conn.execute(
            "SELECT id FROM sedes WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchall()
    ]
    n_sedes = len(sede_ids)
    sedes_detalle = [
        f"{r['name_sede']} ({r['ID_sede']})"
        for r in emp_conn.execute(
            "SELECT name_sede, ID_sede FROM sedes WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchall()
    ]
    n_equipos = emp_conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM inventario_equipos ie
        JOIN servicios srv ON srv.id = ie.servicio_id
        JOIN sedes s ON s.id = srv.sede_id
        WHERE s.empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()["n"]

    if sede_ids:
        placeholders = ",".join("?" * len(sede_ids))
        users_conn.execute(
            f"DELETE FROM usuario_sedes WHERE sede_id IN ({placeholders})",
            sede_ids,
        )
        for sid in sede_ids:
            _cleanup_id_counters(emp_conn, sede_id=sid)
    users_conn.execute(
        "UPDATE usuarios SET empresa_id = NULL WHERE empresa_id = ?",
        (empresa_id,),
    )
    _cleanup_id_counters(emp_conn, empresa_id=empresa_id)
    emp_conn.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))

    return {
        "id": empresa_id,
        "ID_Empresa": empresa["ID_Empresa"],
        "ID_NIT": empresa["ID_NIT"],
        "sedes": n_sedes,
        "sedes_detalle": sedes_detalle,
        "equipos": int(n_equipos),
    }
