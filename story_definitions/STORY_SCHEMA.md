# Story schema — the shape of a story file

> **Kind:** policy
> **Status:** live · created 2026-08-17
> **Owns:** the on-disk shape of a story — braid structure, JSON fields, file
> naming, and the validation contract. Nothing else defines these.

This file was assembled from two documents that were the *only* homes for this
material and are both now retired: `_archive/2026-07-27_pilot_build_plan.md`
(Step 1, the JSON) and `../story_generation/prompts/_archive/segment_writing_v1.md`
(the braid spec). If you change the shape of a story, change it here first.

Related, and deliberately not repeated here:

| What | Where |
|---|---|
| What makes a story *good* | `STORY_CREATION_POLICY.md` |
| How a story gets built, stage by stage | `STORY_GENERATION_WORKFLOW.md` |
| The prose rules the writer obeys | `../story_generation/prompts/segment_writing_v2.md` |
| Per-band ceilings and choice-point counts | `jubu_backend/jubu_chat/configs/story_generation.yaml` |
| The executable form of everything below | `scripts/build_story_explorer.py` → `validate_story()` |

---

## 1. The braid

The shipped braid is **six segments and two choice points**:

```
s1 ──▶ c1 (REJOINS) ──┬──▶ s2a ──┐
                      └──▶ s2b ──┴──▶ s3 ──▶ c2 (SPLITS) ──┬──▶ s4a
                                                           └──▶ s4b
```

- `s1` is the trunk. Both branches out of `c1` rejoin at the shared middle `s3`.
- `s3` must read correctly after **both** `s2a` and `s2b`. This is the single
  most-violated rule and the one both review rubrics check first.
- `c2` is the final choice and always splits: two real endings, both reachable,
  both warm and fully resolved.
- The two paths are therefore `s1 → s2a → s3 → s4a` and `s1 → s2b → s3 → s4b`.

**Known divergence — read this before adding a band.** Six segments matches the
5-6 band's `choice_points: 2`. `story_generation.yaml` declares
`choice_points: 3` for 7-8, 9-10 and 11-12, but the braid shape is **not yet
parameterised** — every story in the library, at every band, is the six-segment
two-choice shape above. Config and reality disagree, deliberately and knowingly.
Parameterising the braid is the open work; until then, treat the config's
`choice_points` as intent, not as what the pipeline emits.

## 2. The JSON

One file per story. Minimal complete example:

```json
{
  "id": "story.volcanoes.journey_001",
  "title": "The Mountain That Breathes",
  "age_band": "5-6",
  "depth": 1,
  "topics": {
    "knowledge_domain": "knowledge_domain.volcanoes",
    "sel_theme": null, "value_lesson": null, "story_element": null,
    "secondary": []
  },
  "pattern": "journey",
  "teller": "we_adventure",
  "tone": {"dominant": "curious_wonder", "accent": "silly"},
  "spine": "what is around the next bend inside the mountain",
  "slots": {
    "companion_name": {"role": "the lava-lizard guide",
                       "kind": "naming", "ask_child": true,
                       "default": "Ember"}
  },
  "start_segment": "s1",
  "segments": [
    {"id": "s1",  "text": "...", "next": {"kind": "choice",  "id": "c1"}},
    {"id": "s2a", "text": "...", "next": {"kind": "segment", "id": "s3"}},
    {"id": "s2b", "text": "...", "next": {"kind": "segment", "id": "s3"}},
    {"id": "s3",  "text": "... {companion_name} ...",
                  "next": {"kind": "choice",  "id": "c2"}},
    {"id": "s4a", "text": "...", "next": null},
    {"id": "s4b", "text": "...", "next": null}
  ],
  "choice_points": [
    {"id": "c1", "rejoins": true, "question": "...",
     "options": [
       {"say_word": "crab",  "label": "Follow the glowing crab",
        "tone_lean": "bold", "curiosity_lean": "just_experience",
        "next_segment": "s2a", "sets_slots": {}},
       {"say_word": "climb", "label": "Climb up to see farther",
        "tone_lean": "gentle", "curiosity_lean": "how_it_works",
        "next_segment": "s2b", "sets_slots": {}}
     ]},
    {"id": "c2", "rejoins": false, "question": "...", "options": ["..."]}
  ],
  "status": "draft",
  "build_record": {"...": "every decision, as codes — see WORKFLOW Stage 7"}
}
```

### Field notes

- **`depth`** is first-class and mirrored at `build_record.library_ingest.depth`.
  Group "same topic, deeper" by `topic` + `depth` — **never** by parsing the
  filename. All current stories are the first on their topic, so all are `d1`.
- **`slots`** are capped at five per story, in two kinds: *naming* slots
  (`ask_child: true`, the child names something) and *playthrough* slots (set by
  a choice via `sets_slots`). Every declared slot must appear as a `{token}` in
  prose and every `{token}` in prose must be declared — a declared-but-unused
  slot is a **fatal** validation error, not a cosmetic one.
- **`say_word`** is one short concrete noun or verb the child can echo. The two
  say-words within a choice must not sound alike.
- **`tone_lean` / `curiosity_lean`** are recorded per option, never shown.
- **`status`** is `draft` until reviewed.

## 3. File naming

```
{topic}__age{band}__d{n}__pregen__{hash6}.json
```

e.g. `mars__age9to10__d1__pregen__a9231e.json`. The `hash6` is a
collision-checked 6-hex token, unique across the library — use it, not the topic
name, when addressing a single story (several topics have two stories at the
same band). Minted by `scripts/ingest_pilot_stories.py`.

## 4. What `validate_story()` enforces

`python scripts/build_story_explorer.py --check` is the gate everything else
trusts. It walks every story and requires:

1. Segment and choice ids unique; every reference resolves.
2. Exactly two options per choice point.
3. The first choice rejoins; the final choice splits.
4. Exactly two endings, both reachable.
5. Every declared slot used, every used slot declared, at most five slots.
6. Say-words distinct within each choice.
7. No banned evaluation language in visible text (see §5).
8. Every topic id exists in the knowledge graph.
9. `build_record` present.

Expected output: `OK: N stories valid`. Run it from the repo root as
`python scripts/build_story_explorer.py` — never `python -m`, never with
`PYTHONPATH=.` (the repo's `logging/` package shadows stdlib logging when the
root lands on `sys.path[0]`).

## 5. Banned evaluation language — one owner

The enumerated list lives in **code**, not prose, and there are two copies that
must agree:

- `jubu_backend/jubu_chat/story_generation/craft_gate.py` → `BANNED_EVALUATION`
- `jubu_datastore/scripts/audit_story_craft.py` → `BANNED_EVALUATION`

Currently blocking: `assessment`, `mastery`, `milestone(s)`, `delayed`,
`gifted`, `grade level`. The graph validator
(`knowledge_graph/graph_validator.py`) adds `your child` for parent-facing
display text.

Only warning, deliberately: `ahead of`, `behind` and their variants — almost
always literal in a story ("the boat ahead of us") and the single biggest source
of spurious blocks. `score` was dropped in 2026-08 for the same reason (it
caught game scores in story prose).

Any prose document that needs this list should link here rather than copy it.

## 6. Age bands

Per-band ceilings live in `jubu_backend/jubu_chat/configs/story_generation.yaml`
and are the only authority. As of 2026-08 the bands are `3-4`, `5-6`, `7-8`,
`9-10`, `11-12`; the config value is a **per-segment word ceiling**, which is a
different number from the per-path word budget quoted in
`STORY_CREATION_POLICY.md` §4 and the writing prompt §2. Do not confuse them,
and do not copy either number into a third file.
