-- Módulo: Preinstalación de Tecnología Biomédica (SITIO)
-- Réplica de Instrumento_Preinstalacion_Tecnologia_Biomedica_SITIO_FINAL.xlsx

CREATE TABLE IF NOT EXISTS pre_evaluaciones (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id              INTEGER NOT NULL,
    inventario_equipo_id     INTEGER,
    institucion              VARCHAR(255),
    sede_id                  INTEGER,
    ID_sede                  VARCHAR(40),
    name_sede                VARCHAR(255),
    ID_servicio              VARCHAR(40),
    servicio_area            VARCHAR(255),
    tecnologia               VARCHAR(255),
    marca_modelo             VARCHAR(255),
    marca                    VARCHAR(255),
    modelo                   VARCHAR(255),
    proveedor                VARCHAR(255),
    serial_codigo            VARCHAR(120),
    num_biomedica            VARCHAR(100),
    registro_invima          VARCHAR(100),
    ubicacion_propuesta      VARCHAR(255),
    fecha_visita             DATE,
    responsable_verificacion VARCHAR(255),
    acompanante_servicio     VARCHAR(255),
    fuente_requisitos        TEXT,
    objetivo                 TEXT,
    preset_id                INTEGER,
    preset_nombre            VARCHAR(255),
    estado_eval              VARCHAR(40) NOT NULL DEFAULT 'BORRADOR'
                             CHECK (estado_eval IN ('BORRADOR', 'EN_REVISION', 'APROBADA', 'RECHAZADA')),
    evaluables_fab           INTEGER DEFAULT 0,
    evaluables_doc           INTEGER DEFAULT 0,
    total_evaluables         INTEGER DEFAULT 0,
    cumplidos                INTEGER DEFAULT 0,
    no_cumplidos             INTEGER DEFAULT 0,
    pendientes               INTEGER DEFAULT 0,
    no_aplica                INTEGER DEFAULT 0,
    criticos_abiertos        INTEGER DEFAULT 0,
    pct_cumplimiento         REAL DEFAULT 0,
    decision                 VARCHAR(80),
    concepto_tecnico         TEXT,
    firma_ic_nombre          VARCHAR(255),
    firma_ic_cargo           VARCHAR(255),
    firma_ic_fecha           DATE,
    firma_servicio_nombre    VARCHAR(255),
    firma_servicio_cargo     VARCHAR(255),
    firma_servicio_fecha     DATE,
    comentario_asistencial   TEXT,
    aprobado_por             INTEGER,
    aprobado_por_login       VARCHAR(255),
    aprobado_at              DATETIME,
    solicitud_id             INTEGER,
    created_by               INTEGER,
    created_by_login         VARCHAR(255),
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pre_eval_servicio ON pre_evaluaciones (servicio_id);
CREATE INDEX IF NOT EXISTS idx_pre_eval_equipo ON pre_evaluaciones (inventario_equipo_id);

CREATE TABLE IF NOT EXISTS pre_items (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluacion_id        INTEGER NOT NULL,
    seccion              VARCHAR(20) NOT NULL
                         CHECK (seccion IN ('fabricante', 'documentacion')),
    item_id              INTEGER NOT NULL,
    categoria            VARCHAR(80) NOT NULL,
    requisito            TEXT NOT NULL,
    exigencia            TEXT,
    evidencia            TEXT,
    criticidad           VARCHAR(20) NOT NULL DEFAULT 'Mayor'
                         CHECK (criticidad IN ('Crítico', 'Mayor', 'Menor')),
    estado               VARCHAR(20) NOT NULL DEFAULT 'Pendiente'
                         CHECK (estado IN ('Cumple', 'No cumple', 'Pendiente', 'No aplica')),
    responsable_cierre   VARCHAR(255),
    fecha_compromiso     DATE,
    observaciones        TEXT,
    evidencia_archivo    VARCHAR(500),
    orden                INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (evaluacion_id) REFERENCES pre_evaluaciones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pre_items_eval ON pre_items (evaluacion_id, seccion);

CREATE TABLE IF NOT EXISTS pre_presets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo         VARCHAR(80) NOT NULL UNIQUE,
    nombre         VARCHAR(255) NOT NULL,
    tipo_equipo    VARCHAR(255),
    marca          VARCHAR(255),
    modelo         VARCHAR(255),
    fabricante     VARCHAR(255),
    fuente         TEXT,
    notas          TEXT,
    es_global      INTEGER NOT NULL DEFAULT 1,
    empresa_id     INTEGER,
    created_by     INTEGER,
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pre_preset_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id    INTEGER NOT NULL,
    seccion      VARCHAR(20) NOT NULL
                 CHECK (seccion IN ('fabricante', 'documentacion')),
    item_id      INTEGER NOT NULL,
    categoria    VARCHAR(80) NOT NULL,
    requisito    TEXT NOT NULL,
    exigencia    TEXT,
    criticidad   VARCHAR(20) NOT NULL DEFAULT 'Mayor',
    estado_inicial VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    orden        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (preset_id) REFERENCES pre_presets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pre_preset_items ON pre_preset_items (preset_id);
