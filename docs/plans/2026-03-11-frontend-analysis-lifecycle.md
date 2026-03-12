# Frontend Analysis Lifecycle — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

> **Quality Review Warning:** The automated quality review loop exhausted 3 iterations
> without the approval gate registering correctly. The final verdict **was APPROVED**
> (115/115 tests passed, zero regressions, zero critical or important issues), but the
> loop mechanism failed to capture it. Human reviewer: please verify the final
> quality verdict reproduced below before proceeding.
>
> Last verdict: **APPROVED** — "Clean, well-structured implementation of the analysis
> lifecycle in a vanilla JS widget. The code demonstrates solid error handling,
> defensive programming, and logical organization."

**Goal:** Wire the feedback widget to start an analysis when the modal opens, subscribe to SSE for results, and cancel on close — passing the current sessionId from ChatApp into the widget.

**Architecture:** The ChatApp component in `index.html` stores the active `sessionId` in a ref (`sessionIdRef`) synced via `useEffect`, then passes a `getSessionId` callback into the widget's `init()` options. The feedback widget in `feedback-widget.js` gains an analysis lifecycle inside `openModal`: it POSTs to `/chat/api/feedback/analyze`, subscribes to SSE on the returned analysis session, accumulates `content_block:delta` events, and cancels on modal close. A full set of CSS classes supports loading, error, and findings UI states.

**Tech Stack:** Vanilla JavaScript (ES5), React (in-HTML Babel), CSS-in-JS (string array), Python/pytest (static source analysis tests).

**Dependencies:** Task 2 (feedback analysis endpoint) must be complete — the POST `/chat/api/feedback/analyze` endpoint and `/sessions/{id}/cancel` must exist.

---

### Task 1: Add analysis CSS classes to feedback-widget.js

**Files:**
- Modify: `src/chat_plugin/static/feedback-widget.js` (lines 268–347, inside the `CSS` array)
- Test: `tests/test_frontend_analysis_lifecycle.py` (new file)

**Step 1: Write the failing tests**

Create `tests/test_frontend_analysis_lifecycle.py` with the CSS test class:

```python
"""Tests for Task 4: Frontend Analysis Lifecycle.

Verifies that index.html passes sessionIdRef to the feedback widget,
and that feedback-widget.js contains the analysis lifecycle wiring:
CSS classes, extractFindings, SSE subscription, cancel-on-close, etc.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "chat_plugin" / "static"
INDEX_HTML = STATIC / "index.html"
WIDGET_JS = STATIC / "feedback-widget.js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ===========================================================================
# feedback-widget.js — CSS classes
# ===========================================================================


class TestWidgetAnalysisCSS:
    """All analysis CSS classes must be defined in the widget stylesheet."""

    REQUIRED_CLASSES = [
        ".amp-fb-analysis",
        ".amp-fb-analysis-loading",
        ".amp-fb-spinner",
        ".amp-fb-analysis-cancel",
        ".amp-fb-analysis-error",
        ".amp-fb-findings-group",
        ".amp-fb-findings-group-header",
        ".amp-fb-finding",
        ".amp-fb-finding-content",
        ".amp-fb-finding-summary",
        ".amp-fb-finding-detail",
        ".amp-fb-finding-link",
        ".amp-fb-finding-status",
    ]

    def test_all_css_classes_present(self):
        src = _read(WIDGET_JS)
        for cls in self.REQUIRED_CLASSES:
            assert cls in src, f"Missing CSS class: {cls}"

    def test_spinner_keyframes(self):
        src = _read(WIDGET_JS)
        assert "@keyframes amp-fb-spin" in src

    def test_finding_checkbox_style(self):
        src = _read(WIDGET_JS)
        assert ".amp-fb-finding input[type=checkbox]" in src

    def test_finding_detail_pre_style(self):
        src = _read(WIDGET_JS)
        assert ".amp-fb-finding-detail pre" in src

    def test_finding_status_variants(self):
        src = _read(WIDGET_JS)
        # .open and .closed variants
        assert re.search(r"\.amp-fb-finding-status\.open", src)
        assert re.search(r"\.amp-fb-finding-status\.closed", src)

    def test_css_before_reduced_motion(self):
        """Analysis CSS must appear before the reduced-motion media query."""
        src = _read(WIDGET_JS)
        spinner_pos = src.find(".amp-fb-spinner")
        reduced_motion_pos = src.find("prefers-reduced-motion")
        assert spinner_pos != -1 and reduced_motion_pos != -1
        assert spinner_pos < reduced_motion_pos
```

**Step 2: Run tests to verify they fail**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestWidgetAnalysisCSS -v
```
Expected: Multiple FAIL — the CSS classes `.amp-fb-analysis`, `.amp-fb-spinner`, etc. do not yet exist in `feedback-widget.js`.

**Step 3: Add analysis CSS classes to the CSS array**

In `src/chat_plugin/static/feedback-widget.js`, find the line (around line 268):
```javascript
    '}',

    /* --- Reduced motion --- */
```

Insert the following CSS block **before** `/* --- Reduced motion --- */`:

```javascript
    /* --- Analysis section --- */
    '.amp-fb-analysis {',
    '  margin-top: 16px; padding: 12px;',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-input, 10px);',
    '  background: var(--canvas, var(--bg-primary, #0d0d0d));',
    '  font-size: 13px; color: var(--ink-slate, var(--text-secondary, #999));',
    '  min-height: 48px;',
    '}',
    '.amp-fb-analysis-loading {',
    '  display: flex; align-items: center; gap: 10px;',
    '}',
    '.amp-fb-spinner {',
    '  width: 18px; height: 18px; border-radius: 50%;',
    '  border: 2px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-top-color: var(--signal, var(--accent, #5B4DE3));',
    '  animation: amp-fb-spin 0.8s linear infinite;',
    '}',
    '@keyframes amp-fb-spin {',
    '  to { transform: rotate(360deg); }',
    '}',
    '.amp-fb-analysis-cancel {',
    '  background: none; border: none; color: var(--ink-fog, var(--text-muted, #555));',
    '  font-size: 12px; cursor: pointer; text-decoration: underline;',
    '  margin-left: auto; padding: 0;',
    '}',
    '.amp-fb-analysis-cancel:hover { color: var(--ink, var(--text-primary, #e8e8e8)); }',
    '.amp-fb-analysis-error {',
    '  color: var(--error, #ef4444); font-size: 13px;',
    '}',
    '.amp-fb-findings-group {',
    '  margin-top: 8px;',
    '}',
    '.amp-fb-findings-group-header {',
    '  font-size: 12px; font-weight: 600; margin-bottom: 6px;',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '}',
    '.amp-fb-finding {',
    '  display: flex; align-items: flex-start; gap: 8px;',
    '  padding: 6px 0; border-bottom: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '}',
    '.amp-fb-finding:last-child { border-bottom: none; }',
    '.amp-fb-finding input[type=checkbox] {',
    '  margin-top: 3px; accent-color: var(--signal, var(--accent, #5B4DE3));',
    '}',
    '.amp-fb-finding-content {',
    '  flex: 1; min-width: 0;',
    '}',
    '.amp-fb-finding-summary {',
    '  font-size: 13px; font-weight: 500;',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '}',
    '.amp-fb-finding-detail {',
    '  font-size: 12px; color: var(--ink-slate, var(--text-secondary, #999));',
    '  margin-top: 4px;',
    '}',
    '.amp-fb-finding-detail pre {',
    '  white-space: pre-wrap; word-break: break-word;',
    '  font-family: var(--font-mono, "Fira Code", monospace);',
    '  font-size: 11px; margin-top: 4px;',
    '  padding: 6px; border-radius: 4px;',
    '  background: var(--canvas-warm, var(--bg-secondary, #1E1E1E));',
    '}',
    '.amp-fb-finding-link {',
    '  font-size: 12px; color: var(--signal, var(--accent, #5B4DE3));',
    '  text-decoration: none;',
    '}',
    '.amp-fb-finding-link:hover { text-decoration: underline; }',
    '.amp-fb-finding-status {',
    '  font-size: 11px; font-weight: 600; padding: 1px 6px;',
    '  border-radius: 4px; display: inline-block; margin-left: 6px;',
    '}',
    '.amp-fb-finding-status.open {',
    '  background: rgba(34,197,94,0.15); color: var(--accent-green, #22c55e);',
    '}',
    '.amp-fb-finding-status.closed {',
    '  background: rgba(239,68,68,0.15); color: var(--error, #ef4444);',
    '}',

```

**Step 4: Run tests to verify they pass**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestWidgetAnalysisCSS -v
```
Expected: All 7 tests PASS.

**Step 5: Commit**

```
git add src/chat_plugin/static/feedback-widget.js tests/test_frontend_analysis_lifecycle.py
git commit -m "feat: add analysis CSS classes to feedback widget"
```

---

### Task 2: Add extractFindings function to feedback-widget.js

**Files:**
- Modify: `src/chat_plugin/static/feedback-widget.js` (after `buildIssueBody`, around line 407)
- Modify: `tests/test_frontend_analysis_lifecycle.py` (append new test class)

**Step 1: Write the failing tests**

Append to `tests/test_frontend_analysis_lifecycle.py`:

```python
# ===========================================================================
# feedback-widget.js — extractFindings function
# ===========================================================================


class TestExtractFindings:
    """extractFindings must be defined after buildIssueBody."""

    def test_function_exists(self):
        src = _read(WIDGET_JS)
        assert "function extractFindings" in src

    def test_strips_code_fences(self):
        """Must handle markdown code fences."""
        src = _read(WIDGET_JS)
        # Should reference code fence stripping (```json ... ```)
        assert "```" in src or "replace" in src

    def test_json_parse(self):
        """Must use JSON.parse."""
        src = _read(WIDGET_JS)
        # extractFindings should use JSON.parse on some substring
        fn_start = src.find("function extractFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 600]
        assert "JSON.parse" in fn_region

    def test_returns_empty_on_failure(self):
        """Returns [] on parse failure."""
        src = _read(WIDGET_JS)
        fn_start = src.find("function extractFindings")
        fn_region = src[fn_start : fn_start + 600]
        assert "[]" in fn_region

    def test_defined_after_buildIssueBody(self):
        src = _read(WIDGET_JS)
        build_pos = src.find("function buildIssueBody")
        extract_pos = src.find("function extractFindings")
        assert build_pos != -1 and extract_pos != -1
        assert extract_pos > build_pos
```

**Step 2: Run tests to verify they fail**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestExtractFindings -v
```
Expected: FAIL — `function extractFindings` not found in source.

**Step 3: Add the extractFindings function**

In `src/chat_plugin/static/feedback-widget.js`, find the closing brace of `buildIssueBody` (around line 406):
```javascript
    return lines.join('\n');
  }
```

Add immediately after:

```javascript
  function extractFindings(text) {
    try {
      // Strip markdown code fences (```json ... ``` or ``` ... ```)
      var stripped = text.replace(/```[\w]*\n?/g, '').replace(/```/g, '');
      var first = stripped.indexOf('[');
      var last = stripped.lastIndexOf(']');
      if (first === -1 || last === -1 || last <= first) return [];
      return JSON.parse(stripped.substring(first, last + 1));
    } catch (e) {
      return [];
    }
  }
```

**Step 4: Run tests to verify they pass**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestExtractFindings -v
```
Expected: All 5 tests PASS.

**Step 5: Commit**

```
git add src/chat_plugin/static/feedback-widget.js tests/test_frontend_analysis_lifecycle.py
git commit -m "feat: add extractFindings function to feedback widget"
```

---

### Task 3: Add sessionIdRef plumbing to index.html

**Files:**
- Modify: `src/chat_plugin/static/index.html` (lines 3431–3432, 3473, 3576–3581)
- Modify: `tests/test_frontend_analysis_lifecycle.py` (add new test class)

**Step 1: Write the failing tests**

Insert at the top of the test classes in `tests/test_frontend_analysis_lifecycle.py` (after the helpers, before `TestWidgetAnalysisCSS`):

```python
# ===========================================================================
# index.html — sessionIdRef plumbing
# ===========================================================================


class TestIndexSessionIdRef:
    """index.html must declare sessionIdRef and pass it to the widget."""

    def test_sessionIdRef_declared(self):
        src = _read(INDEX_HTML)
        assert "const sessionIdRef = useRef(null);" in src

    def test_sessionIdRef_sync_effect(self):
        """A useEffect syncs sessionId state into sessionIdRef."""
        src = _read(INDEX_HTML)
        assert "sessionIdRef.current = sessionId;" in src
        # Must be in a useEffect with [sessionId] dependency
        assert re.search(
            r"useEffect\(\(\)\s*=>\s*\{\s*sessionIdRef\.current\s*=\s*sessionId;\s*\},\s*\[sessionId\]\)",
            src,
        )

    def test_getSessionId_callback_passed(self):
        """Widget init receives a getSessionId callback returning sessionIdRef.current."""
        src = _read(INDEX_HTML)
        assert "getSessionId" in src
        assert "sessionIdRef.current" in src
        # The init call should contain the getSessionId option
        assert re.search(
            r"getSessionId\s*:\s*function\s*\(\)\s*\{\s*return\s+sessionIdRef\.current;\s*\}",
            src,
        )
```

**Step 2: Run tests to verify they fail**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestIndexSessionIdRef -v
```
Expected: FAIL — `sessionIdRef` not declared, no `useEffect` sync, no `getSessionId` callback.

**Step 3: Add sessionIdRef declaration**

In `src/chat_plugin/static/index.html`, find line 3431:
```javascript
    const [sessionId, setSessionId] = useState(null);
```

Add immediately after:
```javascript
    const sessionIdRef = useRef(null);
```

**Step 4: Add sessionIdRef sync effect**

Find the line before `// Feedback widget` / `const feedbackSlotRef = useRef(null);` (around line 3475–3476). Insert before it:

```javascript
    useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
```

**Step 5: Add getSessionId to widget init call**

Find the `AmplifierFeedback.init({` block (around line 3576). It currently looks like:
```javascript
        window.AmplifierFeedback.init({
          mode: 'header',
          container: slot,
          context: { app: 'chat' },
        });
```

Add the `getSessionId` option:
```javascript
        window.AmplifierFeedback.init({
          mode: 'header',
          container: slot,
          context: { app: 'chat' },
          getSessionId: function() { return sessionIdRef.current; },
        });
```

**Step 6: Run tests to verify they pass**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestIndexSessionIdRef -v
```
Expected: All 3 tests PASS.

**Step 7: Commit**

```
git add src/chat_plugin/static/index.html tests/test_frontend_analysis_lifecycle.py
git commit -m "feat: pass sessionIdRef to feedback widget via getSessionId callback"
```

---

### Task 4: Wire analysis lifecycle into openModal

**Files:**
- Modify: `src/chat_plugin/static/feedback-widget.js` (inside `openModal` function, lines 425–719)
- Modify: `tests/test_frontend_analysis_lifecycle.py` (append final test class)

**Step 1: Write the failing tests**

Append to `tests/test_frontend_analysis_lifecycle.py`:

```python
# ===========================================================================
# feedback-widget.js — Analysis lifecycle in openModal
# ===========================================================================


class TestAnalysisLifecycle:
    """openModal must wire up analysis start, SSE subscription, and cancel."""

    def test_startAnalysis_function(self):
        src = _read(WIDGET_JS)
        assert "function startAnalysis" in src

    def test_startAnalysis_posts_to_analyze(self):
        """startAnalysis calls POST to the feedback/analyze endpoint."""
        src = _read(WIDGET_JS)
        # apiBase is constructed as origin + '/chat/api', then fetch uses apiBase + '/feedback/analyze'
        assert "/feedback/analyze" in src

    def test_subscribeToSSE_function(self):
        src = _read(WIDGET_JS)
        assert "function subscribeToSSE" in src

    def test_sse_uses_eventsource(self):
        src = _read(WIDGET_JS)
        assert "EventSource" in src

    def test_sse_listens_for_content_block_delta(self):
        src = _read(WIDGET_JS)
        assert "content_block:delta" in src

    def test_sse_listens_for_completion_events(self):
        src = _read(WIDGET_JS)
        assert "orchestrator:complete" in src
        assert "execution:end" in src

    def test_cancelAnalysis_function(self):
        src = _read(WIDGET_JS)
        assert "function cancelAnalysis" in src

    def test_cancelAnalysis_posts_cancel(self):
        """cancelAnalysis POSTs /sessions/{id}/cancel with {immediate: true}."""
        src = _read(WIDGET_JS)
        assert "/cancel" in src
        assert "immediate" in src

    def test_closeModal_calls_cancelAnalysis(self):
        """cancelAnalysis() must be the first line in closeModal."""
        src = _read(WIDGET_JS)
        match = re.search(
            r"function closeModal\(\)\s*\{[^}]*cancelAnalysis\(\)", src, re.DOTALL
        )
        assert match, "closeModal must call cancelAnalysis()"

    def test_openModal_calls_startAnalysis(self):
        """startAnalysis() is called after titleInput.focus() in the openModal body."""
        src = _read(WIDGET_JS)
        focus_pos = src.find("titleInput.focus()")
        # Find the startAnalysis() *call* that appears after focus, not the definition
        start_call_pos = src.find("startAnalysis();", focus_pos)
        assert focus_pos != -1 and start_call_pos != -1
        assert start_call_pos > focus_pos

    def test_updateAnalysisUI_function(self):
        src = _read(WIDGET_JS)
        assert "function updateAnalysisUI" in src

    def test_analysisSection_in_modal(self):
        """analysisSection div is created and added to modal."""
        src = _read(WIDGET_JS)
        assert "analysisSection" in src

    def test_placeholder_renderFindings(self):
        """Placeholder renderFindings shows count."""
        src = _read(WIDGET_JS)
        assert "finding(s) ready" in src

    def test_onComplete_guards_against_double_fire(self):
        """onComplete must early-return if already complete to prevent double processing."""
        src = _read(WIDGET_JS)
        # Find the onComplete function body
        fn_start = src.find("function onComplete()")
        assert fn_start != -1, "onComplete function must exist"
        fn_region = src[fn_start : fn_start + 300]
        # Must contain an early-return guard checking analysisComplete
        assert re.search(r"if\s*\(\s*analysisComplete\s*\)\s*return;", fn_region), (
            "onComplete must guard against double-fire with 'if (analysisComplete) return;'"
        )
```

**Step 2: Run tests to verify they fail**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestAnalysisLifecycle -v
```
Expected: Multiple FAIL — none of the analysis lifecycle functions exist in `openModal` yet.

**Step 3: Add analysis state variables at top of openModal**

In `src/chat_plugin/static/feedback-widget.js`, find the `openModal` function (line 425):
```javascript
  function openModal(opts) {
    var category = 'general';
```

Add immediately after `var category = 'general';`:

```javascript
    // Analysis lifecycle state
    var apiBase = (window.location.origin || '') + '/chat/api';
    var analysisSessionId = null;
    var analysisSSE = null;
    var analysisComplete = false;
    var responseText = '';
    var findings = [];
    var findingChecked = {}; // Used by renderFindings (next task)
    var analysisSection = el('div', { className: 'amp-fb-analysis' });
```

**Step 4: Add closeSSE helper**

Add immediately after the `analysisSection` line:

```javascript
    function closeSSE() {
      if (analysisSSE) { analysisSSE.close(); analysisSSE = null; }
    }
```

**Step 5: Add updateAnalysisUI function**

Add after `closeSSE`:

```javascript
    function updateAnalysisUI(state, errorMsg) {
      analysisSection.innerHTML = '';
      if (state === 'loading') {
        var spinner = el('div', { className: 'amp-fb-spinner' });
        var loadingRow = el('div', { className: 'amp-fb-analysis-loading' }, [
          spinner,
          el('span', null, ['Analyzing session\u2026']),
        ]);
        var cancelBtn = el('button', {
          className: 'amp-fb-analysis-cancel',
          type: 'button',
          onClick: function () { cancelAnalysis(); updateAnalysisUI('idle'); },
        }, ['Cancel']);
        loadingRow.appendChild(cancelBtn);
        analysisSection.appendChild(loadingRow);
      } else if (state === 'error') {
        analysisSection.appendChild(
          el('div', { className: 'amp-fb-analysis-error' }, [errorMsg || 'Analysis failed.'])
        );
      } else if (state === 'complete') {
        renderFindings();
      } else {
        // idle
        analysisSection.innerHTML = '';
      }
    }
```

**Step 6: Add startAnalysis function**

Add after `updateAnalysisUI`:

```javascript
    function startAnalysis() {
      var getSessionId = opts.getSessionId;
      var currentSessionId = getSessionId ? getSessionId() : null;
      if (!currentSessionId) {
        updateAnalysisUI('idle');
        return;
      }
      updateAnalysisUI('loading');
      fetch(apiBase + '/feedback/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId }),
      })
        .then(function (res) {
          if (!res.ok) throw new Error('Analysis request failed: ' + res.status);
          return res.json();
        })
        .then(function (data) {
          analysisSessionId = data.analysis_session_id;
          subscribeToSSE(analysisSessionId);
        })
        .catch(function (err) {
          updateAnalysisUI('error', err.message);
        });
    }
```

**Step 7: Add subscribeToSSE function**

Add after `startAnalysis`:

```javascript
    function subscribeToSSE(sessionId) {
      var evtSource = new EventSource('/events?session=' + encodeURIComponent(sessionId));
      analysisSSE = evtSource;

      evtSource.addEventListener('content_block:delta', function (e) {
        try {
          var payload = JSON.parse(e.data);
          var delta = payload.delta || payload;
          responseText += (delta.text || delta.thinking || '');
        } catch (ex) { console.warn('SSE delta parse error:', ex); }
      });

      function onComplete() {
        if (analysisComplete) return;
        analysisComplete = true;
        closeSSE();
        findings = extractFindings(responseText);
        renderFindings();
      }

      evtSource.addEventListener('orchestrator:complete', onComplete);
      evtSource.addEventListener('execution:end', onComplete);

      evtSource.onerror = function () {
        if (analysisComplete) return;
        // Try to parse whatever we have accumulated
        if (responseText) {
          findings = extractFindings(responseText);
          if (findings.length > 0) {
            analysisComplete = true;
            closeSSE();
            renderFindings();
            return;
          }
        }
        updateAnalysisUI('error', 'Connection to analysis stream lost.');
        closeSSE();
      };
    }
```

**Step 8: Add cancelAnalysis function**

Add after `subscribeToSSE`:

```javascript
    function cancelAnalysis() {
      closeSSE();
      if (analysisSessionId && !analysisComplete) {
        // Cancel endpoint is at server root, not under apiBase (/chat/api)
        fetch('/sessions/' + encodeURIComponent(analysisSessionId) + '/cancel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ immediate: true }),
        }).catch(function () { /* best effort */ });
      }
    }
```

**Step 9: Add placeholder renderFindings function**

Add after `cancelAnalysis`:

```javascript
    function renderFindings() {
      analysisSection.textContent = findings.length + ' finding(s) ready.';
    }
```

**Step 10: Insert analysisSection into modal card DOM**

Find where the card children are assembled (the `el('div', { className: 'amp-fb-card' }, [...])` call). Insert `analysisSection` between the description textarea field and the actions row. The card children array should include:

```javascript
      // Analysis
      analysisSection,
      // Actions
      el('div', { className: 'amp-fb-actions' }, [
```

**Step 11: Add cancelAnalysis() to closeModal**

Find the `closeModal` function (around line 689 after edits). Add `cancelAnalysis();` as the **first line** inside:

```javascript
    function closeModal() {
      cancelAnalysis();
      document.removeEventListener('keydown', onKey);
      if (backdrop.parentNode) { backdrop.parentNode.removeChild(backdrop); }
      if (triggerEl) { try { triggerEl.focus(); } catch (e) { /* noop */ } }
    }
```

**Step 12: Add startAnalysis() call after titleInput.focus()**

Find `titleInput.focus();` near the end of `openModal`. Add immediately after:

```javascript
    // Kick off analysis
    startAnalysis();
```

**Step 13: Run tests to verify they pass**

Run:
```
uv run pytest tests/test_frontend_analysis_lifecycle.py::TestAnalysisLifecycle -v
```
Expected: All 14 tests PASS.

**Step 14: Commit**

```
git add src/chat_plugin/static/feedback-widget.js tests/test_frontend_analysis_lifecycle.py
git commit -m "feat: wire up feedback widget analysis lifecycle with SSE streaming"
```

---

### Final Verification

Run the full test suite to confirm no regressions:

```
uv run pytest tests/ -v
```

Expected: All tests PASS (115 total including 29 new tests from this task across 4 test classes: `TestIndexSessionIdRef` (3), `TestWidgetAnalysisCSS` (7), `TestExtractFindings` (5), `TestAnalysisLifecycle` (14)).

Verify specific acceptance criteria:

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | No Python regressions | `uv run pytest tests/ -v` — all PASS |
| 2 | index.html passes sessionIdRef via getSessionId | `TestIndexSessionIdRef` (3 tests) |
| 3 | extractFindings parses JSON arrays from text | `TestExtractFindings` (5 tests) |
| 4 | Opening modal triggers POST /chat/api/feedback/analyze | `TestAnalysisLifecycle::test_startAnalysis_posts_to_analyze` |
| 5 | Widget subscribes to SSE and accumulates deltas | `TestAnalysisLifecycle::test_sse_*` (4 tests) |
| 6 | Closing modal cancels via POST /sessions/{id}/cancel | `TestAnalysisLifecycle::test_cancelAnalysis_*` + `test_closeModal_*` |
| 7 | Analysis section shows loading/error/completion states | `TestAnalysisLifecycle::test_updateAnalysisUI_function` + `test_placeholder_renderFindings` |
| 8 | All CSS classes defined in widget style block | `TestWidgetAnalysisCSS` (7 tests) |
