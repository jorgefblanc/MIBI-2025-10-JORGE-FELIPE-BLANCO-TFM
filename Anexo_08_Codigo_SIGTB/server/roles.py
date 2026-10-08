"""Catálogo ROLL / JOB y diccionario de permisos que consume el cliente."""

ROLES = {
    "ASISTENCIAL": ["Director", "Coordinador", "Líder"],
    "OPERATIVO": ["Director Operativo", "Coordinador", "Ingeniero", "Técnico"],
    "ADMIN": ["Administrador"],
}

# Alta pública: el usuario solo elige ROLL. El JOB lo asigna ADMIN después.
REGISTERABLE_ROLES = {
    "ASISTENCIAL": ["Coordinador", "Líder"],
    "OPERATIVO": ["Ingeniero", "Técnico"],
}

ROLL_LABELS = {
    "OPERATIVO": "Operador",
    "ASISTENCIAL": "Asistencial",
    "ADMIN": "Administrador",
}

PENDING_JOB_TOKENS = frozenset({"", "pendiente", "sin asignar"})

# Permisos atómicos del sistema
ALL_PERMISSIONS = {
    "view_sedes",
    "view_inventory",
    "import_inventory",
    "export_inventory",
    "modify_inventory",
    "create_empresa",
    "create_sede",
    "create_servicio",
    "modify_empresa",
    "modify_sede",
    "modify_servicio",
    "delete_empresa",
    "delete_sede",
    "delete_servicio",
    "manage_users",
    "manage_asistencial_users",
    "manage_asistencial_processes",
    "manage_jobs",
    "view_indicators_report",
    "view_all_empresas",
    "import_empresas",
    "assign_sede_coordinators",
    "request_expanded_permissions",
    "approve_expanded_permissions",
    "admin_panel",
    "view_engineering_instruments",
    "view_suficiencia",
    "view_dimensionamiento",
    "view_frecuencia_pm",
    "view_preinstalacion",
    "view_kpis",
    "view_respaldo",
    "view_capex",
    "edit_suficiencia_asistencial",
    "request_suficiencia_update",
    "access_servicio",
    "view_adquisicion_dashboard",
    "view_dimensionamiento_empresa",
}

# Un job de instrumento = un permiso. No usar el paraguas view_engineering_instruments.
INSTRUMENT_VIEW_PERMISSIONS = frozenset(
    {
        "view_suficiencia",
        "view_dimensionamiento",
        "view_frecuencia_pm",
        "view_preinstalacion",
        "view_kpis",
        "view_respaldo",
        "view_capex",
    }
)


def get_roles_catalog():
    return {
        "roles": list(REGISTERABLE_ROLES.keys()),
        "jobsByRole": REGISTERABLE_ROLES,
    }


def get_all_roles_catalog():
    return {
        "roles": list(ROLES.keys()),
        "jobsByRole": ROLES,
    }


def is_valid_roll(roll):
    return roll in REGISTERABLE_ROLES


def is_pending_job(job):
    """Sin cargo asignado (alta pública o JOB aún no definido por ADMIN)."""
    return (job or "").strip().lower() in PENDING_JOB_TOKENS


def roll_label(roll):
    key = (roll or "").strip().upper()
    return ROLL_LABELS.get(key, roll or "")


def job_label(job):
    if is_pending_job(job):
        return "Sin asignar"
    return job


def normalize_job(roll, job):
    """Normaliza alias históricos de cargos."""
    if roll == "ASISTENCIAL" and job == "Dirección":
        return "Director"
    if roll == "OPERATIVO" and job == "Dirección":
        return "Director Operativo"
    return job


def is_operativo_director_job(job):
    return job in ("Director Operativo", "Dirección")


def is_valid_job_for_roll(roll, job):
    if not is_valid_roll(roll):
        return False
    return normalize_job(roll, job) in REGISTERABLE_ROLES[roll]


def is_valid_managed_roll(roll):
    return roll in ROLES


def is_valid_managed_job(roll, job):
    if not is_valid_managed_roll(roll):
        return False
    return normalize_job(roll, job) in ROLES[roll]


def get_permissions_hardcoded(roll, job):
    """Fallback histórico cuando no hay matriz RBAC aplicable."""
    if roll == "ADMIN":
        return set(ALL_PERMISSIONS)

    if is_pending_job(job):
        return set()

    job = normalize_job(roll, job)

    if roll == "ASISTENCIAL":
        base_asistencial = {
            "view_sedes",
            "view_inventory",
            "manage_asistencial_processes",
            "edit_suficiencia_asistencial",
            "view_suficiencia",
        }

        if job == "Director":
            return base_asistencial | {
                "view_indicators_report",
                "manage_asistencial_users",
                "view_preinstalacion",
            }

        if job == "Coordinador":
            return set(base_asistencial)

        # Líder: inventario (consulta) + actualizar suficiencia.
        return {
            "view_sedes",
            "view_inventory",
            "edit_suficiencia_asistencial",
            "view_suficiencia",
        }

    if roll != "OPERATIVO":
        return set()

    if job == "Director Operativo":
        return {
            "view_sedes",
            "view_inventory",
            "import_inventory",
            "export_inventory",
            "modify_inventory",
            "create_sede",
            "create_servicio",
            "modify_empresa",
            "modify_sede",
            "modify_servicio",
            "delete_empresa",
            "delete_sede",
            "delete_servicio",
            "manage_users",
            "manage_jobs",
            "view_indicators_report",
            "assign_sede_coordinators",
            "approve_expanded_permissions",
            "request_suficiencia_update",
            "access_servicio",
            "view_adquisicion_dashboard",
            "view_dimensionamiento_empresa",
        } | set(INSTRUMENT_VIEW_PERMISSIONS)

    if job == "Coordinador":
        return {
            "view_sedes",
            "view_inventory",
            "export_inventory",
            "modify_inventory",
            "create_empresa",
            "create_sede",
            "create_servicio",
            "modify_empresa",
            "modify_sede",
            "modify_servicio",
            "delete_empresa",
            "approve_expanded_permissions",
            "request_suficiencia_update",
            "view_adquisicion_dashboard",
            "view_dimensionamiento_empresa",
        } | set(INSTRUMENT_VIEW_PERMISSIONS)

    if job == "Ingeniero":
        return {
            "view_sedes",
            "view_inventory",
            "export_inventory",
            "modify_inventory",
            "create_sede",
            "create_servicio",
            "request_expanded_permissions",
            "request_suficiencia_update",
        } | set(INSTRUMENT_VIEW_PERMISSIONS)

    return {
        "view_sedes",
        "view_inventory",
    }


# Capacidades temporales al activar una solicitud APROBADA de permisos ampliados.
# Equivale al extra de Coordinador operativo sobre Ingeniero (sin aprobar solicitudes).
EXPANDED_PERMISSIONS_OVERLAY = {
    "create_empresa",
    "modify_empresa",
    "modify_sede",
    "modify_servicio",
}


def get_permissions(roll, job, expanded=False):
    """Devuelve permisos: primero matriz RBAC en BD; si no aplica, hardcode."""
    if roll == "ADMIN":
        return set(ALL_PERMISSIONS)

    if is_pending_job(job):
        return set()

    job = normalize_job(roll, job)
    perms = None
    try:
        from server.rbac import permissions_for_user

        matrix_perms = permissions_for_user(roll, job)
        if matrix_perms is not None:
            perms = set(matrix_perms)
    except Exception:
        perms = None
    if perms is None:
        perms = set(get_permissions_hardcoded(roll, job))
    if expanded:
        perms |= EXPANDED_PERMISSIONS_OVERLAY
    return perms


def permissions_payload(roll, job, expanded=False):
    perms = sorted(get_permissions(roll, job, expanded=expanded))
    return {
        "permissions": perms,
        "can": {name: name in perms for name in sorted(ALL_PERMISSIONS)},
        "expanded_permissions": bool(expanded),
    }
