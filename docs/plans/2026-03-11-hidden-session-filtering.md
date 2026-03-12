# Hidden Session Filtering — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

> **Spec Review Warning:** The automated spec review loop exhausted 3 iterations
> without the approval gate registering correctly. The final verdict **was APPROVED**
> (all 26/26 tests passed, zero regressions, zero code quality issues), but the
> loop mechanism failed to capture it. Human reviewer: please verify the final
> spec verdict reproduced above before proceeding.

**Goal:** Sessions marked `{"hidden": true}` in `metadata.json` must never appear in the session history sidebar.

**Architecture:** Read the `hidden` flag from session metadata during the existing `_read_session_meta()` scan, surface it in the scan result dict, then filter it out in the history API endpoint's list comprehension alongside the existing content filter.

**Tech Stack:** Python, FastAPI, pytest, existing `scan_sessions` / `_read_session_meta` infrastructure.

---

### Task 1: Add `hidden` flag to session metadata reader

**Files:**
- Modify: `src/chat_plugin/session_history.py` (lines 110-146, 190-202)
- Test: `tests/test_session_history.py`

**Step 1: Write the failing tests**

Append these two tests to the end of `tests/test_session_history.py`:

```python
def test_scan_sessions_hidden_flag(tmp_path):
    """Sessions with hidden: true in metadata surface the flag."""
    _make_session(
        tmp_path,
        "sess-hidden",
        transcript='{"role": "user", "content": "secret"}\n',
        metadata={"hidden": True},
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    assert results[0]["hidden"] is True


def test_scan_sessions_not_hidden_by_default(tmp_path):
    """Sessions without hidden metadata default to False."""
    _make_session(
        tmp_path,
        "sess-normal",
        transcript='{"role": "user", "content": "hello"}\n',
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    assert results[0]["hidden"] is False
```

**Step 2: Run tests to verify they fail**

Run:
```
uv run pytest tests/test_session_history.py::test_scan_sessions_hidden_flag tests/test_session_history.py::test_scan_sessions_not_hidden_by_default -v
```
Expected: FAIL — `KeyError: 'hidden'` because `_read_session_meta()` does not yet include `"hidden"` in its return dict.

**Step 3: Add `hidden` variable declaration**

In `src/chat_plugin/session_history.py`, find this block (around line 110):

```python
    parent_session_id: str | None = None
    spawn_agent: str | None = None
    session_name: str | None = None
    session_description: str | None = None
```

Add one line immediately after `session_description`:

```python
    parent_session_id: str | None = None
    spawn_agent: str | None = None
    session_name: str | None = None
    session_description: str | None = None
    hidden: bool = False
```

**Step 4: Read the `hidden` flag from metadata dict**

In the same file, find this block inside the `if isinstance(metadata, dict):` branch (around line 132-134):

```python
            raw_desc = metadata.get("description")
            if isinstance(raw_desc, str) and raw_desc:
                session_description = raw_desc
```

Add immediately after it:

```python
            raw_hidden = metadata.get("hidden")
            if raw_hidden is True:
                hidden = True
```

**Step 5: Add `"hidden"` to the return dict**

In the return dict at the end of `_read_session_meta()` (around line 190-202), find:

```python
        "name": session_name,
        "description": session_description,
    }
```

Change to:

```python
        "name": session_name,
        "description": session_description,
        "hidden": hidden,
    }
```

**Step 6: Run tests to verify they pass**

Run:
```
uv run pytest tests/test_session_history.py::test_scan_sessions_hidden_flag tests/test_session_history.py::test_scan_sessions_not_hidden_by_default -v
```
Expected: both PASS.

**Step 7: Run full session_history test suite for regressions**

Run:
```
uv run pytest tests/test_session_history.py -v
```
Expected: All tests PASS (no regressions in existing tests).

**Step 8: Commit**

```
git add src/chat_plugin/session_history.py tests/test_session_history.py
git commit -m "feat: surface hidden flag from session metadata"
```

---

### Task 2: Filter hidden sessions from history endpoint

**Files:**
- Modify: `src/chat_plugin/routes.py` (lines 98-104)
- Test: `tests/test_routes.py`

**Step 1: Write the failing test**

Append this test to the end of `tests/test_routes.py`:

```python
def test_hidden_sessions_excluded_from_history(client, tmp_path, state):
    import json

    state.settings.projects_dir = tmp_path

    # Create a normal session with content
    normal_dir = tmp_path / "-Users-test" / "sessions" / "normal-session"
    normal_dir.mkdir(parents=True)
    (normal_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "visible"}) + "\n",
        encoding="utf-8",
    )

    # Create a hidden session with content and hidden metadata
    hidden_dir = tmp_path / "-Users-test" / "sessions" / "hidden-session"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "secret"}) + "\n",
        encoding="utf-8",
    )
    (hidden_dir / "metadata.json").write_text(
        json.dumps({"hidden": True}),
        encoding="utf-8",
    )

    # Re-create app with projects_dir set
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    resp = c.get("/chat/api/sessions/history")
    assert resp.status_code == 200
    data = resp.json()
    ids = [s["session_id"] for s in data["sessions"]]
    assert "normal-session" in ids
    assert "hidden-session" not in ids
```

Note: This test follows the exact same pattern as the existing `test_history_with_sessions_on_disk` test (line 87 of `tests/test_routes.py`), which re-creates the FastAPI app with `projects_dir` set on `state.settings`. The `client`, `tmp_path`, and `state` fixtures come from `tests/conftest.py`.

**Step 2: Run test to verify it fails**

Run:
```
uv run pytest tests/test_routes.py::test_hidden_sessions_excluded_from_history -v
```
Expected: FAIL — `assert "hidden-session" not in ids` fails because the endpoint's list comprehension does not yet filter on the `hidden` flag.

**Step 3: Add hidden filter to the list comprehension**

In `src/chat_plugin/routes.py`, find the filter block (around line 98-104):

```python
        # Filter: only include sessions with actual content
        sessions = [
            row
            for row in sessions
            if (row.get("message_count") or 0) > 0 or row.get("last_user_message")
        ]
```

Change to:

```python
        # Filter: only include sessions with actual content, exclude hidden
        sessions = [
            row
            for row in sessions
            if ((row.get("message_count") or 0) > 0 or row.get("last_user_message"))
            and not row.get("hidden")
        ]
```

Note: The existing condition gets wrapped in parentheses and the `and not row.get("hidden")` clause is added on a new line.

**Step 4: Run test to verify it passes**

Run:
```
uv run pytest tests/test_routes.py::test_hidden_sessions_excluded_from_history -v
```
Expected: PASS.

**Step 5: Run full test suites for regressions**

Run:
```
uv run pytest tests/test_session_history.py tests/test_routes.py -v
```
Expected: All tests PASS (no regressions).

**Step 6: Run code quality checks**

Run:
```
uv run ruff check src/chat_plugin/session_history.py src/chat_plugin/routes.py
uv run ruff format --check src/chat_plugin/session_history.py src/chat_plugin/routes.py
```
Expected: No errors, no formatting issues.

**Step 7: Commit**

```
git add src/chat_plugin/routes.py tests/test_routes.py
git commit -m "feat: filter hidden sessions from history sidebar"
```

---

### Final Verification

Run the exact acceptance criteria command:

```
uv run pytest tests/test_session_history.py::test_scan_sessions_hidden_flag tests/test_session_history.py::test_scan_sessions_not_hidden_by_default tests/test_routes.py::test_hidden_sessions_excluded_from_history -v
```

Expected: 3/3 PASS.

Then the full regression check:

```
uv run pytest tests/test_session_history.py tests/test_routes.py -v
```

Expected: All tests PASS, zero regressions.
