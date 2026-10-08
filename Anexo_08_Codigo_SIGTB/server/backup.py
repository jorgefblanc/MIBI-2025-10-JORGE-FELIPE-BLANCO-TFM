"""Respaldo periódico de las bases SQLite y restauración de la última copia sana."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
KEEP_SNAPSHOTS = int(os.environ.get("SIGTB_BACKUP_KEEP", "20"))
INTERVAL_SECONDS = 30 * 60
_scheduler_started = False
_snapshot_lock = threading.Lock()

DB_FILES = {
    "usuarios": DATA_DIR / "usuarios.db",
    "empresas": DATA_DIR / "empresas.db",
    "solicitudes": DATA_DIR / "solicitudes.db",
    "parametros_equipo": DATA_DIR / "parametros_equipo.db",
}


def offsite_dir() -> Path:
    override = os.environ.get("SIGTB_BACKUP_OFFSITE")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or str(DATA_DIR)
    return Path(base) / "SIGTB" / "backups"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _quick_ok(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        row = conn.execute("PRAGMA quick_check").fetchone()
        return bool(row) and str(row[0]).lower() == "ok"
    except sqlite3.Error:
        return False
    finally:
        if conn is not None:
            conn.close()


def _sqlite_copy(src: Path, dest: Path) -> bool:
    """Copia consistente vía sqlite3.backup (incluye WAL aplicado)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=15)
        try:
            src_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            pass
        dst_conn = sqlite3.connect(str(dest), timeout=15)
        src_conn.backup(dst_conn)
        dst_conn.commit()
    except sqlite3.Error:
        if dest.exists():
            dest.unlink()
        return False
    finally:
        if dst_conn is not None:
            dst_conn.close()
        if src_conn is not None:
            src_conn.close()
    return _quick_ok(dest)


def _write_manifest(folder: Path, reason: str, files: dict[str, dict]) -> None:
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "files": files,
    }
    (folder / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def maybe_create_snapshot(reason: str, min_interval_seconds: int = 3600) -> dict:
    """Crea snapshot salvo que ya exista uno reciente."""
    dirs = _snapshot_dirs()
    if dirs and min_interval_seconds > 0:
        age = time.time() - dirs[0].stat().st_mtime
        if age < min_interval_seconds:
            return {
                "ok": True,
                "skipped": True,
                "id": dirs[0].name,
                "reason": reason,
            }
    return create_snapshot(reason)


def create_snapshot(reason: str = "manual") -> dict:
    """Genera un snapshot de todas las bases sanas. Retorna metadatos."""
    with _snapshot_lock:
        return _create_snapshot_unlocked(reason)


def _create_snapshot_unlocked(reason: str) -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = _stamp()
    folder = BACKUP_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    files_meta: dict[str, dict] = {}
    copied = 0
    for key, path in DB_FILES.items():
        info = {"ok": False, "bytes": 0, "skipped": False}
        if not path.exists():
            info["skipped"] = True
            info["error"] = "no existe"
            files_meta[key] = info
            continue
        if not _quick_ok(path):
            info["error"] = "origen no íntegro; no se copió"
            files_meta[key] = info
            continue
        dest = folder / path.name
        if _sqlite_copy(path, dest):
            info["ok"] = True
            info["bytes"] = dest.stat().st_size
            copied += 1
        else:
            info["error"] = "falló la copia SQLite"
        files_meta[key] = info

    if copied == 0:
        shutil.rmtree(folder, ignore_errors=True)
        return {"ok": False, "error": "No se pudo respaldar ninguna base sana.", "id": None}

    off = offsite_dir() / name
    try:
        off.parent.mkdir(parents=True, exist_ok=True)
        files_meta["_offsite"] = {"ok": True, "path": str(off)}
        _write_manifest(folder, reason, files_meta)
        _copy_tree(folder, off)
    except OSError as exc:
        files_meta["_offsite"] = {"ok": False, "error": str(exc)}
        _write_manifest(folder, reason, files_meta)

    prune_snapshots()
    return {
        "ok": True,
        "id": name,
        "reason": reason,
        "path": str(folder),
        "offsite": str(offsite_dir() / name),
        "files": files_meta,
        "copied": copied,
    }


def _snapshot_dirs() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    dirs = [p for p in BACKUP_DIR.iterdir() if p.is_dir() and (p / "manifest.json").exists()]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def prune_snapshots(keep: int = KEEP_SNAPSHOTS) -> None:
    for folder in _snapshot_dirs()[keep:]:
        shutil.rmtree(folder, ignore_errors=True)
    off = offsite_dir()
    if not off.exists():
        return
    off_dirs = sorted(
        [p for p in off.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for folder in off_dirs[keep:]:
        shutil.rmtree(folder, ignore_errors=True)


def list_snapshots() -> list[dict]:
    items = []
    for folder in _snapshot_dirs():
        try:
            meta = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        files = meta.get("files") or {}
        offsite_ok = bool((files.get("_offsite") or {}).get("ok"))
        if not offsite_ok:
            offsite_ok = (offsite_dir() / folder.name).exists()
        items.append(
            {
                "id": folder.name,
                "created_at": meta.get("created_at") or folder.name,
                "reason": meta.get("reason") or "",
                "path": str(folder),
                "ok_files": [k for k, v in files.items() if k != "_offsite" and v.get("ok")],
                "offsite": offsite_ok,
            }
        )
    return items


def _candidate_copies(db_filename: str) -> list[Path]:
    found: list[Path] = []
    for folder in _snapshot_dirs():
        candidate = folder / db_filename
        if candidate.exists():
            found.append(candidate)
    off = offsite_dir()
    if off.exists():
        off_dirs = sorted([p for p in off.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
        for folder in off_dirs:
            candidate = folder / db_filename
            if candidate.exists() and candidate not in found:
                found.append(candidate)
    return found


def restore_file(live_path: Path, snapshot_file: Path) -> bool:
    if not _quick_ok(snapshot_file):
        return False
    live_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = live_path.with_suffix(live_path.suffix + ".restore-tmp")
    if tmp.exists():
        tmp.unlink()
    if not _sqlite_copy(snapshot_file, tmp):
        shutil.copy2(snapshot_file, tmp)
        if not _quick_ok(tmp):
            tmp.unlink(missing_ok=True)
            return False
    if live_path.exists():
        live_path.unlink()
    for extra in (
        live_path.with_suffix(live_path.suffix + "-wal"),
        live_path.with_suffix(live_path.suffix + "-shm"),
    ):
        extra.unlink(missing_ok=True)
    tmp.replace(live_path)
    return _quick_ok(live_path)


def restore_latest_for(live_path: Path) -> Path | None:
    """Restaura la copia más reciente e íntegra de ese archivo. None si no hay."""
    for candidate in _candidate_copies(live_path.name):
        if restore_file(live_path, candidate):
            return candidate
    return None


def restore_snapshot(snapshot_id: str) -> dict:
    if not snapshot_id or any(ch in snapshot_id for ch in ("/", "\\", "..")):
        return {"ok": False, "error": "Snapshot no válido."}
    folder = BACKUP_DIR / snapshot_id
    if not folder.exists():
        off = offsite_dir() / snapshot_id
        if off.exists():
            folder = off
        else:
            return {"ok": False, "error": "Snapshot no encontrado."}
    try:
        resolved = folder.resolve()
        allowed = (BACKUP_DIR.resolve(), offsite_dir().resolve())
        if not any(_is_under(resolved, root) for root in allowed):
            return {"ok": False, "error": "Snapshot no válido."}
    except OSError:
        return {"ok": False, "error": "Snapshot no válido."}

    sources: dict[str, Path] = {}
    missing: list[str] = []
    for key, live in DB_FILES.items():
        src = folder / live.name
        if not src.exists() or not _quick_ok(src):
            missing.append(key)
        else:
            sources[key] = src
    if missing:
        return {
            "ok": False,
            "error": (
                "El snapshot está incompleto. No se restauró ninguna base "
                f"(faltan o están corruptos: {', '.join(missing)})."
            ),
            "restored": [],
            "failed": missing,
            "id": snapshot_id,
        }

    staged: dict[str, Path] = {}
    safes: dict[str, Path] = {}
    try:
        for key, live in DB_FILES.items():
            tmp = live.with_suffix(live.suffix + ".restore-tmp")
            if tmp.exists():
                tmp.unlink()
            if not _sqlite_copy(sources[key], tmp):
                shutil.copy2(sources[key], tmp)
            if not _quick_ok(tmp):
                raise RuntimeError(key)
            staged[key] = tmp

        for key, live in DB_FILES.items():
            if live.exists():
                bak = live.with_suffix(live.suffix + ".pre-restore")
                if bak.exists():
                    bak.unlink()
                shutil.copy2(live, bak)
                safes[key] = bak

        restored: list[str] = []
        for key, live in DB_FILES.items():
            for extra in (
                live.with_suffix(live.suffix + "-wal"),
                live.with_suffix(live.suffix + "-shm"),
            ):
                extra.unlink(missing_ok=True)
            if live.exists():
                live.unlink()
            staged[key].replace(live)
            if not _quick_ok(live):
                raise RuntimeError(key)
            restored.append(key)
    except Exception:
        for key, live in DB_FILES.items():
            bak = safes.get(key)
            if bak and bak.exists():
                live.unlink(missing_ok=True)
                bak.replace(live)
        return {
            "ok": False,
            "error": "La restauración se abortó para no dejar bases desfasadas.",
            "restored": [],
            "failed": list(DB_FILES.keys()),
            "id": snapshot_id,
        }
    finally:
        for bak in safes.values():
            bak.unlink(missing_ok=True)
        for tmp in staged.values():
            tmp.unlink(missing_ok=True)

    return {
        "ok": True,
        "restored": list(DB_FILES.keys()),
        "failed": [],
        "id": snapshot_id,
        "message": "Restauradas las 4 bases del snapshot.",
    }


def _periodic_loop() -> None:
    elapsed = 0
    while True:
        time.sleep(60)
        elapsed += 60
        try:
            from server.inventory_recycle import purge_expired

            purge_expired()
        except Exception as exc:
            print(f"[backup] reciclo de inventario omitido: {exc}")
        try:
            from server.event_log import process_event_log_expiry

            process_event_log_expiry()
        except Exception as exc:
            print(f"[backup] caducidad de log de eventos omitida: {exc}")
        if elapsed < INTERVAL_SECONDS:
            continue
        elapsed = 0
        try:
            maybe_create_snapshot("periodic", min_interval_seconds=25 * 60)
        except Exception as exc:
            print(f"[backup] respaldo periódico omitido: {exc}")


def _atexit_snapshot() -> None:
    try:
        maybe_create_snapshot("shutdown", min_interval_seconds=5 * 60)
    except Exception as exc:
        print(f"[backup] respaldo al cerrar omitido: {exc}")


def start_backup_scheduler(*, debug: bool = False) -> None:
    """Hilo daemon cada 30 min + snapshot al salir. Evita duplicar con el reloader."""
    global _scheduler_started
    if _scheduler_started:
        return
    if debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    _scheduler_started = True
    try:
        from server.inventory_recycle import purge_expired

        purge_expired()
    except Exception as exc:
        print(f"[backup] reciclo de inventario al arrancar omitido: {exc}")
    atexit.register(_atexit_snapshot)
    thread = threading.Thread(target=_periodic_loop, name="sigtb-backup", daemon=True)
    thread.start()
    print(
        f"[backup] programado cada {INTERVAL_SECONDS // 60} min. "
        f"Local: {BACKUP_DIR} | Fuera de OneDrive: {offsite_dir()}"
    )
