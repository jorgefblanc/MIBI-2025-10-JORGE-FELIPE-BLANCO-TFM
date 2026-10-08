-- Base de datos de EMPRESAS (data/empresas.db)
-- Jerarquía: Empresa → Sede (exclusiva) → Servicio(s)

CREATE TABLE IF NOT EXISTS empresas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_Empresa    VARCHAR(255) NOT NULL,
    ID_NIT        VARCHAR(50)  NOT NULL UNIQUE COLLATE NOCASE,
    creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_empresas_nit ON empresas (ID_NIT);

CREATE TABLE IF NOT EXISTS sedes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_sede       VARCHAR(20)  NOT NULL,
    name_sede     VARCHAR(255) NOT NULL,
    prefix        VARCHAR(10)  NOT NULL,
    empresa_id    INTEGER      NOT NULL,
    creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (empresa_id, ID_sede),
    UNIQUE (empresa_id, name_sede COLLATE NOCASE),
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sedes_empresa ON sedes (empresa_id);

CREATE TABLE IF NOT EXISTS servicios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_servicio    VARCHAR(20)  NOT NULL,
    name_servicio  VARCHAR(255) NOT NULL,
    prefix         VARCHAR(10)  NOT NULL,
    sede_id        INTEGER      NOT NULL,
    creation_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (sede_id, ID_servicio),
    UNIQUE (sede_id, name_servicio COLLATE NOCASE),
    FOREIGN KEY (sede_id) REFERENCES sedes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_servicios_sede ON servicios (sede_id);

-- Contadores de IDs por empresa+prefijo (sedes y servicios)
CREATE TABLE IF NOT EXISTS id_counters (
    scope_type  VARCHAR(20) NOT NULL, -- 'sede' | 'servicio'
    scope_key   VARCHAR(40) NOT NULL, -- empresa_id o sede_id
    prefix      VARCHAR(10) NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scope_type, scope_key, prefix)
);

-- ubicacion_logica no es columna: se deriva en server/inventario.py a partir de
-- codigo_ubicacion, servicios.ID_servicio/name_servicio, ubicacion, estado y fecha_baja
-- (bodega de bajas / almacén general ⇒ equipo dado de baja).
CREATE TABLE IF NOT EXISTS inventario_equipos (
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
    estado                VARCHAR(50) CHECK (
        estado IS NULL OR estado IN ('OPERATIVO', 'EN REPARACIÓN', 'FUERA DE SERVICIO')
    ),
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
    clasificacion_biomedica VARCHAR(120),
    tecnologia            VARCHAR(120),
    forma_adquisicion     VARCHAR(120),
    adquisicion_observacion TEXT,
    vida_util_anios       REAL,
    vida_util_txt         VARCHAR(80),
    fecha_compra          DATE,
    fecha_operacion       DATE,
    fecha_garantia        DATE,
    fecha_baja            DATE,
    fecha_ultimo_pm       DATE,
    fecha_actualizacion   DATETIME,
    codigo_activo         VARCHAR(100),
    codigo_ubicacion      VARCHAR(80),
    institucion_origen    VARCHAR(255),
    fuente_import         VARCHAR(40),
    codigo_origen         VARCHAR(80),
    novedad_desc          TEXT,
    voltaje               VARCHAR(80),
    corriente             VARCHAR(80),
    potencia              VARCHAR(80),
    peso                  VARCHAR(80),
    temperatura_trabajo   VARCHAR(80),
    presion               VARCHAR(80),
    fuente_alimentacion   VARCHAR(120),
    comercializador       VARCHAR(255),
    manual_operacion      INTEGER,
    manual_servicio       INTEGER,
    componente1           VARCHAR(255),
    componente2           VARCHAR(255),
    componente3           VARCHAR(255),
    periodicidad_mp       VARCHAR(80),
    periodicidad_cal      VARCHAR(80),
    requiere_calibracion  INTEGER,
    FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inventario_servicio ON inventario_equipos (servicio_id);

-- —— Módulo Suficiencia de equipos ——
CREATE TABLE IF NOT EXISTS suficiencia_parametros (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    utilizacion_segura   REAL NOT NULL DEFAULT 0.75,
    respaldo_general     REAL NOT NULL DEFAULT 0.20,
    umbral_alerta        REAL NOT NULL DEFAULT 0.80,
    redondeo             VARCHAR(20) NOT NULL DEFAULT 'CEIL',
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO suficiencia_parametros (id) VALUES (1);

CREATE TABLE IF NOT EXISTS suficiencia_datos_servicio (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id          INTEGER NOT NULL UNIQUE,
    capacidad_instalada  REAL,
    unidad_capacidad     VARCHAR(100),
    promedio_ocupado     REAL,
    horas_servicio_dia   REAL,
    jornadas_dia         REAL DEFAULT 1,
    fuente_dato          TEXT,
    comentario           TEXT,
    ayuda_diligenciar    TEXT,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS suficiencia_evaluaciones (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id          INTEGER NOT NULL,
    equipo               VARCHAR(255) NOT NULL,
    tipo_calculo         VARCHAR(50) NOT NULL DEFAULT 'mixto',
    pacientes_simultaneos REAL,
    demanda_diaria       REAL,
    tiempo_uso_min       REAL,
    minimo_tecnico       REAL DEFAULT 0,
    respaldo_especifico  REAL DEFAULT 0,
    fuente_dato          TEXT,
    comentario           TEXT,
    cantidad_total       INTEGER DEFAULT 0,
    cantidad_operativa   INTEGER DEFAULT 0,
    en_mantenimiento     INTEGER DEFAULT 0,
    prestado             INTEGER DEFAULT 0,
    disponible_real      INTEGER DEFAULT 0,
    ocupacion_pct        REAL,
    concurrencia_pct     REAL,
    capacidad_base_auto  REAL,
    puestos_ocupados_auto REAL,
    utilizacion_segura   REAL,
    respaldo_pct         REAL,
    horas_servicio_dia   REAL,
    req_capacidad        REAL,
    req_demanda          REAL,
    requerido_base       REAL,
    respaldo_unidades    REAL,
    requerido_final      REAL,
    brecha               REAL,
    suficiencia_pct      REAL,
    resultado            VARCHAR(30),
    acciones_sugeridas   TEXT,
    ayuda_diligenciar    TEXT,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (servicio_id, equipo COLLATE NOCASE),
    FOREIGN KEY (servicio_id) REFERENCES servicios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_suficiencia_eval_servicio
    ON suficiencia_evaluaciones (servicio_id);

-- —— Módulo Dimensionamiento de personal (Ingeniería Clínica) ——
CREATE TABLE IF NOT EXISTS dim_parametros (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id                 INTEGER NOT NULL UNIQUE,
    horas_semana               REAL NOT NULL DEFAULT 42,
    semanas_anio               REAL NOT NULL DEFAULT 52,
    vacaciones_h               REAL NOT NULL DEFAULT 132,
    festivos_h                 REAL NOT NULL DEFAULT 88,
    permisos_h                 REAL NOT NULL DEFAULT 80,
    productividad              REAL NOT NULL DEFAULT 0.7,
    correctivo_sin_historico   REAL NOT NULL DEFAULT 0.15,
    contingencia               REAL NOT NULL DEFAULT 0.15,
    equipos_ic_bajo            REAL NOT NULL DEFAULT 70,
    equipos_ic_medio           REAL NOT NULL DEFAULT 50,
    equipos_ic_alto            REAL NOT NULL DEFAULT 20,
    updated_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dim_actividad_equipo (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    inventario_equipo_id          INTEGER NOT NULL UNIQUE,
    criticidad                    VARCHAR(40) NOT NULL DEFAULT 'Medio',
    alto_unico_area               INTEGER NOT NULL DEFAULT 0,
    alto_especializado            INTEGER NOT NULL DEFAULT 0,
    aplica_mp                     INTEGER NOT NULL DEFAULT 1,
    freq_mp                       REAL NOT NULL DEFAULT 0,
    tiempo_mp                     REAL NOT NULL DEFAULT 0,
    aplica_cal                    INTEGER NOT NULL DEFAULT 0,
    freq_cal                      REAL NOT NULL DEFAULT 0,
    tiempo_cal                    REAL NOT NULL DEFAULT 0,
    aplica_val                    INTEGER NOT NULL DEFAULT 0,
    freq_val                      REAL NOT NULL DEFAULT 0,
    tiempo_val                    REAL NOT NULL DEFAULT 0,
    tercerizado_mp                INTEGER NOT NULL DEFAULT 0,
    tercerizado_cal               INTEGER NOT NULL DEFAULT 0,
    tercerizado_val               INTEGER NOT NULL DEFAULT 0,
    aplica_cap                    INTEGER NOT NULL DEFAULT 0,
    freq_cap                      REAL NOT NULL DEFAULT 0,
    tiempo_cap                    REAL NOT NULL DEFAULT 0,
    tiene_historico_correctivo    INTEGER NOT NULL DEFAULT 0,
    historico_correctivo_h        REAL,
    gestion_documental_h          REAL NOT NULL DEFAULT 0,
    acompanamiento_h              REAL NOT NULL DEFAULT 0,
    otras_tareas_h                REAL NOT NULL DEFAULT 0,
    observaciones                 TEXT,
    updated_at                    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventario_equipo_id) REFERENCES inventario_equipos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dim_actividad_equipo
    ON dim_actividad_equipo (inventario_equipo_id);

