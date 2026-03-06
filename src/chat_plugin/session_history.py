"""Session history — scans amplifierd's sessions_dir to discover past sessions.

Adapted from amplifier-distro's session_history.py for amplifierd's flat
directory layout:

    sessions_dir/
        {session_id}/transcript.jsonl
        {session_id}/metadata.json

Schema (one dict per session in scan_sessions() output):
    session_id: str             — session directory name
    cwd: str|None               — working directory from session-info.json
    parent_session_id: str|None — parent session id from metadata.json
    spawn_agent: str|None       — spawned agent name from metadata.json
    message_count: int          — number of transcript lines with a 'role' key
    last_user_message: str|None — last user message text, truncated to 120 chars
    last_updated: str           — ISO-format mtime of transcript.jsonl
    revision: str               — mtime_ns:size signature for stale-change detection
    name: str|None              — session name from metadata.json
    description: str|None       — session description from metadata.json

Performance notes:
    H3: message_count is read from metadata.json ``turn_count`` when present
        (O(1)), falling back to a full transcript scan only when absent.
    H4: last_user_message uses a tail-seek of the last _TAIL_BYTES of the
        transcript (O(1) w.r.t. file size) instead of a full forward read.
    H5: Session directories that are symlinks escaping sessions_dir are
        silently skipped (containment check).
    H2: Per-session metadata reads in scan_sessions() run in a
        ThreadPoolExecutor(max_workers=8) for parallelism on slow storage.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TRANSCRIPT_FILENAME = "transcript.jsonl"
METADATA_FILENAME = "metadata.json"
SESSION_INFO_FILENAME = "session-info.json"

_VALID_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# H4: only read the last N bytes of a transcript when tail-seeking
_TAIL_BYTES = 8192


def _session_revision_signature(session_dir: Path) -> tuple[str, str]:
    """Return (last_updated_iso, revision_signature) for one session directory."""
    transcript_path = session_dir / TRANSCRIPT_FILENAME
    stat_target = transcript_path if transcript_path.exists() else session_dir
    try:
        stat = stat_target.stat()
        last_updated = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        revision = f"{int(mtime_ns)}:{int(stat.st_size)}"
        return last_updated, revision
    except OSError:
        return datetime.now(tz=UTC).isoformat(), "0:0"


def _tail_seek_last_user_message(transcript_path: Path) -> str | None:
    """H4: Seek to the last _TAIL_BYTES of a transcript to find the last user message.

    Reads at most _TAIL_BYTES from the end of the file, so performance is
    O(1) with respect to total file size regardless of how many turns exist.
    Returns the last user-role message text truncated to 120 characters,
    or None if no user message is found in the tail window.
    """
    last_user_message: str | None = None
    try:
        file_size = transcript_path.stat().st_size
        with open(transcript_path, encoding="utf-8") as f:
            if file_size > _TAIL_BYTES:
                f.seek(file_size - _TAIL_BYTES)
                f.readline()  # discard partial line that starts after the seek point
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or obj.get("role") != "user":
                    continue
                content = obj.get("content", "")
                if isinstance(content, list):
                    # content-block array format — join all text blocks
                    text_parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    last_user_message = " ".join(text_parts)[:120]
                elif isinstance(content, str):
                    last_user_message = content[:120]
    except OSError:
        pass
    return last_user_message


def _read_session_meta(session_dir: Path) -> dict[str, Any]:
    """Extract lightweight metadata from a single session directory.

    Must be a module-level function (not a closure) so ThreadPoolExecutor
    can call it safely from worker threads.
    """
    # --- session-info.json: working directory ---
    cwd: str | None = None
    info_path = session_dir / SESSION_INFO_FILENAME
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        raw = data.get("working_dir")
        if isinstance(raw, str) and raw:
            normalized = os.path.normpath(raw)
            if os.path.isabs(normalized) and len(normalized) <= 4096:
                cwd = normalized
    except (OSError, json.JSONDecodeError):
        pass

    # --- metadata.json: parent, agent, name, description, cwd fallback, turn_count ---
    parent_session_id: str | None = None
    spawn_agent: str | None = None
    session_name: str | None = None
    session_description: str | None = None
    turn_count: int | None = None  # H3: O(1) message_count when present
    metadata_path = session_dir / METADATA_FILENAME
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(metadata, dict):
            raw_parent = metadata.get("parent_id") or metadata.get("parent_session_id")
            if (
                isinstance(raw_parent, str)
                and raw_parent
                and _VALID_SESSION_ID_RE.fullmatch(raw_parent)
            ):
                parent_session_id = raw_parent
            raw_agent = metadata.get("agent_name")
            if isinstance(raw_agent, str) and raw_agent:
                spawn_agent = raw_agent
            raw_name = metadata.get("name")
            if isinstance(raw_name, str) and raw_name:
                session_name = raw_name
            raw_desc = metadata.get("description")
            if isinstance(raw_desc, str) and raw_desc:
                session_description = raw_desc
            # Fallback: CWD from metadata if not found in session-info.json
            if cwd is None:
                raw_cwd = metadata.get("working_dir")
                if isinstance(raw_cwd, str) and raw_cwd:
                    normalized = os.path.normpath(raw_cwd)
                    if os.path.isabs(normalized) and len(normalized) <= 4096:
                        cwd = normalized
            # H3: use turn_count for O(1) message counting when available
            raw_tc = metadata.get("turn_count")
            if isinstance(raw_tc, int) and raw_tc >= 0:
                turn_count = raw_tc
    except (OSError, json.JSONDecodeError):
        pass

    transcript_path = session_dir / TRANSCRIPT_FILENAME
    message_count = 0
    last_user_message: str | None = None
    last_updated, revision = _session_revision_signature(session_dir)

    if transcript_path.exists():
        if turn_count is not None:
            # H3: message_count from metadata — no transcript scan needed
            message_count = turn_count
            # H4: tail-seek for last_user_message — O(1) regardless of file size
            last_user_message = _tail_seek_last_user_message(transcript_path)
        else:
            # Fallback: full forward scan for both message_count and last_user_message
            try:
                with transcript_path.open(encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(entry, dict) or not entry.get("role"):
                            continue
                        message_count += 1
                        if entry["role"] == "user":
                            content = entry.get("content", "")
                            if isinstance(content, str):
                                last_user_message = content[:120]
                            elif isinstance(content, list):
                                for block in content:
                                    if (
                                        isinstance(block, dict)
                                        and block.get("type") == "text"
                                    ):
                                        last_user_message = (
                                            block.get("text") or ""
                                        )[:120]
                                        break
            except OSError:
                logger.warning(
                    "Could not read transcript at %s",
                    transcript_path,
                    exc_info=True,
                )

    return {
        "session_id": session_dir.name,
        "cwd": cwd,
        "parent_session_id": parent_session_id,
        "spawn_agent": spawn_agent,
        "message_count": message_count,
        "last_user_message": last_user_message,
        "last_updated": last_updated,
        "revision": revision,
        "name": session_name,
        "description": session_description,
    }


def _iter_session_dirs(sessions_dir: Path) -> list[Path]:
    """Return validated session directories under sessions_dir.

    H5: Symlinks whose resolved path escapes sessions_dir are silently skipped
    to prevent directory-traversal via crafted symlinks.
    """
    if not sessions_dir.exists():
        return []

    try:
        children = list(sessions_dir.iterdir())
    except OSError:
        logger.warning("Could not list sessions at %s", sessions_dir, exc_info=True)
        return []

    # H5: resolve once so all children can be checked cheaply
    resolved_sessions = sessions_dir.resolve()

    session_dirs: list[Path] = []
    for child in children:
        if not child.is_dir():
            continue
        if not _VALID_SESSION_ID_RE.fullmatch(child.name):
            logger.debug("Skipping session dir with non-standard name: %r", child.name)
            continue
        # H5: symlink containment — skip any entry whose real path escapes sessions_dir
        try:
            if not child.resolve().is_relative_to(resolved_sessions):
                logger.warning(
                    "Skipping session dir that escapes sessions_dir via symlink: %r",
                    str(child),
                )
                continue
        except (OSError, ValueError):
            continue
        session_dirs.append(child)

    return session_dirs


def scan_sessions(sessions_dir: Path | None) -> list[dict[str, Any]]:
    """Scan sessions_dir and return lightweight metadata for all sessions.

    Returns a list sorted newest-first by last_updated.
    Never raises — malformed sessions are included with degraded metadata.

    H2: Per-session reads run in a ThreadPoolExecutor(max_workers=8) so that
    slow or cold-cache file I/O on many sessions overlaps in parallel.
    """
    if sessions_dir is None:
        return []

    session_dirs = list(_iter_session_dirs(sessions_dir))

    # H2: parallel I/O — _read_session_meta is a module-level function so it
    # is safely callable from worker threads without pickling issues.
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_to_dir = {pool.submit(_read_session_meta, d): d for d in session_dirs}
        for future, session_dir in future_to_dir.items():
            try:
                results.append(future.result())
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Skipping session %s due to unexpected error",
                    session_dir,
                    exc_info=True,
                )

    results.sort(key=lambda s: s["last_updated"], reverse=True)
    return results


def scan_session_revisions(
    sessions_dir: Path | None,
    session_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return lightweight revision metadata for session directories on disk.

    Includes name/description from metadata.json so the frontend can update
    session titles without a full history fetch.
    """
    if sessions_dir is None:
        return []

    wanted = set(session_ids) if session_ids is not None else None

    rows: list[dict[str, Any]] = []
    for session_dir in _iter_session_dirs(sessions_dir):
        session_id = session_dir.name
        if wanted is not None and session_id not in wanted:
            continue
        last_updated, revision = _session_revision_signature(session_dir)
        row: dict[str, Any] = {
            "session_id": session_id,
            "last_updated": last_updated,
            "revision": revision,
        }
        # Read name/description from metadata.json for live title updates
        metadata_path = session_dir / METADATA_FILENAME
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(metadata, dict):
                if isinstance(metadata.get("name"), str) and metadata["name"]:
                    row["name"] = metadata["name"]
                if (
                    isinstance(metadata.get("description"), str)
                    and metadata["description"]
                ):
                    row["description"] = metadata["description"]
        except (OSError, json.JSONDecodeError):
            pass
        rows.append(row)

    rows.sort(key=lambda s: s["last_updated"], reverse=True)
    return rows
