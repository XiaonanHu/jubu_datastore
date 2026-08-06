# Pilot stories → cloud: handoff for the next session

**Goal of the next session:** get the pilot story library live in the cloud
and viewable as HTML (the parent-facing `buju.ai/pilot` review experience),
deployed via jubu-deploy. Voice conversion (Cartesia) and the final
parent-facing webpage are explicitly a *later* session — this handoff stops at
"text stories exist in the cloud and render."

**Ordering decision (settled):** push the **text** library to the cloud and
get it rendering **first**; generate voice **second**, only for the stories
that survive review. Voice is the expensive, perishable layer — every Cartesia
clip is invalidated by any wording edit, and there are ~6 segments × 2 paths per
story. Lock the text, let parents read/curate, then voice the keepers. Audio is
additive (files keyed by `story_id` + `segment_id`); doing text-first never
blocks the voice stage.

---

## State at handoff (what this session finished)

- **Pilot library is 86/86 valid** against `scripts/build_story_explorer.py`'s
  `validate_story()` — the same check that gates the HTML build. 24 hand-authored
  pilots + **62 pregenerated stories** (35 age-9 boy topics, 27 age-8 girl topics),
  generator = Kimi K3.
- **Naming scheme adopted:** `{topic}__age{band}__d{n}__pregen__{hash6}.json`
  (the depth token replaces the old pattern token). Example:
  `mars__age9to10__d1__pregen__a9231e.json`. All current stories are the first/only
  story on their topic, so they are all `d1`. A future "deeper on the same topic"
  story is `..__d2__..`, `..__d3__..`.
- **`depth` is now a first-class field** in each story record (`"depth": 1`) and
  mirrored in `build_record.library_ingest.depth` — group "same topic, deeper"
  by `topic` + `depth`, never by parsing the filename.
- **Universal library confirmed:** no story→child wiring anywhere. Every
  pregenerated story is accessible to every kid; the child profile only steers
  what gets generated/surfaced, never a stored link.
- **Two fixes landed this session that the library depended on:**
  1. *Slot contract.* The pilot validator requires every declared slot to appear
     as a `{token}` in the prose. The generator was declaring "playthrough" slots
     whose name it baked into the sentence, leaving them declared-but-unused.
     - Ingested files: 41 of 62 had orphaned slots pruned (declared == used now).
     - **Pipeline root-cause fixed** in `jubu_chat/story_generation/story_builder.py`
       (`_assemble`): it now prunes `slots` to exactly the tokens the prose uses and
       scrubs `sets_slots` to match, so future generations satisfy the contract
       automatically.
  2. *Banned display language.* `jubu_datastore/knowledge_graph/graph_validator.py`
     `BANNED_LANGUAGE_PATTERNS` was hard-failing `ahead of` / `...behind` in visible
     text — but those are almost always literal in a story ("the boat ahead of us").
     Removed both patterns to match the craft-gate decision already made in
     `craft_gate.py`. Still hard-blocked: `assessment`, `mastery`, `score`,
     `milestone`, `your child`, `delayed`, `gifted`, `grade level`.

---

## What the next session needs to start

1. **Connect the `jubu-deploy` repo** (or its runbook). It is not in `jubu_backend`
   or `jubu_datastore` — neither repo has any deploy config beyond a bare Dockerfile
   (`CMD python -m jubu_chat`) and `cd.yml` is empty. The one open question that
   decides the whole path:
   **Is `buju.ai/pilot` served by the backend's `api_server`, or is it a static
   `story_explorer.html` pushed to a bucket/CDN?**
   - If backend-served: the flow is *commit `jubu_datastore` → redeploy the backend*
     (the backend pip-installs `jubu_datastore`, so the pilot JSON ships inside it).
   - If static: the flow is *build `story_explorer.html` → upload the artifact*.
   jubu-deploy answers this.

2. **Commit + push both repos** (see the git plan below) so the pilot JSON is in
   version control — right now the entire `story_definitions/` tree is untracked.

---

## Building / viewing the explorer HTML (from `STORY_EXPLORER_SPEC.md`)

The generator already exists: `jubu_datastore/scripts/build_story_explorer.py`.

- Validate only: `python scripts/build_story_explorer.py --check` → expect
  `OK: 86 stories valid`.
- Build: `python scripts/build_story_explorer.py` → writes
  `story_definitions/preview/story_explorer.html` (zero-dependency single file).
- Run it **from the datastore repo root as `python scripts/...`** — never `python -m`
  and never with `PYTHONPATH=.` (the repo's `logging/` package shadows stdlib).
  It imports `jubu_datastore.*`, so the datastore package must be installed in the
  env (`pip install -e .`) — use the same venv the generation runs used.
- Verify before shipping: `node --check` on the extracted `<script>`, then the jsdom
  click-through test (details in `STORY_EXPLORER_SPEC.md`).

Note: the current `preview/story_explorer.html` on disk is **stale** (built before
this session's cleanup + renames). Rebuild it in the next session.

The explorer is the admin/R&D view. The parent-facing `buju.ai/pilot` page is a
separate build — but the explorer's validated `const DATA` blob and its Play-tab
braid walker are the reference for what the parent page renders.

---

## Voice stage (later session — plumbing is ready, no action now)

`jubu_backend/speech_services/text_to_speech/` already has Cartesia wired:
`CartesiaSpeaker`, model `sonic-3`, a chosen Buju child voice id, behind the same
`TTSService` / `TTSFactory` interface as the old ElevenLabs path, entry point
`text_to_speech()`. Voice conversion is: iterate segments → Cartesia → store audio
keyed by `story_id` + `segment_id` (per-segment so the branching choices work).
Do this only for review-approved stories.
