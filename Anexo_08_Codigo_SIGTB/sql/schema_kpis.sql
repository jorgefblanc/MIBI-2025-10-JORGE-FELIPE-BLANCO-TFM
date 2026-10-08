-- Módulo KPIs de ingeniería clínica (reemplaza el panel de equipos de respaldo).
-- Solo se persisten parámetros, entradas mensuales y estado del plan de decisiones.
-- Los KPI se recalculan en cada lectura para no desincronizar fórmulas.

CREATE TABLE IF NOT EXISTS kpis_parametros (
    empresa_id INTEGER PRIMARY KEY,
    anio INTEGER NOT NULL DEFAULT 2026,
    institucion TEXT,
    proceso TEXT,
    responsable TEXT,
    costo_diario_inactividad REAL NOT NULL DEFAULT 2000000,
    factor_mitigacion REAL NOT NULL DEFAULT 0.5,
    horas_laborales_tecnico_mes REAL NOT NULL DEFAULT 192,
    costo_externo_referencia REAL NOT NULL DEFAULT 0,
    metas_json TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kpis_entrada_mes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    payload_json TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER,
    UNIQUE (empresa_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS idx_kpis_entrada_emp_anio
    ON kpis_entrada_mes (empresa_id, anio);

CREATE TABLE IF NOT EXISTS kpis_decisiones (
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    indicador_key TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    observaciones TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (empresa_id, anio, indicador_key)
);
