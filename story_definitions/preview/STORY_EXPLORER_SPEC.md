# Story Explorer — spec + hard-won know-how for regeneration

Bring this doc to a fresh session to rebuild `story_explorer.html` the same
or better. The generator is `scripts/build_story_explorer.py` in
jubu_datastore; it validates every story JSON, then splices data into an
embedded single-file HTML template. Output: `story_definitions/preview/story_explorer.html`
— zero dependencies, opens from disk, everything inline.

## What the current page is

A single-file interactive map of the story library for admin/R&D review
(not child-facing). Three ideas in one page:

1. **3D topic map** (left, full-bleed SVG, `viewBox="-575 -410 1150 820"`,
   pixel units). Categories sit on a Fibonacci-lattice sphere
   (`_sphere_points`), each category's deep-dive children on a smaller
   sphere around it. Simple perspective projection, drag-to-orbit (no
   auto-rotate — founder preference), pinch/wheel zoom. Nodes are
   front-facing discs, NOT shaded balls. Topics with stories are saturated;
   story-less topics render as pale open slots ("fog of war" — coverage is
   visible, absence is visible too.)
2. **Story panel** (right) with three tabs:
   - **Play** — walk the braid: read segments, tap the 2-option choices
     (character-asked, never narrator-asked), name-the-template-slot
     moments ("that is the name" button), say-word buttons.
   - **Why this story** — the full `build_record` rendered honestly:
     pattern candidates with weights and what was rejected, tone/teller
     choice reasons, branch design against the 5 criteria, gate findings,
     writers_notes, craft_notes, prompt version, `listener_felt_arc`.
     This tab is the point: every generation decision inspectable.
   - **Braid** — an SVG of the 6-segment braided river (s1 → c1 rejoins →
     s2a/s2b → s3 → c2 splits → s4a/s4b), with per-segment felt discs.
3. **Topic pills** (bottom strip) — every topic as a plain clickable chip,
   the always-works fallback when 3D hit-testing frustrates.

Styling follows the Buju brand guide (uploaded PDF, earlier session):
warm cream background, rounded cards, one saturated accent color per
category, friendly rounded sans. Colors are assigned per category and
inherited by children.

## Data contract

- Stories: `story_definitions/stories/pilot/*.json`. The generator runs
  `validate_story()` on each (structure, braid shape, choices, slots,
  build_record presence) and refuses to build on errors — the explorer
  doubles as the library's lint.
- Topics: read from `knowledge_graph_definitions/` via the graph loader;
  categories listed in `PILOT_CATEGORIES` (extend this list when new
  clusters land — the sphere layout handles any count automatically).
- Everything is spliced as one `const DATA = {...}` JSON blob. No fetch,
  no server.

## Know-how — every one of these was learned by breaking it

1. **No inline JS handlers, ever.** `onclick="..."` inside a Python
   template string died twice to quote-escaping (blank page,
   SyntaxError). Rule: elements carry `data-act="..."` (+ `data-story`,
   `data-topic`, ...) and ONE delegated listener on document does
   `ev.target.closest("[data-act]")` and dispatches. Zero backslash
   escapes anywhere in the template.
2. **No regex/`.replace()` splicing with user-ish text.** Template
   substitution is split/join on unique marker strings (`"__DATA__"`),
   because `.replace()` interprets `$` and regex fills tripped ruff W605.
3. **Verify the JS mechanically before shipping**: extract the `<script>`
   body to a temp file → `node --check`. Then a jsdom headless test that
   *renders the page and clicks things* (with small pointer jitter) and
   asserts the panel changed. jsdom test must `process.exit()` explicitly
   — `requestAnimationFrame` loops hang the process.
4. **Click-vs-drag on an orbiting canvas** is the hardest part:
   - Never `setPointerCapture` on the svg — it eats the clicks.
   - Track accumulated movement (`movedBy`); treat as click only if
     `movedBy <= CLICK_SLOP` where **CLICK_SLOP = 10px** (4px ate
     trackpad-jitter clicks).
   - Every floating overlay/label gets `pointer-events:none`
     (`.float`), with `.clickable` opting back in — invisible overlays
     silently intercepting clicks was a twice-reported "can't click
     topics" bug. Verify via jsdom *computed* styles.
   - Give every node an invisible hit circle ≥ ~22px regardless of
     visual radius.
   - Keep the topic pills as a non-3D fallback path to every topic.
5. **Pixel-based SVG, not unit viewBox.** A unit-scale viewBox with px
   stroke/font sizes produced the "weird triangles" first draft. Use a
   large pixel viewBox and real pixel sizes.
6. **Discs facing the viewer, no auto-rotate, drag-only orbit** — founder
   decisions after seeing alternatives. Keep them.
7. **The Why tab is not optional.** Rendering build_record raw-but-pretty
   is what made expert review and founder trust possible. Any regeneration
   must keep full decision provenance visible per story.
8. **Run it as `python scripts/build_story_explorer.py`** from repo root —
   never `python -m` (the repo's `logging/` package shadows stdlib logging
   when root is `sys.path[0]`), and never with a leaked `PYTHONPATH=.`.
9. **Privacy**: the page must never contain child names or account ids;
   template slots render as placeholders (`⟨the name you chose⟩`), and
   "naming" state lives only in-page in JS memory.

## Regeneration checklist for a fresh session

1. Read this doc + `STORY_CREATION_POLICY.md` (terms: segment, choice
   point, braid, pattern, teller, tone recipe, felt arc).
2. Read one story JSON fully (e.g. `stories/pilot/volcanoes.json`) —
   the template must render every field it actually has.
3. Keep the generator pattern: validate → build DATA → splice by
   split/join → write single HTML file.
4. Preserve: data-act delegation, CLICK_SLOP=10, pointer-events rules,
   hit circles, pills fallback, pixel viewBox, no auto-rotate, Why tab,
   felt-disc braid, pale open slots for story-less topics.
5. Verify: `node --check` on extracted script; jsdom click-through test;
   open in browser.

## Ideas for "better" (not yet built)

- Search/filter box (topic, pattern, tone, age).
- Age-band slider dimming topics without that band.
- A shelf view per topic showing pattern spread (are all volcano stories
  the same shape?).
- Read-aloud (TTS) on segments; felt-arc coloring along the Play path.
- Diff view: same topic across prompt versions (v1 archive exists at
  `stories/archive_v1/`).
