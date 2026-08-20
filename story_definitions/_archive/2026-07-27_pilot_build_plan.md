# Story Pilot Build Plan — the interactive explorer

> **Kind:** handoff · **Status:** ARCHIVED 2026-08-17 — executed.
> The story JSON schema in Step 1 was the only home for that material and has
> been moved to `../STORY_SCHEMA.md`, which is now authoritative. Kept for the
> record of the original twelve hand-authored pilots.

**Goal.** A single self-contained webpage where you can see a subset of the
knowledge graph (10+ topics), click a topic, see its stories, and *play*
one — reading segment by segment, making the choices, naming the
characters, and walking different paths of the braid.

**What this is and is not.** This is the fastest honest vertical slice of
the two master docs (`STORY_CREATION_POLICY.md`,
`STORY_GENERATION_WORKFLOW.md`): real branching stories in a real schema,
validated, explorable. It deliberately does **not** build the staged
pipeline yet — the pilot stories are authored directly (the way the graph
packs were), following the policy's rules by hand. The pipeline comes
after, and these stories become its first comparison set.

---

## Step 1 — Freeze the pilot story format (JSON, one file per story)

A story is a braid the player can walk. Minimal schema:

```json
{
  "id": "story.volcanoes.journey_001",
  "title": "The Mountain That Breathes",
  "age_band": "5-6",
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
    {"id": "s1",  "text": "...",  "next": {"kind": "choice",  "id": "c1"}},
    {"id": "s2a", "text": "...",  "next": {"kind": "segment", "id": "s3"}},
    {"id": "s2b", "text": "...",  "next": {"kind": "segment", "id": "s3"}},
    {"id": "s3",  "text": "... {companion_name} ...",
                  "next": {"kind": "choice",  "id": "c2"}},
    {"id": "s4a", "text": "...",  "next": null},
    {"id": "s4b", "text": "...",  "next": null}
  ],
  "choice_points": [
    {"id": "c1", "rejoins": true,  "question": "...",
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
  "status": "draft"
}
```

Shape for age 5-6 (the pilot band): 6 segments, 2 choice points — the
first rejoins (both branches meet again at `s3`), the final one splits
(two real endings). ~700 words per path, so ~150-200 words per segment.

## Step 2 — Pick the topic subset

Twelve kid-favorite topics that already exist in the graph, with patterns
spread across the shelf on purpose (never all problem-stories):

| Topic | Pattern | Teller |
|---|---|---|
| volcanoes | journey | we_adventure |
| planets | journey | we_adventure |
| ocean_animals | journey | we_adventure |
| the_moon | quiet_hour | storyteller_tale |
| birds | quiet_hour | storyteller_tale |
| dinosaurs | mystery | named_hero (child names the explorer) |
| magnets | mystery | we_adventure |
| robots | problem_and_fix | we_adventure |
| whales_and_dolphins | problem_and_fix | we_adventure |
| insects | make_and_build | we_adventure |
| rainforests | romp | we_adventure |
| weather | romp | we_adventure |

## Step 3 — Author the stories

One story per topic, written against the policy digest: speakable short
sentences (heard, not read); feelings shown, plainly nameable at this age
when paired with behavior; both endings warm, no cliffhangers; no fake
choices (options differ in kind, distinct say-words); the topic's per-age
framing, vocabulary, and avoid list respected (read from its YAML pack);
`character_want`/`dramatic_tension` alive in every segment; one spine.
Files land in `story_definitions/stories/pilot/<topic_label>.json`.

## Step 4 — Validate

`python scripts/build_story_explorer.py --check` walks every story:
ids unique and all references resolve; exactly two options per choice;
first choice rejoins, final splits; exactly two endings, both reachable;
every declared slot used, every used slot declared, ≤5 slots; say-words
distinct within each choice; banned evaluation language absent; topic ids
exist in the graph. Fix until clean.

## Step 5 — Build the explorer page

The same script (without `--check`) emits a self-contained
`story_definitions/preview/story_explorer.html`: the topic subset drawn as
a small map (with their real adjacency edges), each topic showing its
story shelf; clicking a story opens the player — name-the-character
prompt for `ask_child` naming slots, segment text, choices as the spoken
question plus two say-word buttons (and a type-what-you'd-say box that
matches loosely, standing in for the voice pipeline), warm ending screen
with the path recap and "play again, choose differently".

## Step 6 — Review

Play every story both ways. Check: do the two branches genuinely differ;
does the rejoined segment read correctly for both; do the endings land
warm; would a five-year-old follow it read aloud? Notes go back into the
story JSONs (they are `status: draft` content like everything else).

## After tonight

These twelve stories become fixtures: the pipeline (workflow doc), once
built, must produce stories at least this good — and the evaluation
harness compares its output against them, blind.
