-- Versionado de fórmulas de los instrumentos (TFM).
CREATE TABLE IF NOT EXISTS formula_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo      VARCHAR(80) NOT NULL,
    version     VARCHAR(40) NOT NULL,
    descripcion TEXT,
    fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activo      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (modulo, version)
);

CREATE TABLE IF NOT EXISTS formula_ejecuciones (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    formula_version_id INTEGER,
    modulo             VARCHAR(80) NOT NULL,
    version            VARCHAR(40) NOT NULL,
    empresa_id         INTEGER,
    sede_id            INTEGER,
    servicio_id        INTEGER,
    usuario_id         INTEGER,
    parametros_json    TEXT,
    resultado_json     TEXT,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (formula_version_id) REFERENCES formula_versions(id)
);

CREATE INDEX IF NOT EXISTS idx_formula_ejecuciones_mod
    ON formula_ejecuciones (modulo, created_at);
CREATE INDEX IF NOT EXISTS idx_formula_ejecuciones_emp
    ON formula_ejecuciones (empresa_id, created_at);
