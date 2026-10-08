-- Base de datos de SOLICITUDES (data/solicitudes.db)
-- Canal propio de radicación y distribución por destinatario.

CREATE TABLE IF NOT EXISTS solicitudes (
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

CREATE INDEX IF NOT EXISTS idx_solicitudes_destinatario
    ON solicitudes (destinatario_id, estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_solicitante
    ON solicitudes (solicitante_id, estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_rol
    ON solicitudes (destinatario_rol, estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_fecha
    ON solicitudes (creation_date DESC);

-- Ocultar mensaje resuelto en la bandeja de un usuario (no borra el registro del otro).
CREATE TABLE IF NOT EXISTS solicitudes_ocultas (
    solicitud_id INTEGER NOT NULL,
    usuario_id   INTEGER NOT NULL,
    hidden_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (solicitud_id, usuario_id)
);
