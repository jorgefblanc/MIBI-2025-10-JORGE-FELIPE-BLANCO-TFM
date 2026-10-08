"""API HTTP de organización e inventario (empresa, sede, servicio y equipos)."""

import csv
import io

from flask import Blueprint, jsonify, make_response, request, send_file, session
from openpyxl import Workbook

from server.authz import (
    assigned_empresa_id,
    assigned_sede_ids,
    can_access_empresa,
    can_access_sede,
    can_access_servicio,
    can_purge_inventory,
    clear_sede_assignments_outside_empresa,
    current_user,
    is_global_scope,
    login_required,
    permission_required,
    user_belongs_to_sede_empresa,
    user_has_permission,
)
from server.db import get_empresas_connection, get_users_connection
from server.pdf_staff import collect_org_staff
from server.org import (
    create_sede_with_servicios,
    delete_empresa_with_inventory,
    delete_sede_with_inventory,
    empresa_payload,
    fetch_empresa_tree,
    sede_payload,
    servicio_payload,
)
from server.sede_ids import SERVICIO_ORDER_SQL, is_letters_only_name, normalize_text_name, parse_servicio_spec
from server.inventario_params import (
    parse_activity_fields,
    row_activity_payload,
)
from server.event_log import empresa_id_for_servicio, log_evento
from server.limits import CODE, CSV_BYTES, IMPORT_ROWS, LABEL, NIT, QUERY_LIMIT, SHORT
from server.validators import sanitize_string
from server.ejecucion_mantenimientos import (
    insert_ejecucion,
    list_ejecucion_por_llave,
    lookup_inventario_llave,
    validate_manual_payload,
)


def _join_detalle(items, empty="ninguno"):
    cleaned = [str(x).strip() for x in (items or []) if str(x or "").strip()]
    return ", ".join(cleaned) if cleaned else empty

org_bp = Blueprint("org", __name__, url_prefix="/api")

# Etiquetas CSV / tabla (orden fijo)
INVENTORY_HEADERS = [
    "#BIOMÉDICA",
    "REGISTRO INVIMA",
    "EQUIPO",
    "MARCA",
    "SERIE",
    "MODELO",
    "CLASIFICACIÓN RIESGO",
    "UBICACIÓN",
    "ESTADO",
    "APLICA MP",
    "FREQ MP/AÑO",
    "TIEMPO MP (H)",
    "APLICA CAL",
    "FREQ CAL/AÑO",
    "TIEMPO CAL (H)",
    "APLICA VAL",
    "FREQ VAL/AÑO",
    "TIEMPO VAL (H)",
]

# ESTADO y parámetros estándar son opcionales en el CSV de importación.
INVENTORY_HEADERS_REQUIRED = [
    h
    for h in INVENTORY_HEADERS
    if h
    not in {
        "ESTADO",
        "APLICA MP",
        "FREQ MP/AÑO",
        "TIEMPO MP (H)",
        "APLICA CAL",
        "FREQ CAL/AÑO",
        "TIEMPO CAL (H)",
        "APLICA VAL",
        "FREQ VAL/AÑO",
        "TIEMPO VAL (H)",
    }
]

INVENTORY_DB_FIELDS = [
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
]

HEADER_TO_FIELD = dict(zip(INVENTORY_HEADERS, INVENTORY_DB_FIELDS))

INVENTORY_EXPORT_EXTRA = [
    ("CLASIFICACIÓN BIOMÉDICA", "clasificacion_biomedica"),
    ("PERIODICIDAD MP", "periodicidad_mp"),
    ("PERIODICIDAD CAL", "periodicidad_cal"),
    ("FECHA ÚLTIMO PM", "fecha_ultimo_pm"),
    ("FECHA COMPRA", "fecha_compra"),
    ("FECHA OPERACIÓN", "fecha_operacion"),
    ("FECHA GARANTÍA", "fecha_garantia"),
    ("FECHA BAJA", "fecha_baja"),
    ("VOLTAJE", "voltaje"),
    ("CORRIENTE", "corriente"),
    ("POTENCIA", "potencia"),
    ("PESO", "peso"),
    ("COMERCIALIZADOR", "comercializador"),
]
INVENTORY_EXPORT_HEADERS = INVENTORY_HEADERS + [h for h, _ in INVENTORY_EXPORT_EXTRA]
INVENTORY_EXPORT_FIELDS = INVENTORY_DB_FIELDS + [f for _, f in INVENTORY_EXPORT_EXTRA]

ESTADOS_VALIDOS = {"OPERATIVO", "EN REPARACIÓN", "FUERA DE SERVICIO"}


def _norm_header(value):
    text = str(value or "").strip().upper()
    # Quitar comillas residuales y BOM
    text = text.strip('"').strip("'").lstrip("\ufeff")
    replacements = (
        ("Á", "A"),
        ("É", "E"),
        ("Í", "I"),
        ("Ó", "O"),
        ("Ú", "U"),
        ("Ü", "U"),
        ("Ñ", "N"),
    )
    for src, dst in replacements:
        text = text.replace(src, dst)
    # Unificar símbolos frecuentes (#, ., -, _)
    for ch in ("#", ".", "-", "_", ":"):
        text = text.replace(ch, " ")
    return " ".join(text.split())


_HEADER_ALIASES = {_norm_header(h): h for h in INVENTORY_HEADERS}
# Alias útiles: Excel sin acentos, sin #, o con nombres cercanos
_HEADER_ALIASES.update(
    {
        _norm_header("BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("#BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("N BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("NO BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("NUM BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("NUMERO BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("CODIGO BIOMEDICA"): "#BIOMÉDICA",
        _norm_header("REGISTRO INVIMA"): "REGISTRO INVIMA",
        _norm_header("INVIMA"): "REGISTRO INVIMA",
        _norm_header("CLASIFICACION RIESGO"): "CLASIFICACIÓN RIESGO",
        _norm_header("CLASIFICACION DE RIESGO"): "CLASIFICACIÓN RIESGO",
        _norm_header("RIESGO"): "CLASIFICACIÓN RIESGO",
        _norm_header("UBICACION"): "UBICACIÓN",
        _norm_header("NOMBRE EQUIPO"): "EQUIPO",
        _norm_header("NOMBRE DEL EQUIPO"): "EQUIPO",
    }
)


def _normalize_estado(value):
    raw = sanitize_string(value).upper().replace("Ó", "O")
    if not raw:
        return None
    compact = " ".join(raw.split())
    if compact == "OPERATIVO":
        return "OPERATIVO"
    if "REPAR" in compact:
        return "EN REPARACIÓN"
    if "FUERA" in compact:
        return "FUERA DE SERVICIO"
    return None


def _equipo_payload(row):
    base = {
        "id": row["id"],
        "servicio_id": row["servicio_id"],
        "ID_servicio": row["ID_servicio"] if "ID_servicio" in row.keys() else None,
        "name_servicio": row["name_servicio"] if "name_servicio" in row.keys() else None,
        "sede_id": row["sede_id"] if "sede_id" in row.keys() else None,
        "ID_sede": row["ID_sede"] if "ID_sede" in row.keys() else None,
        "name_sede": row["name_sede"] if "name_sede" in row.keys() else None,
        "num_biomedica": row["num_biomedica"],
        "registro_invima": row["registro_invima"],
        "equipo": row["equipo"],
        "marca": row["marca"],
        "serie": row["serie"],
        "modelo": row["modelo"],
        "clasificacion_riesgo": row["clasificacion_riesgo"],
        "ubicacion": row["ubicacion"],
        "estado": row["estado"],
        "creation_date": row["creation_date"],
    }
    for extra in (
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
        "codigo_activo",
        "codigo_ubicacion",
        "institucion_origen",
        "novedad_desc",
        "voltaje",
        "corriente",
        "potencia",
        "peso",
        "temperatura_trabajo",
        "presion",
        "fuente_alimentacion",
        "comercializador",
        "periodicidad_mp",
        "periodicidad_cal",
        "requiere_calibracion",
        "fuente_import",
    ):
        if hasattr(row, "keys") and extra in row.keys():
            base[extra] = row[extra]
    base.update(row_activity_payload(row))
    return base


def _si_no_export(value):
    if value is None or value == "":
        return ""
    return "Sí" if int(value) == 1 else "No"


def _row_to_csv_dict(row):
    data = {}
    for header, field in zip(INVENTORY_EXPORT_HEADERS, INVENTORY_EXPORT_FIELDS):
        val = row[field] if hasattr(row, "keys") and field in row.keys() else None
        if field.startswith("aplica_"):
            data[header] = _si_no_export(val)
        else:
            data[header] = "" if val is None else val
    return data


def _equipo_filename_suffix(equipo_filter):
    if not equipo_filter:
        return ""
    slug = "".join(ch if ch.isalnum() else "_" for ch in equipo_filter.strip())
    slug = "_".join(part for part in slug.split("_") if part)[:40]
    return f"_{slug}" if slug else ""


FICHA_INVENTARIO_SQL = """
    SELECT ie.equipo, ie.marca, ie.modelo, ie.serie, ie.codigo_activo, ie.num_biomedica,
           ie.ubicacion, srv.ID_servicio, srv.name_servicio
    FROM inventario_equipos ie
    JOIN servicios srv ON srv.id = ie.servicio_id
"""


def _ficha_inventario_rows(emp_conn, *, servicio_id=None, sede_id=None, equipo_filter=None):
    where = []
    params = []
    if servicio_id is not None:
        where.append("ie.servicio_id = ?")
        params.append(servicio_id)
    elif sede_id is not None:
        where.append("srv.sede_id = ?")
        params.append(sede_id)
    else:
        return []
    if equipo_filter:
        if equipo_filter.casefold() == "sin nombre":
            where.append("(ie.equipo IS NULL OR TRIM(ie.equipo) = '')")
        else:
            where.append("lower(trim(coalesce(ie.equipo, ''))) = lower(?)")
            params.append(equipo_filter)
    sql = (
        FICHA_INVENTARIO_SQL
        + " WHERE "
        + " AND ".join(where)
        + " ORDER BY srv.ID_servicio, ie.equipo COLLATE NOCASE, ie.id"
    )
    return [dict(r) for r in emp_conn.execute(sql, params).fetchall()]


def _pdf_actor_label(user):
    generado = (user.get("NAME_USER") or user.get("usuario_login") or "").strip()
    if user.get("JOB"):
        generado = f"{generado} ({user.get('JOB')})".strip()
    return generado


def _inventario_pdf_response(meta_payload, rows, user, download_name):
    from server.inventario_pdf import build_inventario_pdf

    staff = collect_org_staff(
        empresa_id=meta_payload.get("empresa_id"),
        sede_id=meta_payload.get("sede_id"),
    )
    data = build_inventario_pdf(
        meta_payload, rows, generado_por=_pdf_actor_label(user), staff=staff
    )
    response = make_response(
        send_file(
            data,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )
    )
    response.headers["X-Inventario-Count"] = str(len(rows))
    response.headers["X-Inventario-Vacio"] = "1" if not rows else "0"
    return response


def _inventario_rows_for_export(emp_conn, servicio_id, equipo_filter=None):
    """Inventario del servicio; opcionalmente filtrado por tipo de equipo."""
    fields = ", ".join(INVENTORY_EXPORT_FIELDS)
    if not equipo_filter:
        return emp_conn.execute(
            f"""
            SELECT {fields}
            FROM inventario_equipos
            WHERE servicio_id = ?
            ORDER BY id
            """,
            (servicio_id,),
        ).fetchall()

    if equipo_filter.casefold() == "sin nombre":
        return emp_conn.execute(
            f"""
            SELECT {fields}
            FROM inventario_equipos
            WHERE servicio_id = ?
              AND (equipo IS NULL OR TRIM(equipo) = '')
            ORDER BY id
            """,
            (servicio_id,),
        ).fetchall()

    return emp_conn.execute(
        f"""
        SELECT {fields}
        FROM inventario_equipos
        WHERE servicio_id = ?
          AND lower(trim(coalesce(equipo, ''))) = lower(?)
        ORDER BY id
        """,
        (servicio_id, equipo_filter),
    ).fetchall()


def _decode_csv_bytes(raw_bytes):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _detect_delimiter(sample_text):
    """Excel en español suele exportar CSV con ';'."""
    first_line = (sample_text.splitlines() or [""])[0]
    candidates = [";", ",", "\t", "|"]
    counts = {d: first_line.count(d) for d in candidates}
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    try:
        dialect = csv.Sniffer().sniff(sample_text[:4096], delimiters=";,|\t")
        return dialect.delimiter
    except csv.Error:
        return ","


def _map_inventory_item(raw_item):
    """Normaliza una fila CSV a campos de BD usando las etiquetas oficiales."""
    mapped = {}
    for key, value in (raw_item or {}).items():
        canonical = _HEADER_ALIASES.get(_norm_header(key))
        if not canonical:
            continue
        field = HEADER_TO_FIELD[canonical]
        text = sanitize_string(value) if value is not None else ""
        if field.startswith("aplica_"):
            low = (text or "").strip().lower()
            if low in ("sí", "si", "yes", "true", "1", "s"):
                mapped[field] = 1
            elif low in ("no", "false", "0", "n"):
                mapped[field] = 0
            else:
                mapped[field] = None
        elif field.startswith("freq_") or field.startswith("tiempo_"):
            try:
                mapped[field] = float(str(text).replace(",", ".")) if text not in ("", None) else None
            except (TypeError, ValueError):
                mapped[field] = None
        else:
            cap = CODE if field in ("num_biomedica", "registro_invima") else LABEL
            mapped[field] = sanitize_string(text, cap)
    return mapped


def _parse_inventory_rows(file_storage):
    filename = (file_storage.filename or "").lower()
    rows = []
    if filename.endswith(".xlsx"):
        return None, "Solo se admite CSV. En Excel: Guardar como → CSV (delimitado por comas o punto y coma)."
    if not filename.endswith(".csv"):
        return None, "Debes importar un archivo CSV."

    raw = file_storage.stream.read(CSV_BYTES + 1)
    if len(raw) > CSV_BYTES:
        return None, "El CSV supera el tamaño máximo (8 MB)."
    text = _decode_csv_bytes(raw)
    if not text.strip():
        return None, "El archivo CSV está vacío."

    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return None, "El CSV no tiene encabezados."

    raw_headers = [str(h).strip() for h in reader.fieldnames if h and str(h).strip()]
    found = {
        _HEADER_ALIASES.get(_norm_header(h))
        for h in raw_headers
        if _HEADER_ALIASES.get(_norm_header(h))
    }
    missing = [h for h in INVENTORY_HEADERS_REQUIRED if h not in found]
    if missing:
        return (
            None,
            "No se reconocieron las etiquetas del CSV. "
            "Usa delimitador coma (,) o punto y coma (;). "
            "Encabezados esperados: "
            + ", ".join(INVENTORY_HEADERS_REQUIRED)
            + " (ESTADO opcional). "
            + f"Detectados en tu archivo: {', '.join(raw_headers) or '(ninguno)'}. "
            + f"Faltan: {', '.join(missing)}.",
        )

    for item in reader:
        normalized = {
            (k or "").strip(): ("" if v is None else str(v).strip())
            for k, v in item.items()
            if k
        }
        mapped = _map_inventory_item(normalized)
        if any(mapped.get(f) for f in INVENTORY_DB_FIELDS if f != "estado"):
            rows.append(mapped)
        if len(rows) > IMPORT_ROWS:
            return None, f"El CSV supera el máximo de {IMPORT_ROWS} filas."
    return rows, None


@org_bp.get("/empresas")
@login_required
@permission_required("view_sedes", "view_all_empresas", "create_empresa")
def list_empresas():
    user = current_user()
    with get_empresas_connection() as emp_conn:
        if is_global_scope(user):
            tree = fetch_empresa_tree(emp_conn)
        else:
            empresa_id = assigned_empresa_id(user)
            if not empresa_id:
                return jsonify(
                    {
                        "ok": True,
                        "empresas": [],
                        "empresa_pendiente": True,
                        "message": "Tu usuario aún no tiene empresa asignada.",
                    }
                )
            tree = fetch_empresa_tree(emp_conn, empresa_id)
    return jsonify({"ok": True, "empresas": tree})


@org_bp.post("/empresas")
@login_required
@permission_required("create_empresa", "admin_panel")
def create_empresa():
    """
    Crea empresa y, opcionalmente, sedes exclusivas con sus servicios.
    Body:
      ID_Empresa, ID_NIT,
      sedes: [{ name_sede, servicios: ["Urgencias", ...] }],
      notificacion_id?, asignar_usuario_id?
    """
    user = current_user()
    body = request.get_json(silent=True) or {}
    id_empresa = sanitize_string(body.get("ID_Empresa"), LABEL)
    id_nit = sanitize_string(body.get("ID_NIT"), NIT).upper()
    sedes_payload = body.get("sedes") or []
    notificacion_id = body.get("notificacion_id")
    asignar_usuario_id = body.get("asignar_usuario_id")

    if not id_empresa:
        return jsonify({"ok": False, "error": "ID_Empresa (razón social) es obligatorio."}), 400
    if not id_nit:
        return jsonify({"ok": False, "error": "ID_NIT es obligatorio."}), 400
    if not isinstance(sedes_payload, list):
        return jsonify({"ok": False, "error": "sedes debe ser una lista."}), 400

    # No-ADMIN con empresa ya asignada: no crea otra (evita cruce de información).
    if not is_global_scope(user) and assigned_empresa_id(user):
        return jsonify(
            {
                "ok": False,
                "error": "Ya perteneces a una empresa. Agrega sedes/servicios sobre ella.",
            }
        ), 403

    with get_empresas_connection() as emp_conn, get_users_connection() as users_conn:
        existing = emp_conn.execute(
            "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
            (id_nit,),
        ).fetchone()
        if existing:
            return jsonify(
                {
                    "ok": False,
                    "error": "El ID_NIT ya existe en la base de datos.",
                    "fieldErrors": {"ID_NIT": "Este NIT ya está registrado."},
                }
            ), 409

        cur = emp_conn.execute(
            """
            INSERT INTO empresas (ID_Empresa, ID_NIT, creation_date)
            VALUES (?, ?, datetime('now'))
            """,
            (id_empresa, id_nit),
        )
        empresa_id = cur.lastrowid

        created_sedes = []
        try:
            for item in sedes_payload:
                name_sede = (item or {}).get("name_sede")
                servicios = (item or {}).get("servicios") or []
                if isinstance(servicios, str):
                    servicios = [s.strip() for s in servicios.split(",") if s.strip()]
                created_sedes.append(
                    create_sede_with_servicios(
                        emp_conn,
                        empresa_id,
                        name_sede,
                        servicios,
                        ID_sede=(item or {}).get("ID_sede"),
                    )
                )
        except ValueError as err:
            emp_conn.rollback()
            return jsonify({"ok": False, "error": str(err)}), 400

        # Asignar empresa al creador no-ADMIN o por notificación ADMIN
        target_user_id = None
        if notificacion_id and is_global_scope(user):
            notif = users_conn.execute(
                "SELECT id, solicitante_id FROM notificaciones_admin WHERE id = ?",
                (int(notificacion_id),),
            ).fetchone()
            if notif:
                # empresa_creada_id es id lógico de empresas.db (sin FK cruzada).
                try:
                    users_conn.execute(
                        """
                        UPDATE notificaciones_admin
                        SET estado = 'RESUELTA', empresa_creada_id = ?
                        WHERE id = ?
                        """,
                        (empresa_id, notif["id"]),
                    )
                except Exception:
                    users_conn.execute(
                        """
                        UPDATE notificaciones_admin
                        SET estado = 'RESUELTA'
                        WHERE id = ?
                        """,
                        (notif["id"],),
                    )
                target_user_id = notif["solicitante_id"]

        if asignar_usuario_id and is_global_scope(user):
            target_user_id = int(asignar_usuario_id)

        if not is_global_scope(user):
            target_user_id = user["id_usuario"]

        if target_user_id:
            users_conn.execute(
                "UPDATE usuarios SET empresa_id = ? WHERE id_usuario = ?",
                (empresa_id, target_user_id),
            )
            clear_sede_assignments_outside_empresa(
                users_conn, target_user_id, empresa_id
            )
            if target_user_id == user["id_usuario"]:
                session["empresa_id"] = empresa_id

        emp_conn.commit()
        users_conn.commit()

        row = emp_conn.execute(
            "SELECT * FROM empresas WHERE id = ?", (empresa_id,)
        ).fetchone()

    log_evento(
        empresa_id=empresa_id,
        accion=f"Alta de empresa «{id_empresa}» (NIT {id_nit}).",
        user=user,
    )
    for sede in created_sedes:
        nombres = [
            s.get("name_servicio")
            for s in (sede.get("servicios") or [])
            if s.get("name_servicio")
        ]
        log_evento(
            empresa_id=empresa_id,
            accion=(
                f"Alta de sede «{sede['name_sede']}» ({sede['ID_sede']}) "
                f"con servicios: {_join_detalle(nombres, 'sin servicios')}."
            ),
            user=user,
        )

    return jsonify(
        {
            "ok": True,
            "message": "Empresa creada con sus sedes exclusivas.",
            "empresa": {**empresa_payload(row), "sedes": created_sedes},
        }
    ), 201


@org_bp.route("/empresas/<int:empresa_id>", methods=["DELETE"])
@org_bp.post("/empresas/<int:empresa_id>/eliminar")
@login_required
@permission_required("delete_empresa", "create_empresa", "admin_panel")
def delete_empresa(empresa_id):
    """Elimina la empresa, sedes, servicios e inventario. Desvincula personal."""
    user = current_user()
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_empresa(emp_conn, user, empresa_id):
            return jsonify({"ok": False, "error": "Fuera de tu empresa."}), 403
        try:
            deleted = delete_empresa_with_inventory(emp_conn, users_conn, empresa_id)
            emp_conn.commit()
            users_conn.commit()
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 404

    if not is_global_scope(user) and assigned_empresa_id(user) == empresa_id:
        session["empresa_id"] = None

    log_evento(
        empresa_id=deleted["id"],
        accion=(
            f"Baja de empresa «{deleted['ID_Empresa']}» (NIT {deleted['ID_NIT']}; "
            f"{deleted['sedes']} sede(s): {_join_detalle(deleted.get('sedes_detalle'))}; "
            f"{deleted['equipos']} equipo(s))."
        ),
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": (
                f"Empresa «{deleted['ID_Empresa']}» eliminada "
                f"({deleted['sedes']} sede(s), {deleted['equipos']} equipo(s))."
            ),
            "empresa": deleted,
        }
    )


@org_bp.get("/sedes")
@login_required
@permission_required(
    "view_sedes",
    "view_inventory",
    "view_suficiencia",
    "view_dimensionamiento",
    "view_frecuencia_pm",
    "view_preinstalacion",
    "view_kpis",
    "view_respaldo",
    "view_capex",
    "create_sede",
    "create_empresa",
    "view_all_empresas",
)
def list_sedes():
    user = current_user()
    with get_empresas_connection() as emp_conn, get_users_connection() as users_conn:
        if is_global_scope(user):
            rows = emp_conn.execute(
                """
                SELECT s.*, e.ID_Empresa, e.ID_NIT
                FROM sedes s
                JOIN empresas e ON e.id = s.empresa_id
                ORDER BY e.ID_Empresa COLLATE NOCASE, s.name_sede COLLATE NOCASE
                """
            ).fetchall()
        else:
            empresa_id = assigned_empresa_id(user)
            if not empresa_id:
                return jsonify({"ok": True, "sedes": [], "empresa_pendiente": True})
            rows = emp_conn.execute(
                """
                SELECT s.*, e.ID_Empresa, e.ID_NIT
                FROM sedes s
                JOIN empresas e ON e.id = s.empresa_id
                WHERE s.empresa_id = ?
                ORDER BY s.name_sede COLLATE NOCASE
                """,
                (empresa_id,),
            ).fetchall()

            # Solo sedes de la empresa del usuario. Si tiene asignaciones en
            # usuario_sedes, limitar a esas (ignorando IDs de otras empresas).
            assigned = assigned_sede_ids(users_conn, user["id_usuario"])
            if assigned:
                empresa_sede_ids = {r["id"] for r in rows}
                assigned_in_empresa = assigned & empresa_sede_ids
                if assigned_in_empresa:
                    rows = [r for r in rows if r["id"] in assigned_in_empresa]

        result = []
        for row in rows:
            servicios = emp_conn.execute(
                f"""
                SELECT * FROM servicios WHERE sede_id = ?
                ORDER BY {SERVICIO_ORDER_SQL}
                """,
                (row["id"],),
            ).fetchall()
            item = sede_payload(row)
            item["servicios"] = [servicio_payload(dict(s)) for s in servicios]
            result.append(item)

    return jsonify({"ok": True, "sedes": result})


@org_bp.post("/sedes")
@login_required
@permission_required("create_sede")
def create_sede():
    user = current_user()
    body = request.get_json(silent=True) or {}
    try:
        empresa_id = int(body.get("empresa_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "empresa_id inválido."}), 400

    servicios = body.get("servicios") or []
    if isinstance(servicios, str):
        servicios = [s.strip() for s in servicios.split(",") if s.strip()]

    if not is_global_scope(user):
        assigned = assigned_empresa_id(user)
        if not assigned:
            return jsonify({"ok": False, "error": "Sin empresa asignada."}), 403
        if empresa_id != assigned:
            return jsonify(
                {"ok": False, "error": "La sede solo puede crearse en tu empresa."}
            ), 403

    with get_empresas_connection() as emp_conn:
        if not emp_conn.execute(
            "SELECT id FROM empresas WHERE id = ?", (empresa_id,)
        ).fetchone():
            return jsonify({"ok": False, "error": "La empresa no existe."}), 404
        try:
            sede = create_sede_with_servicios(
                emp_conn,
                empresa_id,
                body.get("name_sede"),
                servicios,
                ID_sede=body.get("ID_sede"),
            )
            emp_conn.commit()
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400

    nombres = [
        s.get("name_servicio")
        for s in (sede.get("servicios") or [])
        if s.get("name_servicio")
    ]
    log_evento(
        empresa_id=empresa_id,
        accion=(
            f"Alta de sede «{sede['name_sede']}» ({sede['ID_sede']}) "
            f"con servicios: {_join_detalle(nombres, 'sin servicios')}."
        ),
        user=user,
    )

    return jsonify({"ok": True, "message": "Sede creada y ligada a la empresa.", "sede": sede}), 201


@org_bp.route("/sedes/<int:sede_id>", methods=["DELETE"])
@org_bp.post("/sedes/<int:sede_id>/eliminar")
@login_required
@permission_required("delete_sede", "create_sede", "admin_panel")
def delete_sede(sede_id):
    """Elimina la sede, sus servicios y el inventario cargado."""
    user = current_user()
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_sede(user, sede_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "No tienes acceso a esta sede."}), 403
        try:
            deleted = delete_sede_with_inventory(emp_conn, users_conn, sede_id)
            emp_conn.commit()
            users_conn.commit()
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 404

    log_evento(
        empresa_id=deleted["empresa_id"],
        accion=(
            f"Baja de sede «{deleted['name_sede']}» ({deleted['ID_sede']}; "
            f"{deleted['servicios']} servicio(s): "
            f"{_join_detalle(deleted.get('servicios_detalle'))}; "
            f"{deleted['equipos']} equipo(s))."
        ),
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": (
                f"Sede «{deleted['name_sede']}» eliminada "
                f"({deleted['servicios']} servicio(s), {deleted['equipos']} equipo(s))."
            ),
            "sede": deleted,
        }
    )


@org_bp.post("/sedes/<int:sede_id>/servicios")
@login_required
@permission_required("create_servicio", "create_sede")
def create_servicio(sede_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    parsed_id, parsed_name = parse_servicio_spec(body.get("name_servicio"))
    name_servicio = normalize_text_name(parsed_name or body.get("name_servicio"))
    external_id = body.get("ID_servicio") or parsed_id
    if not is_letters_only_name(name_servicio):
        return jsonify(
            {
                "ok": False,
                "error": "name_servicio admite letras, números, espacios y separadores (. - _ /).",
            }
        ), 400

    sede_info = None
    row = None
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_sede(user, sede_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "No tienes acceso a esta sede."}), 403
        try:
            from server.sede_ids import next_id_servicio

            id_srv, prefix = next_id_servicio(
                emp_conn, name_servicio, sede_id, external_id=external_id
            )
            taken = emp_conn.execute(
                """
                SELECT id FROM servicios
                WHERE sede_id = ? AND ID_servicio = ? COLLATE NOCASE
                """,
                (sede_id, id_srv),
            ).fetchone()
            if taken:
                return jsonify(
                    {"ok": False, "error": f"El ID_servicio '{id_srv}' ya existe en esta sede."}
                ), 409
            cur = emp_conn.execute(
                """
                INSERT INTO servicios (ID_servicio, name_servicio, prefix, sede_id, creation_date)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (id_srv, name_servicio, prefix, sede_id),
            )
            emp_conn.commit()
            row = emp_conn.execute(
                "SELECT * FROM servicios WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            sede_info = emp_conn.execute(
                "SELECT name_sede, ID_sede, empresa_id FROM sedes WHERE id = ?",
                (sede_id,),
            ).fetchone()
        except Exception as err:
            return jsonify({"ok": False, "error": str(err)}), 400

    if sede_info and sede_info["empresa_id"]:
        log_evento(
            empresa_id=sede_info["empresa_id"],
            accion=(
                f"Alta de servicio «{row['name_servicio']}» ({row['ID_servicio']}) "
                f"en sede «{sede_info['name_sede']}» ({sede_info['ID_sede']})."
            ),
            user=user,
        )

    return jsonify(
        {
            "ok": True,
            "message": f"Servicio creado ({id_srv}).",
            "servicio": servicio_payload(dict(row)),
        }
    ), 201


@org_bp.get("/direccion/empresas-sedes")
@login_required
@permission_required("view_all_empresas")
def direccion_module():
    user = current_user()
    with get_empresas_connection() as emp_conn:
        if is_global_scope(user):
            tree = fetch_empresa_tree(emp_conn)
        else:
            empresa_id = assigned_empresa_id(user)
            if not empresa_id:
                return jsonify({"ok": False, "error": "Sin empresa asignada."}), 403
            tree = fetch_empresa_tree(emp_conn, empresa_id)
    return jsonify({"ok": True, "empresas": tree})


def _inventario_search_clause(q: str) -> tuple[str, list]:
    raw = sanitize_string(q or "", SHORT)
    tokens = [tok for tok in raw.split() if tok][:8]
    if not tokens:
        return "", []
    clauses = []
    params: list[str] = []
    for tok in tokens:
        like = f"%{tok.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        clauses.append(
            "("
            "i.num_biomedica LIKE ? ESCAPE '\\' OR "
            "COALESCE(i.codigo_activo,'') LIKE ? ESCAPE '\\' OR "
            "i.equipo LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([like, like, like])
    return " AND " + " AND ".join(clauses), params


@org_bp.get("/servicios/<int:servicio_id>/inventario")
@login_required
@permission_required("view_inventory", "access_servicio")
def list_inventario(servicio_id):
    user = current_user()
    page = request.args.get("page", type=int) or 1
    page_size = request.args.get("page_size", type=int) or QUERY_LIMIT
    q = request.args.get("q") or ""
    page = max(1, page)
    try:
        page_size = max(10, min(int(page_size), QUERY_LIMIT))
    except (TypeError, ValueError):
        page_size = QUERY_LIMIT
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este servicio."}), 403
        servicio = emp_conn.execute(
            """
            SELECT srv.*, s.ID_sede, s.name_sede, s.empresa_id, e.ID_Empresa
            FROM servicios srv
            JOIN sedes s ON s.id = srv.sede_id
            JOIN empresas e ON e.id = s.empresa_id
            WHERE srv.id = ?
            """,
            (servicio_id,),
        ).fetchone()
        if not servicio:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404

        total = emp_conn.execute(
            "SELECT COUNT(*) AS n FROM inventario_equipos WHERE servicio_id = ?",
            (servicio_id,),
        ).fetchone()["n"]
        total = int(total or 0)
        server_paged = total > QUERY_LIMIT
        search_sql, search_params = ("", [])
        filtered_total = total
        offset = 0
        limit = QUERY_LIMIT
        if server_paged:
            search_sql, search_params = _inventario_search_clause(q)
            filtered_total = emp_conn.execute(
                f"SELECT COUNT(*) AS n FROM inventario_equipos i "
                f"WHERE i.servicio_id = ?{search_sql}",
                (servicio_id, *search_params),
            ).fetchone()["n"]
            filtered_total = int(filtered_total or 0)
            limit = page_size
            offset = (page - 1) * page_size
            if offset >= filtered_total and filtered_total > 0:
                page = max(1, (filtered_total + page_size - 1) // page_size)
                offset = (page - 1) * page_size
        rows = emp_conn.execute(
            f"""
            SELECT i.*, srv.ID_servicio, srv.name_servicio, s.ID_sede, s.name_sede, s.id AS sede_id
            FROM inventario_equipos i
            JOIN servicios srv ON srv.id = i.servicio_id
            JOIN sedes s ON s.id = srv.sede_id
            WHERE i.servicio_id = ?{search_sql}
            ORDER BY i.id
            LIMIT ? OFFSET ?
            """,
            (servicio_id, *search_params, limit, offset),
        ).fetchall()
        inventario = [_equipo_payload(r) for r in rows]
        try:
            from server.frecuencia_pm import resumen_ejecucion_por_llaves
            from server.inventario import attach_flags_lista, clamp_anio

            year = clamp_anio(request.args.get("anio"))
            resumen = resumen_ejecucion_por_llaves(emp_conn, int(servicio["empresa_id"]), anio=year)
            attach_flags_lista(inventario, resumen, year)
        except Exception:
            pass
        from server.inventory_recycle import status_for_servicio

        recycle = status_for_servicio(servicio_id)

    return jsonify(
        {
            "ok": True,
            "servicio": servicio_payload(dict(servicio)),
            "inventario": inventario,
            "total": total,
            "filtered_total": filtered_total,
            "limit": limit,
            "page": page if server_paged else 1,
            "page_size": page_size if server_paged else total,
            "offset": offset,
            "server_paged": server_paged,
            "recycle": recycle,
            "can_purge_inventory": can_purge_inventory(user),
        }
    )


@org_bp.post("/servicios/<int:servicio_id>/inventario/import")
@login_required
@permission_required("import_inventory")
def import_inventario(servicio_id):
    user = current_user()
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Debes enviar un archivo CSV."}), 400
    file_storage = request.files["file"]
    try:
        parsed, parse_error = _parse_inventory_rows(file_storage)
    except Exception as err:
        return jsonify({"ok": False, "error": f"No se pudo leer el archivo: {err}"}), 400
    if parse_error:
        return jsonify({"ok": False, "error": parse_error}), 400
    if not parsed:
        return jsonify({"ok": False, "error": "El archivo no contiene filas."}), 400

    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este servicio."}), 403
        inserted = 0
        skipped = 0
        for item in parsed:
            equipo = sanitize_string(item.get("equipo"), LABEL)
            if not equipo:
                skipped += 1
                continue
            # ESTADO no es obligatorio en importación: si falta o no es válido → en blanco.
            estado = _normalize_estado(item.get("estado"))
            emp_conn.execute(
                """
                INSERT INTO inventario_equipos (
                    servicio_id, num_biomedica, registro_invima, equipo,
                    marca, serie, modelo, clasificacion_riesgo, ubicacion, estado,
                    aplica_mp, freq_mp, tiempo_mp,
                    aplica_cal, freq_cal, tiempo_cal,
                    aplica_val, freq_val, tiempo_val,
                    creation_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    servicio_id,
                    sanitize_string(item.get("num_biomedica")) or None,
                    sanitize_string(item.get("registro_invima")) or None,
                    equipo,
                    sanitize_string(item.get("marca")) or None,
                    sanitize_string(item.get("serie")) or None,
                    sanitize_string(item.get("modelo")) or None,
                    sanitize_string(item.get("clasificacion_riesgo")) or None,
                    sanitize_string(item.get("ubicacion")) or None,
                    estado,
                    item.get("aplica_mp"),
                    item.get("freq_mp"),
                    item.get("tiempo_mp"),
                    item.get("aplica_cal"),
                    item.get("freq_cal"),
                    item.get("tiempo_cal"),
                    item.get("aplica_val"),
                    item.get("freq_val"),
                    item.get("tiempo_val"),
                ),
            )
            inserted += 1
        emp_conn.commit()
        empresa_id = empresa_id_for_servicio(emp_conn, servicio_id)

    if empresa_id:
        log_evento(
            empresa_id=empresa_id,
            accion=f"Importó inventario CSV en servicio {servicio_id}: {inserted} equipo(s).",
            user=user,
        )

    message = f"Inventario importado: {inserted} equipo(s)."
    if skipped:
        message += f" Omitidas {skipped} fila(s) sin EQUIPO."
    return jsonify({"ok": True, "message": message, "inserted": inserted, "skipped": skipped})


def _require_purge_inventory(user, servicio_id, users_conn):
    if not can_purge_inventory(user):
        return jsonify(
            {
                "ok": False,
                "error": "Solo el Administrador o el Director Operativo pueden eliminar o restaurar el inventario cargado.",
            }
        ), 403
    if not can_access_servicio(user, servicio_id, users_conn=users_conn):
        return jsonify({"ok": False, "error": "Sin acceso a este servicio."}), 403
    return None


@org_bp.post("/servicios/<int:servicio_id>/inventario/eliminar-cargado")
@login_required
def purge_inventario_cargado(servicio_id):
    """Vacía el inventario del servicio y guarda un reciclo de 30 min (no usa auto-backup)."""
    user = current_user()
    from server.inventory_recycle import snapshot_and_delete

    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        denied = _require_purge_inventory(user, servicio_id, users_conn)
        if denied:
            return denied
        try:
            recycle = snapshot_and_delete(emp_conn, servicio_id=servicio_id, user=user)
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400
    remaining = int(recycle.get("remaining_seconds") or 0)
    minutos = max(1, (remaining + 59) // 60)
    return jsonify(
        {
            "ok": True,
            "message": (
                f"Inventario eliminado ({recycle.get('equipos') or 0} equipo(s)). "
                f"Puede restaurarlo durante {minutos} minuto(s) con «Restaurar último backup»."
            ),
            "recycle": recycle,
        }
    )


@org_bp.post("/servicios/<int:servicio_id>/inventario/restaurar-backup")
@login_required
def restore_inventario_backup(servicio_id):
    """Restaura el reciclo vigente del servicio. No toca los snapshots de las 4 bases."""
    user = current_user()
    from server.inventory_recycle import restore_last

    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        denied = _require_purge_inventory(user, servicio_id, users_conn)
        if denied:
            return denied
        try:
            result = restore_last(emp_conn, servicio_id=servicio_id)
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400
    return jsonify(
        {
            "ok": True,
            "message": f"Inventario restaurado: {result['restored']} equipo(s).",
            "restored": result["restored"],
        }
    )


@org_bp.post("/servicios/<int:servicio_id>/inventario")
@login_required
@permission_required("modify_inventory", "access_servicio")
def create_inventario_equipo(servicio_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    equipo = sanitize_string(body.get("equipo"), LABEL)
    if not equipo:
        return jsonify({"ok": False, "error": "EQUIPO es obligatorio."}), 400

    estado_raw = body.get("estado")
    if estado_raw is None or str(estado_raw).strip() == "":
        estado = None
    else:
        estado = _normalize_estado(estado_raw)
        if estado is None:
            return jsonify(
                {
                    "ok": False,
                    "error": "ESTADO debe ser OPERATIVO, EN REPARACIÓN, FUERA DE SERVICIO o quedar vacío.",
                }
            ), 400

    activity_params = parse_activity_fields(body)
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        srv = emp_conn.execute(
            "SELECT id FROM servicios WHERE id = ?", (servicio_id,)
        ).fetchone()
        if not srv:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este servicio."}), 403
        cur = emp_conn.execute(
            """
            INSERT INTO inventario_equipos (
                servicio_id, num_biomedica, codigo_activo, registro_invima, equipo,
                marca, serie, modelo, clasificacion_riesgo, ubicacion, estado,
                aplica_mp, freq_mp, tiempo_mp,
                aplica_cal, freq_cal, tiempo_cal,
                aplica_val, freq_val, tiempo_val,
                creation_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                servicio_id,
                sanitize_string(body.get("num_biomedica"), CODE) or None,
                sanitize_string(body.get("codigo_activo"), CODE) or None,
                sanitize_string(body.get("registro_invima"), CODE) or None,
                equipo,
                sanitize_string(body.get("marca"), LABEL) or None,
                sanitize_string(body.get("serie"), LABEL) or None,
                sanitize_string(body.get("modelo"), LABEL) or None,
                sanitize_string(body.get("clasificacion_riesgo"), CODE) or None,
                sanitize_string(body.get("ubicacion"), LABEL) or None,
                estado,
                activity_params.get("aplica_mp"),
                activity_params.get("freq_mp"),
                activity_params.get("tiempo_mp"),
                activity_params.get("aplica_cal"),
                activity_params.get("freq_cal"),
                activity_params.get("tiempo_cal"),
                activity_params.get("aplica_val"),
                activity_params.get("freq_val"),
                activity_params.get("tiempo_val"),
            ),
        )
        emp_conn.commit()
        created_id = cur.lastrowid
        refreshed = emp_conn.execute(
            "SELECT * FROM inventario_equipos WHERE id = ?",
            (created_id,),
        ).fetchone()
        empresa_id = empresa_id_for_servicio(emp_conn, servicio_id)

    log_evento(
        empresa_id=empresa_id,
        accion=f"Creó equipo «{equipo}» (id {created_id}) en servicio {servicio_id}.",
        user=user,
    )
    return jsonify(
        {
            "ok": True,
            "message": "Equipo creado en el inventario.",
            "equipo": _equipo_payload(refreshed),
        }
    ), 201


@org_bp.put("/inventario/<int:equipo_id>")
@login_required
@permission_required("modify_inventory", "access_servicio")
def update_inventario_equipo(equipo_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    equipo = sanitize_string(body.get("equipo"), LABEL)
    if not equipo:
        return jsonify({"ok": False, "error": "EQUIPO es obligatorio."}), 400

    estado_raw = body.get("estado")
    if estado_raw is None or str(estado_raw).strip() == "":
        estado = None
    else:
        estado = _normalize_estado(estado_raw)
        if estado is None:
            return jsonify(
                {
                    "ok": False,
                    "error": "ESTADO debe ser OPERATIVO, EN REPARACIÓN, FUERA DE SERVICIO o quedar vacío.",
                }
            ), 400

    activity_params = parse_activity_fields(body)
    has_activity_update = any(
        k in body
        for k in (
            "aplica_mp",
            "freq_mp",
            "tiempo_mp",
            "aplica_cal",
            "freq_cal",
            "tiempo_cal",
            "aplica_val",
            "freq_val",
            "tiempo_val",
        )
    )

    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        row = emp_conn.execute(
            "SELECT * FROM inventario_equipos WHERE id = ?",
            (equipo_id,),
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Equipo no encontrado."}), 404
        if not can_access_servicio(user, row["servicio_id"], users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este equipo."}), 403

        emp_conn.execute(
            """
            UPDATE inventario_equipos SET
                num_biomedica = ?,
                codigo_activo = ?,
                registro_invima = ?,
                equipo = ?,
                marca = ?,
                serie = ?,
                modelo = ?,
                clasificacion_riesgo = ?,
                ubicacion = ?,
                estado = ?
            WHERE id = ?
            """,
            (
                sanitize_string(body.get("num_biomedica"), CODE) or None,
                sanitize_string(body.get("codigo_activo"), CODE) or None,
                sanitize_string(body.get("registro_invima"), CODE) or None,
                equipo,
                sanitize_string(body.get("marca"), LABEL) or None,
                sanitize_string(body.get("serie"), LABEL) or None,
                sanitize_string(body.get("modelo"), LABEL) or None,
                sanitize_string(body.get("clasificacion_riesgo"), CODE) or None,
                sanitize_string(body.get("ubicacion"), LABEL) or None,
                estado,
                equipo_id,
            ),
        )

        if has_activity_update:
            emp_conn.execute(
                """
                UPDATE inventario_equipos SET
                    aplica_mp = ?, freq_mp = ?, tiempo_mp = ?,
                    aplica_cal = ?, freq_cal = ?, tiempo_cal = ?,
                    aplica_val = ?, freq_val = ?, tiempo_val = ?
                WHERE id = ?
                """,
                (
                    activity_params.get("aplica_mp"),
                    activity_params.get("freq_mp"),
                    activity_params.get("tiempo_mp"),
                    activity_params.get("aplica_cal"),
                    activity_params.get("freq_cal"),
                    activity_params.get("tiempo_cal"),
                    activity_params.get("aplica_val"),
                    activity_params.get("freq_val"),
                    activity_params.get("tiempo_val"),
                    equipo_id,
                ),
            )

        emp_conn.commit()
        refreshed = emp_conn.execute(
            "SELECT * FROM inventario_equipos WHERE id = ?",
            (equipo_id,),
        ).fetchone()
        empresa_id = empresa_id_for_servicio(emp_conn, row["servicio_id"])

    log_evento(
        empresa_id=empresa_id,
        accion=f"Actualizó equipo «{equipo}» (id {equipo_id}).",
        user=user,
    )

    return jsonify(
        {
            "ok": True,
            "message": "Equipo actualizado.",
            "equipo": _equipo_payload(refreshed),
        }
    )


@org_bp.get("/inventario/<int:equipo_id>/ejecucion")
@login_required
@permission_required("modify_inventory", "access_servicio", "view_frecuencia_pm")
def inventario_ejecucion_list(equipo_id):
    user = current_user()
    args = request.args
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        inv = lookup_inventario_llave(emp_conn, equipo_id)
        if not inv:
            return jsonify({"ok": False, "error": "Equipo no encontrado."}), 404
        if not can_access_servicio(user, inv["servicio_id"], users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este equipo."}), 403
        payload = list_ejecucion_por_llave(
            emp_conn,
            int(inv["empresa_id"]),
            inv["num_biomedica"],
            inv["codigo_activo"],
            page=args.get("page") or 1,
            page_size=args.get("page_size") or 25,
        )
        payload["equipo"] = {
            "id": inv["id"],
            "equipo": inv["equipo"],
            "codigo_biomedica": inv["num_biomedica"],
            "codigo_activo": inv["codigo_activo"],
            "sede_id": inv["sede_id"],
            "servicio_id": inv["servicio_id"],
            "empresa_id": inv["empresa_id"],
        }
    return jsonify(payload)


@org_bp.post("/inventario/<int:equipo_id>/ejecucion")
@login_required
@permission_required("modify_inventory", "access_servicio")
def inventario_ejecucion_create(equipo_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        inv = lookup_inventario_llave(emp_conn, equipo_id)
        if not inv:
            return jsonify({"ok": False, "error": "Equipo no encontrado."}), 404
        if not can_access_servicio(user, inv["servicio_id"], users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este equipo."}), 403
        payload_in = {
            **body,
            "codigo_biomedica": body.get("codigo_biomedica") or inv["num_biomedica"],
            "codigo_activo": body.get("codigo_activo") if body.get("codigo_activo") not in (None, "") else (inv["codigo_activo"] or ""),
            "empresa_id": inv["empresa_id"],
            "sede_id": inv["sede_id"],
            "servicio_id": inv["servicio_id"],
            "fuente": "manual",
        }
        payload, error = validate_manual_payload(payload_in)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        row = insert_ejecucion(emp_conn, payload)
        emp_conn.commit()
    log_evento(
        empresa_id=inv["empresa_id"],
        accion=f"Registró ejecución manual del equipo «{inv['equipo']}» (id {equipo_id}).",
        user=user,
        modulo="inventario",
        sede_id=inv["sede_id"],
        servicio_id=inv["servicio_id"],
        parametros={"tipo": payload["tipo_mantenimiento"], "equipo_id": equipo_id},
        resultado={"id": row.get("id")},
    )
    return jsonify({"ok": True, "message": "Ejecución registrada.", "item": row}), 201


@org_bp.delete("/inventario/<int:equipo_id>")
@login_required
@permission_required("modify_inventory", "access_servicio")
def delete_inventario_equipo(equipo_id):
    user = current_user()
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        row = emp_conn.execute(
            "SELECT id, servicio_id, equipo FROM inventario_equipos WHERE id = ?",
            (equipo_id,),
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Equipo no encontrado."}), 404
        if not can_access_servicio(user, row["servicio_id"], users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a este equipo."}), 403
        emp_conn.execute("DELETE FROM inventario_equipos WHERE id = ?", (equipo_id,))
        emp_conn.commit()
        empresa_id = empresa_id_for_servicio(emp_conn, row["servicio_id"])
    log_evento(
        empresa_id=empresa_id,
        accion=f"Eliminó equipo «{row['equipo']}» (id {equipo_id}).",
        user=user,
    )
    return jsonify(
        {
            "ok": True,
            "message": f"Equipo eliminado: {row['equipo']}.",
        }
    )


@org_bp.get("/servicios/<int:servicio_id>/inventario/export.csv")
@login_required
@permission_required("export_inventory")
def export_inventario_csv(servicio_id):
    user = current_user()
    equipo_filter = sanitize_string(request.args.get("equipo"))
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso."}), 403
        rows = _inventario_rows_for_export(emp_conn, servicio_id, equipo_filter)
        srv = emp_conn.execute(
            "SELECT ID_servicio FROM servicios WHERE id = ?", (servicio_id,)
        ).fetchone()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=INVENTORY_EXPORT_HEADERS)
    writer.writeheader()
    for row in rows:
        writer.writerow(_row_to_csv_dict(row))
    data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    data.seek(0)
    code = srv["ID_servicio"] if srv else str(servicio_id)
    suffix = _equipo_filename_suffix(equipo_filter)
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"inventario_{code}{suffix}.csv",
    )


@org_bp.get("/servicios/<int:servicio_id>/inventario/export.xlsx")
@login_required
@permission_required("export_inventory")
def export_inventario_xlsx(servicio_id):
    user = current_user()
    equipo_filter = sanitize_string(request.args.get("equipo"))
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso."}), 403
        rows = _inventario_rows_for_export(emp_conn, servicio_id, equipo_filter)
        srv = emp_conn.execute(
            "SELECT ID_servicio FROM servicios WHERE id = ?", (servicio_id,)
        ).fetchone()

    wb = Workbook()
    sheet = wb.active
    sheet.title = "inventario"
    sheet.append(INVENTORY_EXPORT_HEADERS)
    for row in rows:
        sheet.append(
            [
                ("" if row[field] is None else row[field])
                if hasattr(row, "keys") and field in row.keys()
                else ""
                for field in INVENTORY_EXPORT_FIELDS
            ]
        )
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    code = srv["ID_servicio"] if srv else str(servicio_id)
    suffix = _equipo_filename_suffix(equipo_filter)
    return send_file(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"inventario_{code}{suffix}.xlsx",
    )


@org_bp.get("/servicios/<int:servicio_id>/inventario/export/pdf")
@org_bp.get("/servicios/<int:servicio_id>/inventario/export.pdf")
@login_required
@permission_required("view_inventory", "export_inventory")
def export_inventario_pdf(servicio_id):
    """Ficha PDF de consulta del inventario del servicio (roles con vista)."""
    user = current_user()
    equipo_filter = sanitize_string(request.args.get("equipo"))
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_servicio(user, servicio_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso."}), 403
        meta = emp_conn.execute(
            """
            SELECT srv.id AS servicio_id, srv.ID_servicio, srv.name_servicio,
                   s.id AS sede_id, s.ID_sede, s.name_sede, s.empresa_id,
                   e.ID_Empresa, e.ID_NIT
            FROM servicios srv
            JOIN sedes s ON s.id = srv.sede_id
            JOIN empresas e ON e.id = s.empresa_id
            WHERE srv.id = ?
            """,
            (servicio_id,),
        ).fetchone()
        if not meta:
            return jsonify({"ok": False, "error": "Servicio no encontrado."}), 404
        meta_payload = {
            "alcance": "servicio",
            "ID_servicio": meta["ID_servicio"],
            "name_servicio": meta["name_servicio"],
            "ID_sede": meta["ID_sede"],
            "name_sede": meta["name_sede"],
            "ID_Empresa": meta["ID_Empresa"],
            "ID_NIT": meta["ID_NIT"],
            "empresa_id": meta["empresa_id"],
            "sede_id": meta["sede_id"],
        }
        rows = _ficha_inventario_rows(
            emp_conn, servicio_id=servicio_id, equipo_filter=equipo_filter
        )

    if equipo_filter:
        meta_payload["equipo_filtro"] = equipo_filter
    code = meta_payload.get("ID_servicio") or str(servicio_id)
    suffix = _equipo_filename_suffix(equipo_filter)
    return _inventario_pdf_response(
        meta_payload, rows, user, f"inventario_{code}{suffix}.pdf"
    )


@org_bp.get("/sedes/<int:sede_id>/inventario/export/pdf")
@org_bp.get("/sedes/<int:sede_id>/inventario/export.pdf")
@login_required
@permission_required("view_inventory", "export_inventory")
def export_inventario_sede_pdf(sede_id):
    """Ficha PDF del inventario de todos los servicios de la sede."""
    user = current_user()
    with get_users_connection() as users_conn, get_empresas_connection() as emp_conn:
        if not can_access_sede(user, sede_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a esta sede."}), 403
        meta = emp_conn.execute(
            """
            SELECT s.id AS sede_id, s.ID_sede, s.name_sede, s.empresa_id,
                   e.ID_Empresa, e.ID_NIT
            FROM sedes s
            JOIN empresas e ON e.id = s.empresa_id
            WHERE s.id = ?
            """,
            (sede_id,),
        ).fetchone()
        if not meta:
            return jsonify({"ok": False, "error": "Sede no encontrada."}), 404
        servicios_n = emp_conn.execute(
            "SELECT COUNT(*) AS n FROM servicios WHERE sede_id = ?",
            (sede_id,),
        ).fetchone()["n"]
        meta_payload = {
            "alcance": "sede",
            "ID_sede": meta["ID_sede"],
            "name_sede": meta["name_sede"],
            "ID_Empresa": meta["ID_Empresa"],
            "ID_NIT": meta["ID_NIT"],
            "servicios_n": int(servicios_n),
            "empresa_id": meta["empresa_id"],
            "sede_id": meta["sede_id"],
        }
        rows = _ficha_inventario_rows(emp_conn, sede_id=sede_id)

    code = meta_payload.get("ID_sede") or str(sede_id)
    return _inventario_pdf_response(
        meta_payload, rows, user, f"inventario_sede_{code}.pdf"
    )


@org_bp.get("/empresas/<int:empresa_id>/personal")
@login_required
@permission_required("assign_sede_coordinators", "view_all_empresas", "create_empresa")
def list_empresa_personal(empresa_id):
    """Personal de la empresa (excluye ADMIN)."""
    actor = current_user()
    with get_empresas_connection() as emp_conn, get_users_connection() as users_conn:
        if not can_access_empresa(emp_conn, actor, empresa_id):
            return jsonify({"ok": False, "error": "Fuera de tu empresa."}), 403
        empresa = emp_conn.execute(
            "SELECT id FROM empresas WHERE id = ?", (empresa_id,)
        ).fetchone()
        if not empresa:
            return jsonify({"ok": False, "error": "Empresa no encontrada."}), 404
        rows = users_conn.execute(
            """
            SELECT id_usuario, usuario_login, NAME_USER, LAST_NAME_USER, JOB, ROLL, empresa_id
            FROM usuarios
            WHERE empresa_id = ? AND ROLL != 'ADMIN'
            ORDER BY LAST_NAME_USER COLLATE NOCASE, NAME_USER COLLATE NOCASE
            """,
            (empresa_id,),
        ).fetchall()
    personal = [
        {
            "id_usuario": r["id_usuario"],
            "usuario_login": r["usuario_login"],
            "NAME_USER": r["NAME_USER"],
            "LAST_NAME_USER": r["LAST_NAME_USER"],
            "JOB": r["JOB"],
            "ROLL": r["ROLL"],
            "empresa_id": r["empresa_id"],
        }
        for r in rows
    ]
    return jsonify({"ok": True, "personal": personal})


@org_bp.get("/sedes/<int:sede_id>/personal")
@login_required
@permission_required(
    "assign_sede_coordinators",
    "view_all_empresas",
    "view_sedes",
    "create_empresa",
)
def list_sede_personal(sede_id):
    """Personas asignadas a la sede (usuario_sedes) con rol/cargo."""
    actor = current_user()
    with get_empresas_connection() as emp_conn, get_users_connection() as users_conn:
        if not can_access_sede(actor, sede_id, users_conn=users_conn):
            return jsonify({"ok": False, "error": "Sin acceso a la sede."}), 403
        sede = emp_conn.execute(
            "SELECT id, ID_sede, name_sede, empresa_id FROM sedes WHERE id = ?",
            (sede_id,),
        ).fetchone()
        if not sede:
            return jsonify({"ok": False, "error": "Sede no encontrada."}), 404
        rows = users_conn.execute(
            """
            SELECT u.id_usuario, u.usuario_login, u.NAME_USER, u.LAST_NAME_USER,
                   u.JOB, u.ROLL, us.assigned_at
            FROM usuario_sedes us
            JOIN usuarios u ON u.id_usuario = us.usuario_id
            WHERE us.sede_id = ?
              AND u.empresa_id = ?
            ORDER BY u.LAST_NAME_USER COLLATE NOCASE, u.NAME_USER COLLATE NOCASE
            """,
            (sede_id, sede["empresa_id"]),
        ).fetchall()
        # Limpia vínculos cruzados residuales (usuario cambió de empresa).
        users_conn.execute(
            """
            DELETE FROM usuario_sedes
            WHERE sede_id = ?
              AND usuario_id IN (
                SELECT id_usuario FROM usuarios
                WHERE empresa_id IS NULL OR empresa_id != ?
              )
            """,
            (sede_id, sede["empresa_id"]),
        )
        users_conn.commit()
    personal = [
        {
            "id_usuario": r["id_usuario"],
            "usuario_login": r["usuario_login"],
            "NAME_USER": r["NAME_USER"],
            "LAST_NAME_USER": r["LAST_NAME_USER"],
            "JOB": r["JOB"],
            "ROLL": r["ROLL"],
            "assigned_at": r["assigned_at"],
        }
        for r in rows
    ]
    return jsonify(
        {
            "ok": True,
            "sede": {
                "id": sede["id"],
                "ID_sede": sede["ID_sede"],
                "name_sede": sede["name_sede"],
                "empresa_id": sede["empresa_id"],
            },
            "personal": personal,
        }
    )


@org_bp.post("/sedes/<int:sede_id>/asignar-personal")
@login_required
@permission_required("assign_sede_coordinators")
def assign_personal(sede_id):
    """Asigna cualquier usuario de la misma empresa a la sede."""
    body = request.get_json(silent=True) or {}
    try:
        usuario_id = int(body.get("usuario_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "usuario_id inválido."}), 400

    actor = current_user()
    with get_empresas_connection() as emp_conn, get_users_connection() as users_conn:
        sede = emp_conn.execute(
            "SELECT id, empresa_id FROM sedes WHERE id = ?", (sede_id,)
        ).fetchone()
        if not sede:
            return jsonify({"ok": False, "error": "Sede no encontrada."}), 404
        if not can_access_empresa(emp_conn, actor, sede["empresa_id"]):
            return jsonify({"ok": False, "error": "Fuera de tu empresa."}), 403
        user = users_conn.execute(
            """
            SELECT id_usuario, ROLL, JOB, empresa_id, NAME_USER, LAST_NAME_USER
            FROM usuarios WHERE id_usuario = ?
            """,
            (usuario_id,),
        ).fetchone()
        if not user:
            return jsonify({"ok": False, "error": "Usuario no encontrado."}), 404
        if user["ROLL"] == "ADMIN":
            return jsonify(
                {"ok": False, "error": "No se asigna el Administrador a sedes."}
            ), 400
        ok_same, err_msg = user_belongs_to_sede_empresa(user, sede["empresa_id"])
        if not ok_same:
            return jsonify({"ok": False, "error": err_msg}), 400
        # Por si quedaron sedes de una empresa anterior, alinear antes de insertar.
        clear_sede_assignments_outside_empresa(
            users_conn, usuario_id, sede["empresa_id"]
        )
        users_conn.execute(
            """
            INSERT OR IGNORE INTO usuario_sedes (usuario_id, sede_id, assigned_by, assigned_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (usuario_id, sede_id, actor["id_usuario"]),
        )
        users_conn.commit()
        nombre = f"{user['NAME_USER']} {user['LAST_NAME_USER']}".strip()
    return jsonify(
        {
            "ok": True,
            "message": f"{nombre} ({user['JOB']}) asignado a la sede.",
        }
    )


@org_bp.post("/sedes/<int:sede_id>/asignar-coordinador")
@login_required
@permission_required("assign_sede_coordinators")
def assign_coordinator(sede_id):
    """Compatibilidad: redirige a asignación de personal."""
    return assign_personal(sede_id)
