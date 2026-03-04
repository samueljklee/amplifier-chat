import json

from chat_plugin.session_history import scan_session_revisions, scan_sessions


def test_scan_sessions_none_dir():
    assert scan_sessions(None) == []


def test_scan_sessions_empty_dir(tmp_path):
    assert scan_sessions(tmp_path) == []


def test_scan_sessions_with_transcript(tmp_path):
    session_dir = tmp_path / "sess-abc"
    session_dir.mkdir()
    transcript = session_dir / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "Hello"}) + "\n"
        + json.dumps({"role": "assistant", "content": "Hi"}) + "\n",
        encoding="utf-8",
    )
    results = scan_sessions(tmp_path)
    assert len(results) == 1
    row = results[0]
    assert row["session_id"] == "sess-abc"
    assert row["message_count"] == 2
    assert row["last_user_message"] == "Hello"
    assert row["revision"]  # non-empty


def test_scan_sessions_with_metadata(tmp_path):
    session_dir = tmp_path / "sess-xyz"
    session_dir.mkdir()
    (session_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "test"}) + "\n",
        encoding="utf-8",
    )
    (session_dir / "metadata.json").write_text(
        json.dumps({
            "name": "My Session",
            "description": "A test session",
            "parent_id": "sess-parent",
        }),
        encoding="utf-8",
    )
    results = scan_sessions(tmp_path)
    assert len(results) == 1
    row = results[0]
    assert row["name"] == "My Session"
    assert row["description"] == "A test session"
    assert row["parent_session_id"] == "sess-parent"


def test_scan_session_revisions(tmp_path):
    session_dir = tmp_path / "sess-rev"
    session_dir.mkdir()
    (session_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n",
        encoding="utf-8",
    )
    rows = scan_session_revisions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-rev"
    assert "revision" in rows[0]
    assert "last_updated" in rows[0]


def test_scan_session_revisions_filter(tmp_path):
    for name in ["sess-a", "sess-b", "sess-c"]:
        d = tmp_path / name
        d.mkdir()
        (d / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    rows = scan_session_revisions(tmp_path, session_ids={"sess-b"})
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-b"


def test_scan_session_revisions_none_dir():
    assert scan_session_revisions(None) == []


def test_invalid_session_ids_skipped(tmp_path):
    (tmp_path / "valid-id").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "has spaces").mkdir()
    results = scan_sessions(tmp_path)
    session_ids = {r["session_id"] for r in results}
    assert "valid-id" in session_ids
    assert ".hidden" not in session_ids
    assert "has spaces" not in session_ids
