# scripts/

What each script is for, and which one you actually run.

Every script here is run **from the repo root, as a script**:

```bash
python scripts/<name>.py
```

Never `python -m scripts.<name>`, never with `PYTHONPATH=.`. The package
has a `logging/` subpackage that shadows stdlib `logging` when the repo
root lands on `sys.path[0]`.

---

## The pilot story pipeline, in order

```
   generate            ingest              build                publish
jubu_backend  ->  stories/pilot/  ->  preview/pilot_site/  ->  buju_website + GCS
```

| # | Step | Command | Lives in |
|---|---|---|---|
| 1 | Write stories | `story_review/generate_stories.py` (bench) or `build_story.py` | **jubu_backend** |
| 2 | Promote keepers into the library | `ingest_pilot_stories.py` | here |
| 3 | Narrate the approved ones | `generate_story_audio.py` | here |
| 4 | Ship everything | `publish_pilot_audio.py` | here |

Steps 2 and 4 are the only ones with side effects outside this repo.

---

## Entry points — things you run by hand

### `ingest_pilot_stories.py`
Promotes a generation run into the library. Takes the raw output of
`_demo_run_*` directories in jubu_backend and writes library-form stories
into `story_definitions/stories/pilot/`.

```bash
python scripts/ingest_pilot_stories.py --source ../jubu_backend/_demo_run_kid1 --dry-run
```

Per story it unwraps the bench envelope, skips anything the craft gate
blocked, prunes orphaned naming slots (a declared-but-unused slot is a
*fatal* validation error, so this is not cosmetic), mints a
collision-checked 6-hex token, rewrites the id, appends `depth` and
`build_record.library_ingest`, then re-gates what it wrote.

Use `--only <substring>` when a source directory holds files from more
than one run — output directories accumulate, and sweeping in stories
from an older run at the wrong age band is the easy mistake here.

### `generate_story_audio.py`
Narrates stories through Cartesia. One clip = one prose paragraph.
Needs `CARTESIA_API_KEY` (environment, or jubu_backend's `.env`).

```bash
python scripts/generate_story_audio.py --stories <id substring> [<id substring>…]
python scripts/generate_story_audio.py --all          # deliberately separate: cost
```

`--stories` matches on story **id** substring. The 6-hex suffix is unique
across the library, so use that — several topics have two stories at the
same age band, and a bare topic name will voice both.

Idempotent; `--force` regenerates. Clips land in
`story_definitions/preview/pilot_audio/` (gitignored). **Listen before
publishing** — that is the quality gate, and it is why generation and
publishing are two commands.

Also: `--audition <voice_id>…`, `--diagnose`, `--pause-test` for tuning
by ear. Anything in `audio_voices.json` is baked into the mp3s, so
changing it means regenerating with `--force`.

### `publish_pilot_audio.py`
**The one command that ships.** Despite the name it publishes the whole
pilot, not just audio.

```bash
python scripts/publish_pilot_audio.py -m "commit message"
```

In order: upload clips to `gs://buju-pilot-audio` → rebuild `pilot_site`
→ verify every clip `stories.json` references actually exists in the
bucket → copy `stories.json` + explorer into buju_website → run the
website's pilot test suites → commit and push both repos.

The order is the point: clips reach the bucket *before* the data that
points at them is deployed, so a family can never open a story whose
audio isn't there. The bucket-coverage check is what prevents "Listen
buttons but silence."

Flags: `--dry-run`, `--no-push`, `--skip-tests`, `--website <path>`.

### `audit_story_craft.py`
Reads the library and reports craft findings. Two things BLOCK — a
segment over its age band's word ceiling, and banned evaluation language.
Everything else warns for human eyes.

```bash
python scripts/audit_story_craft.py            # whole library
python scripts/audit_story_craft.py --story bees --verbose
```

### `verify_knowledge_graph.py`, `verify_migrations.py`
CI gates for the knowledge-graph YAML packs and the Alembic migration
history. Run by CI; run them by hand before touching either.

### `build_review_packet.py`
One-off: builds the print-ready packet for the expert story reviewer.

---

## Builders — usually called for you

### `build_story_explorer.py`
The **validator** plus the admin explorer. Its `validate_story()` is the
definition of a valid story; `--check` is the gate everything else trusts.

```bash
python scripts/build_story_explorer.py --check     # expect: OK: N stories valid
```

Holds `PILOT_CATEGORIES` — the topics that appear on the map. Deep dives
ride along automatically under their parent (`registry.children_of`), so
a `tier: deep_dive` topic with a `subtopic_of` already in the list does
**not** need adding.

### `build_pilot_site.py`
Builds the parent-facing data — `stories.json`, map positions, audio
stamps — into `story_definitions/preview/pilot_site/`. Calls the explorer
builder first.

Holds `PARENT_MAP_GROUPS`, which must contain **exactly** the same topic
set as `PILOT_CATEGORIES` or the build exits with "out of sync". Change
the two together, in the same commit.

### `story_audio_chunks.py`
Library, not a command. Paragraph chunking + slot substitution. This
split is implemented three times — here, in the player
(`buju_website/pilot/js/stories.js`), and in
`buju_website/api/pilot-name-audio.js` — and all three MUST stay in sync
or clip indices drift between the mp3s and what the player requests.

---

## Things that have bitten us

- **Two ceilings, two files.** The generation ceiling lives in
  jubu_backend's `configs/story_generation.yaml`; the audit's copy lives
  in `audit_story_craft.py`. A new age band needs both, plus an entry in
  `story_definitions/audio_voices.json`, plus `BANDS` in the pilot's
  `stories.js` and a stop on the slider in `stories.html`.
- **The audio staleness check compares chunk *counts*, not text.** Edit a
  story's wording without changing its paragraph count and
  `build_pilot_site.py` will happily stamp the old audio onto the new
  prose. After editing a voiced story, regenerate it with `--force`.
  (`audio_manifest.json`'s per-chunk `chars` include the baked-in SSML
  break tags, so don't compare those against raw prose — compare
  timestamps.)
- **`publish_pilot_audio.py` writes files into buju_website after your
  last commit there.** If you run it and then push buju_website from an
  earlier shell, you ship stale `stories.json`. Let the script do the
  commit.
- **Deleting story files is a two-repo operation.** Stories live here;
  the site data derived from them lives in buju_website. Rebuild and
  republish, don't hand-edit `pilot/data/stories.json`.
