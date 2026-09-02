# SEL Course Track — the 2B product

> **Kind:** plan
> **Status:** v2, 2026-08-20 · first story built and deployed · decisions marked **Decided**
> **Owns:** how the school product differs from the consumer one, and what a
> course story has to satisfy.

---

## Part 0 — Context you need (read this if you're new)

*Nothing here is a proposal. It exists so the document stands alone.*

**Buju** makes branching audio stories for children aged 3–12. 144 exist, 142
narrated. A child listens; a character asks a question; the child picks.

**Two products, one engine.**

| | **2C — the library** | **2B — courses** |
|---|---|---|
| Who buys | Parents | Schools and teachers |
| Where | `buju.ai/pilot`, email-gated per family | `buju.ai/pilot-courses`, Basic Auth |
| Purpose | A story need not teach | One SEL objective per story |
| Text on screen | No — audio only | Yes — read-along with a word cursor |
| Language rules | Guidance, warns only | Enforced per band |
| After the story | Nothing | Three questions |
| Status | 144 stories live | 1 story live |

**The knowledge graph** maps what stories are about: 263 topics on four axes —
`knowledge_domain` (173: volcanoes, bridges, the brain), `story_element` (44:
dragons, pirates), `sel_theme` (27: frustration, jealousy, being left out),
`value_lesson` (19: honesty, fairness). Every topic has a treatment written per
year of age: a framing sentence, vocabulary, and things to avoid.

**A story** is six segments and two choice points:

```
s1 ──▶ choice 1 (rejoins) ──┬──▶ s2a ──┐
                            └──▶ s2b ──┴──▶ s3 ──▶ choice 2 (splits) ──┬──▶ s4a
                                                                       └──▶ s4b
```

Both branches from the first choice rejoin at `s3`, so **`s3` is the only segment
every reader crosses.** The second choice splits into two endings. This matters a
lot below.

**The library is universal.** Any child, any story, any order. No story-to-child
link exists in the data.

**Age bands** are 3-4, 5-6, 7-8, 9-10, 11-12, mapped to grades for schools:
Pre-K, K, 1–2, 3–4, 5.

**Banned words.** The craft gate blocks `assessment`, `mastery`, `milestone`,
`delayed`, `gifted`, `grade level` from any child-facing text. This is not
squeamishness — it is the product's founding refusal. Buju does not rank children.

See also: `STORY_WORLD.md` (the recurring cast and the map),
`STORY_SCHEMA.md` (JSON shape), `course_definitions/course_bands.yaml` (the
per-band numbers), `scripts/check_course_story.py` (the validator).

---

## Part 1 — What exists now

Built and deployed since v1 of this plan:

**One course story, end to end.** *The Tower That Kept Falling* — Pip's tower
falls, his hands go tight, his face goes hot. Both first-choice options fail. The
breath lands in `s3`, so every path reaches it. Two warm endings.

| | |
|---|---|
| SEL objective | `sel_theme.frustration` / notice the body, then breathe |
| Setting | `knowledge_domain.bridges_and_buildings` |
| Band | 5-6 (Kindergarten), BR160L–230L |
| Length | 188–194 words per path, MSL 5.1–5.4 |
| Sight words | 57–60% band-gated, 69–71% full Dolch corpus |
| Narration | 8 clips, word-level timings, 153 wpm |
| Illustrations | 6 scenes, WebP, ~45 KB each |

**A validator** — `check_course_story.py`. Band-gated Dolch scoring, dynamic braid
traversal, SEL invariants, glossary completeness. Blocks on things that are
broken; warns on things that are judgment calls.

**An audio pipeline** — `generate_course_audio.py`. Cartesia `/tts/sse` with
`add_timestamps`, giving a word cursor. Sentence pauses baked in as SSML from
`course_bands.yaml`, kept separate from the pilot's `audio_voices.json` so the 142
published clips are untouched.

**An image pipeline** — `generate_story_images.py`. Gemini image models on Vertex.
Style, cast and scene anchors repeated verbatim in every prompt for continuity.

**A publish step** — `publish_course.py`. Validate, copy assets, splice, verify,
sweep. Refuses to publish a failing story.

**A player** — three word tiers, tappable glossary, branch choices, three-question
check, and an adult-facing result card.

---

## Part 2 — Decided

### 2B and 2C have different rules

**Decided.** They are different products that share an engine.

| | 2C library | 2B course |
|---|---|---|
| Must it teach? | No — "a story need not teach" holds | Yes, one objective |
| Word count, sentence length | Warn | Warn |
| Structural integrity | Block | Block |
| One SEL objective + sub-skill | n/a | Block |
| Glossary covers every content word | n/a | Block |
| Both branches reach the objective | n/a | Block |
| Read-along text | No | Yes |
| Sight-word scoring | Not applicable — audio only | Applies |

**On what blocks:** v1 made course stories *stricter* than library ones, on the
theory that a curriculum needs guarantees. That was backwards, and you caught it.
A course is the thing being actively tuned, so hard blocks stop you experimenting.
Blocks are now reserved for **things that are simply broken** — a path that never
reaches an ending, a content word with no glossary entry, a missing SEL objective.
Word counts and sentence length warn.

### The didactic layer stays out of the prose

**Decided.** This is the load-bearing decision of the whole track.

The research framework wants the protagonist to hit a trigger, show the symptom,
and model a coping strategy step by step, with a branded name for the tool. Applied
literally, that drives your own prose rubric to its floor — the `heart` dimension
scores **1 out of 5** for *"preachy — a lesson is stated outright."*

So: **the character does the thing; the wrapper names it.**

- **In the prose:** Pip feels it in his body, tries something, it works. No named
  protocol recited at the listener. No narrator explaining what just happened.
- **In the wrapper:** the pre-story frame, the three questions, and the educator
  note name the strategy, label the steps, and do the transfer work.

The strategy is still modelled step by step — as *action a child watches*, not
*instruction a child receives*.

> **Rule.** No course story may state its own lesson. If you delete the
> post-story wrapper and the child still hears a sermon, the story has failed.

Every "educational app in a costume" you position against fails exactly here, by
putting the lesson in the character's mouth.

### The gradient never says "mastered"

**Decided.** Master doc §7 already solved this shape for science: NGSS sits as an
optional overlay, never the structure, and the gradient stops at *Demonstrated*
because "Mastered is an overclaim for conversational detection."

Same here. The schema field is `evidence_level`, values
`not_yet_observed | emerging | demonstrated`. `mastery` stays a blocked word
everywhere, including internally.

A three-level *observation* is defensible from one story. A binary mastery verdict
is not.

### Both branches reach the objective

**Decided.** The strategy lives in `s3`, the shared segment every path crosses.
The branch choice is about *what the child tries first*, and in the current story
**both first options fail** — pushing the blocks away, or rebuilding too fast.

That is deliberate: a first try failing is normal, and seeing it fail twice
without blame is the point. The educator note says so explicitly.

**Still open:** whether that reads as blame to an actual child. This is the design
question worth putting in front of the expert first.

### Lexile applies only where the child sees text

**Decided.** Lexile, Dolch and Fry measure *reading* difficulty — decoding,
sight-word recognition. A child listening to narration does none of that.

Two separate tracks, never conflated:

| Track | Surface | Claimable |
|---|---|---|
| **Language comprehension** | audio (all 144 library stories) | vocabulary, listening comprehension, verbal reasoning |
| **Decoding** | read-along and print (course track, printed books) | text-level reading placement |

The course track has read-along text, so **Lexile and Dolch legitimately apply
there** — and only there. Sight-word scoring is not a gate on audio-only stories.

### Sight words are band-gated, and the gap is the product

**Decided.** Dolch is scored against the tiers a child at that band should
actually know, not the whole 315-word corpus. Otherwise a Pre-K text passes by
leaning on third-grade words.

The tower story: **57–60% band-gated**, 69–71% against the full corpus. The
framework's 80% describes a controlled decodable reader, not a narrative carrying
real content words.

Rather than lower the bar and move on, the reader marks **three tiers**:

| | |
|---|---|
| **Solid thin underline** | Words to know now — this band's Dolch pool |
| **Dashed thin underline** | Words coming next — upper Dolch the child is growing into |
| **Amber highlight, tappable** | New words — hover or tap for a kid-friendly gloss |

30 / 6 / 13 words in the current story. So "57% coverage" reads as **57% known,
11% emerging, 24% explicitly taught.** That is a curriculum, not a shortfall. The
validator **blocks** if any content word lacks a gloss.

---

## Part 3 — SEL is embedded in the knowledge graph

**Decided** — see `STORY_WORLD.md` Part 3 for the full reasoning.

An SEL course is **set at a knowledge topic**. The child is exploring nature, or
making something, or tasting sweets, and the feeling happens there. SEL never gets
its own territory on the map.

A topic hosts more than one shelf:

- `mode: library` — the ordinary story, teaches nothing in particular
- `mode: course` — the SEL story, one objective, read-along, questions

The SEL story does not displace the ordinary one.

**Why this makes school-to-home work.** A child meets Pip at school in a course
story set in `bridges_and_buildings`. At home the map shows that same topic with
more stories on it. Same place, same people, no seam. Not "the school product" and
"the home product" — one world entered from two doors.

**The knowledge topic is the setting, never a second thing to assess.** All three
questions are pure SEL. The validator blocks any check marked as assessing
knowledge, and warns if a course story has *no* setting — "the story has nowhere
interesting to happen."

**Action outstanding.** The first course story is filed as
`frustration__age5to6__d1__course__c41a7b.json`, but its setting is
`bridges_and_buildings`. Under this model the filename is backwards. It should be
`bridges_and_buildings__age5to6__d1__course__c41a7b.json` — the SEL theme is a tag
inside the file, not the file's identity. Rename before more course stories exist.

---

## Part 4 — The three questions

Every course story carries exactly three, in this order. The validator blocks
otherwise.

| Tier | Asks | Passing looks like |
|---|---|---|
| **recognition** | How did the character's body feel? | Names the physical cue, not just the emotion word |
| **strategy_recall** | What did they do about it? | Recalls the actual step |
| **transfer** | Novel situation — what could you do? | Applies it without prompting |

Recorded as `evidence_level`, never a score.

**How they're answered.** Today: tapped in the reader, three options each.
**Decided** for later: take-home questionnaires — a link a family answers offline —
and answering aloud by voice.

**Who administers.** For the first pilot, the teacher. Buju asking the questions
aloud is natural and fits the voice product, but it means evaluating child speech,
which is a new capability with real implications. Teacher-administered ships
sooner and sidesteps the hardest privacy question.

---

## Part 5 — Where things live

| What | Where | Why |
|---|---|---|
| SEL competencies, sub-skills, per-year benchmarks | `knowledge_graph_definitions/sel_theme/` | 27 nodes already exist with the right shape. **No parallel SEL taxonomy.** |
| Per-band language bounds, Lexile targets, sentence pauses | `course_definitions/course_bands.yaml` | Machine-read by the generator and the validator |
| The rules | this file | |
| Course payload per story | inside the story JSON under `course` | Travels with the story |
| The strategic claim | master doc §9 and §15 | One paragraph, never the design |

### The course payload

```json
"course": {
  "sel_theme": "sel_theme.frustration",
  "sub_skill": "notice_the_body_then_breathe",
  "casel_domain": "self_management",
  "grade_view": ["K"],
  "branch_model": "stumble_then_recover",
  "glossary": [{"word": "tight", "say": "tite", "kid_gloss": "..."}],
  "checks": [{"tier": "recognition", "prompt": "...", "look_for": "...",
              "options": ["..."], "correct": 0}],
  "evidence_levels": ["not_yet_observed", "emerging", "demonstrated"],
  "educator_notes": "..."
}
```

Note `look_for` rather than `expected_answer`, and `evidence_level` rather than
`mastery_indicator`. The wording is the policy.

---

## Part 6 — Loose ends

**Blocking:**

- **L1. SEL nodes have no 3-4 or 11-12 band.** All 27 cover ages 5–10 only. The
  framework's Level 1 is Pre-K, so the youngest band needs authoring before
  anything can happen there.
- **L2. Sub-skills don't exist.** `sel_theme` nodes have a depth ladder
  (naming the feeling → navigating it → understanding others) but no discrete
  sub-skill beneath each node. "One SEL objective" needs that level.
- **L3. Rename the course story to its host topic** (Part 3).

**Real, not blocking:**

- **L4. Do `sel_theme` and `value_lesson` merge?** You asked twice. Answer:
  **don't merge the axes, give them a shared spine.** They are different — SEL is
  what happens *inside* a child, values are how a child *treats others*. But
  `saying_sorry` (SEL) and `admitting_mistakes` (value) are nearly the same story.
  Map both onto CASEL's five domains as a crosswalk. A course then says "this is
  Self-Management" without caring which axis the node sits on, and near-duplicates
  become visible because they land in the same cell.
- **L5. Should the 27 nodes be expanded** against the SEL deep-search output? Yes,
  probably — but expand *depth* (sub-skills, missing bands) before *breadth*. 27
  themes with no sub-skills is a shallower problem than 40 themes with none.
- **L6. Language complexity is still uncontrolled in the library.** Across all 144
  stories, mean sentence length is flat at ~9 words in every band and varies more
  *within* a band than between bands. What scales with age today is length and
  subject matter, not language. That is a 2C quality gap independent of the course
  product, and a prerequisite for any literacy claim.
- **L7. Retrofit.** 119 library stories already carry a `value_lesson` tag. Some
  may be close to course-ready with a wrapper and no prose change. Cheap to check;
  the pilot event data says which are most played.
- **L8. The teacher surface does not exist.** Class rosters, assigning a story,
  recording what was observed, a report in the three-level gradient. That is a new
  application, not a view on the pilot. Largest unbuilt piece.

**The filter question.** Master doc §2 asks whether a feature makes stories richer
or gives *parents* deeper insight. A teacher is a third party the filter doesn't
name. **Decided:** gain a clause. The 2B line is a different product with a
different goal, sharing the underlying structure. Better to say so than to let it
quietly erode a rule that has been doing useful work.

**Compliance.** Selling to schools moves this from COPPA to COPPA + FERPA + state
student-privacy law + district data-processing agreements. Any per-child
observation record — even a three-level one — is an education record.
**Open:** whether observations are stored per child at all, or aggregated to the
class. Class-level aggregate reporting sidesteps most of it, is consistent with
everything the consumer product promises, and may be enough for a first pilot.
Worth testing with a real educator before assuming per-child records are needed.

---

## Part 7 — What to do next

1. **Show the tower story to the expert.** It exists, it validates, it is
   deployed. The two things to watch: does the failed first try read as blame, and
   does the story still score well on `heart` now that it teaches?
2. **Author sub-skills** beneath the 27 SEL nodes (L2), and the CASEL crosswalk.
3. **Author the missing 3-4 and 11-12 bands** (L1).
4. **Rename the course story** (L3).
5. **Add MSL and clause depth to the library gate as warns** (L6). Useful even if
   the course line never ships.
6. **A second course story** at a different band and a different feeling, to find
   out what the first one got right by accident.
7. Only then: the teacher surface.
