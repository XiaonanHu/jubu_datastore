# Handoff — update the parent-facing topic map

> **For:** a fresh Cowork session with no memory of prior work.
> **Written:** 2026-09-01. Facts verified against the repos on that date.
> **Target:** `buju_website/pilot/js/map.js` — the map real families use.
> **This ships to production.** Everything below assumes that.

---

## 0. What Buju is, in four sentences

Buju makes branching audio stories for children aged 3–12. A child listens; a
character asks a question; the child picks; the story branches. 144 stories
exist, 142 narrated. Underneath sits a **knowledge graph** of 263 topics that
says what a story can be about and how deep to go for a given age.

The company is mid-pivot toward a school product with SEL objectives and
on-screen read-along text. That work is elsewhere; **this task is the consumer
side** — the map parents browse.

---

## 1. What you are changing

`buju.ai/pilot` is gated: a parent enters the email they signed up with, and
middleware sets a signed `bj_pilot` cookie carrying their family id, age band
and chosen topics. Behind it, `pilot/stories.html` shows a **topic disc** — a
front-facing clustered map of similarity wedges (space → earth → water → life →
food → mind → arts → machines) with a gentle z-bulge for parallax.

| | |
|---|---|
| Renderer | `buju_website/pilot/js/map.js` (886 lines) |
| Story list / panel | `buju_website/pilot/js/stories.js` (1239 lines) |
| Page | `buju_website/pilot/stories.html` |
| Data | `buju_website/pilot/data/stories.json` (1.8 MB, generated) |
| Generator | `jubu_datastore/scripts/build_pilot_site.py` (466 lines) |
| Tests | `buju_website/tests/pilot/test_map.js` (jsdom) |

**Layout is computed in Python, not JavaScript.** `build_pilot_site.py`
pre-computes every node's x/y/z from `PARENT_MAP_GROUPS` and writes them into
`stories.json`. `map.js` renders those positions and applies a clamped rotation
wobble. If you want to move things around the disc, edit the Python.

**There is a second, separate map** — an internal R&D explorer with a different
codebase (`build_story_explorer.py` → a 3.1 MB local HTML file, plus a deployed
copy at `buju.ai/pilot/explorer` behind Basic Auth). **Do not confuse them.**
Nothing in this task touches it. But see §6: the two builders are coupled, and
you cannot delete one without breaking the other.

---

## 2. What the map already does — learn this before changing it

The map is not naive. Four systems already run, and the requested changes have
to fit between them rather than on top of them.

**Personalization tiers** (`computeTiers`). Every node gets one of four:

- `fam` — a topic this family chose at signup. Glows, carries a ring, is listed
  in the side panel, and its label is never dropped by the declutterer.
- `near` — one edge or one parent/child step from a family topic. Full colour.
- `far` — everything else that has stories. Dimmed.
- `soon` — no stories written yet.

**Age-band visibility** (`refreshBandFlags`). Re-run whenever the band changes:

| Node | Shown as |
|---|---|
| Written, in band | Bright |
| Written, out of band, family's own | Faint, with a "please generate it" ask |
| Written, out of band, not theirs | **Hidden** |
| Never written, one step from a written topic | Faint dashed |
| Never written, far from everything | **Hidden** |

**Coverage pruning** (`computeNearGenerated`). A never-written topic earns a
spot only if it sits one step from a topic that has stories — otherwise the map
drowns in empty dots.

**Per-band availability** (`bandStats`). For the selected band it already counts
`total`, `voiced`, and `lang` (stories carrying the family's narration
language), and renders them as badges in the guide panel.

**Two themes.** `dark` (deep-ink sky) and `light` (cream page). The parent picks
and the choice is remembered. Any new visual state **must be defined in both**
— they are separate objects in `THEMES`, and a colour defined in only one is a
bug that ships looking fine on your machine.

Colour is assigned by hashing the node's **category root**, so a branch reads as
one family. Six accents per theme.

---

## 3. Change 1 — coverage and status, honestly

This is the change that needs a decision before any code, because **half of it
should not ship to parents at all.**

**The measured facts.** All 263 graph nodes and all 144 stories are
`status: draft`. Zero have been human-reviewed. The review workflow is real and
enforced in code — `published` is refused without a named `reviewed_by` — but it
has never been run.

**The conflict.** On the internal explorer, rendering "draft" is honesty. On the
parent map it is a warning label on the story a parent is about to play for
their child. Same field, opposite meaning. Do not port the internal treatment
across.

**What is shippable today, and genuinely honest:**

1. **Voiced vs unvoiced.** 142 of 144 stories are narrated. A topic whose only
   in-band story is unvoiced currently looks available and is not playable.
   `bandStats` already computes `voiced` — surfacing it on the node itself, not
   just in the panel badge, is real and costs nothing.
2. **Sharpen the existing three-way coverage** — has stories in your band / has
   stories in another band / not written yet. The data is there; the disc
   currently leans on dimming, which is easy to miss on a phone in daylight.
3. **"New since you were last here."** Honest, useful, and it makes a growing
   library feel like it is growing.

**What to raise with the founder rather than decide alone:** if review status
should appear at all, it belongs as an *earned positive mark* — "an educator has
reviewed this" — never as a deficiency marker on everything else. Note that
today this renders on nothing, so the feature would ship invisible and stay
invisible until review actually happens. That may be the right build order, or
it may be work better done after the first review pass. Ask.

---

## 4. Change 2 — region narrative and the recurring cast

**Read `jubu_datastore/docs/STORY_WORLD.md` first.** It is the design document
and it stands alone.

Two hard facts to absorb before planning anything.

**(a) The cast does not exist as data.** `STORY_WORLD.md` designs ~7 recurring
characters, two residents per region, defined by their range from instinct to
reflection. Nobody has authored them. There is no `cast` field in the story
schema and no `world_definitions/` directory. All 144 stories carry
`build_record.cast`, but that is a different thing — per-story roles the
generator invented, with reasoning (`{"role": "Mama Duck", "reused": false,
"why": "..."}`), no visual detail, not shared between stories.

**(b) The map's groups are not the graph's regions.** This will bite you.

- The graph has a `region` field on `knowledge_domain` nodes: **10 distinct
  values** — `animals` (42), `nature_and_earth` (25), `how_things_work` (21),
  `space` (18), `arts_and_music` (18), `people_and_places` (13),
  `numbers_and_patterns` (11), `long_ago` (9), `plants_and_life` (8),
  `human_body` (8). `story_element` has its own 6. `sel_theme` and
  `value_lesson` have **none**.
- The parent map does not use that field. It groups by `PARENT_MAP_GROUPS`, a
  hand-written list of **8 similarity groups** in `build_pilot_site.py`, chosen
  so neighbouring wedges feel related.

So "show the region narrative" is ambiguous in the data as it stands. Adopting
the graph's 10 regions would relayout the entire disc and change what parents
see. Narrativizing the existing 8 wedges keeps the layout but means the map's
regions and the graph's regions stay permanently different things. **This is a
founder decision, not an implementation detail.**

*(Note: the master doc's §0 says "16 map regions". The measured value today is
10 on `knowledge_domain`. Flag it — the master doc marks these facts
`[GENERATED]`, meaning read them off the system rather than trusting the prose.)*

**Suggested order:** decide the grouping question, author the cast into the
graph where the story generator can also read it, then display. Building the
display first against a stub is defensible — it makes the missing data concrete
— but inventing seven characters inside the renderer is not.

---

## 5. Rules you must not rediscover the hard way

These were all learned by breaking something in production.

1. **CSP is `script-src 'self'`.** No inline `<script>`, no `onclick="..."`,
   ever. Elements carry `data-act="..."` and one delegated listener on
   `document` does `ev.target.closest("[data-act]")`. A page with an inline
   handler is a *silently dead* page — styled, and nothing works. This exact
   failure shipped twice. The full policy is in `vercel.json`; `connect-src`
   allows only `'self'`, formspree and `storage.googleapis.com`.
2. **Click-vs-drag on an orbiting canvas is the hardest part.** Never
   `setPointerCapture` on the SVG — it eats clicks. `CLICK_SLOP = 10px`
   accumulated movement (4px ate trackpad jitter). Every node needs an
   invisible hit circle ≥22px regardless of drawn radius. Every floating
   overlay is `pointer-events:none` unless explicitly `.clickable` — invisible
   overlays intercepting clicks was a twice-reported "can't tap topics" bug.
3. **Pixel viewBox** (`-430 -340 860 680`), real pixel sizes. A unit-scale
   viewBox with px strokes produced a broken first draft.
4. **Front-facing discs, drag-only rotation, no auto-rotate.** Founder
   decisions made after seeing the alternatives. The rotation is a *clamped*
   parallax wobble — the disc leans but never turns edge-on, so nothing ever
   hides. Keep that clamp.
5. **Auto-fit re-frames on band change only**, never mid-drag, so dragging
   stays calm. Usable area is `FIT_W 690 × FIT_H 560` inside the viewBox —
   deliberately generous, because rim labels sit beside their nodes and must
   not clip.
6. **Define every new colour in both themes.**
7. **Privacy.** The page must never contain a child's name or account id. Any
   name a family chooses lives in browser memory only. The gate copy promises
   this explicitly — it is a commitment, not a preference.
8. **Splice with split/join on unique markers, never regex or `.replace()`.**
   `.replace()` interprets `$`. Three silent failures in this project so far.

---

## 6. Build, test, and the coupling that will surprise you

```bash
cd jubu_datastore
python scripts/build_pilot_site.py          # regenerates stories.json + layout
cd ../buju_website
node tests/pilot/test_map.js                # jsdom: tiers, orientation, voting
```

Run scripts **from the repo root as scripts** — never `python -m`, never
`PYTHONPATH=.`. The datastore has a `logging/` subpackage that shadows stdlib
`logging` when the root lands on `sys.path[0]`.

**The coupling.** `build_pilot_site.py` imports `build_story_explorer` and calls
`bse.main()`, `bse.load_stories()`, `bse.load_default_registry()` and
`bse.build_explorer_data()`. The explorer script is not just a viewer — it holds
the **story loader and validator** the whole pipeline runs on
(`generate_story_audio.py` imports it too). Building the parent map *runs the
explorer build first*.

There is also a hard consistency check: every category in
`bse.PILOT_CATEGORIES` must appear exactly once in `PARENT_MAP_GROUPS`, or the
build exits with a `SystemExit` naming what drifted. If you add a topic
category, edit both lists.

**Verify before claiming it works.** The jsdom test must call `process.exit()`
explicitly or `requestAnimationFrame` hangs it. Check computed
`pointer-events` styles, not just the markup — that is how the click-eating
overlay bug was finally caught.

---

## 7. Working on the founder's machine

Repos are at `~/mnt/{jubu_datastore,jubu_backend,buju_website}` through the
device bridge.

- `device_bash` **cannot delete files.** `rm`/`rmdir`/`unlink` fail with
  "Operation not permitted". Move unwanted files into a `_to_delete/` folder
  and tell the founder.
- **Never run `git add` through the device bridge.** It leaves an undeletable
  `.git/index.lock` and orphan `tmp_obj_*` files. Hand the founder the git
  commands instead.
- **`BUJU_EVAL_PW` is missing from Vercel**, so the middleware's hardcoded
  fallback `"123456"` is what currently guards `/pilot/explorer`, `/eval`,
  `/grading` and `/pilot-courses` in production. Unrelated to this task, but
  worth not being surprised by.

---

## 8. Open questions for the founder

1. Should review status appear to parents at all? (§3 — my read is no, and that
   the useful honest signal is *what is ready to listen to right now*.)
2. Regions: relayout the disc to the graph's 10 regions, or narrativize the
   existing 8 wedges? (§4b)
3. Cast first, or the display against a stub first? (§4a)
4. `sel_theme` and `value_lesson` — 46 nodes — are invisible on every map that
   exists, and the school product is built on them. Out of scope here, but it
   is the largest structural gap in the visualization layer.
