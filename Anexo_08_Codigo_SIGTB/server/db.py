"""Conexiones SQLite, aplicación de esquemas y recuperación desde el último respaldo sano."""

import os
import sqlite3
from pathlib import Path

import bcrypt

from server.sede_ids import next_id_sede, next_id_servicio

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
USERS_DB_PATH = DATA_DIR / "usuarios.db"
EMPRESAS_DB_PATH = DATA_DIR / "empresas.db"
SOLICITUDES_DB_PATH = DATA_DIR / "solicitudes.db"
PARAMETROS_EQUIPO_DB_PATH = DATA_DIR / "parametros_equipo.db"

SCHEMA_USERS = ROOT_DIR / "sql" / "schema_usuarios.sql"
SCHEMA_EMPRESAS = ROOT_DIR / "sql" / "schema_empresas.sql"
SCHEMA_SOLICITUDES = ROOT_DIR / "sql" / "schema_solicitudes.sql"
SCHEMA_PARAMETROS_EQUIPO = ROOT_DIR / "sql" / "schema_parametros_equipo.sql"
SCHEMA_FRECUENCIA_PM = ROOT_DIR / "sql" / "schema_frecuencia_pm.sql"
SCHEMA_PREINSTALACION = ROOT_DIR / "sql" / "schema_preinstalacion.sql"
SCHEMA_EJECUCION = ROOT_DIR / "sql" / "schema_ejecucion_mantenimientos.sql"

ADMIN_EMAIL = "admin@sigtb.local"
# Contraseña inicial del administrador y de los perfiles demo. Se lee del entorno;
# el valor por defecto es un marcador y el arranque se detiene si no se cambia.
PASSWORD_PLACEHOLDER = "CAMBIAR_ANTES_DE_USAR"
ADMIN_PASSWORD = os.environ.get("SIGTB_ADMIN_PASSWORD", PASSWORD_PLACEHOLDER)
ADMIN_NAME = "Admin"
ADMIN_LAST_NAME = "Sistema"
ADMIN_JOB = "Administrador"
ADMIN_ROLL = "ADMIN"
BCRYPT_ROUNDS = 12

DEMO_USERS = [
    {
        "usuario_login": "direccion@sigtb.local",
        "NAME_USER": "Diana",
        "LAST_NAME_USER": "Direccion",
        "JOB": "Director Operativo",
        "ROLL": "OPERATIVO",
    },
    {
        "usuario_login": "coordinador@sigtb.local",
        "NAME_USER": "Carlos",
        "LAST_NAME_USER": "Coordinador",
        "JOB": "Coordinador",
        "ROLL": "OPERATIVO",
    },
    {
        "usuario_login": "ingeniero@sigtb.local",
        "NAME_USER": "Irene",
        "LAST_NAME_USER": "Ingeniera",
        "JOB": "Ingeniero",
        "ROLL": "OPERATIVO",
    },
    {
        "usuario_login": "asistencial@sigtb.local",
        "NAME_USER": "Ana",
        "LAST_NAME_USER": "Asistencial",
        "JOB": "Líder",
        "ROLL": "ASISTENCIAL",
    },
]


def _on_synced_folder(path: Path) -> bool:
    """OneDrive/Dropbox/Drive corrompen WAL; ahí se usa journal DELETE + sync FULL."""
    text = str(path).lower().replace("\\", "/")
    return any(token in text for token in ("onedrive", "dropbox", "google drive", "googledrive"))


def _connect(path):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000;")
    if _on_synced_folder(Path(path)):
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("PRAGMA synchronous = FULL;")
    else:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA wal_autocheckpoint = 100;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _is_malformed(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        row = conn.execute("PRAGMA quick_check").fetchone()
        return not row or str(row[0]).lower() != "ok"
    except sqlite3.DatabaseError:
        return True
    except sqlite3.Error:
        return True
    finally:
        if conn is not None:
            conn.close()


def _quarantine_db(path: Path) -> Path | None:
    """Mueve un SQLite corrupto a *.malformed-YYYYmmdd-HHMMSS para no bloquear el arranque."""
    if not path.exists():
        return None
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.stem}.malformed-{stamp}{path.suffix}")
    n = 1
    while dest.exists():
        dest = path.with_name(f"{path.stem}.malformed-{stamp}-{n}{path.suffix}")
        n += 1
    path.replace(dest)
    for extra in (path.with_suffix(path.suffix + "-wal"), path.with_suffix(path.suffix + "-shm")):
        if extra.exists():
            extra.replace(dest.with_name(dest.name + extra.suffix.replace(path.suffix, "")))
    return dest


def _connect_healthy(path: Path):
    if _is_malformed(path):
        quarantined = _quarantine_db(path)
        print(f"[db] SQLite corrupto. Resguardo: {quarantined}.")
        from server.backup import restore_latest_for

        restored = restore_latest_for(path)
        if restored:
            print(f"[db] Restaurado {path.name} desde {restored}.")
        else:
            print(f"[db] Sin respaldo válido. Se recreará {path.name} vacío.")
    return _connect(path)


def get_users_connection():
    return _connect_healthy(USERS_DB_PATH)


def get_empresas_connection():
    return _connect_healthy(EMPRESAS_DB_PATH)


def get_solicitudes_connection():
    return _connect_healthy(SOLICITUDES_DB_PATH)


def discard_pending_solicitud(solicitud_id) -> None:
    """Compensa un INSERT ya confirmado en solicitudes.db si falló el vínculo en empresas.db."""
    if not solicitud_id:
        return
    try:
        with get_solicitudes_connection() as conn:
            conn.execute(
                "DELETE FROM solicitudes WHERE id = ? AND estado = 'PENDIENTE'",
                (int(solicitud_id),),
            )
            conn.commit()
    except Exception:
        pass


def revert_solicitud_estado(solicitud_id, estado: str) -> None:
    """Devuelve una solicitud al estado previo si falló el espejo en empresas.db."""
    if not solicitud_id or not estado:
        return
    try:
        with get_solicitudes_connection() as conn:
            conn.execute(
                """
                UPDATE solicitudes
                SET estado = ?, resolved_at = NULL
                WHERE id = ?
                """,
                (estado, int(solicitud_id)),
            )
            conn.commit()
    except Exception:
        pass


def get_parametros_equipo_connection():
    return _connect_healthy(PARAMETROS_EQUIPO_DB_PATH)


def get_connection():
    """Compatibilidad: por defecto conexión a usuarios."""
    return get_users_connection()


def _hash_password(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")


def _ensure_admin_roll_allowed(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'usuarios'"
    ).fetchone()
    if row is None or row["sql"] is None or "ADMIN" in row["sql"]:
        return

    cols = {c["name"] for c in conn.execute("PRAGMA table_info(usuarios)").fetchall()}
    has_empresa = "empresa_id" in cols
    extra_col = ", empresa_id" if has_empresa else ""
    extra_sel = ", empresa_id" if has_empresa else ""
    extra_def = ", empresa_id INTEGER" if has_empresa else ""

    conn.executescript(
        f"""
        CREATE TABLE usuarios_migrated (
            id_usuario     INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_login  VARCHAR(255) NOT NULL UNIQUE COLLATE NOCASE,
            password_hash  VARCHAR(255) NOT NULL,
            creation_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            NAME_USER      VARCHAR(255) NOT NULL,
            LAST_NAME_USER VARCHAR(255) NOT NULL,
            JOB            VARCHAR(255) NOT NULL,
            ROLL           VARCHAR(50)  NOT NULL CHECK (ROLL IN ('ASISTENCIAL', 'OPERATIVO', 'ADMIN'))
            {extra_def}
        );
        INSERT INTO usuarios_migrated (
            id_usuario, usuario_login, password_hash, creation_date,
            NAME_USER, LAST_NAME_USER, JOB, ROLL{extra_col}
        )
        SELECT id_usuario, usuario_login, password_hash, creation_date,
               NAME_USER, LAST_NAME_USER, JOB, ROLL{extra_sel}
        FROM usuarios;
        DROP TABLE usuarios;
        ALTER TABLE usuarios_migrated RENAME TO usuarios;
        CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios (usuario_login);
        """
    )


def _migrate_cross_db_refs(users_conn):
    """
    Quita FKs a sedes/empresas en usuarios.db (viven en empresas.db).
    sede_id / empresa_id quedan como referencias lógicas.
    """
    usuarios_sql = users_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'"
    ).fetchone()
    if usuarios_sql and usuarios_sql[0] and "REFERENCES empresas" in usuarios_sql[0]:
        users_conn.execute("PRAGMA foreign_keys = OFF")
        users_conn.executescript(
            """
            CREATE TABLE usuarios_new (
                id_usuario     INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_login  VARCHAR(255) NOT NULL UNIQUE COLLATE NOCASE,
                password_hash  VARCHAR(255) NOT NULL,
                creation_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                NAME_USER      VARCHAR(255) NOT NULL,
                LAST_NAME_USER VARCHAR(255) NOT NULL,
                JOB            VARCHAR(255) NOT NULL,
                ROLL           VARCHAR(50)  NOT NULL
                               CHECK (ROLL IN ('ASISTENCIAL', 'OPERATIVO', 'ADMIN')),
                empresa_id     INTEGER
            );
            INSERT INTO usuarios_new (
                id_usuario, usuario_login, password_hash, creation_date,
                NAME_USER, LAST_NAME_USER, JOB, ROLL, empresa_id
            )
            SELECT
                id_usuario, usuario_login, password_hash, creation_date,
                NAME_USER, LAST_NAME_USER, JOB, ROLL, empresa_id
            FROM usuarios;
            DROP TABLE usuarios;
            ALTER TABLE usuarios_new RENAME TO usuarios;
            CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios (usuario_login);
            CREATE INDEX IF NOT EXISTS idx_usuarios_empresa ON usuarios (empresa_id);
            """
        )
        users_conn.execute("PRAGMA foreign_keys = ON")

    us_sql = users_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='usuario_sedes'"
    ).fetchone()
    if us_sql and us_sql[0] and "REFERENCES sedes" in us_sql[0]:
        users_conn.executescript(
            """
            CREATE TABLE usuario_sedes_new (
                usuario_id  INTEGER NOT NULL,
                sede_id     INTEGER NOT NULL,
                assigned_by INTEGER,
                assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (usuario_id, sede_id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
                FOREIGN KEY (assigned_by) REFERENCES usuarios(id_usuario)
            );
            INSERT INTO usuario_sedes_new (usuario_id, sede_id, assigned_by, assigned_at)
            SELECT usuario_id, sede_id, assigned_by, assigned_at FROM usuario_sedes;
            DROP TABLE usuario_sedes;
            ALTER TABLE usuario_sedes_new RENAME TO usuario_sedes;
            """
        )

    sp_sql = users_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='solicitudes_permiso'"
    ).fetchone()
    if sp_sql and sp_sql[0] and "REFERENCES sedes" in sp_sql[0]:
        users_conn.executescript(
            """
            CREATE TABLE solicitudes_permiso_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitante_id  INTEGER NOT NULL,
                sede_id         INTEGER NOT NULL,
                tipo            VARCHAR(50) NOT NULL,
                mensaje         TEXT,
                estado          VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                                CHECK (estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA')),
                coordinador_id  INTEGER,
                email_destino   VARCHAR(255),
                creation_date   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (solicitante_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
                FOREIGN KEY (coordinador_id) REFERENCES usuarios(id_usuario)
            );
            INSERT INTO solicitudes_permiso_new (
                id, solicitante_id, sede_id, tipo, mensaje, estado,
                coordinador_id, email_destino, creation_date
            )
            SELECT
                id, solicitante_id, sede_id, tipo, mensaje, estado,
                coordinador_id, email_destino, creation_date
            FROM solicitudes_permiso;
            DROP TABLE solicitudes_permiso;
            ALTER TABLE solicitudes_permiso_new RENAME TO solicitudes_permiso;
            """
        )

    # empresa_creada_id es referencia lógica a empresas.db (no FK local).
    notif_sql = users_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='notificaciones_admin'"
    ).fetchone()
    if notif_sql and notif_sql[0] and "REFERENCES empresas" in notif_sql[0]:
        users_conn.executescript(
            """
            CREATE TABLE notificaciones_admin_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo               VARCHAR(50)  NOT NULL,
                mensaje            TEXT,
                solicitante_id     INTEGER,
                solicitante_email  VARCHAR(255),
                solicitante_nombre VARCHAR(255),
                empresa_sugerida   VARCHAR(255),
                nit_sugerido       VARCHAR(50),
                estado             VARCHAR(20)  NOT NULL DEFAULT 'PENDIENTE'
                                   CHECK (estado IN ('PENDIENTE', 'RESUELTA', 'DESCARTADA')),
                empresa_creada_id  INTEGER,
                creation_date      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (solicitante_id) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
            );
            INSERT INTO notificaciones_admin_new (
                id, tipo, mensaje, solicitante_id, solicitante_email,
                solicitante_nombre, empresa_sugerida, nit_sugerido,
                estado, empresa_creada_id, creation_date
            )
            SELECT
                id, tipo, mensaje, solicitante_id, solicitante_email,
                solicitante_nombre, empresa_sugerida, nit_sugerido,
                estado, empresa_creada_id, creation_date
            FROM notificaciones_admin;
            DROP TABLE notificaciones_admin;
            ALTER TABLE notificaciones_admin_new RENAME TO notificaciones_admin;
            CREATE INDEX IF NOT EXISTS idx_notif_admin_estado
                ON notificaciones_admin (estado);
            """
        )


def _initial_password() -> str:
    if not ADMIN_PASSWORD or ADMIN_PASSWORD == PASSWORD_PLACEHOLDER:
        raise SystemExit("Defina SIGTB_ADMIN_PASSWORD en el entorno antes de crear los usuarios iniciales.")
    return ADMIN_PASSWORD


def _seed_users(conn):
    exists = conn.execute(
        "SELECT id_usuario FROM usuarios WHERE usuario_login = ? COLLATE NOCASE",
        (ADMIN_EMAIL,),
    ).fetchone()
    if not exists:
        conn.execute(
            """
            INSERT INTO usuarios (
                usuario_login, password_hash, creation_date,
                NAME_USER, LAST_NAME_USER, JOB, ROLL
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
            """,
            (
                ADMIN_EMAIL,
                _hash_password(_initial_password()),
                ADMIN_NAME,
                ADMIN_LAST_NAME,
                ADMIN_JOB,
                ADMIN_ROLL,
            ),
        )

    password_hash = None
    for user in DEMO_USERS:
        exists = conn.execute(
            "SELECT id_usuario FROM usuarios WHERE usuario_login = ? COLLATE NOCASE",
            (user["usuario_login"],),
        ).fetchone()
        if exists:
            continue
        if password_hash is None:
            password_hash = _hash_password(_initial_password())
        conn.execute(
            """
            INSERT INTO usuarios (
                usuario_login, password_hash, creation_date,
                NAME_USER, LAST_NAME_USER, JOB, ROLL
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
            """,
            (
                user["usuario_login"],
                password_hash,
                user["NAME_USER"],
                user["LAST_NAME_USER"],
                user["JOB"],
                user["ROLL"],
            ),
        )

    conn.execute("UPDATE usuarios SET JOB = 'Coordinador' WHERE JOB = 'Coordinación'")
    conn.execute(
        """
        UPDATE usuarios
        SET JOB = 'Director'
        WHERE ROLL = 'ASISTENCIAL' AND JOB = 'Dirección'
        """
    )
    conn.execute(
        """
        UPDATE usuarios
        SET JOB = 'Director Operativo'
        WHERE ROLL = 'OPERATIVO' AND JOB = 'Dirección'
        """
    )


def _restore_org_from_usuarios_legacy(emp_conn, users_conn):
    """
    Si empresas.db se recreó vacío, recupera empresas/sedes que aún vivan
    en tablas legado de usuarios.db (antes de la separación de bases).
    """
    existing = emp_conn.execute("SELECT COUNT(*) AS n FROM empresas").fetchone()["n"]
    if existing:
        return
    try:
        legacy_empresas = users_conn.execute(
            "SELECT id, ID_Empresa, ID_NIT, creation_date FROM empresas"
        ).fetchall()
    except sqlite3.Error:
        return
    if not legacy_empresas:
        return
    id_map = {}
    for row in legacy_empresas:
        nit = row["ID_NIT"]
        found = emp_conn.execute(
            "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE", (nit,)
        ).fetchone()
        if found:
            id_map[row["id"]] = found["id"]
            continue
        cur = emp_conn.execute(
            """
            INSERT INTO empresas (ID_Empresa, ID_NIT, creation_date)
            VALUES (?, ?, COALESCE(?, datetime('now')))
            """,
            (row["ID_Empresa"], nit, row["creation_date"]),
        )
        id_map[row["id"]] = cur.lastrowid
    try:
        legacy_sedes = users_conn.execute(
            "SELECT id, ID_sede, name_sede, prefix, empresa_id, creation_date FROM sedes"
        ).fetchall()
    except sqlite3.Error:
        return
    sede_id_map = {}
    _servicio_como_sede = {
        "urgencias",
        "cirugía",
        "cirugia",
        "consulta externa",
        "hospitalizacion",
        "hospitalización",
    }
    for row in legacy_sedes:
        nombre = (row["name_sede"] or "").strip().lower()
        if nombre in _servicio_como_sede:
            continue
        new_emp = id_map.get(row["empresa_id"])
        if not new_emp:
            continue
        exists = emp_conn.execute(
            """
            SELECT id FROM sedes
            WHERE empresa_id = ? AND name_sede = ? COLLATE NOCASE
            """,
            (new_emp, row["name_sede"]),
        ).fetchone()
        if exists:
            sede_id_map[row["id"]] = exists["id"]
            continue
        cur = emp_conn.execute(
            """
            INSERT INTO sedes (ID_sede, name_sede, prefix, empresa_id, creation_date)
            VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')))
            """,
            (row["ID_sede"], row["name_sede"], row["prefix"], new_emp, row["creation_date"]),
        )
        sede_id_map[row["id"]] = cur.lastrowid
        for servicio in ("Urgencias", "Cirugía", "Consulta Externa"):
            exists_srv = emp_conn.execute(
                """
                SELECT id FROM servicios
                WHERE sede_id = ? AND name_servicio = ? COLLATE NOCASE
                """,
                (cur.lastrowid, servicio),
            ).fetchone()
            if exists_srv:
                continue
            id_srv, srv_prefix = next_id_servicio(emp_conn, servicio, cur.lastrowid)
            emp_conn.execute(
                """
                INSERT INTO servicios (ID_servicio, name_servicio, prefix, sede_id, creation_date)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (id_srv, servicio, srv_prefix, cur.lastrowid),
            )


def _seed_empresas_structure(emp_conn, users_conn):
    empresa = emp_conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        ("900123456-1",),
    ).fetchone()
    if empresa:
        empresa_id = empresa["id"]
    else:
        cur = emp_conn.execute(
            """
            INSERT INTO empresas (ID_Empresa, ID_NIT, creation_date)
            VALUES (?, ?, datetime('now'))
            """,
            ("Buenos Aires", "900123456-1"),
        )
        empresa_id = cur.lastrowid

        # Sede Bolarqui con servicios (exclusiva de Buenos Aires)
        id_sede, prefix = next_id_sede(emp_conn, "Bolarqui", empresa_id)
        sede_cur = emp_conn.execute(
            """
            INSERT INTO sedes (ID_sede, name_sede, prefix, empresa_id, creation_date)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (id_sede, "Bolarqui", prefix, empresa_id),
        )
        sede_id = sede_cur.lastrowid
        for servicio in ("Urgencias", "Cirugía", "Consulta Externa"):
            id_srv, srv_prefix = next_id_servicio(emp_conn, servicio, sede_id)
            emp_conn.execute(
                """
                INSERT INTO servicios (ID_servicio, name_servicio, prefix, sede_id, creation_date)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (id_srv, servicio, srv_prefix, sede_id),
            )

    # Vincular usuarios demo a la empresa
    users_conn.execute(
        """
        UPDATE usuarios
        SET empresa_id = ?
        WHERE ROLL != 'ADMIN'
          AND empresa_id IS NULL
          AND usuario_login IN (
            'direccion@sigtb.local',
            'coordinador@sigtb.local',
            'ingeniero@sigtb.local',
            'asistencial@sigtb.local'
          )
        """,
        (empresa_id,),
    )

    coord = users_conn.execute(
        """
        SELECT id_usuario FROM usuarios
        WHERE usuario_login = 'coordinador@sigtb.local' COLLATE NOCASE
        """
    ).fetchone()
    direccion = users_conn.execute(
        """
        SELECT id_usuario FROM usuarios
        WHERE usuario_login = 'direccion@sigtb.local' COLLATE NOCASE
        """
    ).fetchone()
    if coord:
        sedes = emp_conn.execute(
            "SELECT id FROM sedes WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchall()
        for sede in sedes:
            try:
                users_conn.execute(
                    """
                    INSERT OR IGNORE INTO usuario_sedes
                        (usuario_id, sede_id, assigned_by, assigned_at)
                    VALUES (?, ?, NULL, datetime('now'))
                    """,
                    (coord["id_usuario"], sede["id"]),
                )
            except Exception:
                # No bloquear el arranque si el vínculo demo ya es inválido.
                continue
        users_conn.commit()

    return empresa_id


def _seed_inventario_hipotetico(emp_conn, users_conn):
    """
    Inventario de prueba (prefijo HIPO-) en sede Bolarqui / Buenos Aires.
    Idempotente. Asigna acceso de sede al perfil ingeniero@sigtb.local.
    """
    empresa = emp_conn.execute(
        "SELECT id FROM empresas WHERE ID_NIT = ? COLLATE NOCASE",
        ("900123456-1",),
    ).fetchone()
    if not empresa:
        return 0

    sede = emp_conn.execute(
        """
        SELECT id FROM sedes
        WHERE empresa_id = ? AND name_sede = ? COLLATE NOCASE
        ORDER BY id LIMIT 1
        """,
        (empresa["id"], "Bolarqui"),
    ).fetchone()
    if not sede:
        sede = emp_conn.execute(
            "SELECT id FROM sedes WHERE empresa_id = ? ORDER BY id LIMIT 1",
            (empresa["id"],),
        ).fetchone()
    if not sede:
        return 0

    # Vincular ingeniero demo a la sede (sin crear perfiles nuevos).
    ingeniero = users_conn.execute(
        """
        SELECT id_usuario FROM usuarios
        WHERE usuario_login = 'ingeniero@sigtb.local' COLLATE NOCASE
        """
    ).fetchone()
    if ingeniero:
        users_conn.execute(
            """
            INSERT OR IGNORE INTO usuario_sedes
                (usuario_id, sede_id, assigned_by, assigned_at)
            VALUES (?, ?, NULL, datetime('now'))
            """,
            (ingeniero["id_usuario"], sede["id"]),
        )
        users_conn.execute(
            "UPDATE usuarios SET empresa_id = ? WHERE id_usuario = ? AND empresa_id IS NULL",
            (empresa["id"], ingeniero["id_usuario"]),
        )

    already = emp_conn.execute(
        """
        SELECT COUNT(*) AS n FROM inventario_equipos
        WHERE num_biomedica LIKE 'HIPO-%'
        """
    ).fetchone()["n"]
    if already:
        return 0

    servicios = {
        r["name_servicio"]: dict(r)
        for r in emp_conn.execute(
            "SELECT id, ID_servicio, name_servicio FROM servicios WHERE sede_id = ?",
            (sede["id"],),
        ).fetchall()
    }
    if not servicios:
        return 0

    def srv(name):
        return servicios.get(name) or next(iter(servicios.values()))

    # (servicio, biomedica, equipo, marca, modelo, serie, riesgo, ubicacion,
    #  aplica_mp, freq_mp, tiempo_mp, aplica_cal, freq_cal, tiempo_cal,
    #  aplica_val, freq_val, tiempo_val)
    catalog = []
    # Cirugía — 5 monitores (solo el primero con MP/Cal)
    for i in range(1, 6):
        has = i == 1
        catalog.append(
            (
                "Cirugía",
                f"HIPO-MP-{i:02d}",
                "MONITOR MULTIPARAMETROS",
                "GE",
                "B450",
                f"SN-MP-{i:03d}",
                "Alto",
                "Quirófano",
                1 if has else None,
                2.0 if has else None,
                1.5 if has else None,
                1 if has else None,
                1.0 if has else None,
                0.75 if has else None,
                0 if has else None,
                0 if has else None,
                0 if has else None,
            )
        )
    # Cirugía — 3 mesas (1 con datos)
    for i in range(1, 4):
        has = i == 1
        catalog.append(
            (
                "Cirugía",
                f"HIPO-MQ-{i:02d}",
                "MESA QUIRURGICA",
                "Maquet",
                "Alphamaquet",
                f"SN-MQ-{i:03d}",
                "Alto",
                "Quirófano",
                1 if has else None,
                1.0 if has else None,
                2.0 if has else None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
    # Cirugía — 2 electrobisturís sin datos + 1 arco en C con datos
    for i in range(1, 3):
        catalog.append(
            (
                "Cirugía",
                f"HIPO-EB-{i:02d}",
                "ELECTROBISTURI",
                "Valleylab",
                "Force FX",
                f"SN-EB-{i:03d}",
                "Alto",
                "Quirófano",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
    catalog.append(
        (
            "Cirugía",
            "HIPO-AC-01",
            "ARCO EN C",
            "Philips",
            "BV Pulsera",
            "SN-AC-001",
            "Alto",
            "Quirófano",
            1,
            2.0,
            3.0,
            1,
            1.0,
            2.0,
            1,
            1.0,
            1.5,
        )
    )
    # Urgencias
    for i in range(1, 5):
        has = i == 1
        catalog.append(
            (
                "Urgencias",
                f"HIPO-TN-{i:02d}",
                "TENSIOMETRO",
                "Omron",
                "HBP-1320",
                f"SN-TN-{i:03d}",
                "Medio",
                "Triage",
                1 if has else None,
                4.0 if has else None,
                0.25 if has else None,
                1 if has else None,
                1.0 if has else None,
                0.5 if has else None,
                None,
                None,
                None,
            )
        )
    for i in range(1, 3):
        has = i == 1
        catalog.append(
            (
                "Urgencias",
                f"HIPO-DF-{i:02d}",
                "DESFIBRILADOR",
                "Zoll",
                "R Series",
                f"SN-DF-{i:03d}",
                "Soporte vital",
                "Reanimación",
                1 if has else None,
                4.0 if has else None,
                1.0 if has else None,
                1 if has else None,
                2.0 if has else None,
                1.0 if has else None,
                1 if has else None,
                1.0 if has else None,
                0.5 if has else None,
            )
        )
    # Consulta Externa
    for i in range(1, 4):
        catalog.append(
            (
                "Consulta Externa",
                f"HIPO-MB-{i:02d}",
                "MONITOR BASICO",
                "Mindray",
                "uMEC10",
                f"SN-MB-{i:03d}",
                "Medio",
                "Consultorio",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
    for i in range(1, 3):
        has = i == 1
        catalog.append(
            (
                "Consulta Externa",
                f"HIPO-BA-{i:02d}",
                "BASCULA",
                "Seca",
                "769",
                f"SN-BA-{i:03d}",
                "Bajo",
                "Consultorio",
                1 if has else None,
                1.0 if has else None,
                0.5 if has else None,
                1 if has else None,
                1.0 if has else None,
                0.4 if has else None,
                0 if has else None,
                0 if has else None,
                0 if has else None,
            )
        )

    inserted = 0
    for row in catalog:
        (
            srv_name,
            bio,
            equipo,
            marca,
            modelo,
            serie,
            riesgo,
            ubicacion,
            a_mp,
            f_mp,
            t_mp,
            a_cal,
            f_cal,
            t_cal,
            a_val,
            f_val,
            t_val,
        ) = row
        s = srv(srv_name)
        emp_conn.execute(
            """
            INSERT INTO inventario_equipos (
                servicio_id, num_biomedica, registro_invima, equipo, marca, serie,
                modelo, clasificacion_riesgo, ubicacion, estado, creation_date,
                aplica_mp, freq_mp, tiempo_mp,
                aplica_cal, freq_cal, tiempo_cal,
                aplica_val, freq_val, tiempo_val
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPERATIVO', datetime('now'),
                      ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s["id"],
                bio,
                f"INV-{bio}",
                equipo,
                marca,
                serie,
                modelo,
                riesgo,
                ubicacion,
                a_mp,
                f_mp,
                t_mp,
                a_cal,
                f_cal,
                t_cal,
                a_val,
                f_val,
                t_val,
            ),
        )
        inserted += 1
    return inserted


def _migrate_inventario_std_params(emp_conn):
    """Añade columnas estandarizadas MP/Cal/Val al inventario biomédico."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "inventario_equipos" not in tables:
        return
    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(inventario_equipos)").fetchall()
    }
    additions = {
        "aplica_mp": "INTEGER",
        "freq_mp": "REAL",
        "tiempo_mp": "REAL",
        "aplica_cal": "INTEGER",
        "freq_cal": "REAL",
        "tiempo_cal": "REAL",
        "aplica_val": "INTEGER",
        "freq_val": "REAL",
        "tiempo_val": "REAL",
    }
    for name, typ in additions.items():
        if name not in cols:
            emp_conn.execute(f"ALTER TABLE inventario_equipos ADD COLUMN {name} {typ}")


INVENTARIO_COMPLEMENT_COLUMNS = {
    "clasificacion_biomedica": "VARCHAR(120)",
    "tecnologia": "VARCHAR(120)",
    "forma_adquisicion": "VARCHAR(120)",
    "vida_util_anios": "REAL",
    "vida_util_txt": "VARCHAR(80)",
    "fecha_compra": "DATE",
    "fecha_operacion": "DATE",
    "fecha_garantia": "DATE",
    "fecha_baja": "DATE",
    "fecha_ultimo_pm": "DATE",
    "fecha_actualizacion": "DATETIME",
    "codigo_activo": "VARCHAR(100)",
    "codigo_ubicacion": "VARCHAR(80)",
    "institucion_origen": "VARCHAR(255)",
    "fuente_import": "VARCHAR(40)",
    "codigo_origen": "VARCHAR(80)",
    "novedad_desc": "TEXT",
    "voltaje": "VARCHAR(80)",
    "corriente": "VARCHAR(80)",
    "potencia": "VARCHAR(80)",
    "peso": "VARCHAR(80)",
    "temperatura_trabajo": "VARCHAR(80)",
    "presion": "VARCHAR(80)",
    "fuente_alimentacion": "VARCHAR(120)",
    "comercializador": "VARCHAR(255)",
    "manual_operacion": "INTEGER",
    "manual_servicio": "INTEGER",
    "componente1": "VARCHAR(255)",
    "componente2": "VARCHAR(255)",
    "componente3": "VARCHAR(255)",
    "periodicidad_mp": "VARCHAR(80)",
    "periodicidad_cal": "VARCHAR(80)",
    "requiere_calibracion": "INTEGER",
}


def _migrate_inventario_complement_columns(emp_conn):
    """Campos del CSV institucional usados por PM, dimensión, suficiencia y preinstalación."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "inventario_equipos" not in tables:
        return
    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(inventario_equipos)").fetchall()
    }
    for name, typ in INVENTARIO_COMPLEMENT_COLUMNS.items():
        if name not in cols:
            emp_conn.execute(f"ALTER TABLE inventario_equipos ADD COLUMN {name} {typ}")
    emp_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventario_fuente ON inventario_equipos (fuente_import)"
    )
    emp_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventario_origen ON inventario_equipos (codigo_origen)"
    )
    emp_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventario_codigo_activo ON inventario_equipos (codigo_activo)"
    )
    emp_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventario_num_biomedica ON inventario_equipos (num_biomedica)"
    )


def _repair_instrument_coherence(emp_conn):
    from server.inventory_foscagib import repair_instrument_coherence

    try:
        n_bad = emp_conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM inventario_equipos ie
            JOIN pm_inventario p ON p.inventario_equipo_id = ie.id
            JOIN pm_cronograma cr ON cr.pm_inventario_id = p.id
            WHERE ie.estado = 'FUERA DE SERVICIO'
              AND (cr.mes_01+cr.mes_02+cr.mes_03+cr.mes_04+cr.mes_05+cr.mes_06
                  +cr.mes_07+cr.mes_08+cr.mes_09+cr.mes_10+cr.mes_11+cr.mes_12) > 0
            """
        ).fetchone()["n"]
        n_fake = emp_conn.execute(
            """
            SELECT COUNT(*) AS n FROM inventario_equipos
            WHERE fuente_import = 'FOSCAGIB'
              AND fecha_ultimo_pm IS NOT NULL
              AND (
                novedad_desc IS NULL
                OR (
                  UPPER(novedad_desc) NOT LIKE '%MP%'
                  AND UPPER(novedad_desc) NOT LIKE '%PREVENTIVO%'
                )
              )
            """
        ).fetchone()["n"]
        if not n_bad and not n_fake:
            return
        repair_instrument_coherence(emp_conn)
    except Exception as exc:
        print(f"[coherencia] ajuste omitido: {exc}")


def _repair_ubicacion_ids(emp_conn):
    from server.org_ubicacion import reorganize_ubicacion_ids_if_needed

    try:
        reorganize_ubicacion_ids_if_needed(emp_conn)
    except Exception as exc:
        print(f"[ubicacion-ids] ajuste omitido: {exc}")


def _seed_foscagib_inventory(emp_conn):
    from server.inventory_foscagib import seed_foscagib_if_needed

    try:
        seed_foscagib_if_needed(emp_conn)
    except Exception as exc:
        print(f"[foscagib] carga omitida: {exc}")


def _migrate_inventario_schema(emp_conn):
    """Migra inventario_equipos al esquema biomédico (#BIOMÉDICA … ESTADO)."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "inventario_equipos" not in tables:
        return

    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(inventario_equipos)").fetchall()
    }
    required = {
        "num_biomedica",
        "registro_invima",
        "equipo",
        "clasificacion_riesgo",
        "ubicacion",
    }
    if required.issubset(cols):
        return

    emp_conn.executescript(
        """
        CREATE TABLE inventario_equipos_new (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            servicio_id           INTEGER NOT NULL,
            num_biomedica         VARCHAR(100),
            registro_invima       VARCHAR(100),
            equipo                VARCHAR(255) NOT NULL,
            marca                 VARCHAR(255),
            serie                 VARCHAR(255),
            modelo                VARCHAR(255),
            clasificacion_riesgo  VARCHAR(100),
            ubicacion             VARCHAR(255),
            estado                VARCHAR(50),
            creation_date         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            aplica_mp             INTEGER,
            freq_mp               REAL,
            tiempo_mp             REAL,
            aplica_cal            INTEGER,
            freq_cal              REAL,
            tiempo_cal            REAL,
            aplica_val            INTEGER,
            freq_val              REAL,
            tiempo_val            REAL,
            FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
        );
        """
    )

    if "nombre_equipo" in cols:
        emp_conn.execute(
            """
            INSERT INTO inventario_equipos_new (
                id, servicio_id, num_biomedica, registro_invima, equipo,
                marca, serie, modelo, clasificacion_riesgo, ubicacion, estado, creation_date
            )
            SELECT
                id,
                servicio_id,
                codigo_equipo,
                NULL,
                COALESCE(NULLIF(TRIM(nombre_equipo), ''), 'Sin nombre'),
                marca,
                serie,
                modelo,
                NULL,
                NULL,
                CASE
                    WHEN UPPER(TRIM(REPLACE(REPLACE(COALESCE(estado, ''), 'Ó', 'O'), 'ó', 'o'))) = 'OPERATIVO'
                        THEN 'OPERATIVO'
                    WHEN UPPER(TRIM(REPLACE(REPLACE(COALESCE(estado, ''), 'Ó', 'O'), 'ó', 'o'))) LIKE '%REPAR%'
                        THEN 'EN REPARACIÓN'
                    WHEN UPPER(TRIM(COALESCE(estado, ''))) LIKE '%FUERA%'
                        THEN 'FUERA DE SERVICIO'
                    ELSE NULL
                END,
                creation_date
            FROM inventario_equipos
            """
        )

    emp_conn.executescript(
        """
        DROP TABLE inventario_equipos;
        ALTER TABLE inventario_equipos_new RENAME TO inventario_equipos;
        CREATE INDEX IF NOT EXISTS idx_inventario_servicio ON inventario_equipos (servicio_id);
        """
    )


def _migrate_dim_tercerizado_columns(emp_conn):
    """Flags de servicio tercerizado en actividades MP/Cal/Val del dimensionamiento."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "dim_actividad_equipo" not in tables:
        return
    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(dim_actividad_equipo)").fetchall()
    }
    for name in ("tercerizado_mp", "tercerizado_cal", "tercerizado_val"):
        if name not in cols:
            emp_conn.execute(
                f"ALTER TABLE dim_actividad_equipo ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
            )


def _migrate_dim_empresa_ratios(emp_conn):
    """Plantilla IC por criticidad (Bajo/Medio/Alto) y unificación de soporte vital."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "dim_parametros" in tables:
        cols = {
            c["name"]
            for c in emp_conn.execute("PRAGMA table_info(dim_parametros)").fetchall()
        }
        additions = {
            "equipos_ic_bajo": "REAL NOT NULL DEFAULT 70",
            "equipos_ic_medio": "REAL NOT NULL DEFAULT 50",
            "equipos_ic_alto": "REAL NOT NULL DEFAULT 20",
        }
        for name, typ in additions.items():
            if name not in cols:
                emp_conn.execute(f"ALTER TABLE dim_parametros ADD COLUMN {name} {typ}")
    if "dim_actividad_equipo" in tables:
        emp_conn.execute(
            """
            UPDATE dim_actividad_equipo
            SET criticidad = 'Alto'
            WHERE lower(trim(coalesce(criticidad, ''))) IN (
                    'soporte vital', 'soporte-vital', 'vital',
                    'especializado', 'especializados'
                )
               OR lower(coalesce(criticidad, '')) LIKE '%vital%'
                OR lower(coalesce(criticidad, '')) LIKE '%especializ%'
            """
        )
        act_cols = {
            c["name"]
            for c in emp_conn.execute("PRAGMA table_info(dim_actividad_equipo)").fetchall()
        }
        for name, typ in {
            "alto_unico_area": "INTEGER NOT NULL DEFAULT 0",
            "alto_especializado": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in act_cols:
                emp_conn.execute(f"ALTER TABLE dim_actividad_equipo ADD COLUMN {name} {typ}")


def _migrate_suficiencia_columns(emp_conn):
    """Agrega columnas nuevas del informe de suficiencia si la tabla ya existía."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "suficiencia_datos_servicio" in tables:
        datos_cols = {
            c["name"]
            for c in emp_conn.execute(
                "PRAGMA table_info(suficiencia_datos_servicio)"
            ).fetchall()
        }
        for name, typ in {
            "unidad_capacidad": "VARCHAR(100)",
            "jornadas_dia": "REAL DEFAULT 1",
            "ayuda_diligenciar": "TEXT",
        }.items():
            if name not in datos_cols:
                emp_conn.execute(
                    f"ALTER TABLE suficiencia_datos_servicio ADD COLUMN {name} {typ}"
                )

    if "suficiencia_evaluaciones" not in tables:
        return
    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(suficiencia_evaluaciones)").fetchall()
    }
    additions = {
        "concurrencia_pct": "REAL",
        "capacidad_base_auto": "REAL",
        "puestos_ocupados_auto": "REAL",
        "utilizacion_segura": "REAL",
        "respaldo_pct": "REAL",
        "horas_servicio_dia": "REAL",
        "ayuda_diligenciar": "TEXT",
    }
    for name, typ in additions.items():
        if name not in cols:
            emp_conn.execute(
                f"ALTER TABLE suficiencia_evaluaciones ADD COLUMN {name} {typ}"
            )


def _migrate_reportes_fallos(users_conn):
    from server.fallos import ensure_fallos_schema

    ensure_fallos_schema(users_conn)


def _migrate_eventos_log(users_conn):
    from server.event_log import ensure_eventos_schema

    ensure_eventos_schema(users_conn)


def _migrate_notificaciones_ocultas(users_conn):
    """Bandeja: ocultar notificaciones resueltas por usuario, sin borrar el registro."""
    users_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notificaciones_ocultas (
            notificacion_id INTEGER NOT NULL,
            usuario_id      INTEGER NOT NULL,
            hidden_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (notificacion_id, usuario_id)
        );
        """
    )


def _migrate_password_reset_tokens(users_conn):
    users_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id     INTEGER NOT NULL,
            token_hash     VARCHAR(64) NOT NULL UNIQUE,
            expires_at     DATETIME NOT NULL,
            used_at        DATETIME,
            creation_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_password_reset_hash ON password_reset_tokens (token_hash);
        CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens (usuario_id);
        """
    )


def _migrate_usuarios_profile_columns(users_conn):
    cols = {
        c["name"] for c in users_conn.execute("PRAGMA table_info(usuarios)").fetchall()
    }
    if "telefono" not in cols:
        users_conn.execute("ALTER TABLE usuarios ADD COLUMN telefono VARCHAR(40)")
    if "last_seen" not in cols:
        users_conn.execute("ALTER TABLE usuarios ADD COLUMN last_seen DATETIME")
    if "aviso_version" not in cols:
        users_conn.execute("ALTER TABLE usuarios ADD COLUMN aviso_version VARCHAR(20)")
    if "aviso_aceptado_en" not in cols:
        users_conn.execute("ALTER TABLE usuarios ADD COLUMN aviso_aceptado_en DATETIME")
    users_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bandeja_lecturas (
            usuario_id INTEGER NOT NULL,
            kind       VARCHAR(20) NOT NULL,
            item_id    INTEGER NOT NULL,
            leido_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, kind, item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_bandeja_lecturas_user
            ON bandeja_lecturas (usuario_id, kind);
        """
    )


def _migrate_jobs_codigo_permiso(users_conn):
    tables = {
        r["name"]
        for r in users_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "Jobs" not in tables:
        return
    cols = {
        c["name"] for c in users_conn.execute("PRAGMA table_info(Jobs)").fetchall()
    }
    if "codigo_permiso" not in cols:
        users_conn.execute("ALTER TABLE Jobs ADD COLUMN codigo_permiso VARCHAR(80)")


def _migrate_rbac_new_capability_defaults(users_conn):
    """Una sola vez: alinea módulos nuevos (p. ej. Agregar empresa) en roles alias."""
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_new_caps_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import align_new_capability_defaults_force

    align_new_capability_defaults_force(users_conn)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_new_caps_v1', '1')"
    )


def _migrate_asistencial_coord_independent_modules(users_conn):
    """
    Una sola vez: apaga instrumentos de ingeniería que el Coordinador asistencial
    tenía encendidos en bloque. Después el admin puede activarlos uno a uno.
    """
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_asist_coord_independent_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import _revoke_asistencial_coord_engineering_suite

    _revoke_asistencial_coord_engineering_suite(users_conn)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_asist_coord_independent_v1', '1')"
    )


def _migrate_rbac_access_servicio(users_conn):
    """Una sola vez: enciende Acceso a servicio específico en Admin y Dirección Operativa."""
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_access_servicio_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import _enable_access_servicio_defaults

    _enable_access_servicio_defaults(users_conn, force=True)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_access_servicio_v1', '1')"
    )


def _migrate_rbac_adquisicion_tablero(users_conn):
    """Una sola vez: tablero de adquisición para Admin, Dirección y Coordinación."""
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_adquisicion_tablero_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import _enable_adquisicion_tablero_defaults

    _enable_adquisicion_tablero_defaults(users_conn, force=True)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_adquisicion_tablero_v1', '1')"
    )


def _migrate_rbac_uat_instruments(users_conn):
    """Una sola vez: módulos que el acta UAT exige y la matriz tenía apagados."""
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_uat_instruments_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import enable_uat_instrument_defaults

    enable_uat_instrument_defaults(users_conn)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_uat_instruments_v1', '1')"
    )


def _migrate_rbac_dim_empresa(users_conn):
    """Una sola vez: dashboard empresarial para Admin, Dirección y Coordinación."""
    users_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = users_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'rbac_dim_empresa_v1'"
    ).fetchone()
    if done:
        return
    from server.rbac import _enable_dim_empresa_defaults

    _enable_dim_empresa_defaults(users_conn, force=True)
    users_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('rbac_dim_empresa_v1', '1')"
    )


def _migrate_inventario_adquisicion_observacion(emp_conn):
    """Observación al completar la forma de adquisición desde bandeja."""
    tables = {
        r["name"]
        for r in emp_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "inventario_equipos" not in tables:
        return
    cols = {
        c["name"]
        for c in emp_conn.execute("PRAGMA table_info(inventario_equipos)").fetchall()
    }
    if "adquisicion_observacion" not in cols:
        emp_conn.execute(
            "ALTER TABLE inventario_equipos ADD COLUMN adquisicion_observacion TEXT"
        )


def _migrate_solicitudes_ref_columns(sol_conn):
    """Añade vínculo tipado (ref_tipo/ref_id/meta_json) a solicitudes.db."""
    tables = {
        r["name"]
        for r in sol_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "solicitudes" not in tables:
        return
    cols = {
        c["name"] for c in sol_conn.execute("PRAGMA table_info(solicitudes)").fetchall()
    }
    if "ref_tipo" not in cols:
        sol_conn.execute("ALTER TABLE solicitudes ADD COLUMN ref_tipo VARCHAR(40)")
    if "ref_id" not in cols:
        sol_conn.execute("ALTER TABLE solicitudes ADD COLUMN ref_id INTEGER")
    if "meta_json" not in cols:
        sol_conn.execute("ALTER TABLE solicitudes ADD COLUMN meta_json TEXT")


def _migrate_solicitudes_workflow(sol_conn):
    """Estados TOMADA/RESUELTA/REENVIADA/CERRADA y columnas de asignación."""
    tables = {
        r["name"]
        for r in sol_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "solicitudes" not in tables:
        return
    info = sol_conn.execute("PRAGMA table_info(solicitudes)").fetchall()
    cols = {c["name"] for c in info}
    ddl_row = sol_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='solicitudes'"
    ).fetchone()
    ddl = (ddl_row["sql"] if ddl_row else "") or ""
    ddl_u = ddl.upper()
    extras = (
        ("servicio_id", "INTEGER"),
        ("asignado_a", "INTEGER"),
        ("asignado_nombre", "VARCHAR(255)"),
        ("comentario", "TEXT"),
        ("fecha_tomada", "DATETIME"),
        ("fecha_resuelta", "DATETIME"),
        ("parent_id", "INTEGER"),
    )
    for name, typ in extras:
        if name not in cols:
            sol_conn.execute(f"ALTER TABLE solicitudes ADD COLUMN {name} {typ}")
    need_rebuild = (
        "TOMADA" not in ddl_u
        or "REENVIADA" not in ddl_u
        or "CERRADA" not in ddl_u
        or "RESUELTA" not in ddl_u
    )
    if need_rebuild:
        from server.solicitudes_workflow import SOLICITUDES_COPY_COLS

        sol_conn.execute("PRAGMA foreign_keys = OFF")
        sol_conn.executescript(
            """
            CREATE TABLE solicitudes_wf_new (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitante_id       INTEGER NOT NULL,
                solicitante_email    VARCHAR(255),
                solicitante_nombre   VARCHAR(255),
                solicitante_roll     VARCHAR(50),
                solicitante_job      VARCHAR(255),
                destinatario_id      INTEGER NOT NULL,
                destinatario_email   VARCHAR(255),
                destinatario_nombre  VARCHAR(255),
                destinatario_rol     VARCHAR(40) NOT NULL,
                sede_id              INTEGER NOT NULL,
                empresa_id           INTEGER,
                servicio_id          INTEGER,
                ID_sede              VARCHAR(40),
                name_sede            VARCHAR(255),
                tipo                 VARCHAR(50) NOT NULL,
                mensaje              TEXT,
                prioridad            VARCHAR(20) NOT NULL DEFAULT 'MODERADA'
                                     CHECK (prioridad IN ('BAJA', 'MODERADA', 'ALTA')),
                estado               VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                                     CHECK (estado IN (
                                         'PENDIENTE', 'TOMADA', 'RESUELTA', 'REENVIADA', 'CERRADA',
                                         'APROBADA', 'RECHAZADA'
                                     )),
                asignado_a           INTEGER,
                asignado_nombre      VARCHAR(255),
                comentario           TEXT,
                fecha_tomada         DATETIME,
                fecha_resuelta       DATETIME,
                parent_id            INTEGER,
                calificacion         VARCHAR(40),
                calificado_at        DATETIME,
                resolved_at          DATETIME,
                ref_tipo             VARCHAR(40),
                ref_id               INTEGER,
                meta_json            TEXT,
                creation_date        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        present = {
            c["name"]
            for c in sol_conn.execute("PRAGMA table_info(solicitudes)").fetchall()
        }
        copy_cols = [c for c in SOLICITUDES_COPY_COLS if c in present]
        col_sql = ", ".join(copy_cols)
        sol_conn.execute(
            f"INSERT INTO solicitudes_wf_new ({col_sql}) SELECT {col_sql} FROM solicitudes"
        )
        sol_conn.execute("DROP TABLE solicitudes")
        sol_conn.execute("ALTER TABLE solicitudes_wf_new RENAME TO solicitudes")
        sol_conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_solicitudes_destinatario
                ON solicitudes (destinatario_id, estado);
            CREATE INDEX IF NOT EXISTS idx_solicitudes_solicitante
                ON solicitudes (solicitante_id, estado);
            CREATE INDEX IF NOT EXISTS idx_solicitudes_rol
                ON solicitudes (destinatario_rol, estado);
            CREATE INDEX IF NOT EXISTS idx_solicitudes_fecha
                ON solicitudes (creation_date DESC);
            """
        )
        sol_conn.execute("PRAGMA foreign_keys = ON")
    sol_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_asignado ON solicitudes (asignado_a, estado)"
    )
    sol_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_parent ON solicitudes (parent_id)"
    )
    sol_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_sede_tipo ON solicitudes (sede_id, tipo, estado)"
    )
    sol_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_estado_fecha ON solicitudes (estado, creation_date DESC)"
    )


def _migrate_solicitudes_ocultas(sol_conn):
    """Bandeja: ocultar solicitudes resueltas por usuario, sin borrar el registro."""
    sol_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS solicitudes_ocultas (
            solicitud_id INTEGER NOT NULL,
            usuario_id   INTEGER NOT NULL,
            hidden_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (solicitud_id, usuario_id)
        );
        """
    )


def _migrate_solicitudes_extra_columns(users_conn):
    """Legacy: columnas extra en usuarios.db (ya no se usan para escritura)."""
    tables = {
        r["name"]
        for r in users_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "solicitudes_permiso" not in tables:
        return
    cols = {
        c["name"]
        for c in users_conn.execute("PRAGMA table_info(solicitudes_permiso)").fetchall()
    }
    if "prioridad" not in cols:
        users_conn.execute(
            "ALTER TABLE solicitudes_permiso ADD COLUMN prioridad VARCHAR(20) DEFAULT 'MODERADA'"
        )
    if "destinatario_rol" not in cols:
        users_conn.execute(
            "ALTER TABLE solicitudes_permiso ADD COLUMN destinatario_rol VARCHAR(40)"
        )
    if "calificacion" not in cols:
        users_conn.execute(
            "ALTER TABLE solicitudes_permiso ADD COLUMN calificacion VARCHAR(40)"
        )
    if "calificado_at" not in cols:
        users_conn.execute(
            "ALTER TABLE solicitudes_permiso ADD COLUMN calificado_at DATETIME"
        )


def _migrate_solicitudes_from_usuarios(users_conn, sol_conn):
    """Copia una vez las solicitudes históricas de usuarios.db → solicitudes.db."""
    sol_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    done = sol_conn.execute(
        "SELECT value FROM app_meta WHERE key = 'migrated_from_usuarios_v1'"
    ).fetchone()
    if done:
        return

    tables = {
        r["name"]
        for r in users_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "solicitudes_permiso" not in tables:
        sol_conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('migrated_from_usuarios_v1', '1')"
        )
        return

    rows = users_conn.execute("SELECT * FROM solicitudes_permiso").fetchall()
    for row in rows:
        keys = row.keys() if hasattr(row, "keys") else []
        solicitante = users_conn.execute(
            """
            SELECT usuario_login, NAME_USER, LAST_NAME_USER, ROLL, JOB
            FROM usuarios WHERE id_usuario = ?
            """,
            (row["solicitante_id"],),
        ).fetchone()
        dest = None
        if row["coordinador_id"]:
            dest = users_conn.execute(
                """
                SELECT usuario_login, NAME_USER, LAST_NAME_USER
                FROM usuarios WHERE id_usuario = ?
                """,
                (row["coordinador_id"],),
            ).fetchone()
        dest_rol = "coordinacion"
        if "destinatario_rol" in keys and row["destinatario_rol"]:
            dest_rol = row["destinatario_rol"]
        prioridad = "MODERADA"
        if "prioridad" in keys and row["prioridad"]:
            prioridad = row["prioridad"]
        calificacion = row["calificacion"] if "calificacion" in keys else None
        calificado_at = row["calificado_at"] if "calificado_at" in keys else None
        sol_conn.execute(
            """
            INSERT OR IGNORE INTO solicitudes (
                id, solicitante_id, solicitante_email, solicitante_nombre,
                solicitante_roll, solicitante_job,
                destinatario_id, destinatario_email, destinatario_nombre, destinatario_rol,
                sede_id, empresa_id, ID_sede, name_sede,
                tipo, mensaje, prioridad, estado, calificacion, calificado_at, creation_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["solicitante_id"],
                solicitante["usuario_login"] if solicitante else None,
                (
                    f"{solicitante['NAME_USER']} {solicitante['LAST_NAME_USER']}".strip()
                    if solicitante
                    else None
                ),
                solicitante["ROLL"] if solicitante else None,
                solicitante["JOB"] if solicitante else None,
                row["coordinador_id"] or row["solicitante_id"],
                dest["usuario_login"] if dest else row["email_destino"],
                (
                    f"{dest['NAME_USER']} {dest['LAST_NAME_USER']}".strip()
                    if dest
                    else None
                ),
                dest_rol,
                row["sede_id"],
                None,
                None,
                None,
                row["tipo"],
                row["mensaje"],
                prioridad,
                row["estado"],
                calificacion,
                calificado_at,
                row["creation_date"],
            ),
        )
    sol_conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('migrated_from_usuarios_v1', '1')"
    )


def warn_onedrive_conflicts() -> None:
    """Avisa si OneDrive dejó copias al lado de las bases vivas.

    Esas copias no se abren (el nombre no coincide), pero se confunden con
    la base en uso cuando el proyecto se sincroniza desde otro equipo.
    """
    if not DATA_DIR.exists():
        return
    markers = ("conflict", "malformed", "copia de")
    found = []
    for path in DATA_DIR.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if any(marker in name for marker in markers):
            found.append(path.name)
    if found:
        print(
            "[db] Hay copias de OneDrive o bases en cuarentena junto a las bases vivas. "
            "El aplicativo no las usa. Muévelas fuera de data/: "
            + ", ".join(sorted(found))
        )


def init_db():
    from server.backup import create_snapshot, maybe_create_snapshot
    from server.rbac import ensure_rbac_seed

    warn_onedrive_conflicts()

    try:
        maybe_create_snapshot("pre-init", min_interval_seconds=6 * 3600)
    except Exception as exc:
        print(f"[backup] pre-init omitido: {exc}")

    users_schema = SCHEMA_USERS.read_text(encoding="utf-8")
    empresas_schema = SCHEMA_EMPRESAS.read_text(encoding="utf-8")
    solicitudes_schema = SCHEMA_SOLICITUDES.read_text(encoding="utf-8")
    parametros_schema = SCHEMA_PARAMETROS_EQUIPO.read_text(encoding="utf-8")
    frecuencia_pm_schema = SCHEMA_FRECUENCIA_PM.read_text(encoding="utf-8")
    preinstalacion_schema = SCHEMA_PREINSTALACION.read_text(encoding="utf-8")

    with (
        get_users_connection() as users_conn,
        get_empresas_connection() as emp_conn,
        get_solicitudes_connection() as sol_conn,
        get_parametros_equipo_connection() as param_conn,
    ):
        users_conn.executescript(users_schema)
        emp_conn.executescript(empresas_schema)
        emp_conn.executescript(frecuencia_pm_schema)
        emp_conn.executescript(preinstalacion_schema)
        from server.kpis import ensure_kpis_schema
        from server.ejecucion_mantenimientos import ensure_ejecucion_schema

        ensure_kpis_schema(emp_conn)
        ensure_ejecucion_schema(emp_conn)
        _restore_org_from_usuarios_legacy(emp_conn, users_conn)
        sol_conn.executescript(solicitudes_schema)
        param_conn.executescript(parametros_schema)
        _migrate_inventario_schema(emp_conn)
        _migrate_inventario_std_params(emp_conn)
        _migrate_inventario_complement_columns(emp_conn)
        _migrate_dim_tercerizado_columns(emp_conn)
        _migrate_dim_empresa_ratios(emp_conn)
        _migrate_inventario_adquisicion_observacion(emp_conn)
        _migrate_suficiencia_columns(emp_conn)
        from server.formula_versions import ensure_formula_versions_schema

        ensure_formula_versions_schema(emp_conn)
        _ensure_admin_roll_allowed(users_conn)
        _migrate_cross_db_refs(users_conn)
        _migrate_usuarios_profile_columns(users_conn)
        _migrate_password_reset_tokens(users_conn)
        _migrate_notificaciones_ocultas(users_conn)
        _migrate_reportes_fallos(users_conn)
        _migrate_eventos_log(users_conn)
        _migrate_jobs_codigo_permiso(users_conn)
        _migrate_solicitudes_extra_columns(users_conn)
        _migrate_solicitudes_ref_columns(sol_conn)
        _migrate_solicitudes_ocultas(sol_conn)
        _migrate_solicitudes_workflow(sol_conn)
        _seed_users(users_conn)
        ensure_rbac_seed(users_conn)
        _migrate_rbac_new_capability_defaults(users_conn)
        _migrate_asistencial_coord_independent_modules(users_conn)
        _migrate_rbac_access_servicio(users_conn)
        _migrate_rbac_adquisicion_tablero(users_conn)
        _migrate_rbac_dim_empresa(users_conn)
        _migrate_rbac_uat_instruments(users_conn)
        from server.org_ubicacion import relabel_santa_cruz

        relabel_santa_cruz(emp_conn)
        _seed_empresas_structure(emp_conn, users_conn)
        _seed_inventario_hipotetico(emp_conn, users_conn)
        _seed_foscagib_inventory(emp_conn)
        from server.ejecucion_mantenimientos import maybe_sync_foscagib_ejecucion

        try:
            maybe_sync_foscagib_ejecucion(emp_conn)
        except Exception as exc:
            print(f"[ejecucion] seed omitido: {exc}")
        _repair_ubicacion_ids(emp_conn)
        _repair_instrument_coherence(emp_conn)
        _migrate_solicitudes_from_usuarios(users_conn, sol_conn)
        users_conn.commit()
        emp_conn.commit()
        sol_conn.commit()
        param_conn.commit()

    try:
        create_snapshot("post-init")
    except Exception as exc:
        print(f"[backup] post-init omitido: {exc}")

    return {
        "usuarios": USERS_DB_PATH,
        "empresas": EMPRESAS_DB_PATH,
        "solicitudes": SOLICITUDES_DB_PATH,
        "parametros_equipo": PARAMETROS_EQUIPO_DB_PATH,
    }
