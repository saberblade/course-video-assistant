"""Runtime configuration and verified snapshots. No credentials are printed."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings


def service_id(root=ROOT):
    return hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:16]


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def data_directory():
    data = safe_directory(get_settings().data_dir)
    for name in (".git", ".venv", "backend", "frontend", "modules", "scripts", "deploy", "migrations", "models", "tools", "docs", "tests"):
        code = (ROOT / name).resolve()
        if data == code or data.is_relative_to(code) or code.is_relative_to(data):
            raise ValueError(f"DATA_DIR overlaps project resources: {data}")
    return data


def linked(path):
    try:
        return bool(getattr(Path(path).lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) or Path(path).is_symlink()
    except FileNotFoundError:
        return False


def safe_directory(path, *, parent=None):
    path = Path(path).absolute()
    if any(linked(part) for part in (path, *path.parents)):
        raise ValueError(f"Refuse linked directory: {path}")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home() or resolved == ROOT or resolved in ROOT.parents:
        raise ValueError(f"Unsafe directory: {resolved}")
    if parent is not None and resolved.parent != Path(parent).resolve():
        raise ValueError(f"Directory is outside expected parent: {resolved}")
    return resolved


def tree_files(path):
    for folder, dirs, files in os.walk(path, followlinks=False):
        for name in [*dirs, *files]:
            if linked(Path(folder) / name):
                raise ValueError(f"Refuse linked snapshot entry: {Path(folder) / name}")
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for name in files:
            if name != ".draining":
                yield Path(folder) / name


def copy_tree(source, target):
    source, target = Path(source), Path(target)
    if not source.exists():
        return
    safe_directory(source)
    for item in tree_files(source):
        destination = target / item.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_offline(port):
    with socket.socket() as connection:
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Port {port} is listening; stop the service before backup/restore")


def database_check(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Snapshot database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Snapshot database contains orphan rows")


def runtime_state(live=False):
    settings = get_settings()
    state = {"port": settings.app_port, "data_dir": str(settings.data_dir), "service_id": service_id(), "video_busy": 0, "rag_busy": 0}
    if settings.database_path.exists():
        with closing(sqlite3.connect(settings.database_path.as_uri() + "?mode=ro", uri=True)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "videos" in tables:
                state["video_busy"] = db.execute("SELECT count(*) FROM videos WHERE status IN ('queued','transcribing','indexing')").fetchone()[0]
            if "rag_indexes" in tables:
                state["rag_busy"] = db.execute("SELECT count(*) FROM rag_indexes WHERE status IN ('pending','building')").fetchone()[0]
    if live:
        import httpx
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.get(f"http://127.0.0.1:{settings.app_port}/api/health")
            health = response.json()
        if health.get("service_id") != service_id():
            raise RuntimeError("The listening service belongs to a different checkout; refuse to stop it")
        state.update({key: health.get(key) for key in ("question_busy", "assistant_busy", "draining")})
    return state


def backup(*, keep=7):
    if keep < 1:
        raise ValueError("keep must be at least 1")
    settings = get_settings()
    assert_offline(settings.app_port)
    data = data_directory()
    database_check(data / "app.db")
    parent = ROOT / "backups"
    safe_directory(parent)
    if parent.resolve().is_relative_to(data) or data.is_relative_to(parent.resolve()):
        raise ValueError("DATA_DIR and backups must not overlap")
    parent.mkdir(parents=True, exist_ok=True)
    dest = safe_directory(parent / stamp(), parent=parent)
    dest.mkdir()
    copy_tree(data, dest / "data")
    for folder in ("backend", "modules", "scripts", "deploy", "migrations", "frontend/dist"):
        copy_tree(ROOT / folder, dest / folder)
    for name in ("alembic.ini", "requirements.lock.txt", ".env.example", "frontend/package.json", "frontend/package-lock.json"):
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    manifest = {"format": 2, "created_utc": datetime.now(timezone.utc).isoformat(), "source": result.stdout.strip(), "original_data_dir": str(data),
                "files": {str(item.relative_to(dest).as_posix()): sha(item) for item in tree_files(dest)}}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (dest / "MANIFEST.txt").write_text(f"format: 2\nsource: {manifest['source']}\nSee manifest.json for all file hashes.\n", encoding="utf-8")
    # Rotate only verified snapshots; pre_restore and arbitrary directories are never selected.
    snapshots = []
    for candidate in parent.iterdir():
        if candidate.is_dir() and re.fullmatch(r"\d{8}_\d{6}_\d{6}", candidate.name) and (candidate / "manifest.json").is_file():
            checked = safe_directory(candidate, parent=parent)
            entry = json.loads((checked / "manifest.json").read_text(encoding="utf-8"))
            if entry.get("format") == 2:
                try:
                    verify_snapshot(checked)
                except ValueError:
                    continue
                snapshots.append(checked)
    for old in sorted(snapshots)[:-keep]:
        if old != dest:
            shutil.rmtree(safe_directory(old, parent=parent))
    return {"backup": str(dest), "files": len(manifest["files"])}


def verify_snapshot(snapshot):
    snapshot = safe_directory(snapshot)
    manifest = snapshot / "manifest.json"
    if not manifest.is_file():
        raise ValueError("Verified manifest.json missing; legacy backups must be inspected before use")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("format") != 2 or not isinstance(payload.get("files"), dict) or "data/app.db" not in payload["files"]:
        raise ValueError("Unsupported or incomplete backup manifest")
    actual = {item.relative_to(snapshot).as_posix() for item in tree_files(snapshot)} - {"manifest.json", "MANIFEST.txt"}
    if actual != set(payload["files"]):
        raise ValueError("Snapshot file list differs from its manifest")
    for relative, expected in payload["files"].items():
        path = (snapshot / relative).resolve()
        if not path.is_relative_to(snapshot) or not path.is_file() or sha(path) != expected:
            raise ValueError(f"Backup hash mismatch: {relative}")
    database_check(snapshot / "data/app.db")
    return snapshot


def restore(snapshot):
    settings = get_settings()
    assert_offline(settings.app_port)
    snapshot = verify_snapshot(snapshot)
    data = data_directory()
    dist = safe_directory(ROOT / "frontend/dist")
    targets = [(snapshot / "data", data)]
    if (snapshot / "frontend/dist").exists():
        targets.append((snapshot / "frontend/dist", dist))
    staged, installed, retained = [], [], []
    try:
        for src, target in targets:
            if snapshot.is_relative_to(target) or target.is_relative_to(snapshot):
                raise ValueError("Snapshot and restore target must not overlap")
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = safe_directory(target.parent / f".{target.name}.restore_{uuid4().hex}", parent=target.parent)
            copy_tree(src, stage)
            staged.append((stage, target))
        for stage, target in staged:
            old = safe_directory(target.parent / f"{target.name}.pre_restore_{stamp()}", parent=target.parent)
            if target.exists():
                os.replace(safe_directory(target), old)
                retained.append((old, target))
            os.replace(stage, target)
            installed.append(target)
        # Stored media paths are absolute; a clean-directory restore must relocate them.
        original_data = Path(json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))["original_data_dir"])
        with closing(sqlite3.connect(data / "app.db")) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "videos" in tables:
                for video_id, local_path in db.execute("SELECT id, local_path FROM videos").fetchall():
                    previous = Path(local_path)
                    if not previous.is_absolute() or not previous.is_relative_to(original_data):
                        raise ValueError(f"Media path lies outside the snapshotted DATA_DIR: {video_id}")
                    relocated = (data / previous.relative_to(original_data)).resolve()
                    if not relocated.is_relative_to(data) or not relocated.is_file():
                        raise ValueError(f"Restored media missing: {video_id}")
                    db.execute("UPDATE videos SET local_path=? WHERE id=?", (str(relocated), video_id))
                db.commit()
        database_check(data / "app.db")
    except Exception:
        for target in reversed(installed):
            failed = safe_directory(target.parent / f"{target.name}.failed_restore_{stamp()}", parent=target.parent)
            os.replace(safe_directory(target), failed)
        for old, target in reversed(retained):
            os.replace(safe_directory(old, parent=target.parent), target)
        raise
    finally:
        for stage, _ in staged:
            if stage.exists():
                shutil.rmtree(safe_directory(stage, parent=stage.parent))
    return {"restored_from": str(snapshot), "data_dir": str(data), "retained": [str(old) for old, _ in retained]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    state = subs.add_parser("state")
    state.add_argument("--live", action="store_true")
    subs.add_parser("drain")
    subs.add_parser("undrain")
    save = subs.add_parser("backup")
    save.add_argument("--keep", type=int, default=7)
    load = subs.add_parser("restore")
    load.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    if args.action == "state":
        result = runtime_state(args.live)
    elif args.action in ("drain", "undrain"):
        marker = get_settings().data_dir / ".draining"
        if args.action == "drain":
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("stop requested", encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)
        result = {"draining": args.action == "drain"}
    elif args.action == "backup":
        result = backup(keep=args.keep)
    else:
        path = args.snapshot if args.snapshot.is_absolute() else ROOT / args.snapshot
        result = restore(path)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Operation refused: {exc}", file=sys.stderr)
        raise SystemExit(1)
