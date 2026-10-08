"""Lógica RBAC: Roles, Jobs (módulos) y matriz de permisos."""

from __future__ import annotations

ADMIN_ROLE_NAME = "Administrador"

DEFAULT_ROLES = [
    {"nombre_rol": "Administrador", "protegido": 1, "estado": "ACTIVO"},
    {"nombre_rol": "Director operativo", "protegido": 0, "estado": "ACTIVO"},
    {"nombre_rol": "Coordinación", "protegido": 0, "estado": "ACTIVO"},
    {"nombre_rol": "Ingeniería", "protegido": 0, "estado": "ACTIVO"},
    {"nombre_rol": "Soporte", "protegido": 0, "estado": "ACTIVO"},
    {"nombre_rol": "Director asistencial", "protegido": 0, "estado": "ACTIVO"},
    {"nombre_rol": "Coordinador asistencial", "protegido": 0, "estado": "ACTIVO"},
]

# Catálogo de módulos. codigo_permiso = clave primaria en ALL_PERMISSIONS
# (un módulo puede mapear a varios permisos vía JOB_PERMISSIONS).
DEFAULT_JOBS = [
    {
        "nombre_job": "Gestión de usuarios",
        "descripcion": "Alta, edición y baja de cuentas de usuario.",
        "icono": "users",
        "codigo_permiso": "manage_users",
    },
    {
        "nombre_job": "Visualización de reportes",
        "descripcion": "Consulta de reportes e indicadores del sistema.",
        "icono": "chart",
        "codigo_permiso": "view_indicators_report",
    },
    {
        "nombre_job": "Edición de datos clínicos",
        "descripcion": "Modificación de información clínica asociada.",
        "icono": "clinical",
        "codigo_permiso": "modify_inventory",
    },
    {
        "nombre_job": "Acceso a base de datos",
        "descripcion": "Consulta avanzada sobre datos persistidos.",
        "icono": "database",
        "codigo_permiso": "view_inventory",
    },
    {
        "nombre_job": "Configuración del sistema",
        "descripcion": "Ajustes de empresa y parámetros institucionales.",
        "icono": "settings",
        "codigo_permiso": "modify_empresa",
    },
    {
        "nombre_job": "Exportación de datos",
        "descripcion": "Descarga de inventarios, listados y reportes.",
        "icono": "export",
        "codigo_permiso": "export_inventory",
    },
    {
        "nombre_job": "Importación de inventario",
        "descripcion": "Carga masiva de inventario biomédico.",
        "icono": "import",
        "codigo_permiso": "import_inventory",
    },
    {
        "nombre_job": "Módulo de ingeniería",
        "descripcion": "Funciones operativas del área de ingeniería (inventario y sedes). No abre instrumentos: actívelos uno a uno.",
        "icono": "engineering",
        "codigo_permiso": None,
    },
    {
        "nombre_job": "Módulo de soporte",
        "descripcion": "Herramientas de atención y soporte técnico.",
        "icono": "support",
        "codigo_permiso": "view_sedes",
    },
    {
        "nombre_job": "Módulo asistencial",
        "descripcion": "Perfil asistencial. No abre módulos por sí mismo: active Inventario o Suficiencia por separado.",
        "icono": "asistencial",
        "codigo_permiso": None,
    },
    {
        "nombre_job": "Reporte final de indicadores",
        "descripcion": "Visualización del reporte final de indicadores asistenciales.",
        "icono": "indicators",
        "codigo_permiso": "view_indicators_report",
    },
    {
        "nombre_job": "Visualización de inventarios y sedes",
        "descripcion": "Consulta de sedes e inventario biomédico, incluida la descarga en plantilla PDF.",
        "icono": "inventory",
        "codigo_permiso": "view_inventory",
    },
    {
        "nombre_job": "Alcance por empresa",
        "descripcion": "La visión de datos se limita a la empresa asignada al usuario. Solo el administrador ve todas las empresas.",
        "icono": "company",
        "codigo_permiso": None,
    },
    {
        "nombre_job": "Procesos asistenciales",
        "descripcion": "Agregar información propia de los procesos asistenciales.",
        "icono": "process",
        "codigo_permiso": "manage_asistencial_processes",
    },
    {
        "nombre_job": "Gestión de personal asistencial",
        "descripcion": "Agregar o eliminar personal asistencial y modificar cargo.",
        "icono": "staff",
        "codigo_permiso": "manage_asistencial_users",
    },
    {
        "nombre_job": "Indicadores operativos",
        "descripcion": "Acceso a indicadores del módulo operativo.",
        "icono": "indicators",
        "codigo_permiso": "view_indicators_report",
    },
    {
        "nombre_job": "Edición de JOBS",
        "descripcion": "Editar cargos/JOBS del sistema (excepto Administrador).",
        "icono": "jobs",
        "codigo_permiso": "manage_jobs",
    },
    {
        "nombre_job": "Personal de sedes",
        "descripcion": "Asignar o modificar el personal de las sedes.",
        "icono": "staff",
        "codigo_permiso": "assign_sede_coordinators",
    },
    {
        "nombre_job": "Agregar empresa",
        "descripcion": "Permite crear empresas nuevas en el aplicativo.",
        "icono": "company",
        "codigo_permiso": "create_empresa",
    },
    {
        "nombre_job": "Crear y modificar sedes",
        "descripcion": "Alta y edición de sedes y servicios.",
        "icono": "sede",
        "codigo_permiso": "create_sede",
    },
    {
        "nombre_job": "Acceso a servicio específico",
        "descripcion": "Visualización y tratamiento de la información de un servicio concreto dentro de una sede.",
        "icono": "servicio",
        "codigo_permiso": "access_servicio",
    },
    {
        "nombre_job": "Tablero de forma de adquisición",
        "descripcion": "Seguimiento de equipos en comodato/leasing y solicitudes de modalidad de adquisición. Solo Coordinador y Director operativo.",
        "icono": "acquisition",
        "codigo_permiso": "view_adquisicion_dashboard",
    },
    {
        "nombre_job": "Dimensionamiento de la empresa",
        "descripcion": "Dashboard consolidado de todas las sedes y plantilla de ingenieros clínicos por criticidad. Administrador, Coordinador y Director operativo.",
        "icono": "staffing",
        "codigo_permiso": "view_dimensionamiento_empresa",
    },
    {
        "nombre_job": "Aprobar solicitudes",
        "descripcion": "Aprobar o rechazar solicitudes de permisos ampliados.",
        "icono": "approve",
        "codigo_permiso": "approve_expanded_permissions",
    },
    {
        "nombre_job": "Solicitar permisos ampliados",
        "descripcion": "Enviar solicitudes de ampliación de permisos.",
        "icono": "request",
        "codigo_permiso": "request_expanded_permissions",
    },
    {
        "nombre_job": "Suficiencia de equipos",
        "descripcion": "Consulta del instrumento de suficiencia (independiente de los demás instrumentos).",
        "icono": "sufficiency",
        "codigo_permiso": "view_suficiencia",
    },
    {
        "nombre_job": "Dimensionamiento de personal",
        "descripcion": "Cálculo y dimensionamiento de personal técnico (módulo independiente).",
        "icono": "staffing",
        "codigo_permiso": "view_dimensionamiento",
    },
    {
        "nombre_job": "Frecuencia de mantenimiento preventivo",
        "descripcion": "Instrumento OMS + Fabricante + GE para frecuencia y cronograma de PM (módulo independiente).",
        "icono": "acquisition",
        "codigo_permiso": "view_frecuencia_pm",
    },
    {
        "nombre_job": "Preinstalación de la tecnología biomédica",
        "descripcion": "Verificación de sitio (SITIO) antes de instalar tecnología biomédica (módulo independiente).",
        "icono": "preinstalacion",
        "codigo_permiso": "view_preinstalacion",
    },
    {
        "nombre_job": "KPIs de ingeniería clínica",
        "descripcion": "Tablero de KPIs de ingeniería clínica (módulo independiente).",
        "icono": "kpis",
        "codigo_permiso": "view_kpis",
    },
    {
        "nombre_job": "Instrumento CAPEX",
        "descripcion": "Evaluación de inversión de capital (CAPEX) (módulo independiente).",
        "icono": "capex",
        "codigo_permiso": "view_capex",
    },
    {
        "nombre_job": "Actualizar datos de suficiencia",
        "descripcion": "Captura asistencial de capacidad, concurrencia y demanda.",
        "icono": "sufficiency",
        "codigo_permiso": "edit_suficiencia_asistencial",
    },
    {
        "nombre_job": "Solicitar actualización de suficiencia",
        "descripcion": "Solicitar al rol asistencial actualización de datos de suficiencia.",
        "icono": "request",
        "codigo_permiso": "request_suficiencia_update",
    },
]

# Un módulo puede conceder varios permisos atómicos.
JOB_PERMISSIONS: dict[str, set[str]] = {
    "Gestión de usuarios": {"manage_users"},
    "Visualización de reportes": {"view_indicators_report"},
    "Edición de datos clínicos": {"modify_inventory"},
    "Acceso a base de datos": {"view_sedes", "view_inventory"},
    "Configuración del sistema": {"modify_empresa"},
    "Exportación de datos": {"export_inventory"},
    "Importación de inventario": {"import_inventory"},
    "Módulo de ingeniería": {
        "view_sedes",
        "view_inventory",
        "modify_inventory",
    },
    "Módulo de soporte": {"view_sedes", "view_inventory"},
    "Módulo asistencial": set(),
    "Reporte final de indicadores": {"view_indicators_report"},
    "Visualización de inventarios y sedes": {"view_sedes", "view_inventory"},
    "Alcance por empresa": set(),
    "Procesos asistenciales": {"manage_asistencial_processes"},
    "Gestión de personal asistencial": {"manage_asistencial_users"},
    "Indicadores operativos": {"view_indicators_report"},
    "Edición de JOBS": {"manage_jobs"},
    "Personal de sedes": {"assign_sede_coordinators"},
    "Agregar empresa": {"create_empresa", "delete_empresa"},
    "Crear y modificar sedes": {
        "create_sede",
        "create_servicio",
        "modify_sede",
        "modify_servicio",
        "delete_sede",
        "delete_servicio",
    },
    "Acceso a servicio específico": {
        "access_servicio",
        "view_inventory",
        "modify_inventory",
    },
    "Tablero de forma de adquisición": {"view_adquisicion_dashboard"},
    "Dimensionamiento de la empresa": {"view_dimensionamiento_empresa"},
    "Aprobar solicitudes": {"approve_expanded_permissions"},
    "Solicitar permisos ampliados": {"request_expanded_permissions"},
    "Suficiencia de equipos": {"view_suficiencia"},
    "Dimensionamiento de personal": {"view_dimensionamiento"},
    "Frecuencia de mantenimiento preventivo": {"view_frecuencia_pm"},
    "Preinstalación de la tecnología biomédica": {"view_preinstalacion"},
    "KPIs de ingeniería clínica": {"view_kpis", "view_respaldo"},
    "Cálculo de equipos de respaldo": {"view_kpis", "view_respaldo"},
    "Instrumento CAPEX": {"view_capex"},
    "Actualizar datos de suficiencia": {
        "edit_suficiencia_asistencial",
        "view_suficiencia",
    },
    "Solicitar actualización de suficiencia": {
        "request_suficiencia_update",
        "view_suficiencia",
    },
}

INSTRUMENT_JOBS = {
    "Suficiencia de equipos",
    "Dimensionamiento de personal",
    "Frecuencia de mantenimiento preventivo",
    "Preinstalación de la tecnología biomédica",
    "KPIs de ingeniería clínica",
    "Instrumento CAPEX",
}

# Matriz inicial: rol RBAC → jobs activos (por nombre)
DEFAULT_MATRIX = {
    "Administrador": {j["nombre_job"] for j in DEFAULT_JOBS},
    "Director operativo": {
        "Gestión de usuarios",
        "Visualización de reportes",
        "Edición de datos clínicos",
        "Acceso a base de datos",
        "Configuración del sistema",
        "Exportación de datos",
        "Importación de inventario",
        "Módulo de ingeniería",
        "Módulo de soporte",
        "Módulo asistencial",
        "Reporte final de indicadores",
        "Visualización de inventarios y sedes",
        "Alcance por empresa",
        "Procesos asistenciales",
        "Gestión de personal asistencial",
        "Indicadores operativos",
        "Edición de JOBS",
        "Personal de sedes",
        "Crear y modificar sedes",
        "Acceso a servicio específico",
        "Tablero de forma de adquisición",
        "Dimensionamiento de la empresa",
        "Aprobar solicitudes",
        "Solicitar actualización de suficiencia",
        *INSTRUMENT_JOBS,
    },
    "Coordinación": {
        "Gestión de usuarios",
        "Visualización de reportes",
        "Exportación de datos",
        "Edición de datos clínicos",
        "Visualización de inventarios y sedes",
        "Alcance por empresa",
        "Agregar empresa",
        "Crear y modificar sedes",
        "Configuración del sistema",
        "Aprobar solicitudes",
        "Tablero de forma de adquisición",
        "Dimensionamiento de la empresa",
        "Solicitar actualización de suficiencia",
        *INSTRUMENT_JOBS,
    },
    "Ingeniería": {
        "Visualización de reportes",
        "Módulo de ingeniería",
        "Exportación de datos",
        "Edición de datos clínicos",
        "Visualización de inventarios y sedes",
        # create/modify empresa-sede: solo tras permisos ampliados (overlay de sesión)
        "Solicitar permisos ampliados",
        "Solicitar actualización de suficiencia",
        "Tablero de forma de adquisición",
        *INSTRUMENT_JOBS,
    },
    "Soporte": {
        "Visualización de reportes",
        "Módulo de soporte",
        "Visualización de inventarios y sedes",
    },
    "Director asistencial": {
        "Módulo asistencial",
        "Reporte final de indicadores",
        "Visualización de inventarios y sedes",
        "Alcance por empresa",
        "Procesos asistenciales",
        "Gestión de personal asistencial",
        "Actualizar datos de suficiencia",
        "Suficiencia de equipos",
        "Preinstalación de la tecnología biomédica",
        "Frecuencia de mantenimiento preventivo",
    },
    "Coordinador asistencial": {
        "Módulo asistencial",
        "Visualización de inventarios y sedes",
        "Alcance por empresa",
        "Procesos asistenciales",
        "Actualizar datos de suficiencia",
    },
}

# ROLL + JOB de usuario → nombre canónico de rol en matriz RBAC
USER_TO_RBAC_ROLE = {
    ("ADMIN", "Administrador"): "Administrador",
    ("OPERATIVO", "Director Operativo"): "Director operativo",
    ("OPERATIVO", "Dirección"): "Director operativo",
    ("OPERATIVO", "Coordinador"): "Coordinación",
    ("OPERATIVO", "Ingeniero"): "Ingeniería",
    ("OPERATIVO", "Técnico"): "Soporte",
    ("ASISTENCIAL", "Director"): "Director asistencial",
    ("ASISTENCIAL", "Dirección"): "Director asistencial",
    ("ASISTENCIAL", "Coordinador"): "Coordinador asistencial",
    ("ASISTENCIAL", "Líder"): "Coordinador asistencial",
}

# Alias por si el admin renombró el rol en la UI
RBAC_ROLE_ALIASES = {
    "Administrador": ("Administrador",),
    "Director operativo": ("Director operativo", "Director Operativo"),
    "Coordinación": ("Coordinación", "Coordinacion", "Coordinador Operativo"),
    "Ingeniería": ("Ingeniería", "Ingenieria"),
    "Soporte": ("Soporte",),
    "Director asistencial": ("Director asistencial",),
    "Coordinador asistencial": ("Coordinador asistencial",),
}

# Jobs nuevos del catálogo cuyas celdas deben alinearse a DEFAULT_MATRIX
NEW_CAPABILITY_JOBS = {
    "Agregar empresa",
    "Crear y modificar sedes",
    "Importación de inventario",
    "Aprobar solicitudes",
    "Solicitar permisos ampliados",
    "Actualizar datos de suficiencia",
    "Solicitar actualización de suficiencia",
    "Preinstalación de la tecnología biomédica",
    "Acceso a servicio específico",
    "Tablero de forma de adquisición",
    "Dimensionamiento de la empresa",
}


def resolve_rbac_role_name(roll: str, job: str) -> str | None:
    if roll == "ADMIN":
        return ADMIN_ROLE_NAME
    return USER_TO_RBAC_ROLE.get((roll, job))


def find_role_by_canonical(conn, canonical_name: str):
    aliases = RBAC_ROLE_ALIASES.get(canonical_name, (canonical_name,))
    for alias in aliases:
        row = conn.execute(
            """
            SELECT * FROM Roles WHERE nombre_rol = ? COLLATE NOCASE
            """,
            (alias,),
        ).fetchone()
        if row:
            return row
    return None


def permissions_for_job_name(nombre_job: str, codigo_permiso: str | None = None) -> set[str]:
    mapped = set(JOB_PERMISSIONS.get(nombre_job) or set())
    if codigo_permiso:
        mapped.add(codigo_permiso)
    return mapped


def _role_payload(row):
    return {
        "id_rol": row["id_rol"],
        "nombre_rol": row["nombre_rol"],
        "estado": row["estado"],
        "protegido": bool(row["protegido"]),
        "creation_date": row["creation_date"] if "creation_date" in row.keys() else None,
    }


def _job_payload(row):
    keys = row.keys() if hasattr(row, "keys") else []
    codigo = row["codigo_permiso"] if "codigo_permiso" in keys else None
    return {
        "id_job": row["id_job"],
        "nombre_job": row["nombre_job"],
        "descripcion": row["descripcion"],
        "icono": row["icono"] if "icono" in keys else None,
        "estado": row["estado"],
        "codigo_permiso": codigo,
        "creation_date": row["creation_date"] if "creation_date" in keys else None,
    }


def _sync_job_codigo(conn, job_def: dict):
    """Actualiza codigo_permiso / descripción de un job existente del catálogo."""
    codigo = job_def.get("codigo_permiso")
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(Jobs)").fetchall()}
    if "codigo_permiso" in cols:
        conn.execute(
            """
            UPDATE Jobs
            SET descripcion = ?, icono = ?, codigo_permiso = ?
            WHERE nombre_job = ? COLLATE NOCASE
            """,
            (
                job_def["descripcion"],
                job_def["icono"],
                codigo,
                job_def["nombre_job"],
            ),
        )
    else:
        conn.execute(
            """
            UPDATE Jobs SET descripcion = ?, icono = ?
            WHERE nombre_job = ? COLLATE NOCASE
            """,
            (job_def["descripcion"], job_def["icono"], job_def["nombre_job"]),
        )


def _upsert_defaults(conn):
    """Siembra roles/jobs; agrega módulos nuevos del catálogo si faltan."""
    role_count = conn.execute("SELECT COUNT(*) AS c FROM Roles").fetchone()["c"]
    if role_count == 0:
        for role in DEFAULT_ROLES:
            conn.execute(
                """
                INSERT INTO Roles (nombre_rol, estado, protegido, creation_date)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (role["nombre_rol"], role["estado"], role["protegido"]),
            )
    else:
        admin = conn.execute(
            "SELECT id_rol FROM Roles WHERE nombre_rol = ? COLLATE NOCASE",
            (ADMIN_ROLE_NAME,),
        ).fetchone()
        if not admin:
            protected = next(
                (r for r in DEFAULT_ROLES if r["nombre_rol"] == ADMIN_ROLE_NAME),
                {"nombre_rol": ADMIN_ROLE_NAME, "estado": "ACTIVO", "protegido": 1},
            )
            conn.execute(
                """
                INSERT INTO Roles (nombre_rol, estado, protegido, creation_date)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (protected["nombre_rol"], protected["estado"], protected["protegido"]),
            )

    cols = {c["name"] for c in conn.execute("PRAGMA table_info(Jobs)").fetchall()}
    has_codigo = "codigo_permiso" in cols

    for job in DEFAULT_JOBS:
        exists = conn.execute(
            "SELECT id_job FROM Jobs WHERE nombre_job = ? COLLATE NOCASE",
            (job["nombre_job"],),
        ).fetchone()
        if exists:
            _sync_job_codigo(conn, job)
            continue
        if has_codigo:
            conn.execute(
                """
                INSERT INTO Jobs (
                    nombre_job, descripcion, icono, codigo_permiso, estado, creation_date
                ) VALUES (?, ?, ?, ?, 'ACTIVO', datetime('now'))
                """,
                (
                    job["nombre_job"],
                    job["descripcion"],
                    job["icono"],
                    job.get("codigo_permiso"),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO Jobs (nombre_job, descripcion, icono, estado, creation_date)
                VALUES (?, ?, ?, 'ACTIVO', datetime('now'))
                """,
                (job["nombre_job"], job["descripcion"], job["icono"]),
            )

    roles_by_name = {
        r["nombre_rol"]: r["id_rol"]
        for r in conn.execute("SELECT id_rol, nombre_rol FROM Roles").fetchall()
    }
    jobs = {
        j["nombre_job"]: j["id_job"]
        for j in conn.execute("SELECT id_job, nombre_job FROM Jobs").fetchall()
    }

    for role_name, job_names in DEFAULT_MATRIX.items():
        role_row = find_role_by_canonical(conn, role_name)
        role_id = role_row["id_rol"] if role_row else roles_by_name.get(role_name)
        if not role_id:
            continue
        for job_name, job_id in jobs.items():
            exists = conn.execute(
                """
                SELECT id_permiso, permiso_activo FROM Permisos
                WHERE id_rol = ? AND id_job = ?
                """,
                (role_id, job_id),
            ).fetchone()
            desired = 1 if (role_name == ADMIN_ROLE_NAME or job_name in job_names) else 0
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, ?)
                """,
                (role_id, job_id, desired),
            )

    _align_new_capability_defaults(conn)


def _canonical_for_role_name(nombre_rol: str) -> str | None:
    needle = (nombre_rol or "").casefold()
    for canonical, aliases in RBAC_ROLE_ALIASES.items():
        if needle in {a.casefold() for a in aliases}:
            return canonical
    if nombre_rol in DEFAULT_MATRIX:
        return nombre_rol
    return None


def _align_new_capability_defaults(conn, *, force: bool = False):
    """
    Inserta celdas faltantes de módulos nuevos según DEFAULT_MATRIX.
    Con force=True (migración única) también corrige permiso_activo=0 heredado
    de seeds previos que no resolvían aliases de rol.
    """
    jobs = {
        j["nombre_job"]: j["id_job"]
        for j in conn.execute("SELECT id_job, nombre_job FROM Jobs").fetchall()
    }
    for canonical, job_names in DEFAULT_MATRIX.items():
        role = find_role_by_canonical(conn, canonical)
        if not role:
            continue
        for job_name in job_names:
            if job_name not in NEW_CAPABILITY_JOBS:
                continue
            job_id = jobs.get(job_name)
            if not job_id:
                continue
            exists = conn.execute(
                """
                SELECT id_permiso, permiso_activo FROM Permisos
                WHERE id_rol = ? AND id_job = ?
                """,
                (role["id_rol"], job_id),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                    VALUES (?, ?, 1)
                    """,
                    (role["id_rol"], job_id),
                )
            elif force and not exists["permiso_activo"]:
                conn.execute(
                    "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                    (exists["id_permiso"],),
                )


def align_new_capability_defaults_force(conn):
    """Migración única: corrige defaults de capacidades nuevas en roles alias."""
    _align_new_capability_defaults(conn, force=True)


def _enable_access_servicio_defaults(conn, *, force: bool = False):
    """Administrador y Dirección (Operativa) reciben Acceso a servicio específico."""
    job = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Acceso a servicio específico' COLLATE NOCASE
        """
    ).fetchone()
    if not job:
        return
    for canonical in (ADMIN_ROLE_NAME, "Director operativo"):
        role = find_role_by_canonical(conn, canonical)
        if not role:
            continue
        exists = conn.execute(
            """
            SELECT id_permiso, permiso_activo FROM Permisos
            WHERE id_rol = ? AND id_job = ?
            """,
            (role["id_rol"], job["id_job"]),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, 1)
                """,
                (role["id_rol"], job["id_job"]),
            )
        elif force and not exists["permiso_activo"]:
            conn.execute(
                "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                (exists["id_permiso"],),
            )


def _enable_adquisicion_tablero_defaults(conn, *, force: bool = False):
    """Director operativo y Coordinación reciben el tablero de forma de adquisición."""
    job = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Tablero de forma de adquisición' COLLATE NOCASE
        """
    ).fetchone()
    if not job:
        return
    for canonical in (ADMIN_ROLE_NAME, "Director operativo", "Coordinación"):
        role = find_role_by_canonical(conn, canonical)
        if not role:
            continue
        exists = conn.execute(
            """
            SELECT id_permiso, permiso_activo FROM Permisos
            WHERE id_rol = ? AND id_job = ?
            """,
            (role["id_rol"], job["id_job"]),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, 1)
                """,
                (role["id_rol"], job["id_job"]),
            )
        elif force and not exists["permiso_activo"]:
            conn.execute(
                "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                (exists["id_permiso"],),
            )


def _enable_dim_empresa_defaults(conn, *, force: bool = False):
    """Director operativo y Coordinación reciben el dashboard empresarial."""
    job = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Dimensionamiento de la empresa' COLLATE NOCASE
        """
    ).fetchone()
    if not job:
        return
    for canonical in (ADMIN_ROLE_NAME, "Director operativo", "Coordinación"):
        role = find_role_by_canonical(conn, canonical)
        if not role:
            continue
        exists = conn.execute(
            """
            SELECT id_permiso, permiso_activo FROM Permisos
            WHERE id_rol = ? AND id_job = ?
            """,
            (role["id_rol"], job["id_job"]),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, 1)
                """,
                (role["id_rol"], job["id_job"]),
            )
        elif force and not exists["permiso_activo"]:
            conn.execute(
                "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                (exists["id_permiso"],),
            )


def _revoke_ingenieria_sede_edit_defaults(conn):
    """
    Ingeniería no edita empresa/sede de fábrica: ese extra es el overlay
    de permisos ampliados (bandeja → Activar). La matriz RBAC antigua
    incluía «Crear y modificar sedes» y saltaba ese flujo.
    """
    role = find_role_by_canonical(conn, "Ingeniería")
    if not role:
        return
    for job_name in ("Crear y modificar sedes", "Agregar empresa"):
        job = conn.execute(
            "SELECT id_job FROM Jobs WHERE nombre_job = ? COLLATE NOCASE",
            (job_name,),
        ).fetchone()
        if not job:
            continue
        conn.execute(
            """
            UPDATE Permisos SET permiso_activo = 0
            WHERE id_rol = ? AND id_job = ? AND permiso_activo = 1
            """,
            (role["id_rol"], job["id_job"]),
        )


def _revoke_asistencial_coord_engineering_suite(conn):
    """
    Migración única: el Coordinador/Líder asistencial partía con instrumentos
    de ingeniería encendidos en bloque. Tras esto, el admin puede activarlos
    uno a uno en Roles y permisos.
    """
    role = find_role_by_canonical(conn, "Coordinador asistencial")
    if not role:
        return
    for job_name in (
        "Preinstalación de la tecnología biomédica",
        "Suficiencia de equipos",
        "Dimensionamiento de personal",
        "Frecuencia de mantenimiento preventivo",
        "KPIs de ingeniería clínica",
        "Cálculo de equipos de respaldo",
        "Instrumento CAPEX",
        "Módulo de ingeniería",
        "Solicitar actualización de suficiencia",
    ):
        job = conn.execute(
            "SELECT id_job FROM Jobs WHERE nombre_job = ? COLLATE NOCASE",
            (job_name,),
        ).fetchone()
        if not job:
            continue
        conn.execute(
            """
            UPDATE Permisos SET permiso_activo = 0
            WHERE id_rol = ? AND id_job = ? AND permiso_activo = 1
            """,
            (role["id_rol"], job["id_job"]),
        )


def enable_uat_instrument_defaults(conn) -> None:
    """
    Enciende, una sola vez, los módulos que el acta UAT pide y que la matriz
    dejó en 0 aunque DEFAULT_MATRIX ya los incluye.
    No reactiva la suite de ingeniería del Coordinador asistencial.
    """
    wanted = {
        "Director operativo": (
            "Suficiencia de equipos",
            "Dimensionamiento de personal",
            "Frecuencia de mantenimiento preventivo",
            "Preinstalación de la tecnología biomédica",
            "KPIs de ingeniería clínica",
        ),
        "Ingeniería": (
            "Preinstalación de la tecnología biomédica",
            "Tablero de forma de adquisición",
            "Visualización de inventarios y sedes",
        ),
        "Director asistencial": (
            "Preinstalación de la tecnología biomédica",
            "Frecuencia de mantenimiento preventivo",
            "Suficiencia de equipos",
        ),
        "Soporte": ("Visualización de inventarios y sedes",),
    }
    jobs = {
        j["nombre_job"]: j["id_job"]
        for j in conn.execute("SELECT id_job, nombre_job FROM Jobs").fetchall()
    }
    for canonical, job_names in wanted.items():
        role = find_role_by_canonical(conn, canonical)
        if not role:
            continue
        for job_name in job_names:
            job_id = jobs.get(job_name)
            if not job_id:
                continue
            exists = conn.execute(
                """
                SELECT id_permiso, permiso_activo FROM Permisos
                WHERE id_rol = ? AND id_job = ?
                """,
                (role["id_rol"], job_id),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                    VALUES (?, ?, 1)
                    """,
                    (role["id_rol"], job_id),
                )
            elif not exists["permiso_activo"]:
                conn.execute(
                    "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                    (exists["id_permiso"],),
                )


def ensure_rbac_seed(conn):
    """Siembra Roles, Jobs y Permisos; también agrega faltantes en BD existentes."""
    # Renombre AMFE → Preinstalación de la tecnología biomédica.
    old_amfe = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Instrumento AMFE' COLLATE NOCASE
        """
    ).fetchone()
    new_pre = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Preinstalación de la tecnología biomédica' COLLATE NOCASE
        """
    ).fetchone()
    if old_amfe and new_pre and old_amfe["id_job"] != new_pre["id_job"]:
        old_cells = conn.execute(
            "SELECT id_rol, permiso_activo FROM Permisos WHERE id_job = ?",
            (old_amfe["id_job"],),
        ).fetchall()
        for cell in old_cells:
            exists = conn.execute(
                "SELECT id_permiso FROM Permisos WHERE id_rol = ? AND id_job = ?",
                (cell["id_rol"], new_pre["id_job"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                    VALUES (?, ?, ?)
                    """,
                    (cell["id_rol"], new_pre["id_job"], cell["permiso_activo"]),
                )
        conn.execute("DELETE FROM Permisos WHERE id_job = ?", (old_amfe["id_job"],))
        conn.execute("DELETE FROM Jobs WHERE id_job = ?", (old_amfe["id_job"],))
    elif old_amfe and not new_pre:
        conn.execute(
            """
            UPDATE Jobs
            SET nombre_job = 'Preinstalación de la tecnología biomédica',
                descripcion = 'Verificación de sitio (SITIO) antes de instalar tecnología biomédica.',
                icono = 'preinstalacion'
            WHERE id_job = ?
            """,
            (old_amfe["id_job"],),
        )

    # Renombre del instrumento (antes Evaluación de adquisición).
    old = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Evaluación de adquisición de tecnología' COLLATE NOCASE
        """
    ).fetchone()
    new = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Frecuencia de mantenimiento preventivo' COLLATE NOCASE
        """
    ).fetchone()
    if old and new:
        # Ya existe el nuevo nombre: mover celdas de permisos y borrar el antiguo.
        old_cells = conn.execute(
            "SELECT id_rol, permiso_activo FROM Permisos WHERE id_job = ?",
            (old["id_job"],),
        ).fetchall()
        for cell in old_cells:
            exists = conn.execute(
                "SELECT id_permiso FROM Permisos WHERE id_rol = ? AND id_job = ?",
                (cell["id_rol"], new["id_job"]),
            ).fetchone()
            if exists:
                if cell["permiso_activo"]:
                    conn.execute(
                        "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                        (exists["id_permiso"],),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                    VALUES (?, ?, ?)
                    """,
                    (cell["id_rol"], new["id_job"], cell["permiso_activo"]),
                )
        conn.execute("DELETE FROM Permisos WHERE id_job = ?", (old["id_job"],))
        conn.execute("DELETE FROM Jobs WHERE id_job = ?", (old["id_job"],))
    elif old and not new:
        conn.execute(
            """
            UPDATE Jobs
            SET nombre_job = 'Frecuencia de mantenimiento preventivo',
                descripcion = 'Instrumento OMS + Fabricante + GE para frecuencia y cronograma de PM.'
            WHERE id_job = ?
            """,
            (old["id_job"],),
        )
    # Renombre Cálculo de equipos de respaldo → KPIs de ingeniería clínica.
    old_res = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'Cálculo de equipos de respaldo' COLLATE NOCASE
        """
    ).fetchone()
    new_kpi = conn.execute(
        """
        SELECT id_job FROM Jobs
        WHERE nombre_job = 'KPIs de ingeniería clínica' COLLATE NOCASE
        """
    ).fetchone()
    if old_res and new_kpi and old_res["id_job"] != new_kpi["id_job"]:
        old_cells = conn.execute(
            "SELECT id_rol, permiso_activo FROM Permisos WHERE id_job = ?",
            (old_res["id_job"],),
        ).fetchall()
        for cell in old_cells:
            exists = conn.execute(
                "SELECT id_permiso FROM Permisos WHERE id_rol = ? AND id_job = ?",
                (cell["id_rol"], new_kpi["id_job"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                    VALUES (?, ?, ?)
                    """,
                    (cell["id_rol"], new_kpi["id_job"], cell["permiso_activo"]),
                )
            elif cell["permiso_activo"]:
                conn.execute(
                    "UPDATE Permisos SET permiso_activo = 1 WHERE id_permiso = ?",
                    (exists["id_permiso"],),
                )
        conn.execute("DELETE FROM Permisos WHERE id_job = ?", (old_res["id_job"],))
        conn.execute("DELETE FROM Jobs WHERE id_job = ?", (old_res["id_job"],))
    elif old_res and not new_kpi:
        conn.execute(
            """
            UPDATE Jobs
            SET nombre_job = 'KPIs de ingeniería clínica',
                descripcion = 'Tablero de KPIs de ingeniería clínica (módulo independiente).',
                icono = 'kpis'
            WHERE id_job = ?
            """,
            (old_res["id_job"],),
        )
    _upsert_defaults(conn)
    _enable_access_servicio_defaults(conn)
    _enable_adquisicion_tablero_defaults(conn)
    _enable_dim_empresa_defaults(conn)
    _revoke_ingenieria_sede_edit_defaults(conn)


def ensure_permission_cells(conn):
    """Garantiza una celda Permisos por cada par Rol×Job."""
    roles = conn.execute("SELECT id_rol, nombre_rol FROM Roles").fetchall()
    jobs = conn.execute("SELECT id_job FROM Jobs").fetchall()
    for role in roles:
        canonical = _canonical_for_role_name(role["nombre_rol"])
        desired_jobs = DEFAULT_MATRIX.get(canonical) if canonical else None
        for job in jobs:
            exists = conn.execute(
                """
                SELECT id_permiso FROM Permisos
                WHERE id_rol = ? AND id_job = ?
                """,
                (role["id_rol"], job["id_job"]),
            ).fetchone()
            if exists:
                continue
            active = 1 if role["nombre_rol"].casefold() == ADMIN_ROLE_NAME.casefold() else 0
            if desired_jobs is not None:
                job_name = conn.execute(
                    "SELECT nombre_job FROM Jobs WHERE id_job = ?",
                    (job["id_job"],),
                ).fetchone()
                if job_name and job_name["nombre_job"] in desired_jobs:
                    active = 1
            conn.execute(
                """
                INSERT INTO Permisos (id_rol, id_job, permiso_activo)
                VALUES (?, ?, ?)
                """,
                (role["id_rol"], job["id_job"], active),
            )


def fetch_matrix(conn):
    ensure_permission_cells(conn)
    roles = [
        _role_payload(r)
        for r in conn.execute(
            "SELECT * FROM Roles ORDER BY protegido DESC, nombre_rol COLLATE NOCASE"
        ).fetchall()
    ]
    jobs = [
        _job_payload(j)
        for j in conn.execute(
            "SELECT * FROM Jobs ORDER BY nombre_job COLLATE NOCASE"
        ).fetchall()
    ]
    cells = {}
    for p in conn.execute(
        "SELECT id_rol, id_job, permiso_activo, id_permiso FROM Permisos"
    ).fetchall():
        cells[f"{p['id_rol']}:{p['id_job']}"] = {
            "id_permiso": p["id_permiso"],
            "permiso_activo": bool(p["permiso_activo"]),
        }
    return {"roles": roles, "jobs": jobs, "permisos": cells}


EXPORT_MATRIX_COLUMNS = [
    "id_rol",
    "nombre_rol",
    "estado_rol",
    "protegido",
    "id_job",
    "nombre_job",
    "codigo_permiso",
    "descripcion_job",
    "estado_job",
    "permiso_activo",
]


def build_matrix_export_rows(conn) -> list[dict]:
    """Filas planas: un registro por rol × módulo con su permiso activo/inactivo."""
    data = fetch_matrix(conn)
    rows = []
    for role in data["roles"]:
        for job in data["jobs"]:
            key = f"{role['id_rol']}:{job['id_job']}"
            active = bool(data["permisos"].get(key, {}).get("permiso_activo"))
            if role.get("protegido"):
                active = True
            rows.append(
                {
                    "id_rol": role["id_rol"],
                    "nombre_rol": role["nombre_rol"],
                    "estado_rol": role["estado"],
                    "protegido": "Sí" if role.get("protegido") else "No",
                    "id_job": job["id_job"],
                    "nombre_job": job["nombre_job"],
                    "codigo_permiso": job.get("codigo_permiso") or "",
                    "descripcion_job": job.get("descripcion") or "",
                    "estado_job": job["estado"],
                    "permiso_activo": "Sí" if active else "No",
                }
            )
    return rows


def build_matrix_pivot(conn) -> tuple[list[str], list[list]]:
    """
    Matriz rol × módulo para Excel.
    Retorna (encabezados, filas) donde cada fila es [módulo, estado, Sí/No por rol…].
    """
    data = fetch_matrix(conn)
    roles = data["roles"]
    jobs = data["jobs"]
    headers = ["módulo", "codigo_permiso", "estado_módulo"] + [
        r["nombre_rol"] for r in roles
    ]
    rows = []
    for job in jobs:
        row = [
            job["nombre_job"],
            job.get("codigo_permiso") or "",
            job["estado"],
        ]
        for role in roles:
            key = f"{role['id_rol']}:{job['id_job']}"
            active = bool(data["permisos"].get(key, {}).get("permiso_activo"))
            if role.get("protegido"):
                active = True
            row.append("Sí" if active else "No")
        rows.append(row)
    return headers, rows


def enforce_admin_full_access(conn):
    admin = conn.execute(
        "SELECT id_rol FROM Roles WHERE nombre_rol = ? COLLATE NOCASE",
        (ADMIN_ROLE_NAME,),
    ).fetchone()
    if not admin:
        return
    conn.execute(
        "UPDATE Permisos SET permiso_activo = 1 WHERE id_rol = ?",
        (admin["id_rol"],),
    )
    conn.execute(
        "UPDATE Roles SET estado = 'ACTIVO' WHERE id_rol = ?",
        (admin["id_rol"],),
    )


def permissions_from_matrix(conn, roll: str, job: str) -> set[str] | None:
    """
    Resuelve permisos desde la matriz RBAC guardada.
    Devuelve None si no hay mapeo de rol (usar fallback hardcode).
    """
    role_name = resolve_rbac_role_name(roll, job)
    if not role_name:
        return None

    ensure_rbac_seed(conn)
    ensure_permission_cells(conn)

    role = find_role_by_canonical(conn, role_name)
    if not role:
        return None
    if role["estado"] != "ACTIVO":
        return set()

    rows = conn.execute(
        """
        SELECT j.nombre_job, j.codigo_permiso, j.estado AS job_estado, p.permiso_activo
        FROM Permisos p
        JOIN Jobs j ON j.id_job = p.id_job
        WHERE p.id_rol = ?
        """,
        (role["id_rol"],),
    ).fetchall()

    if not rows:
        return None

    granted: set[str] = set()
    for row in rows:
        if not row["permiso_activo"]:
            continue
        if row["job_estado"] != "ACTIVO":
            continue
        keys = row.keys() if hasattr(row, "keys") else []
        codigo = row["codigo_permiso"] if "codigo_permiso" in keys else None
        granted |= permissions_for_job_name(row["nombre_job"], codigo)
    return granted


def permissions_for_user(roll: str, job: str) -> set[str] | None:
    """Lee permisos RBAC desde usuarios.db. None = usar fallback hardcode."""
    if roll == "ADMIN":
        from server.roles import ALL_PERMISSIONS

        return set(ALL_PERMISSIONS)

    from server.db import get_users_connection

    with get_users_connection() as conn:
        result = permissions_from_matrix(conn, roll, job)
        conn.commit()
    return result
