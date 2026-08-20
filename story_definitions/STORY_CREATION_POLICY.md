# Story Creation Master Policy

**What this document is.** The rulebook for how Buju stories get designed,
written, and judged — the branching, pre-written stories of the Story Studio.
It answers: how a story is structured, how one is written, what sets its
tone and style, how do topics fit in, and what counts as good.

**How to read it.** Same conventions as the Knowledge Graph Master Policy:
defined record types appear in `code font`; the plain word **topic** always
means one `KnowledgeGraphNode` from the knowledge graph. Ideas still under
discussion are marked **[open design note]**. Committed decisions are marked
**Decision.** Every section starts with: what it's for, who provides the
input, who uses the output.

**Status: second draft, incorporating founder review.** Every Decision is a
starting position chosen so we can build and test — not a final answer.

---

## 1. Where to find things

*For:* finding the files this document builds on. *Input from:* n/a.
*Output used by:* anyone working on stories.

| What | Where |
|---|---|
| This policy | `jubu_datastore/story_definitions/STORY_CREATION_POLICY.md` |
| The on-disk shape of a story (braid, JSON, naming, validation) | `jubu_datastore/story_definitions/STORY_SCHEMA.md` |
| The engineering pipeline that implements it | `jubu_datastore/story_definitions/STORY_GENERATION_WORKFLOW.md` |
| Knowledge Graph Master Policy (topics, family records) | `jubu_datastore/knowledge_graph_definitions/KNOWLEDGE_GRAPH_POLICY.md` |
| Per-topic, per-age writing instructions (`GenerationBrief`) | built by `jubu_datastore/knowledge_graph/age_view.py` |
| Today's conversation engine design | `jubu_backend/docs/STORY_GENERATION_PLAN.md`, `jubu_backend/docs/CONVERSATION_MANAGER.md` |
| The voice rules for talking to children | `jubu_backend/jubu_chat/configs/interactions/buju_base.yaml` |
| Voice personalities (cozy, plain, whimsical inventor) | `jubu_backend/jubu_chat/configs/styles/*.yaml` |
| Session state fields stories inherit ideas from | `jubu_backend/jubu_chat/chat/core/turn_state.py` |
| Text-to-speech constraints | `jubu_backend/jubu_chat/chat/utils/voice_sanitizer.py`, `jubu_backend/voice_profiles/*.yaml` |
| Today's story table (a saved-transcript archive, to be replaced) | `jubu_datastore/story_datastore.py` |

## 2. What we already have, and what carries over

*For:* grounding this design in the working system instead of starting from
zero. *Input from:* the jubu_backend codebase. *Output used by:* §3–§11.

Today's product is a **live** voice companion: the child talks, Buju answers
in real time, and the "story" table just archives the transcript afterward.
The Story Studio is different: stories are **written in advance, offline**,
with branch points where the child chooses. That difference removes the old
speed pressure (nothing has to be generated while a child waits) but keeps
every rule about how text must *sound*.

**We keep, unchanged:**

- **The voice rules.** Text must be speakable: short complete sentences, no
  ellipses, no stage directions, no symbols. Pacing must come from sentence
  structure and word choice, because the text-to-speech engines ignore
  pacing markup. Age bands already define sentence counts and vocabulary
  simplicity per age.
- **The two private compass fields.** Every scene in the current engine
  carries `character_want` (what the lead character is concretely reaching
  for right now — "get the stuck door open", never a feeling-word) and
  `dramatic_tension` (what is unresolved, at gentle cartoon-safe stake).
  These two fields make scenes feel alive; every story segment carries both.
- **Vivid framing.** Concrete and sensory over abstract, always: "a hungry
  place in the sky that gobbles up even light," not "a region of spacetime."
- **Safety floors.** Cartoon-safe conflict, no blood or injury detail, no
  scary-graphic content, the per-voice forbidden lists, and the child's real
  name never spoken by the narrator.

**We keep, adjusted:**

- **The spine (was: "throughline").** Not every story needs the old
  emotional throughline. **Decision:** every story needs exactly **one
  spine** — the single thread that holds it together — but the spine's
  *kind* matches the story: feelings and values stories use an **emotional
  question** ("is it okay to need help?", never spoken aloud); discovery
  stories can use a simple **quest** (find the glowing pearl); pure-fun
  stories can use a **running joke or game** (everything the dragon toasts
  turns purple). One spine, of whichever kind — a story with no spine
  wanders, a story with two spines splits.
- **Feelings: shown by default, named when naming is the point.** The live
  system's rule was "the narrator never names a feeling." **Decision:** for
  stories we soften this by age, matching the feelings ladder in the
  knowledge graph. At ages 3–6 — where the ladder's first rung is literally
  *naming the feeling* — the narrator or a character may plainly name it,
  paired with shown behavior: "Nemo is a little scared. He swims closer to
  the rock anyway." At older ages, showing carries the load and naming
  becomes rare. Never name feelings as labels-without-bodies at any age.

**We do not carry over:** the child-led free-form turn loop (a pre-written
story leads; the child steers at choice points), and the flat story table
(a branching story needs a new schema — §12).

## 3. The pattern plan of one story

*For:* the structure guiding generation. *Input from:* the story's topics
and age. *Output used by:* the outline step (§5).

**Decision: every story is built on a pattern plan.** A **story pattern**
is the kind of movement that pulls a story forward — a problem to fix, a
journey, a gentle mystery, a feeling to move through, a thing to build.
The pattern library — eight patterns, each with its beat list, reference
authors, and topic affinities — is defined once, in
`STORY_GENERATION_WORKFLOW.md` (Stage 1), so the two documents cannot
drift. A **pattern plan** is one of three things:

- a **single pattern** — always, at ages 3-4 (short stories have room for
  one kind of movement), and the most common plan at every age;
- a **fixed sequence** of two or three pattern stretches (a quiet hour
  that turns into a small problem; a mystery whose answer creates a
  dilemma). Every handoff needs a **hinge** — one moment that belongs to
  both stretches — and the last stretch owns the warm landing;
- a **forked plan**: a shared opening, then a choice point whose two
  options lead into two *different* patterns — the soft pick into a quiet
  hour, the bold pick into a journey. A pattern fork always splits.

**Beats are a list of jobs, not a script.** Each beat names something its
stretch must accomplish; the outline may merge beats, stretch one across
two segments, or open mid-action — as long as every job gets done. Young
children *like* structural familiarity; most repetition that bothers
adults is surface repetition, which setting, cast, tone, and telling-style
rotation (§6–§7) address.

**Branches: a braided river, and every choice leaves a trace.**

A story that split permanently at every choice would need eight endings
after three choices. Instead:

- Choices always offer **exactly two options**, answered **by voice — in
  the child's own words**: the voice pipeline interprets whatever the child
  says and picks the branch; no magic word is required. Each option still
  carries a short **say-word** ("the crab" / "climb") that makes the
  question easy to answer and anchors interpretation, and the two
  say-words must not sound alike. (Tap input is a later add-on.)
- Each choice point is marked **rejoining** or **splitting**. A *rejoining*
  choice changes the next segment, then the paths merge back. A *splitting*
  choice never merges. **Decision:** the final choice is always splitting
  (two real endings); pattern forks are always splitting; other choices are
  rejoining by default.
- **Rejoining must not erase the choice.** When paths merge, whatever the
  child chose carries forward visibly. Story text is therefore stored as a
  **template with slots**: shared segments are written once, with named
  blanks — the companion who came along, the tool found in the cave, the
  name the child gave the boat — and each earlier choice sets those
  blanks' values. "We squeeze through the crack, and {companion} squeezes
  in after us, still carrying {found_item}." The choice happened once; the
  story remembers it to the last page. **Slots are capped at five per
  story**, in two kinds: **naming slots** (child-given names, stored in
  family records per topic family and character role, so a name given once
  propagates to every later story in that topic family — down through its
  deep-dive descendants — and changes only when the child renames) and
  **playthrough slots** (choice consequences, living only within one
  playthrough). The full slot recording-and-propagation design is in the
  workflow doc, Stage 3f.

**Rule: no fake choices.** If both options lead to the same next sentence
with different wallpaper, the choice is a lie and children notice. Each
option must change the scene, the approach, or the feel of what follows —
and set at least one slot the story uses again.

## 4. How big is a story — and how many stories per topic

*For:* length, and the topic-to-story relationship. *Input from:* the age
band and the topic. *Output used by:* outlining and writing (§5), the
library plan.

**Decision: length follows age, not topic.** Listening lengths below are one
walk from start to an ending. All numbers live in config:

| Age band | One listen-through | Words per path | Choice points |
|---|---|---|---|
| 3-4 | about 3 minutes | ~350 | 1 |
| 5-6 | about 5 minutes | ~700 | 2 |
| 7-8 | about 8 minutes | ~1,200 | 3 |
| 9-10 | about 11 minutes | ~1,700 | 3 |
| 11-12 | about 14 minutes | **not set** | 3 |

Listen-through and choice points come from `age_bands` in
`jubu_backend/jubu_chat/configs/story_generation.yaml`, which is the authority
— do not copy them anywhere else. **Words per path is a design budget that
exists only in this table**, and it was never set for 11-12 even though the
band now holds 34 stories; the per-segment ceiling (440) is doing all the work
there. Note the two are different numbers: config enforces a *per-segment*
ceiling, this column is the *per-path* budget.

**Decision: one topic-and-age pair maps to many stories — deliberately.**
Each story is one complete, self-contained braid (its own outline, branches,
endings). A rich topic like `volcanoes` at age 6 should accumulate a shelf
of distinct stories over time — a cozy one, a daring one, one framed by each
facet, one for each telling style — rather than one ever-growing mega-story.
This is exactly right, for three reasons: replayability (a child who loved
the volcano story wants *another* volcano story, not the same one longer),
variety pressure (each new story must differ from the family's recent plays
in pattern, telling style, tone, or facet — enforced at request time),
and the map (each play is another story tagged to the topic, which is what
coverage and exploration count). A choice point itself is spoken as one
short, concrete question with two options a child can hold in their head —
never three, never abstract.

## 5. How a story gets written

*For:* the generation procedure. *Input from:* the story request (topics +
age + tone recipe + telling style) and the topics' `GenerationBrief`s.
*Output used by:* the story pipeline; quality gates in §10.

**Decision: outline first, then write in rounds. Not one shot.**

(This section states the rules; the full staged engineering pipeline —
gather materials, make the creative decisions, then write — lives in
`STORY_GENERATION_WORKFLOW.md`.)

**Step 1 — the outline.** One pass produces the whole story's plan: the
pattern plan, spine, cast, setting, every segment's 2-3 sentence summary (with its
`character_want` and `dramatic_tension`), every choice point (question, both
options, rejoining-or-splitting, which slots each option sets), and the
slots each later segment uses. The outline covers the entire braid, so we
know the whole story hangs together before any prose exists. It is checked
before writing begins: every pattern stretch's beat jobs done, choices real, slots consistent,
avoid-list clean, every ending warm.

**Step 2 — the writing rounds.** Segments are written in reading order, but
the unit is not always one segment: where a choice point branches, the two
continuation segments are written **together in one call**, so they contrast
deliberately. The trunk and each shared segment are one call each. (Stage 5 of
the workflow doc owns this rule; it changed there after founder review and
this paragraph went two revisions without being updated.) Each round sees: the outline, the finished text of the
segments on its path so far, the slot values in play on that path, and the
topic's per-age instructions (framing, vocabulary, avoid list). Shared
(rejoined) segments are written once, with their slots as named blanks, and
checked against every combination of slot values that can reach them.

**Why rounds beat one shot** (and how we verify): a single pass writing 8-9
segments spreads attention thin — details drift, options converge, endings
rush. Rounds let us check between steps (vocabulary, sentence lengths for
speech, safety, continuity) and regenerate one bad segment instead of the
whole story. The extra model calls cost nothing that matters: stories are
written offline. **[open design note]** Still run the honest comparison:
same short stories both ways, blind human reading decides. For the 3-4 band
(one choice, ~350 words) one-shot may be fine and cheaper. The pipeline
supports both so the test stays cheap.

## 6. How the story is told — three ways in

*For:* narrator, protagonist, and point of view. *Input from:* the story's
pattern plan and the family's recent plays. *Output used by:* outlining and
writing.

**Decision: three telling styles, rotated for variety:**

The per-pattern default teller is **not listed here** — it lives in
`pattern_default` in `jubu_backend/jubu_chat/configs/story_telling_styles.yaml`,
which is what the code reads. This section defines what each teller *is*; the
config decides which one a pattern gets by default.

1. **"We" adventure.** Buju and the child go together: "We push open the
   mossy door. Warm air breathes on our faces. Should we follow the glowing
   crab, or climb up to see farther?" Companionship instead of a spotlight
   — the child is never alone in the story, and choices are naturally
   *ours*.
2. **The named hero.** A child-aged character the listener watches over and
   chooses for — and here we borrow a beloved trick from the live system
   (which already keeps child-coined names and uses them verbatim): at the
   story's start, **the child names the hero**. "This story is about a
   brave explorer. What should we call her?" The name is a slot; the family
   keeps it, and the hero can return in later stories. Chosen where a little
   distance is protective: it is
   easier to help *Mira* with her jealousy than to be told about your own.
3. **The storyteller's tale.** A character in the frame tells their own
   adventure: the lighthouse keeper who once rowed out in the storm, the
   grandmother dragon remembering her first flight. "Did I ever tell you
   about the night the sea turned green? I was younger than your boots..."
   Warm, intriguing, and it makes "I" safe — the *storyteller* says I, never
   the narrator-as-child. Lovely for history topics, long_ago, and any story
   that benefits from being remembered rather than happening now.

The narrator never addresses the listening child by their real name, in any
style. Rotation rule: don't serve the same telling style twice in a row to
the same family unless the child asks for it.

**[open design note]** for the psychologist: confirm the named-hero rule for
feelings stories per age, and whether "we" adventures work at 3-4 or need an
even simpler frame.

## 7. Tone: how the story feels

*For:* the feel of a story, and personalization through choices.
*Input from:* the topic, the family's settings and history, the child's
picks. *Output used by:* every writing round.

**The palette, five tones.** Two of them sound close, so their boundary is
stated: `curious_wonder` is **stillness** — wide eyes, whispering, "look at
THAT" awe at big true things; `big_adventure` is **motion** — wind, racing
(cartoon-safe) hearts, daring. A telescope night is wonder; a volcano chase
is adventure. The rest: `cozy` (blankets, lanterns, small safe worlds),
`silly` (giggles, absurd logic, funny failure), `crazy_inventor`
(contraptions, sparks, "what if we tried—", glorious mess).

**Decision: a story carries a tone recipe, not a single tone.** Your
instinct is right — good stories are chords, not single notes. A recipe is
**one dominant tone plus at most one accent tone**, blended by craft rules
that keep it cohesive rather than muddled:

- The **dominant** owns the opening, the landing, and most segments.
- The **accent** enters through a *carrier* — usually one character or one
  recurring element that embodies it. In a `curious_wonder` story with a
  `silly` accent, the wonder belongs to the night sky and the silliness
  belongs entirely to the penguin who keeps mispronouncing "constellation."
  Accent-through-a-carrier is what keeps two tones from smearing into
  neither.
- Never two accents. Recipes like wonder+silly, adventure+cozy (thrills
  with a safe base camp), inventor+wonder are the expected combinations.

**Who sets the recipe:** the topic suggests, the family decides — parent
preference and the child's own track record outrank the topic's default. No
topic locks a tone; there should eventually be a cozy volcano story.

**Decision: choices steer tone — personalization through self-selected
branching, adopted.** Each choice option carries a hidden tone lean. Picking
the daring option turns the dominant up a notch or lets the accent step
forward; the careful option turns it gentler. Tone moves one step per
choice, never leaps, and the age's excitement ceiling and the topic's avoid
list always cap it. Each pick's tone lean is recorded on the
`StoryBranchChoice`, so over many stories the family's records learn the
child's taste — which feeds the *starting* recipe of future stories. The
choices teach us; no quiz ever asked.

## 8. Topics inside a story — and what choices reveal

*For:* how topics shape stories, combine, and what branching can learn
beyond tone. *Input from:* the knowledge graph and the story request.
*Output used by:* outlining; the map and family records (through tags).

**Which tags a story must carry.** **Decision: at least one topic tag total;
everything else is optional and must be earned.** The four axes are an upper
frame, not a quota: a story carries at most one main topic per axis, and
only for axes genuinely present in the story. A pure-play dragon romp may
carry only its story hook. A typical discovery story carries a knowledge
topic and a hook. A feelings or values tag is added only when the story
truly works that theme — never bolted on to look complete.

**Decision: within one axis, one main topic; no mid-story subject changes.
Branches may *visit* a neighbor.** One branch option may step briefly into
an adjacent topic's world — the volcano story's daring path glimpses the
island the eruption built. The visit is tagged as a secondary topic, so the
map records the child touched islands, and the recommendation list can offer
a full islands story next. The child steers wider exploration from inside
the story, without the story losing its subject.

**Decision: choices also reveal *how* a child is curious — not just tone.**
Your observation, adopted: some children reach for the mechanism, some for
the use and the why, some just want to live in the experience. So besides a
tone lean, a choice option may carry a hidden **curiosity lean**:

- `how_it_works` — "should we open the volcano robot and see inside?"
- `what_its_for` — "should we ask the ranger why the town lives so close?"
- `just_experience` — "should we just watch the lava glow until the stars
  come out?"

The pick is recorded on the `StoryBranchChoice` alongside the tone lean.
Over time this learns the child's way of being curious, and future stories
weight their material accordingly — more gears, more why, or more being
there. (The live system already tracks a close cousin of this — its
deepen-vs-widen curiosity style and "the underlying pull" of a child's
interest — so this extends a proven idea rather than inventing one.)

**The three real children, as worked examples:**

- **Friend A** (fashion, dolls, cooking, makeup, the beach, sand): making
  and transforming interests → `romp`, `journey`, and `make_and_build` patterns, cozy/silly
  recipes, "we" adventures about creating things. The graph gaps this
  exposes (no fashion/making-things topics yet) are what the growth recipe
  (Knowledge Graph Policy §8) is for; cooking and the beach land under
  existing food and ocean topics meanwhile.
- **Friend B** (space, aerospace, stars): the deep-diver → deep-dive topics
  under `planets` and `astronauts_and_space_travel`, `curious_wonder`
  dominant, `journey` stories dense with true wow-facts; his choices
  will quickly reveal whether he is a `how_it_works` child or a
  `just_experience` child, and his stories should follow.
- **Friend C** (a new fascination weekly — this week, opera): the
  novelty-seeker → serve one quick story from the nearest existing topic
  (`musical_instruments` / `theater_and_pretending`) with an opera flavor,
  no graph growth until an interest persists. One enchanted week earns a
  story; a lasting fascination earns new topics.

## 9. Which signal controls what

*For:* keeping every input's job separate and debuggable. *Input from:*
family records and parent settings. *Output used by:* the recommendation
job and the story pipeline.

| Signal | Decides | Does *not* decide |
|---|---|---|
| Interest level (`AccountTopicInterest`) | which topics get offered; when the map grows | tone, style, length |
| Choice picks (`StoryBranchChoice`) | tone now and tone taste over time; curiosity style; appetite for visited neighbors | which topics exist |
| Parent settings | starting tone preference; **which value topics rotate into their child's stories**; favorite recurring characters to bring back; anything pinned | what the child picks inside a story |
| The topic's per-age instructions (`GenerationBrief`) | facts, framing, vocabulary, avoid list | tone taste, length |
| Age band | length, vocabulary, choice count, excitement ceiling | topic selection beyond band existence |

**Values: their own stories, or woven in?** **Decision: both, with woven-in
as the default.** Value topics are always real graph topics (they already
are — that axis exists). As *stories*, values usually ride inside knowledge
and play stories: the volcano story quietly carries `keeping_promises`
because the character promised to come back before dark. Occasionally a
story is value-led — a `dilemma` story with the value as its main topic —
for values that deserve center stage. Parents' value picks bias which values
get woven and how often; they never turn stories into sermons (the §10
quality bar applies to value-led stories hardest of all).

## 10. What makes a story good

*For:* the quality bar. *Input from:* everything above. *Output used by:*
the pipeline's quality gates; human reviewers.

**A story does not have to teach.** A pure-play story that is nothing but
joyful nonsense is a full citizen — it still gets tagged on the map (that is
coverage, not curriculum), and joy is why a child comes back. The *library*
mixes: discovery and feelings stories carry the learning; pure-play stories
carry the love of stories. The mix ratio is a config setting.

**The quality bar — every story, every path:**

1. **Pull — the healthy kind.** *Within* a story, segments end on motion
   (something reaching, something not yet solved — `character_want` and
   `dramatic_tension` doing their jobs) so the child wants the next
   segment. But *between* stories, the pull is the warmth left behind: a
   child comes back because stories feel good, never because something was
   withheld. Concretely: every ending resolves fully; no cliffhangers, no
   "come back tomorrow to find out," no streaks, no fear of missing out.
   We are building appetite, not compulsion — your correction, adopted as a
   hard rule.
2. **Real choices.** Both options tempting, both changing what follows,
   different in kind. No option ever punished — the "other" choice leads to
   a different good story, never a scolding.
3. **Concrete and sensory.** Every abstract idea wears a body a child can
   see, hear, or touch; vocabulary from the topic's per-age list appears
   naturally, each new word with a picture built around it.
4. **Feelings handled by age** — shown through body and behavior by
   default; plainly named (paired with shown behavior) where naming the
   feeling *is* the age's learning, per §2.
5. **Warm landing on every path.**
6. **Speakable.** Short complete sentences, readable aloud in one breath;
   the text will be heard, not read.
7. **Safe on every path** — avoid lists, excitement ceilings,
   banned-language rules, cartoon-safety floor, including the daring paths.

**The gates:** outline check → per-segment checks each round (vocabulary,
sentence lengths, safety, continuity, slot consistency) → whole-story
read-through of every path, with every reachable slot-value combination →
human/psychologist review for `inner_weather` and `dilemma` stories until the
gates earn trust.

## 11. After the ending: how one story leads to the next

*For:* the moment a story ends and the child says "again!" or "more!"
*Input from:* the finished playthrough and the family's recommendation
list. *Output used by:* the app's end-of-story moment.

**Decision: invite, never auto-play.** The warm landing lands; then Buju may
offer a bridge — as a question, always the child's (or parent's) call:
"Want to hear what happened when {hero} sailed to the island next door?"
Silence or no is a fine answer, and bedtime settings can turn bridges off
entirely. This is the same anti-compulsion rule as §10.1 wearing its
product hat: the *stories* are warm and complete; the *invitation* is where
continuation lives.

What makes a bridge feel magical rather than mechanical:

- **Carried names.** The hero the child named, the boat they christened,
  the penguin who can't say "constellation" — these live as slot values in
  the family's records and can walk into the next story. Familiar faces are
  the cheapest, most beloved continuity there is.
- **A connector sentence,** generated at serving time from the last
  playthrough: one line that hands the old story to the new one. "The
  volcano was quiet now. But far across the water, {hero} could still see
  that new little island steaming..."
- **The offer comes from the recommendation list,** so a bridge points at a
  neighbor the child brushed in a branch, more of a favorite, or — 
  sometimes — a far topic with a kindred feel. The bridge is the
  recommendation list made warm.

## 12. What a story records

*For:* the contract with the datastore and Workstream C. *Input from:*
§3–§11. *Output used by:* the new story schema, the map, the
recommendation job.

**The story itself** (shared content, one copy for everyone): topic tags
(one main per axis where present + branch secondaries), age band, pattern plan,
telling style, tone recipe, the segment braid (segments, choice points
marked rejoining/splitting, slots), per choice option its spoken text, tone
lean, curiosity lean, slot assignments, and optional neighbor topic. Review
status like topics: draft → reviewed → published.

**Per family** (`StoryPlaythrough` / `StoryBranchChoice`, defined in the
Knowledge Graph Policy §3): which story, who started it, the path walked,
each choice with its tone and curiosity leans, whether it was finished —
plus the family's slot values that persist (the hero's name, the boat).
Family-named characters are family data, never written into shared story
text; the shared text keeps the blank, the family keeps the name.

**The build record — your point about saving the generation logic,
adopted.** Every story stores a `StoryBuildRecord`: everything needed to
explain, debug, and regenerate it — the input topic ids, pattern plan, tone
recipe, telling style, the outline, per-round model and settings, prompt
version, and each gate's results. Two rules keep this safe and useful:

- **Stored as codes, not prose.** The record references versioned
  definitions by id (pattern id, tone ids, prompt version id) rather than
  copying their text. The *meanings* of the codes live in this
  version-controlled repo; a leaked database of build records exposes
  bookkeeping, not the recipe book.
- **Internal only.** Build records are never served to the app and live
  separately from family data.

Today's `stories` table (a flat transcript archive tied to a live
conversation) fits none of this and will be replaced, not extended.

## 13. What to build next, and open questions

*For:* sequencing. *Input from:* this draft. *Output used by:* the next
work sessions.

Yes — next we build the story engine and run it on the real case studies.
Recommended order, chosen so the first pilot needs zero new graph work:

1. **Story schema** in jubu_datastore per §12 (story braid + slots +
   `StoryBuildRecord`), replacing the old table.
2. **The pipeline**: outline → rounds → gates, supporting one-shot too so
   the §5 comparison is cheap.
3. **Pilot 1 — Friend B (space).** The graph already covers it. One
   `journey` story, "we" telling, wonder-dominant recipe, hand-reviewed
   path by path.
4. **Pilot 2 — Friend C (opera-flavored)** from `musical_instruments` /
   `theater_and_pretending` — tests the "nearest existing topic, no graph
   growth" rule.
5. **Graph extension + Friend A's topics** (two-tier schema, then the
   making-things/fashion topics via the growth recipe), then **Pilot 3**.
6. Wire tone/curiosity leans into `StoryBranchChoice` and the bridge offer
   into the recommendation list (with Workstream C).

Open questions gathered from this draft:

- One-shot vs. rounds for the 3-4 band (§5) — decide by blind reading.
- Named-hero rule per age for feelings stories; "we" telling at 3-4 (§6) —
  psychologist.
- The library's fun-vs-learning starting mix (§10).
- Whether a middle choice should ever be splitting in practice, and how
  often the budget allows it (§3) — decide after the pilots.
- How bridges behave at bedtime vs. daytime (§11) — parent settings design.
