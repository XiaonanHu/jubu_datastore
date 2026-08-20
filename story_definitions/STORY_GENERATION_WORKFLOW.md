# Story Generation Workflow (Engineering)

**Version 1.0 — finalized 2026-07-27.** This version incorporates every
founder decision to date (pattern plans, bounded weights, voice answering,
slot design, evaluation harness) and is the reference for implementation.
Future changes bump the version number at the top of this file.

**What this document is.** The step-by-step engineering process that turns a
request — "a story about this topic, for this age, for this family" — into a
finished, checked, reviewable story. The Story Creation Master Policy
(`STORY_CREATION_POLICY.md`, same folder) is the rulebook: tones, telling
styles, quality rules, safety rules. This document is the assembly line.
Policy changes rarely; this workflow will be tuned constantly — that is why
they are separate documents.

**How to read it.** Defined record types in `code font`; the plain word
**topic** means one `KnowledgeGraphNode`; open items marked
**[open design note]**. Figures are small and each explains exactly one
idea.

**The order of decisions follows their leverage.** The single
highest-impact decision is what kind of story this is — what makes it move.
The pipeline decides that first, then gathers materials aimed at it, then
makes the smaller decisions, then writes.

---

## The pipeline at a glance

```
Stage 0   the request            (topic, age, family context)
Stage 1   choose the PATTERN PLAN — what kind(s) of story, in what order
Stage 2   brainstorm materials, aimed at that plan     → MaterialSheet
Stage 3   remaining decisions (tone, teller, cast,
          value, branch plan)                          → StoryDesignDecisions
Stage 4   outline the whole braid          [gate: outline checklist]
Stage 5   write the segments               [gate: per-unit checks]
Stage 6   read every full path             [gate: whole-story checks]
Stage 7   package: story + build record → review queue (status: draft)
```

Every stage writes its output down before the next begins, so a failed
build resumes where it failed and every decision is auditable. Rule of
thumb for what runs where: rules and lookups are plain code; idea-making
and prose are model calls; picking-the-best is a model call constrained by
rules.

**Warnings travel forward.** Every gate, at every stage, appends its
findings — hard failures and soft warnings alike ("vocabulary drifted
older", "second use of the word 'suddenly'") — to a running memo called the
`WritersNotes`. Every later model call in the same build receives the memo.
A problem caught at segment two is never repeated at segment seven, because
segment seven's writer was told about it. The memo also lands in the build
record, so reviewers see what the pipeline struggled with.

---

## Stage 0 — The request

*Produces:* a `StoryRequest` record.
*Run by:* a developer command today
(`python -m jubu_datastore.story_generation.build --topic
knowledge_domain.volcanoes --age 6 ...`); later, the content pipeline.

A `StoryRequest` pins down:

- the **main topic id** and **age** (required);
- optional requested tags: a story hook, a feelings topic, a value topic;
- the optional **family context bundle** — derived preferences only: tone
  taste, curiosity style, pattern taste, recently served patterns and
  tellers, carried character names, parent value picks. Never identity,
  never raw history;
- practicalities: pipeline variant flags, config version.

## Stage 1 — Choose the pattern plan

*Consumes:* the request, the topic's definition, the family's pattern
taste, and the topic's existing shelf of stories.
*Produces:* a **pattern plan** (defined below) plus one backup, with
reasons recorded.

### The story pattern library

A **story pattern** is the kind of movement that pulls a story forward —
what keeps a child listening. Eight patterns, each with real-author
reference points so writers and models know the register:

| Pattern | What pulls the story forward | Feels like |
|---|---|---|
| `problem_and_fix` | Something is wrong or blocked; try, fail differently, try again, solve it. A soft antagonist allowed, optional. | Roald Dahl's drive, minus the cruelty |
| `journey` | Being taken somewhere amazing; the movement itself is the plot. Nothing needs to be wrong. | The Magic School Bus; a magical trip into a new space |
| `mystery` | A gentle question opens; clues accumulate; the answer satisfies. Curiosity is the fuel, never danger. | "Why does the tide always come back?" |
| `dilemma` | A choice the character must make, and living with it. | classic fable, without the finger-wag |
| `inner_weather` | A feeling arrives, swells, softens. Not a problem to fix — weather to move through. | gentle picture-book arcs |
| `quiet_hour` | Almost nothing happens, beautifully. A mood, a small strange encounter, a warm glow at the end. | Naoko Awa; bedtime registers |
| `romp` | Escalating play and silly logic, each step sillier or grander. | pure play |
| `make_and_build` | Wanting to make or do something, and getting there step by step — learning by building. Not a problem being fixed: a thing coming into being. | Richard Scarry; workshop energy |

Each pattern has a beat list (its jobs) in the recipe-book config. The
no-fake-choices rule, the braid rules, and the warm landing apply to every
pattern identically.

**The library is capped at eight.** A new pattern gets in only by naming a
distinct pull, a distinct Stage-2 material checklist, and three example
stories no existing pattern serves. Gaps close on demand, not by
speculation.

**Do not confuse patterns with tellers.** The friendly old neighbor telling
you about his own adventures is not a missing pattern — it is the
storyteller's-tale *teller* (policy §6) wrapped around some pattern,
usually `quiet_hour` or `journey`. Pattern = what moves the story.
Teller = whose voice carries it. Any teller can carry any pattern.
Likewise "a good teacher showing you things" is not a pattern of its own:
its warm version is `make_and_build` or a `journey` through an idea —
never a lecture (the policy forbids sermons).

### A story can be built from more than one pattern

A short story is one pattern. A longer story can be a **sequence of
pattern stretches** — and this is often what makes a story feel alive:

```
a bedtime story:      |-- quiet_hour --|-- problem_and_fix --|
a bigger story:       |-- mystery --|-- dilemma --|-- inner_weather --|
```

Rules that keep a sequence from becoming a mess:

- **Stretch count follows age** (tunable in config): ages 3-4 always one
  pattern; 5-6 one, sometimes two; 7-8 up to two; 9-10 up to three. Short
  stories simply don't have room for more, as founder review noted.
- **Every handoff needs a hinge**: one moment that belongs to both
  stretches. The quiet hour is interrupted by a small wrong thing (hinge
  into `problem_and_fix`); the mystery's answer creates a hard choice
  (hinge into `dilemma`); living with the choice stirs a feeling (hinge
  into `inner_weather`). The recipe book keeps a list of proven handoffs
  with hinge examples; unlisted handoffs need a reviewer's eye.
- **The last stretch owns the ending.** Whatever came before, the final
  pattern lands the story warm. Quiet-leaning patterns make the best final
  stretch for bedtime.

The pipeline treats single-pattern and multi-pattern plans as equals from
day one — single-pattern is simply the most common plan, not a separate
mode — and the pilot set must include both, so both are tested before any
rollout decision is made.

### The plan can fork at a choice: the child picks the next pattern

The most interesting consequence of multi-pattern stories, from founder
review: an early choice point can offer **two different patterns as its two
options**. The soft option leads into a `quiet_hour` stretch; the bold
option leads into a `journey` stretch. This extends
personalization-through-branching from tone all the way up to the kind of
story:

```
                       ┌── soft choice ──▶ |-- quiet_hour --|── ending A
|-- mystery --|── ◆ ──┤
                       └── bold choice ──▶ |-- journey ----|── ending B

◆ = a pattern-fork choice point. It always SPLITS (never rejoins):
    two patterns cannot merge back into one shared segment.
```

Two related rules:

- **A pattern-fork choice is always a splitting choice**, so it spends more
  of the story's budget than a rejoining one; the branch plan (Stage 3f)
  accounts for that.
- **A `dilemma` stretch and the braid share their choice.** When the plan
  includes a dilemma, the dilemma's central decision *is* one of the
  story's choice points — the pattern and the branching are the same moment,
  not two mechanisms.

So a **pattern plan** is one of three things, in increasing richness:
a single pattern; a fixed sequence (same stretches on every path); or a
forked plan (a shared opening stretch, then a pattern-fork choice).

### How the plan is chosen

1. **Start from the topic's own leanings — hand-authored numbers, not a
   model's opinion.** The base weights live in `story_patterns.yaml` as
   plain numbers per topic kind, written by us and reviewed like content.
   For example, nature-phenomena topics might carry: journey 0.35, mystery
   0.25, problem_and_fix 0.20, quiet_hour 0.10, romp 0.05, inner_weather
   0.03, dilemma 0.02. Mechanisms weight `mystery`/`problem_and_fix` up;
   making-and-doing topics weight `make_and_build` up; feelings lean
   `inner_weather`; values lean `dilemma`; bedtime and ages 3-4 weight
   `quiet_hour` up. Expect the first numbers to be somewhat wrong — they
   are cheap config edits, and the pilots calibrate them. Later, an
   offline job may re-fit them from real completion and replay data, but
   even then the update lands as a config diff a human reviews.
2. **Nudge, never overrule.** Two adjustments modify the base weights, and
   both are *bounded* clamped multipliers in config: the **shelf nudge**
   (×0.5 per same-pattern story already on this topic-and-age's shelf,
   never below ×0.25 total — so the shelf grows varied) and the **family
   nudge** (between ×0.7 and ×1.3, applied only after a minimum number of
   playthroughs — patterns this child finishes and replays drift up).
   After the nudges, weights are renormalized. A bounded nudge can reorder
   the plausible candidates; it can never promote a pattern the topic
   fundamentally doesn't fit, and never bury one the topic strongly wants.
   A volcano will mostly get journeys, mysteries, and problems — the
   nudges decide *which of those* comes next, plus the occasional
   deliberate `quiet_hour` surprise.
3. **Sample, then judge.** Sample the primary pattern from the adjusted
   weights (sampled, not best-pick — best-pick makes every volcano story
   the same). Decide the stretch count from age. If more than one stretch:
   pick companions by handoff compatibility with the primary, and decide
   whether the plan is a fixed sequence or forks at a choice. One small
   model call confirms the plan against the topic's actual treatments and
   names a backup plan. Choice, reasons, and rejected candidates are all
   recorded. No model ever invents or edits the weights at request time;
   this judge call is the model's only role in the whole stage.

**[open design note — founder hypothesis to verify with playthrough
data:** children who love certain kinds of topics may also love certain
kinds of stories; if the data confirms it, topic taste can help predict
pattern taste for new families. Seed with static affinities; learn per
family; assume nothing.]

**Why this stage comes first:** the plan determines what is worth
brainstorming. A `journey` needs marvelous sights, not problems; a
`quiet_hour` needs atmospheres, not obstacles. Brainstorming before
choosing collapses, in practice, into "some problem gets fixed" every
single time — the exact repetition this stage exists to prevent.

## Stage 2 — Brainstorm materials, aimed at the plan

*Consumes:* the request + the pattern plan. *Produces:* a `MaterialSheet`.
*How:* plain-code lookups, then one brainstorming model call whose
checklist depends on the plan.

**Lookups (no model):**

- the topic's `GenerationBrief` for this age (framing, vocabulary, avoid
  list) and the age band's size numbers;
- candidate value topics (parent picks intersected with plausible fits);
- **the topic family's existing cast** — recurring character roles already
  used in stories on this topic, its parent topic, and its sibling
  deep-dive topics. If the volcano ranger exists, the plate-tectonics story
  should know about her;
- the two kinds of **doors** for branches, kept deliberately separate
  because they serve different children:
  - **deeper doors** — the same topic, closer up: its deep-dive subtopics
    and facets (for `spider`: webs, hunting, senses). For the child who
    wants *more of this*;
  - **wider doors** — the topic's map neighbors a branch could visit
    (volcanoes → islands). For the child who wants *what's next door*.

**The brainstorm (one model call):** over-generate, roughly three to five
times what one story needs.

*Always gathered, whatever the plan:* true wonder-facts (age-right, each
with its sensory picture); candidate settings; candidate characters — with
the existing cast listed prominently, so reuse is the easy path and new
characters must earn their place; candidate value angles; one concrete
scene idea per deeper door and wider door, so branches have somewhere real
to go.

*Gathered per pattern in the plan* (a two-pattern plan gets two of these
sections):

| Pattern | Its own section of the sheet |
|---|---|
| `problem_and_fix` | problems worth caring about, and the failed attempts that make the fix earned |
| `journey` | the marvels along the route, and the route itself |
| `mystery` | opening questions, clues, and the satisfying answer each supports |
| `dilemma` | temptations, what each option costs, the repair afterward |
| `inner_weather` | moments where the feeling shows in the body; small things that help it soften |
| `quiet_hour` | atmospheres, small strange encounters, the one image left glowing |
| `romp` | games, escalations, gloriously silly failure modes |
| `make_and_build` | the thing being made, the steps that get there, the wobbles along the way, and the moment it finally works |

The avoid list is applied here — forbidden material never reaches the
sheet. Wonder-facts get one verification pass so later stages can trust
them. Unused entries stay on the sheet for this topic's next story.

## Stage 3 — Make the remaining decisions

*Consumes:* `MaterialSheet` + request + pattern plan. *Produces:*
`StoryDesignDecisions` — every creative decision as data, before any prose.
Each decision states what is decided, who proposes, who decides.

**3a. Confirm the plan against the real materials.** One quick model check:
does the sheet actually feed the plan? Almost always yes. If not (the
`mystery` turned up no good question), switch to the Stage-1 backup plan
and re-run Stage 2. Plans are never patched mid-build; switching means
re-brainstorming.

**3b. Tone recipe.** The story's dominant tone and optional accent (policy
§7). Rules sample two or three candidate recipes — weighted by the plan,
the family's taste, and variety against recent recipes — and one model call
picks the candidate the materials actually support, saying why.

**3c. Teller.** Who tells it: "we" adventure, named hero, or storyteller's
tale (policy §6). The rotation rule removes whatever this family just had;
the plan suggests a per-pattern default, and the same model call as 3b picks
from what remains. The defaults are deliberately **not listed here, nor in the
policy** — they live in `pattern_default` in
`jubu_backend/jubu_chat/configs/story_telling_styles.yaml`, which is what the
code actually reads. Both documents previously carried partial copies that
disagreed with the config and with each other.

**3d. The cast — reuse before invent.** When the main topic is a deep-dive
child of another topic (especially an immediate child) or a sibling in the
same topic family, prefer bringing back the family's recurring characters
over inventing new ones. The child who met the beetle guide in the first
insects story finds her again in the spider story. Character **names are
always slots**: a recurring character is defined by role ("the beetle
guide"); the name lives in each family's records, chosen by the child at
first meeting, and walks into every later story in the topic family
automatically. New characters are allowed when the sheet offers a clearly
better fit or the cast has grown stale (a variety rule); the judge decides
and records why.

**3e. Value: in or out, and which one.** A value goes in only if all three
hold: (1) Stage 2 found a *natural* value angle in the materials; (2) the
request or the parents' value picks welcome it; (3) this family's recent
stories are not already value-heavy (a frequency cap in config). Otherwise
the story carries no value — a normal, good outcome.

**3f. The branch plan.** What is decided, per choice point: where it sits
(in which pattern stretch, at which beat); its two options; whether it
rejoins or splits (the final one always splits; a pattern-fork always
splits); each option's tone lean and curiosity lean; which slots each
option sets. For the story as a whole: whether one branch opens a deeper
door, a wider door, or one of each.

**How the child answers — by voice, saying anything (product decision).**
The child answers out loud in their own words; the existing jubu_backend
voice pipeline hears it, and a serving-time interpreter decides which
option the child meant and returns the branch. The child is **never**
required to say a magic word — "the shiny one!", "let's go up!", or a
whole sentence all work. The pipeline still authors one short **say-word**
per option (the concrete noun or verb of that option: "the crab" /
"climb") for two reasons: it makes the spoken question naturally easy to
answer, and it anchors the interpreter's matching. The two options'
say-words must not sound alike. If the interpreter can't tell what the
child meant, Buju re-asks as a simple either-or. Interpreting and
re-asking are serving-time behavior; the options and say-words are
authored here and checked by the gates. Tap input is a later add-on.

**Slots are capped at five per story** (config), and they come in two
kinds with different lifetimes — this distinction is the core of the slot
design and must be implemented exactly:

- **Naming slots** (persistent): names the child gives — the hero, the
  beetle guide, the boat. The value lives in the **family records**, keyed
  by *(topic family, character role)*, not by story. Once the child names
  the beetle guide in the first insects story, every later story anywhere
  in that topic family — the parent topic, siblings, and deep-dive
  descendants all the way down — reads the same value automatically. The
  value changes **only** when the child explicitly renames; it is never
  silently regenerated or overwritten.
- **Playthrough slots** (transient): choice consequences carried through
  rejoins — the companion who came along, the tool found in the cave.
  These live only inside one playthrough and reset on replay.

Beyond five slots total, checking every combination in Stage 6 stops
being affordable.

**What makes a choice point worth having** — the five criteria from
founder review, now the design checklist for every choice point:

1. **It makes the story more interesting** — the paths genuinely differ.
2. **It makes the story more engaging for this child** — both options are
   tempting *to a child*, not just structurally different.
3. **It can reveal the child's taste** — daring vs. careful, cozy vs. wild
   (the tone lean captures this).
4. **It can reveal how the child likes to learn** — toward the mechanism,
   toward the use and the why, or toward pure experience (the curiosity
   lean captures this).
5. **It can reflect the child's mood today** — a soft option and a lively
   option at the same fork lets the same story fit different evenings.

Criteria 1 and 2 are mandatory for every choice point. Criteria 3-5 are
what the leans are *for*: each pick is recorded on the `StoryBranchChoice`,
and over time these become the family's picture of what their child
enjoys — which can be summarized for parents in preference language
("chose the gentle path three bedtimes in a row"), never in evaluation
language (the banned-language rules apply to these summaries too).

**3g. Selected materials.** The subset of the sheet this story will use,
recorded as ids — along with every sampled-but-rejected alternative from
3b/3c. This record is most of the eventual `StoryBuildRecord`, and it is
how the next story on this topic can be forced to choose differently.

## Stage 4 — Outline the whole braid

*Consumes:* `StoryDesignDecisions` + selected materials only (focused
prompts write better than everything-prompts) + `WritersNotes`.
*Produces:* the full story outline: every segment summarized in 2-3
sentences with its `character_want` and `dramatic_tension`; every choice
point's question and options; rejoin/split marks; slots; the spine in one
line; every ending sketched.

**The outline gate is a checklist.** Plain rules check what rules can
check; one reviewing model call checks the rest. The outline passes only if
every item passes:

1. Every job in every pattern stretch's beat list is done somewhere in
   that stretch.
2. Every handoff between stretches has its hinge moment.
3. Every choice point meets criteria 1 and 2 of the branch checklist, and
   its options differ in kind.
4. Every slot an option sets is used later on the relevant paths; no
   segment uses a slot that no path on its way there sets.
5. Nothing from the avoid list appears anywhere.
6. Every ending is warm and fully resolved.
7. The segment count and per-segment lengths fit the age's word budget.
8. Every choice point's two options carry distinct, easy-to-say say-words
   that a listening child can echo, and they don't sound alike.

If any item fails, the failure notes are appended to `WritersNotes` and
the outline is regenerated with them (up to N attempts, then a human
looks). A flawed outline is never handed to the writing stage in the hope
that good prose will fix it.

## Stage 5 — Write the segments

*Consumes:* the outline, the `GenerationBrief`, the `WritersNotes`, and —
per unit — the finished text of the path leading to it.
*Produces:* all segment texts.

**The writing unit is not always one segment.** Founder review improved
this: where a choice point branches, the two continuation segments are
written **together in one call**, which sees the shared path before the
fork. Writing the siblings together, aware of each other, is how they come
out *deliberately* different — different in kind, not accidentally similar.

```
   trunk        fork            after the fork
  [ S1 ] → ◆ → [ S2a | S2b ] → [ S3 (shared, with slots) ] → ...

  one call      ONE call         one call
  for S1        writes BOTH      for S3, written once with
                S2a and S2b      blanks; must read correctly
                together         for either choice
```

So: trunk and shared segments are one call each; each fork's sibling pair
is one call. Fail → regenerate that unit only. Every finding, pass or fail,
is appended to `WritersNotes` and travels into all later units' calls.

**The writing prompt itself is versioned**, in `story_generation/prompts/`.
It is the sole owner of the craft rules, and this document deliberately does
**not** summarise them — a summary here drifts the moment the prompt is
revised, and it did: this paragraph described v2.1 while the prompt had moved
to v2.3, so the two newest craft sections were invisible to anyone reading
only the workflow. Read `segment_writing_v2.md` for what the writer is
actually told. The version in force is `prompt.version_id` in
`jubu_backend/jubu_chat/configs/story_generation.yaml`, and it is stamped into
every build record so a story traces to the rules that wrote it. Its
predecessor and the review that replaced it are in `prompts/_archive/`.

**The per-unit gate.** Two things block, because they are exact:

- **segment length ceiling**, with no minimum — padding is the failure, so
  there is nothing to enforce on the short side (v1's word quota is exactly
  what produced decorative description);
- **safety** — avoid-list terms, banned evaluation words.

Everything else about craft **warns for human eyes** rather than failing,
because a blocking threshold on a judgment call is how arbitrary rules
creep back in: flat rhythm (little variation in sentence length, or a run
of near-identical ones), abstract mood words, a low share of speech or
physical action, an object introduced and never used, and a
formula detector — the same comparison or joke shape repeating across
nearby segments. Plus the structural checks that remain exact: continuity
with the path, slot usage matching the outline, and the sibling-pair
contrast check.

The **one-shot variant** replaces Stages 4-5 with a single call producing
outline and segments together; it exists so the rounds-vs-one-shot quality
comparison (policy §5) stays a flag, not a project.

## Stage 6 — Read every full path

*Consumes:* all segments. *Produces:* pass, or a fix list pointing at
specific units.

Every path is assembled exactly as a child will hear it — every reachable
combination of slot values — and read for: flow across segment joins, no
detail drift, tone recipe held (dominant owns the landing; the accent
stayed with its carrier), pattern integrity per stretch (a `quiet_hour`
that grew a villain fails here), hinge moments landing naturally, the
policy §10 quality bar, and the full safety and banned-language pass.
Failures point at units and loop back to Stage 5, with the findings added
to `WritersNotes` so the regenerated unit knows exactly what went wrong.

## Stage 7 — Package for review

*Produces:* the stored story (status `draft`) + its `StoryBuildRecord`,
queued for human review.

The story record carries what policy §12 requires. The `StoryBuildRecord`
carries the whole provenance **as codes referencing versioned definition
files** — the pattern plan, tone ids, teller id, cast roles, material entry
ids, prompt and config versions, per-stage model settings, all gate
results, the final `WritersNotes`, and the rejected alternatives from
Stages 1 and 3. It never copies definition text, so a leaked record exposes
bookkeeping, not the recipe book. Build records are internal-only.
`inner_weather` and `dilemma` stretches route the story to psychologist
review; the rest to standard review until the gates earn trust.

---

## Where things live

| Piece | Where | Why |
|---|---|---|
| Pipeline code | `jubu_backend/jubu_chat/story_generation/` | One module per responsibility; `story_builder.py` is the only file that calls models |
| Entry point | `jubu_backend/scripts/build_story.py` | The only CLI |
| Recipe book: patterns (beats, affinities), tones, tellers, polish voice cards | `jubu_backend/jubu_chat/configs/story_{patterns,tones,telling_styles,voice_cards}.yaml` | The versioned definitions build-record codes point into |
| Recurring cast roles per topic family | alongside the stories' records; names live in family records only | Shared world, personal names |
| Prompts per stage | `jubu_datastore/story_generation/prompts/`, versioned | Prompt id goes into the build record |
| Tunables (age-band ceilings and choice points, nudge floors/caps, slot cap, over-generation factor, polish growth limit, retry counts) | `jubu_backend/jubu_chat/configs/story_generation.yaml` | Tunables live in config, per backend convention |
| Stage artifacts (request, sheet, decisions, outline, notes, build record) | persisted per build | Resumable, auditable |
| Finished stories + review status | `jubu_datastore/story_definitions/stories/pilot/`; shape defined in `STORY_SCHEMA.md` | Replaces the old flat `stories` table |

## Engineering rules

- **Every stage writes its output before the next begins**; failed builds
  resume at the failed stage.
- **Warnings propagate**: every gate appends to `WritersNotes`; every later
  model call receives it; the final memo is kept in the build record.
- **Regeneration is surgical**: a bad unit alone; a bad outline from Stage
  4; a plan switch from Stage 2; only a bad request restarts.
- **Sampling is seeded**: same request + sheet + seed = same decisions;
  variety comes from deliberate seeds and the bounded nudges, never from
  untracked randomness.
- **Model routing by job**: strong model for brainstorm, outline, prose;
  cheap model for gates; plain code wherever rules suffice.
- **No family identity anywhere**: the context bundle carries derived
  preferences only; shared-library builds store no family reference at all.

## What to build first

1. The recipe-book configs — **story_patterns.yaml first** (eight patterns
   with beat lists, affinities, and the handoff list), then tones and
   tellers.
2. Stages 0-3 end to end for two contrasting requests — volcanoes age 6
   (expect a `journey` or `mystery` plan, possibly two stretches) and a
   bedtime `quiet_hour` — printing the plan, `MaterialSheet`, and
   `StoryDesignDecisions` for human eyes. This is where we learn whether
   the strategy stage and the brainstorm are any good, before investing in
   the writing loop.
3. Stages 4-7 with the gates and `WritersNotes`.
4. **The evaluation harness**: build the same request every way we care
   about (rounds vs. one-shot; single- vs. multi-pattern plans), strip the
   labels, and present blind pairs with a short score sheet. The harness
   structure is committed now; the actual scoring dimensions and any
   evaluation prompts are **deliberately left open** and will be decided
   when we first run it (candidate dimensions: held attention / sounded
   good read aloud / choices felt real / fit the age / would the child ask
   for another). Scores are stored next to the build records, so "which is
   better" is answered by readings, not vibes.
5. The pilot stories (policy §13) run through that harness, covering both
   plan kinds.
   (Policy §3 has been updated to reference this pattern library — the two
   documents no longer describe structure differently.)
