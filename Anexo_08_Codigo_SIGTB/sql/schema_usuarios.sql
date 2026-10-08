-- Base de datos de USUARIOS (data/usuarios.db)

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario     INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_login  VARCHAR(255) NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  VARCHAR(255) NOT NULL,
    creation_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    NAME_USER      VARCHAR(255) NOT NULL,
    LAST_NAME_USER VARCHAR(255) NOT NULL,
    JOB            VARCHAR(255) NOT NULL,
    ROLL           VARCHAR(50)  NOT NULL CHECK (ROLL IN ('ASISTENCIAL', 'OPERATIVO', 'ADMIN')),
    empresa_id     INTEGER,
    telefono       VARCHAR(40),
    last_seen      DATETIME,
    aviso_version  VARCHAR(20),
    aviso_aceptado_en DATETIME
);

CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios (usuario_login);
CREATE INDEX IF NOT EXISTS idx_usuarios_empresa ON usuarios (empresa_id);

-- Sedes asignadas a coordinadores (sede_id lógico de empresas.db)
CREATE TABLE IF NOT EXISTS usuario_sedes (
    usuario_id  INTEGER NOT NULL,
    sede_id     INTEGER NOT NULL,
    assigned_by INTEGER,
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, sede_id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS solicitudes_permiso (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitante_id  INTEGER NOT NULL,
    sede_id         INTEGER NOT NULL,
    tipo            VARCHAR(50) NOT NULL,
    mensaje         TEXT,
    estado          VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                    CHECK (estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA')),
    coordinador_id  INTEGER,
    email_destino   VARCHAR(255),
    prioridad       VARCHAR(20) DEFAULT 'MODERADA',
    destinatario_rol VARCHAR(40),
    calificacion    VARCHAR(40),
    calificado_at   DATETIME,
    creation_date   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (solicitante_id) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (coordinador_id) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS notificaciones_admin (
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

CREATE INDEX IF NOT EXISTS idx_notif_admin_estado ON notificaciones_admin (estado);

CREATE TABLE IF NOT EXISTS notificaciones_ocultas (
    notificacion_id INTEGER NOT NULL,
    usuario_id      INTEGER NOT NULL,
    hidden_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (notificacion_id, usuario_id)
);

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

-- RBAC administrativo: Roles × JOBS (módulos) × Permisos
CREATE TABLE IF NOT EXISTS Roles (
    id_rol     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_rol VARCHAR(100) NOT NULL UNIQUE COLLATE NOCASE,
    estado     VARCHAR(20)  NOT NULL DEFAULT 'ACTIVO'
               CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    protegido  INTEGER NOT NULL DEFAULT 0,
    creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Jobs (
    id_job      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_job  VARCHAR(150) NOT NULL UNIQUE COLLATE NOCASE,
    descripcion TEXT,
    icono       VARCHAR(40),
    codigo_permiso VARCHAR(80),
    estado      VARCHAR(20) NOT NULL DEFAULT 'ACTIVO'
                CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Permisos (
    id_permiso     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_rol         INTEGER NOT NULL,
    id_job         INTEGER NOT NULL,
    permiso_activo INTEGER NOT NULL DEFAULT 0 CHECK (permiso_activo IN (0, 1)),
    UNIQUE (id_rol, id_job),
    FOREIGN KEY (id_rol) REFERENCES Roles(id_rol) ON DELETE CASCADE,
    FOREIGN KEY (id_job) REFERENCES Jobs(id_job) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_permisos_rol ON Permisos (id_rol);
CREATE INDEX IF NOT EXISTS idx_permisos_job ON Permisos (id_job);

CREATE TABLE IF NOT EXISTS reportes_fallos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo VARCHAR(40) NOT NULL
        CHECK (tipo IN ('Funcional', 'Estructura', 'Diseño', 'Modulo')),
    descripcion TEXT NOT NULL,
    solucion_recomendada TEXT,
    remitente_nombre VARCHAR(255) NOT NULL DEFAULT 'Invitado',
    remitente_id INTEGER,
    remitente_email VARCHAR(255),
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE', 'RESUELTO', 'IMPLEMENTADO', 'DESCARTADO')),
    observacion_admin TEXT,
    creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    resolved_by INTEGER
);

CREATE TABLE IF NOT EXISTS reportes_fallos_ocultos (
    reporte_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    hidden_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (reporte_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS eventos_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    usuario_id INTEGER,
    usuario_nombre VARCHAR(255),
    usuario_login VARCHAR(255),
    accion TEXT NOT NULL,
    modulo VARCHAR(80),
    sede_id INTEGER,
    servicio_id INTEGER,
    parametros_json TEXT,
    resultado_json TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eventos_log_avisos (
    empresa_id INTEGER PRIMARY KEY,
    first_event_at DATETIME NOT NULL,
    aviso_at DATETIME,
    notificacion_id INTEGER
);

-- Lectura por usuario (bandeja: solicitudes, notificaciones, fallos).
CREATE TABLE IF NOT EXISTS bandeja_lecturas (
    usuario_id INTEGER NOT NULL,
    kind       VARCHAR(20) NOT NULL,
    item_id    INTEGER NOT NULL,
    leido_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, kind, item_id)
);
CREATE INDEX IF NOT EXISTS idx_bandeja_lecturas_user ON bandeja_lecturas (usuario_id, kind);

