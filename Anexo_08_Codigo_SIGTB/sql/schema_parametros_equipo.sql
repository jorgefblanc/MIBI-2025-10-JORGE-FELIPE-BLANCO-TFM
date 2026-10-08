-- Catálogo de parámetros MP / Calibración / Validación por tipo de equipo.
-- Base independiente: data/parametros_equipo.db
-- Solo se conserva el último valor por descripción (sin histórico).

CREATE TABLE IF NOT EXISTS parametros_tipo_equipo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion_norm    TEXT NOT NULL UNIQUE,
    descripcion         TEXT NOT NULL,
    aplica_mp           INTEGER,
    freq_mp             REAL,
    tiempo_mp           REAL,
    tercerizado_mp      INTEGER NOT NULL DEFAULT 0,
    aplica_cal          INTEGER,
    freq_cal            REAL,
    tiempo_cal          REAL,
    tercerizado_cal     INTEGER NOT NULL DEFAULT 0,
    aplica_val          INTEGER,
    freq_val            REAL,
    tiempo_val          REAL,
    tercerizado_val     INTEGER NOT NULL DEFAULT 0,
    criticidad          VARCHAR(40),
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parametros_tipo_descripcion
    ON parametros_tipo_equipo (descripcion_norm);
