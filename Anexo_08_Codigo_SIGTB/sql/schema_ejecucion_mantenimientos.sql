-- Ejecución de mantenimientos (preventivo, correctivo y visitas).
-- Tabla en empresas.db (no un .db aparte) para poder cruzar inventario/sedes
-- sin ATTACH. La llave de EQUIPO es (codigo_biomedica, codigo_activo);
-- cada fila es un evento, no un equipo único.

CREATE TABLE IF NOT EXISTS ejecucion_mantenimientos (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_biomedica      TEXT NOT NULL,
    codigo_activo         TEXT NOT NULL,
    codigo_biomedica_norm TEXT NOT NULL,
    codigo_activo_norm    TEXT NOT NULL,
    empresa_id            INTEGER NOT NULL,
    sede_id               INTEGER,
    servicio_id           INTEGER,
    tipo_mantenimiento    TEXT NOT NULL
                          CHECK (tipo_mantenimiento IN ('preventivo', 'correctivo', 'visita')),
    fecha_ejecucion       DATE,
    fecha_atencion        TEXT,
    fecha_cierre          TEXT,
    proveedor             TEXT,
    duracion_horas        REAL,
    observaciones         TEXT,
    fuente                TEXT NOT NULL DEFAULT 'manual'
                          CHECK (fuente IN ('manual', 'importado', 'sincronizado')),
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ejecucion_biomedica
    ON ejecucion_mantenimientos (codigo_biomedica);

CREATE INDEX IF NOT EXISTS idx_ejecucion_activo
    ON ejecucion_mantenimientos (codigo_activo);

CREATE INDEX IF NOT EXISTS idx_ejecucion_sede
    ON ejecucion_mantenimientos (sede_id);

CREATE INDEX IF NOT EXISTS idx_ejecucion_empresa_fecha
    ON ejecucion_mantenimientos (empresa_id, fecha_ejecucion);

CREATE INDEX IF NOT EXISTS idx_ejecucion_llave_norm
    ON ejecucion_mantenimientos (empresa_id, codigo_biomedica_norm, codigo_activo_norm);

CREATE INDEX IF NOT EXISTS idx_ejecucion_tipo_fecha
    ON ejecucion_mantenimientos (empresa_id, tipo_mantenimiento, fecha_ejecucion);
