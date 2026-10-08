"""Versionado de fórmulas: cada ejecución persistida registra módulo, versión y fecha."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from server.db import get_empresas_connection
from server.limits import META_JSON, clip

CATALOGO: list[dict[str, str]] = [
    {
        "modulo": "suficiencia",
        "version": "TFM-1.0",
        "descripcion": (
            "D=ΣIi; Ceq=(H·u)/t; Rd=⌈P/Ceq⌉; Rc=⌈Q⌉; Rb según modo; "
            "Rfinal=⌈Rb·(1+b)⌉+Re; S=D/Rfinal."
        ),
    },
    {
        "modulo": "dimensionamiento",
        "version": "TFM-1.0",
        "descripcion": (
            "Nh=⌈Hparque·(1+c)/Hdisp⌉ con Hnom=42·52 y Hdisp=(Hnom−Hvac−Hfest−Hperm)·p. "
            "Nc=⌈Σ(Ek/rk)⌉. Métodos no se mezclan. Excluye comodato, leasing y baja."
        ),
    },
    {
        "modulo": "ge",
        "version": "TFM-1.0",
        "descripcion": (
            "GE=F+A+M+Hf. TGE: ≥19 → 4 meses; 15–18 → 6; 12–14 → 12; <12 sin TGE. "
            "TPM=min(TGE,Tfab) si GE≥12; si GE<12 prevalece fabricante."
        ),
    },
    {
        "modulo": "preinstalacion",
        "version": "TFM-1.0",
        "descripcion": (
            "Csitio=100·Σ(ai·ci)/Σ(ai). ≥90 sin críticos incumplidos: "
            "Aprobado, o con condiciones si hay pendientes. Σ(ai)=0 → Revisar."
        ),
    },
]


def formula_meta(modulo: str) -> dict[str, str]:
    item = next((x for x in CATALOGO if x["modulo"] == modulo), None)
    if not item:
        return {"formula_modulo": modulo, "formula_version": "n/d", "formula_descripcion": ""}
    return {
        "formula_modulo": item["modulo"],
        "formula_version": item["version"],
        "formula_descripcion": item["descripcion"],
    }


def _now_sql() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def ensure_formula_versions_schema(emp_conn) -> None:
    from pathlib import Path

    sql_path = Path(__file__).resolve().parent.parent / "sql" / "schema_formula_versions.sql"
    emp_conn.executescript(sql_path.read_text(encoding="utf-8"))
    stamp = _now_sql()
    for item in CATALOGO:
        emp_conn.execute(
            """
            INSERT INTO formula_versions (modulo, version, descripcion, fecha, activo)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(modulo, version) DO UPDATE SET
                descripcion = excluded.descripcion,
                activo = 1
            """,
            (item["modulo"], item["version"], item["descripcion"], stamp),
        )
        emp_conn.execute(
            """
            UPDATE formula_versions
            SET activo = CASE WHEN version = ? THEN 1 ELSE 0 END
            WHERE modulo = ?
            """,
            (item["version"], item["modulo"]),
        )


def active_version_row(emp_conn, modulo: str) -> dict[str, Any] | None:
    row = emp_conn.execute(
        """
        SELECT id, modulo, version, descripcion, fecha, activo
        FROM formula_versions
        WHERE modulo = ? AND activo = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (modulo,),
    ).fetchone()
    return dict(row) if row else None


def _clip_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    return clip(raw, META_JSON)


def registrar_calculo(
    *,
    modulo: str,
    empresa_id: int | None = None,
    sede_id: int | None = None,
    servicio_id: int | None = None,
    usuario_id: int | None = None,
    parametros: dict | None = None,
    resultado: dict | None = None,
    user=None,
    also_event_log: bool = True,
) -> dict[str, str]:
    """Persiste la ejecución y, si aplica, un renglón resumido en la bitácora."""
    meta = formula_meta(modulo)
    try:
        with get_empresas_connection() as conn:
            ensure_formula_versions_schema(conn)
            ver = active_version_row(conn, modulo)
            vid = int(ver["id"]) if ver else None
            version = (ver["version"] if ver else None) or meta["formula_version"]
            conn.execute(
                """
                INSERT INTO formula_ejecuciones (
                    formula_version_id, modulo, version,
                    empresa_id, sede_id, servicio_id, usuario_id,
                    parametros_json, resultado_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vid,
                    modulo,
                    version,
                    int(empresa_id) if empresa_id else None,
                    int(sede_id) if sede_id else None,
                    int(servicio_id) if servicio_id else None,
                    int(usuario_id) if usuario_id else None,
                    _clip_json(parametros or {}),
                    _clip_json(resultado or {}),
                    _now_sql(),
                ),
            )
            conn.commit()
    except Exception as exc:
        print(f"[formula_versions] no se pudo registrar ejecución: {exc}")

    if also_event_log and empresa_id:
        try:
            from server.event_log import log_evento

            resumen = (
                f"Cálculo {modulo} v{meta['formula_version']}"
                + (f" sede={sede_id}" if sede_id else "")
                + (f" servicio={servicio_id}" if servicio_id else "")
            )
            log_evento(
                empresa_id=empresa_id,
                accion=resumen,
                user=user,
                modulo=modulo,
                sede_id=sede_id,
                servicio_id=servicio_id,
                parametros=parametros,
                resultado=resultado,
            )
        except Exception as exc:
            print(f"[formula_versions] bitácora omitida: {exc}")
    return meta
