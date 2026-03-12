# Message-to-Activity Correlation — Layout & Scroll Behavior Spec

**Goal:** Make the spatial relationship between conversation messages and their corresponding activities legible, navigable, and unobtrusive in the two-panel workspace UI.

**Author:** Layout design session, 2026-03-12

---

## 1. Current State Analysis

### Data Model

A single `chronoItems` array holds all items with a shared monotonic `order` counter. In workspace mode, two `MessageList` instances render from the same array with different filters:

| Panel | Filter | Shows |
|-------|--------|-------|
| Main pane | `i => i.type === 'text'` | User prompts, assistant responses, system messages |
| Activity panel | `i => i.type !== 'text'` | Tool calls, thinking blocks, token usage |

**Critical gap:** There is no explicit turn boundary. No `turnId` or `turnIndex` on items. The only linkage between a user message and the activities it spawned is temporal ordering via the shared `order` counter.

### Current Scroll Behavior

Each `MessageList` instance manages its own scroll independently:
- Auto-anchors to bottom on first load
- Stays pinned to bottom while new content arrives (if already near bottom)
- Shows jump-to-top / jump-to-bottom controls when content overflows
- Shows a "New messages" pill when content arrives while scrolled away

**Problem:** Scrolling through a long conversation in the main pane leaves the activity panel wherever it was. There is no way to see which activities correspond to which message.

---

## 2. Turn Derivation — The Foundation

Since there are no explicit turns, we derive them from the item stream:

```
Turn boundary rule:
  A new turn starts at every user message (type: 'text', role: 'user').
  Everything between two consecutive user messages belongs to one turn.
  Items before the first user message belong to turn 0 ("Session start").
```

### Computation

```js
// Computed once per chronoItems change (memoized)
function deriveTurns(items) {
  const sorted = [...items].sort((a, b) => a.order - b.order);
  let turnIndex = 0;
  let turnPrompt = null;
  let turnStartOrder = 0;
  const turns = [];      // Array of { index, prompt, startOrder, endOrder }
  const itemTurnMap = new Map();  // itemId → turnIndex

  for (const item of sorted) {
    if (item.type === 'text' && item.role === 'user') {
      // Close previous turn
      if (turns.length > 0) {
        turns[turns.length - 1].endOrder = item.order - 1;
      }
      turnIndex = turns.length;
      turnPrompt = item.content;
      turnStartOrder = item.order;
      turns.push({
        index: turnIndex,
        prompt: turnPrompt,
        promptItemId: item.id,
        startOrder: turnStartOrder,
        endOrder: Infinity,  // updated when next turn starts
      });
    }
    itemTurnMap.set(item.id, turnIndex);
  }

  return { turns, itemTurnMap };
}
```

**Performance:** O(n) single pass, memoized via `useMemo([chronoItems])`. For a 500-item conversation this is <1ms.

### Turn Assignment for Activity Items

Each activity item inherits the turn of the most recent preceding user message. This means:
- Tool calls spawned by an assistant response belong to the turn that prompted that response
- Token usage summaries at turn end belong to that same turn
- Thinking blocks belong to the turn they're reasoning about

---

## 3. Scroll Synchronization Strategy

### Rejected Alternatives

| Approach | Why rejected |
|----------|-------------|
| **Lock-step pixel scrolling** | Panels have wildly asymmetric heights. A single user message might correspond to 15 tool calls. Lock-step creates empty space or impossible compression. |
| **Forced vertical alignment** | Inserting spacers to align turn boundaries across panels wastes space and breaks both panels' natural flow. Unacceptable for a developer tool. |
| **Bidirectional auto-follow** | Both panels following each other creates feedback loops and disorienting behavior. |

### Chosen: Soft Follow at Turn Granularity

The activity panel follows the main panel at **turn granularity**, not pixel granularity.

```
Main pane scroll → detect dominant turn → scroll activity panel to that turn's group
```

This preserves independent scroll freedom while communicating which activities belong to the visible conversation context.

### Dominant Turn Detection

The "dominant turn" is the turn most visually prominent in the main pane viewport:

```
Algorithm:
1. Find all user messages currently intersecting the main pane viewport
   (using IntersectionObserver with rootMargin: "-20% 0px -20% 0px"
   to bias toward viewport center)
2. Among intersecting user messages, pick the one whose vertical center
   is closest to the viewport's vertical center
3. If no user messages are in the center 60% of viewport, use the last
   user message that was scrolled past (above viewport)
4. That message's turn index = dominant turn
```

**Why IntersectionObserver?** It's cheaper than computing `getBoundingClientRect()` on every user message during scroll. The observer fires callbacks only when visibility thresholds cross, and we batch the result.

### Follow Directionality

| Direction | Trigger | Behavior |
|-----------|---------|----------|
| Main → Activity | Scroll in main pane | Activity panel smoothly scrolls to dominant turn's group (auto-follow) |
| Activity → Main | **Click** on turn header in activity panel | Main pane scrolls to corresponding user message |
| Activity scroll | Direct scroll/wheel on activity panel | Auto-follow **pauses** — user is exploring freely |

**Critically:** Activity → Main is click-initiated only. Never scroll-follow. This prevents feedback loops.

### Follow Pause/Resume

When the user directly scrolls the activity panel (wheel, touch, scrollbar drag):

1. Auto-follow pauses immediately
2. A subtle indicator appears in the activity panel header: `"Paused · Resume ↓"`
3. Auto-follow resumes when ANY of:
   - User clicks the "Resume" action
   - User scrolls the **main pane** (re-engaging main→activity flow)
   - A new turn begins during streaming (new user message sent)

**Why no inactivity timer?** Considered a 5-second auto-resume, but rejected — developers often pause to read a long tool call output and would be disoriented by unexpected scroll jumps. Explicit resume is safer.

### Scroll Animation

```js
// When auto-follow triggers:
turnGroupElement.scrollIntoView({
  behavior: 'smooth',   // respects prefers-reduced-motion
  block: 'start',       // align to top of activity viewport
});
```

Duration governed by the browser's native smooth scroll implementation (~300-400ms). For `prefers-reduced-motion: reduce`, the browser makes this instant — no additional CSS needed.

### Debouncing

The scroll→turn-detection→follow pipeline is debounced:

```
Main pane scroll event
  → requestAnimationFrame (coalesce within frame)
  → check if dominant turn changed (compare to last known)
  → if changed AND follow is active: scroll activity panel
```

No additional setTimeout debounce needed — rAF already limits to ~16ms granularity, and we only act on turn *changes*, not every frame.

---

## 4. Turn Grouping in the Activity Panel

### Structure

Activities are wrapped in turn groups with lightweight separators:

```
┌─ Activity Panel ──────────────────────┐
│ ┌─ Turn Header (sticky) ────────────┐ │
│ │ ▸ "Refactor the auth module to..." │ │
│ └────────────────────────────────────┘ │
│   [thinking block]                     │
│   [tool_call: read_file]              │
│   [tool_call: edit_file]              │
│   [tool_call: bash — npm test]        │
│   [token_usage: 12,450 tokens]        │
│                                        │
│ ┌─ Turn Header (sticky) ────────────┐ │
│ │ ▸ "Now add error handling for..."  │ │
│ └────────────────────────────────────┘ │
│   [thinking block]                     │
│   [tool_call: edit_file]              │
│   [token_usage: 8,200 tokens]         │
│                                        │
│ ┌─ Turn Header (sticky, streaming) ─┐ │
│ │ ● "Write tests for the new..."     │ │
│ └────────────────────────────────────┘ │
│   [thinking block — streaming]         │
│   [tool_call: read_file — running]    │
└────────────────────────────────────────┘
```

### Turn Header Design

The turn header is the primary correlation affordance. It shows:

1. **Prompt preview** — First ~60 characters of the user message, truncated with ellipsis
2. **Turn state** — Chevron (▸/▾) for complete turns, pulsing dot (●) for streaming turn
3. **Activity count badge** — e.g., "5 activities" in muted text (optional, right-aligned)

```
┌──────────────────────────────────────────────┐
│ ▸  "Refactor the auth module to..."   5 acts │
└──────────────────────────────────────────────┘
```

**Sticky behavior:** Turn headers stick to the top of the activity panel viewport as you scroll through a long turn group. Only the current turn's header is sticky — previous headers scroll away.

**Why sticky?** When a turn has 20+ tool calls, the user needs persistent context about *which* turn they're viewing. Without sticky headers, the prompt context scrolls out of view and the user loses orientation.

### CSS

```css
.turn-group {
  /* No visible container — grouping is structural, not visual */
}

.turn-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
  min-height: 24px;
}

.turn-header:first-child {
  border-top: none;  /* No separator above first turn */
}

.turn-header:hover {
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--bg-secondary) 92%, var(--accent));
}

.turn-header-prompt {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.turn-header-count {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.7;
}

.turn-header-chevron {
  flex-shrink: 0;
  font-size: 9px;
  transition: transform 150ms ease;
}

.turn-header-streaming {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: turn-pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes turn-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .turn-header-streaming {
    animation: none;
    opacity: 1;
  }
}
```

### Why Not Cards?

Cards (bordered containers with background fill per turn group) were considered and rejected:
- The activity panel already contains tool call cards with their own borders and backgrounds
- Wrapping cards in cards creates visual nesting overload
- Cards consume more vertical space (padding + margins)
- The developer tool aesthetic favors density over ornamentation

Lightweight separators + sticky headers achieve the same grouping clarity with less chrome.

---

## 5. Navigation Flow — Click-to-Correlate

### Message → Activities (Main pane → Activity panel)

**Trigger:** User clicks on a user message bubble in the main pane.

**Behavior:**
1. Determine the turn index of the clicked message
2. Find the corresponding turn group element in the activity panel
3. Scroll the activity panel: `element.scrollIntoView({ behavior: 'smooth', block: 'start' })`
4. Apply a brief highlight to the turn group (see Highlight Design below)
5. Auto-follow resumes (pinned to this turn)

**Affordance:** User messages should have a subtle hover cursor change (`cursor: pointer` in workspace mode only) to signal clickability. A small tooltip or title: `"Click to show activities"`.

### Activities → Message (Activity panel → Main pane)

**Trigger:** User clicks on a turn header in the activity panel.

**Behavior:**
1. Look up the turn's `promptItemId` (the user message's DOM id)
2. Find that element in the main pane
3. Scroll the main pane: `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`
4. Apply a brief highlight ring to the user message (see below)
5. Auto-follow is **not** resumed (user is exploring)

### Hover Cross-Highlight

**Trigger:** Hovering over a user message in the main pane, OR hovering over a turn header in the activity panel.

**Behavior:**
1. The corresponding element in the OTHER panel gets a subtle background tint
2. No scroll movement — just visual correlation
3. Tint appears with 100ms delay (prevents flicker on fast mouse movement)
4. Tint removes immediately on mouse-out (no delay)

**Implementation:** A shared `hoveredTurnIndex` state, set on mouseenter/mouseleave of user messages and turn headers. Both panels check if their turn matches and apply a CSS class.

### Highlight Design

```css
/* Brief flash when navigating to a turn group */
.turn-group.highlight-flash {
  animation: turn-flash 600ms ease-out;
}

@keyframes turn-flash {
  0% { background: rgba(var(--accent-rgb), 0.12); }
  100% { background: transparent; }
}

/* Brief ring when navigating to a user message */
.user-message.highlight-ring {
  animation: message-ring 800ms ease-out;
}

@keyframes message-ring {
  0% { box-shadow: 0 0 0 2px rgba(var(--accent-rgb), 0.4); }
  100% { box-shadow: 0 0 0 2px transparent; }
}

/* Hover cross-highlight (no animation, just tint) */
.turn-group.cross-hover {
  background: rgba(var(--accent-rgb), 0.04);
}

.user-message.cross-hover {
  background: rgba(var(--accent-rgb), 0.04);
  border-radius: 4px;
}

@media (prefers-reduced-motion: reduce) {
  .turn-group.highlight-flash,
  .user-message.highlight-ring {
    animation: none;
  }
  /* Still show the tint, just without animation */
  .turn-group.highlight-flash {
    background: rgba(var(--accent-rgb), 0.08);
    transition: background 1s ease-out;
  }
}
```

---

## 6. Edge Cases

### Long Turns (Many Activities)

A turn with 20+ tool calls creates a very tall turn group in the activity panel.

**Handling:**
- Sticky turn header stays visible throughout the group
- Auto-follow scrolls to the **top** of the group (not center)
- The user can scroll freely within the group without triggering a turn change
- Consider: turns with >15 activities could show a count + "Show all" with initial collapse of items beyond the first 8. This is a progressive disclosure optimization for a future iteration.

### Turns with No Activities

Common in quick back-and-forth exchanges (user asks a simple question, assistant replies from context without tool use).

**Handling:**
- No turn group is rendered in the activity panel for empty turns
- When auto-follow would scroll to an empty turn, the activity panel stays at its current position (no jarring scroll to nothing)
- The turn header is still rendered but shows: `"No tool activity"` in italic muted text, collapsed to a single line

Rationale: Rendering the empty-turn header maintains the turn sequence for orientation. The user can see "turn 3 had no activity" rather than wondering if something is missing.

### Very Short Turns

Single-line user message, single tool call response.

**Handling:** No special treatment. The turn separator and header render normally. Short turns are naturally compact.

### Streaming (Current Turn Still Generating)

The most complex edge case. During streaming:

1. **The streaming turn is always the last group** in the activity panel
2. **Turn header shows pulsing dot** (●) instead of chevron
3. **New activities appear at the bottom** of the streaming turn group
4. **Auto-scroll within the streaming turn:**
   - If user is near the bottom of the activity panel → auto-scroll to show new activities (existing behavior, preserved)
   - If user has scrolled up in the activity panel → do NOT auto-scroll (follow is paused)
5. **When streaming completes:**
   - Pulsing dot → chevron
   - Token usage summary appears as last item in the group
   - No scroll position change

**Interaction with auto-follow during streaming:**
- If user is at the bottom of main pane AND follow is active → both panels scroll together to show latest content (natural tail-follow)
- If user scrolls up in main pane during streaming → follow activates to that turn, activity panel scrolls to the corresponding earlier turn group
- If user scrolls up in activity panel during streaming → follow pauses, streaming continues at bottom but panel stays where user put it

### Session Start (Pre-First-User-Message)

System messages and initial content that appear before any user message:

**Handling:**
- Grouped as "Turn 0" with header: `"Session start"` (no prompt to show)
- Rarely has activities, but if there are initial system tool calls, they appear here
- This turn header is not sticky (too small to matter)

### Transcript Replay (Loading History)

When loading a saved session:

1. All items arrive at once via `transcriptToChronoItems`
2. Turn derivation runs on the complete set
3. Activity panel renders all turn groups immediately
4. Auto-follow starts active, pinned to the last turn (bottom of both panels)
5. User can then scroll up to explore history with full correlation

No special handling needed — the turn derivation works identically on historical and live data.

---

## 7. Activity Panel Header — Enhanced

The current activity panel header is a static label:

```html
<div class="activity-panel-header">Activity</div>
```

Enhanced to show follow state and current turn context:

```
┌─ Activity Panel Header ───────────────────────┐
│ Activity                    Following · Pause  │
│ — or —                                         │
│ Activity                    Paused · Resume ↓  │
└────────────────────────────────────────────────┘
```

```css
.activity-panel-header {
  /* existing styles preserved */
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.follow-status {
  font-size: 10px;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 150ms;
}

.follow-status:hover {
  opacity: 1;
  color: var(--text-secondary);
}

.follow-status-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

.follow-status-dot.active {
  background: var(--accent-green, #22c55e);
}

.follow-status-dot.paused {
  background: var(--text-muted);
}
```

---

## 8. Accessibility

### ARIA Structure

```html
<!-- Activity panel landmark -->
<aside aria-label="Session activity" class="activity-panel">
  <div class="activity-panel-header" role="banner">
    Activity
    <button class="follow-status" aria-label="Scroll following is active. Click to pause.">
      Following · Pause
    </button>
  </div>

  <div class="activity-scroll" role="log" aria-label="Activity feed">
    <!-- Turn groups -->
    <div class="turn-group" role="group" aria-label="Turn 1: Refactor the auth module">
      <div class="turn-header"
           role="button"
           tabindex="0"
           aria-label="Turn 1: Refactor the auth module. Click to scroll to message.">
        ▸ "Refactor the auth module to..."
      </div>
      <!-- activity items -->
    </div>
  </div>
</aside>
```

### Keyboard Navigation

| Key | Context | Action |
|-----|---------|--------|
| Tab | Activity panel | Move focus between turn headers |
| Enter/Space | Turn header focused | Scroll main pane to corresponding message |
| Escape | Activity panel focused | Resume auto-follow |
| Arrow Up/Down | Turn header focused | Move to previous/next turn header |

### Screen Reader Announcements

- When auto-follow scrolls to a new turn: `aria-live="polite"` region announces `"Showing activities for: [truncated prompt]"`
- When follow pauses: announces `"Activity following paused"`
- When follow resumes: announces `"Activity following resumed"`

### Reduced Motion

All scroll animations use the browser's native `behavior: 'smooth'` which automatically respects `prefers-reduced-motion`. The highlight flash animations have explicit reduced-motion overrides (see CSS above).

---

## 9. Performance Considerations

### Turn Derivation
- Memoized with `useMemo` keyed on `chronoItems` reference
- O(n) single pass — negligible for any realistic conversation length
- Returns stable object references when items haven't changed

### IntersectionObserver for Dominant Turn
- One observer for all user message elements in the main pane
- Threshold: `[0, 0.5, 1.0]` with `rootMargin: "-20% 0px -20% 0px"`
- Callbacks are batched by the browser — no per-scroll-event cost
- Observer is disconnected/reconnected on session switch

### Scroll Handler
- Main pane scroll fires rAF-debounced dominant turn check
- Activity panel scroll fires rAF-debounced follow-pause detection
- No `setTimeout` debouncing needed

### DOM Considerations
- Turn groups add one wrapper `<div>` per turn — minimal DOM overhead
- Sticky headers use `position: sticky` (GPU-composited, no JS)
- Highlight animations use `background`/`box-shadow` (composited properties)
- Consider `content-visibility: auto` on turn groups for very long sessions (100+ turns)

---

## 10. State Model Summary

New state introduced in `ChatApp`:

```js
// Derived (memoized, not stored)
const { turns, itemTurnMap } = useMemo(
  () => deriveTurns(chronoItems),
  [chronoItems]
);

// Interactive state
const [followActive, setFollowActive] = useState(true);
const [dominantTurnIndex, setDominantTurnIndex] = useState(0);
const [hoveredTurnIndex, setHoveredTurnIndex] = useState(null);

// Refs (no re-renders)
const followActiveRef = useRef(true);
const lastScrolledTurnRef = useRef(0);
```

Passed to components:

| Prop | Passed to | Purpose |
|------|-----------|---------|
| `turns` | Activity panel `MessageList` | Grouping activities by turn |
| `itemTurnMap` | Both `MessageList` instances | Mapping items to turns |
| `dominantTurnIndex` | Activity panel | Which turn to auto-scroll to |
| `hoveredTurnIndex` | Both panels | Cross-highlight on hover |
| `followActive` | Activity panel header | Show follow state |
| `setHoveredTurnIndex` | Both panels | Hover callbacks |
| `onTurnHeaderClick` | Activity panel | Navigate main pane to message |
| `onMessageClick` | Main pane | Navigate activity panel to turn |

---

## 11. Visual Summary

```
┌──────────────────────────────┬──────────────────────────────┐
│ Main Pane                    │ Activity Panel               │
│                              │ ┌──────────────────────────┐ │
│ [user] "Fix the login..."   │ │ ▸ "Fix the login..."  3  │ │
│                              │ └──────────────────────────┘ │
│ [assistant] "I'll start     │   [thinking] Analyzing...     │
│  by examining the auth..."  │   [tool] read_file auth.py   │
│                              │   [token] 4,200              │
│                              │                              │
│ ╔══════════════════════════╗ │ ┌──────────────────────────┐ │
│ ║[user] "Now add rate      ║▸│ │ ▸ "Now add rate limit.." │ │
│ ║ limiting to the API"     ║ │ └──────────────────────────┘ │
│ ╚══════════════════════════╝ │   [thinking] Let me...       │
│                              │   [tool] read_file routes.py │
│ [assistant] "I'll add       │   [tool] edit_file routes.py  │
│  rate limiting using..."    │   [tool] bash — pytest        │
│                              │   [token] 12,450             │
│                              │                              │
│ [user] "Write tests for..." │ ┌──────────────────────────┐ │
│                              │ │ ● "Write tests for..."   │ │
│ [assistant] streaming...     │ └──────────────────────────┘ │
│                              │   [thinking] streaming...     │
│              ▼               │   [tool] read_file — running │
│                              │                     ▼        │
└──────────────────────────────┴──────────────────────────────┘

Legend:
  ╔══╗  = dominant turn (highlighted in main pane via cross-hover)
  ▸     = turn header with auto-follow arrow
  ●     = streaming turn indicator
  ▼     = auto-scroll anchor point
```

---

## 12. Implementation Sequence

Recommended order of implementation:

| # | Task | Depends on | Complexity |
|---|------|-----------|------------|
| 1 | `deriveTurns()` function + memoization | — | Low |
| 2 | Turn group wrapper in activity panel `MessageList` | 1 | Medium |
| 3 | Turn header component (static, no interaction) | 2 | Low |
| 4 | Sticky header CSS | 3 | Low |
| 5 | IntersectionObserver for dominant turn detection | 1 | Medium |
| 6 | Auto-follow scroll (main → activity) | 2, 5 | Medium |
| 7 | Follow pause/resume on activity panel scroll | 6 | Low |
| 8 | Follow indicator in activity panel header | 7 | Low |
| 9 | Click-to-navigate: message → activities | 2 | Low |
| 10 | Click-to-navigate: turn header → message | 2 | Low |
| 11 | Hover cross-highlight | 1 | Medium |
| 12 | Streaming turn handling (pulsing dot, live group) | 2, 6 | Medium |
| 13 | Empty turn handling | 2 | Low |
| 14 | ARIA labels and keyboard navigation | 3, 9, 10 | Medium |
| 15 | Performance optimization (content-visibility) | 2 | Low |

**Estimated total effort:** ~2-3 focused implementation sessions.

Tasks 1-4 are the foundation and can ship as a standalone improvement (turn grouping without scroll sync). Tasks 5-8 add the scroll correlation. Tasks 9-11 add navigation. Tasks 12-15 are polish.

---

## 13. What This Spec Does NOT Cover

Explicitly out of scope (different specialists own these):

- **Responsive behavior** — How the activity panel adapts on tablet/mobile. The responsive strategist should define whether the activity panel becomes a drawer, bottom sheet, or hidden entirely.
- **Design tokens** — The spacing values (6px, 8px, 24px) used here are working values. The design system architect should formalize these as tokens.
- **Component internals** — The turn header is described structurally, but its interactive states, icon choices, and visual polish are component design decisions.
- **Aesthetic direction** — Color choices for highlights, the exact accent color, and overall visual weight are art direction decisions.

---

## 14. Success Criteria

This design succeeds when:

- [ ] **Scrolling through conversation reveals corresponding activities** without manual hunting
- [ ] **Developers are never surprised by unexpected scroll jumps** — the follow behavior is predictable and pausable
- [ ] **Long sessions (50+ turns) remain navigable** — turn headers provide wayfinding
- [ ] **Streaming feels natural** — the current turn stays visible without fighting for scroll position
- [ ] **Click navigation is instant and clear** — clicking a message highlights its activities, clicking a turn header highlights its message
- [ ] **Keyboard users can navigate the correlation** — tab between turn headers, enter to cross-navigate
- [ ] **Performance is imperceptible** — no scroll jank, no layout thrash, no dropped frames