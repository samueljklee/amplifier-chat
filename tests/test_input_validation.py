"""
Tests for input validation across all unvalidated entry points (S-16).

Written in TDD RED phase — tests for invalid session IDs are expected to FAIL
against the current (unfixed) code, confirming validation gaps exist at:
  - Legacy pin routes: /chat/pins/{session_id}
  - Shell route:      /chat/api/sessions/{session_id}/shell
  - Dispatch command: /chat/command  (session_id in JSON body)
  - Feedback analyze: /chat/api/feedback/analyze (AnalyzeRequest.session_id)

NOTE on URL encoding: Path traversal strings like ``../../../etc/passwd``
contain slashes which Starlette normalises before route-matching (the route
never fires → 404, not 400).  Tests therefore use dotted variants such as
``..bad`` which:
  - contain dots that VALID_SESSION_ID_RE rejects (``^[a-zA-Z0-9_\\-]+$``)
  - represent the same class of traversal-like injection
  - reach the route handler so the validation gap is visible

After the security fix (S-16) is applied, tests 1, 2, 4, 5, 8 should PASS
(invalid session IDs rejected with 400 / 422). Tests 3, 6, 7 verify valid
inputs still work and are expected to pass both before and after the fix.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from chat_plugin.feedback import create_feedback_routes

# Traversal-like session_id that reaches route handlers without Starlette
# normalising the path.  Contains a dot, which VALID_SESSION_ID_RE rejects.
_TRAVERSAL_SESSION_ID = "..bad"


# ---------------------------------------------------------------------------
# Legacy pin routes — /chat/pins/{session_id}
# ---------------------------------------------------------------------------


def test_legacy_pin_rejects_invalid_session_id(client):
    """POST /chat/pins with a traversal-like session_id must return 400.

    The legacy /chat/pins/ routes accept *any* string as session_id today —
    there is no call to VALID_SESSION_ID_RE.  The session_id ``..bad``
    contains a dot (not in ``[a-zA-Z0-9_-]``) representing the same class of
    injection risk as ``../../../etc/passwd``.

    CURRENTLY FAILS: current code returns 200 (no session_id validation).
    """
    resp = client.post(f"/chat/pins/{_TRAVERSAL_SESSION_ID}")
    assert resp.status_code == 400, (
        f"Expected 400 for traversal-like session_id {_TRAVERSAL_SESSION_ID!r}, "
        f"got {resp.status_code}: {resp.text}"
    )


def test_legacy_unpin_rejects_invalid_session_id(client):
    """DELETE /chat/pins with a traversal-like session_id must return 400.

    CURRENTLY FAILS: current code returns 200 (no session_id validation).
    """
    resp = client.delete(f"/chat/pins/{_TRAVERSAL_SESSION_ID}")
    assert resp.status_code == 400, (
        f"Expected 400 for traversal-like session_id {_TRAVERSAL_SESSION_ID!r}, "
        f"got {resp.status_code}: {resp.text}"
    )


def test_legacy_pin_accepts_valid_session_id(client):
    """POST /chat/pins with a well-formed session_id must return 200.

    Regression guard: after S-16, valid session IDs must still be accepted.
    Expected to PASS both before and after the fix.
    """
    resp = client.post("/chat/pins/session-abc-123")
    assert resp.status_code == 200, (
        f"Expected 200 for valid session_id 'session-abc-123', "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Shell route — POST /chat/api/sessions/{session_id}/shell
# ---------------------------------------------------------------------------


def test_shell_rejects_invalid_session_id(client):
    """POST /chat/api/sessions/<traversal>/shell must return 400 or 404.

    The shell endpoint currently performs no session_id validation.  Given a
    valid body (command + cwd), the current handler executes the shell command
    and returns 200 (StreamingResponse).

    The command runs to completion in the test environment — this DEMONSTRATES
    the vulnerability: the traversal-like session_id is silently accepted and
    the command proceeds unchanged.

    CURRENTLY FAILS: returns 200 instead of 400 or 404.
    """
    resp = client.post(
        f"/chat/api/sessions/{_TRAVERSAL_SESSION_ID}/shell",
        json={"command": "echo test", "cwd": "/tmp"},
    )
    assert resp.status_code in (400, 404), (
        f"Expected 400 or 404 for traversal-like session_id {_TRAVERSAL_SESSION_ID!r}, "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Dispatch command — POST /chat/command
# ---------------------------------------------------------------------------


def test_dispatch_command_rejects_invalid_session_id(client):
    """POST /chat/command with a traversal session_id in the body must return 400.

    The dispatch endpoint passes session_id straight to the command handler
    without validation today, returning 200 {"type": "prompt", ...}.

    CURRENTLY FAILS: returns 200 (no validation on body session_id).
    """
    resp = client.post(
        "/chat/command",
        json={"session_id": "../../../etc/passwd"},
    )
    assert resp.status_code == 400, (
        f"Expected 400 for traversal session_id '../../../etc/passwd', "
        f"got {resp.status_code}: {resp.text}"
    )


def test_dispatch_command_allows_valid_session_id(client):
    """POST /chat/command with a well-formed session_id must NOT be rejected.

    Regression guard: valid session IDs must not be incorrectly refused by
    S-16 validation.  Expected to PASS both before and after the fix.
    """
    resp = client.post(
        "/chat/command",
        json={"command": "/help", "session_id": "valid-session-123"},
    )
    assert not (resp.status_code == 400 and "Invalid session" in resp.text), (
        f"Valid session_id 'valid-session-123' must not be rejected with "
        f"'Invalid session': status={resp.status_code}, body={resp.text}"
    )


def test_dispatch_command_allows_null_session_id(client):
    """POST /chat/command without a session_id must not crash (no 500).

    Null / absent session_id is a legitimate call pattern (e.g. global
    commands).  Expected to PASS both before and after S-16.
    """
    resp = client.post(
        "/chat/command",
        json={"command": "/help"},
    )
    assert resp.status_code != 500, (
        f"Missing session_id must not cause a server error (500): {resp.text}"
    )


# ---------------------------------------------------------------------------
# Feedback analyze — POST /chat/api/feedback/analyze
# ---------------------------------------------------------------------------


def test_analyze_rejects_invalid_session_id(tmp_path, monkeypatch):
    """POST /chat/api/feedback/analyze with a traversal session_id must return 400 or 422.

    The AnalyzeRequest Pydantic model currently declares ``session_id: str``
    with no format constraint, so any string passes Pydantic validation and
    the handler proceeds to look up the transcript (returning 404 — not found).

    A minimal inline app is used here so ``projects_dir`` is a real path,
    ensuring the handler moves past the "not configured" guard and into the
    session_id-dependent code path.

    CURRENTLY FAILS: returns 404 (transcript not found) instead of 400/422.
    """
    monkeypatch.setenv("CHAT_PLUGIN_HOME_DIR", str(tmp_path))
    app = FastAPI()
    router = create_feedback_routes(projects_dir=tmp_path, daemon_session_path=None)
    app.include_router(router)
    feedback_client = TestClient(app)

    resp = feedback_client.post(
        "/chat/api/feedback/analyze",
        json={"session_id": "../../../etc/passwd"},
    )
    assert resp.status_code in (400, 422), (
        f"Expected 400 or 422 for traversal session_id '../../../etc/passwd', "
        f"got {resp.status_code}: {resp.text}"
    )
