-- Módulo: Frecuencia de Mantenimiento Preventivo (OMS + Fabricante + GE)
-- Tablas equivalentes al Excel Instrumento_Frecuencia_Mantenimiento_Preventivo_...

CREATE TABLE IF NOT EXISTS pm_inventario (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id           INTEGER NOT NULL,
    inventario_equipo_id  INTEGER,
    codigo_equipo         VARCHAR(40),
    equipo                VARCHAR(255) NOT NULL,
    marca                 VARCHAR(255),
    modelo                VARCHAR(255),
    serie                 VARCHAR(255),
    estado                VARCHAR(80),
    pm_fabricante_meses   REAL,
    funcion               VARCHAR(120),
    puntaje_funcion       REAL,
    aplicacion            VARCHAR(120),
    puntaje_aplicacion    REAL,
    requisito_mantto      VARCHAR(120),
    puntaje_requisito     REAL,
    antecedentes_fallas   VARCHAR(80),
    puntaje_fallas        REAL,
    ge_total              REAL,
    frecuencia_oms        VARCHAR(80),
    frecuencia_definitiva VARCHAR(120),
    accion_sugerida       TEXT,
    fecha_ultimo_pm       DATE,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_inventario_servicio ON pm_inventario (servicio_id);

CREATE TABLE IF NOT EXISTS pm_cronograma (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    pm_inventario_id      INTEGER NOT NULL,
    anio                  INTEGER NOT NULL,
    frecuencia_definitiva VARCHAR(120),
    fecha_ultimo_pm       DATE,
    mes_01                INTEGER NOT NULL DEFAULT 0,
    mes_02                INTEGER NOT NULL DEFAULT 0,
    mes_03                INTEGER NOT NULL DEFAULT 0,
    mes_04                INTEGER NOT NULL DEFAULT 0,
    mes_05                INTEGER NOT NULL DEFAULT 0,
    mes_06                INTEGER NOT NULL DEFAULT 0,
    mes_07                INTEGER NOT NULL DEFAULT 0,
    mes_08                INTEGER NOT NULL DEFAULT 0,
    mes_09                INTEGER NOT NULL DEFAULT 0,
    mes_10                INTEGER NOT NULL DEFAULT 0,
    mes_11                INTEGER NOT NULL DEFAULT 0,
    mes_12                INTEGER NOT NULL DEFAULT 0,
    observacion           TEXT,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pm_inventario_id, anio),
    FOREIGN KEY (pm_inventario_id) REFERENCES pm_inventario(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_cronograma_anio ON pm_cronograma (anio);

CREATE TABLE IF NOT EXISTS pm_validacion (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    pm_inventario_id      INTEGER NOT NULL,
    anio                  INTEGER NOT NULL,
    mes                   INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    fecha_programada      DATE,
    fecha_ejecucion       DATE,
    estado                VARCHAR(40) NOT NULL DEFAULT 'PENDIENTE'
                          CHECK (estado IN ('PENDIENTE', 'CUMPLIDO', 'APROBADO', 'RECHAZADO')),
    ejecutado_por         INTEGER,
    ejecutado_por_login   VARCHAR(255),
    evidencia             TEXT,
    validado_por          INTEGER,
    validado_por_login    VARCHAR(255),
    calificacion          REAL,
    comentario            TEXT,
    solicitud_id          INTEGER,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pm_inventario_id, anio, mes),
    FOREIGN KEY (pm_inventario_id) REFERENCES pm_inventario(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_validacion_estado ON pm_validacion (estado);
