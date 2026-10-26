"""Safe snapshot and restore of shell and Git configuration. Not a dotfile manager.

`jadis backup shell|git` copies known configuration files into the jadis data directory with a manifest
(path, size, mode, SHA-256). Credentials are never included: `.git-credentials`, `.netrc`, anything under
`~/.ssh`, and any file whose content looks like it holds a token or private key are skipped and listed.
`jadis restore ID` shows per-file what would change and restores only with authorization (backing up the
current file first).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from jadis.redact import PATTERNS

SETS = {
    "shell": [".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile", ".zshenv", ".zshrc.local", ".bashrc.local", ".inputrc"],
    "git": [".gitconfig", ".config/git/config", ".config/git/ignore", ".gitignore_global"],
}
NEVER = {".git-credentials", ".netrc", ".config/gh/hosts.yml"}


def data_dir(env: dict[str, str]) -> Path:
    base = env.get("XDG_DATA_HOME") or os.path.join(env.get("HOME", "."), ".local", "share")
    return Path(base) / "jadis" / "backups"


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p, _ in PATTERNS)


def create(env: dict[str, str], which: str) -> dict[str, Any]:
    home = Path(env["HOME"])
    backup_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + which + "-" + uuid.uuid4().hex[:4]
    dest = data_dir(env) / backup_id
    files, skipped = [], []
    for rel in SETS[which]:
        src = home / rel
        if not src.is_file() or rel in NEVER:
            continue
        data = src.read_bytes()
        if looks_secret(data.decode("utf-8", "replace")):
            skipped.append({"path": rel, "reason": "content looks like it contains a credential"})
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
        files.append({"path": rel, "size": len(data), "mode": oct(src.stat().st_mode & 0o777), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "format": "jadis-backup v1",
        "id": backup_id,
        "set": which,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": files,
        "skipped": skipped,
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def load(env: dict[str, str], backup_id: str) -> dict[str, Any]:
    if "/" in backup_id or backup_id.startswith("."):
        raise LookupError("invalid backup id")
    path = data_dir(env) / backup_id / "manifest.json"
    if not path.is_file():
        raise LookupError(f"no backup {backup_id}")
    return json.loads(path.read_text())


def list_backups(env: dict[str, str]) -> list[dict[str, Any]]:
    root = data_dir(env)
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        try:
            m = json.loads((d / "manifest.json").read_text())
            out.append({"id": m["id"], "set": m["set"], "files": len(m["files"]), "created_at": m["created_at"]})
        except (OSError, ValueError, KeyError):
            continue
    return out


def restore_preview(env: dict[str, str], backup_id: str) -> list[dict[str, Any]]:
    manifest = load(env, backup_id)
    home, src = Path(env["HOME"]), data_dir(env) / backup_id
    out = []
    for f in manifest["files"]:
        stored = src / f["path"]
        if not stored.is_file() or hashlib.sha256(stored.read_bytes()).hexdigest() != f["sha256"]:
            out.append({"path": f["path"], "action": "skip", "reason": "backup copy missing or altered"})
            continue
        current = home / f["path"]
        if not current.exists():
            out.append({"path": f["path"], "action": "create"})
        elif hashlib.sha256(current.read_bytes()).hexdigest() == f["sha256"]:
            out.append({"path": f["path"], "action": "unchanged"})
        else:
            out.append({"path": f["path"], "action": "overwrite"})
    return out


def restore(env: dict[str, str], backup_id: str) -> dict[str, Any]:
    """Caller has already shown the preview and obtained authorization."""
    home, src = Path(env["HOME"]), data_dir(env) / backup_id
    safety = create(env, load(env, backup_id)["set"])  # current state first, so a restore is itself undoable
    restored = []
    for item in restore_preview(env, backup_id):
        if item["action"] in ("create", "overwrite"):
            target = home / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / item["path"], target)
            restored.append(item["path"])
    return {"restored": restored, "pre_restore_backup": safety["id"]}
