"""Shared session utilities — atomic writes and forked metadata patching.

Extracted from routes.py and commands.py to deduplicate the
_patch_forked_metadata logic and provide atomic JSON writes using
the same tmp+rename pattern as PinStorage._save().
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, data: dict) -> None:
    """Atomically write JSON data to a file using tmp + os.rename.

    Creates parent directories if needed. Uses the same pattern as
    PinStorage._save(): write to a .tmp sibling, then os.rename()
    to the target path. This prevents half-written files on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, path)


def patch_forked_metadata(
    forked_dir: Path,
    parent_dir: Path,
    cwd: str | None,
) -> None:
    """Patch a forked session's metadata.json with working_dir and any
    fields that fork_session() left as null (e.g. bundle, model).

    Uses atomic_write_json for crash safety.

    Args:
        forked_dir: Path to the forked session directory.
        parent_dir: Path to the parent session directory.
        cwd: Working directory to set. If None, falls back to parent's
            working_dir or cwd field.
    """
    meta_path = forked_dir / "metadata.json"
    try:
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        meta = {}

    # Read parent metadata for fallback values
    parent_meta: dict = {}
    parent_meta_path = parent_dir / "metadata.json"
    try:
        parent_meta = json.loads(parent_meta_path.read_text())
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    changed = False

    # Patch working_dir
    if not cwd:
        cwd = parent_meta.get("working_dir") or parent_meta.get("cwd")
    if cwd:
        meta["working_dir"] = cwd
        changed = True

    # Patch bundle if null
    if not meta.get("bundle") and parent_meta.get("bundle"):
        meta["bundle"] = parent_meta["bundle"]
        changed = True

    # Patch model if null
    if not meta.get("model") and parent_meta.get("model"):
        meta["model"] = parent_meta["model"]
        changed = True

    if changed:
        try:
            atomic_write_json(meta_path, meta)
        except OSError:
            pass  # best-effort
