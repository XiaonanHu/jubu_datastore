# Story World — recurring cast, regions, and what keeps a child coming back

> **Kind:** policy (DRAFT — decision frame)
> **Status:** open · v3, 2026-08-20 · decisions marked **Decided**
> **Owns:** who recurs across stories, how SEL sits on the map, and what makes a
> child open the next story.

---

## Part 0 — Context you need (read this if you're new)

*Nothing in this section is a proposal. It exists so the document stands alone.*

**Buju** makes branching audio stories for children aged 3–12. A child listens; a
character asks a question; the child picks. 144 stories exist today, 142 narrated.

**The knowledge graph** maps what stories are *about*. 263 topics, each with a
treatment written per year of age — a framing sentence, vocabulary, and things to
avoid. Four axes:

| Axis | Count | What it is | On the map? |
|---|---|---|---|
| `knowledge_domain` | 173 | Things to learn about: volcanoes, bridges, the brain | **yes** |
| `story_element` | 44 | Hooks a child picks: dragons, pirates | **yes** |
| `sel_theme` | 27 | Feelings: frustration, jealousy, being left out | no — see Part 3 |
| `value_lesson` | 19 | Conduct: honesty, fairness, keeping promises | no — see Part 3 |

**A region** is a cluster of topics shown together. Sixteen exist; ten carry real
`knowledge_domain` content: animals (42 topics), nature_and_earth (25),
how_things_work (21), space (18), arts_and_music (18), people_and_places (13),
numbers_and_patterns (11), long_ago (9), plants_and_life (8), human_body (8).

**Topics nest.** A curriculum topic can have deep-dive children via
`subtopic_of` — `insects` → `spiders` → and facets like webs, hunting, senses.
This tree shape matters in Part 4.

**A story** is six segments and two choice points, always this shape:

```
s1 ──▶ choice 1 (rejoins) ──┬──▶ s2a ──┐
                            └──▶ s2b ──┴──▶ s3 ──▶ choice 2 (splits) ──┬──▶ s4a
                                                                       └──▶ s4b
```

Both branches from the first choice rejoin at `s3`. The second choice splits into
two real endings.

**Slots** are blanks a child fills, usually a character's name. The default lives
in the shared library; what a child types lives only in that family's records.
Identity is shared, names are personal.

**The library is universal.** Any child, any story, any order. There is no
story-to-child link in the data. This one rule constrains nearly everything below.

**Tellers** — who narrates. Three: "we" adventure (Buju and the child go
together), named hero (a child-aged character the listener chooses for and names),
storyteller's tale (someone in the frame recounts it).

**Patterns** — what moves a story forward. Eight: journey, mystery,
problem_and_fix, make_and_build, romp, quiet_hour, inner_weather, dilemma. They
are *sampled*, not argmaxed, so one topic doesn't always get the same shape.

**Two tracks.** `mode: library` is the consumer product (2C) — a story need not
teach. `mode: course` is the school product (2B) — one SEL objective, tighter
language bands, a read-along view, and three post-story questions. Same engine,
same world, different rules. See `SEL_COURSE_PLAN.md`.

Other documents, none required to follow this one: `STORY_CREATION_POLICY.md`
(what makes a story good), `STORY_SCHEMA.md` (the JSON shape),
`STORY_GENERATION_WORKFLOW.md` (the build pipeline).

---

## Part 1 — Decided

| | |
|---|---|
| **Cast size** | 7 core characters. 20 total at the absolute most. |
| **Residents** | 2 per region. Not more. |
| **Arcs** | **None.** Stable traits and revealed facets only. A character is the same person every time; different stories show different sides. Nothing depends on reading order. |
| **Callback lines** | Later. Good idea, not now. |
| **Cast definition** | **Not by story function.** By position on a range from instinct to reflection. See Part 5. |
| **Where SEL lives** | **Embedded at a knowledge topic.** SEL never gets its own place on the map. See Part 3. |
| **SEL vs plain stories** | A topic can host both. The SEL story does not displace the ordinary one. |

Settled earlier, during the course build:

- `sel_theme` is the axis for feelings. No parallel SEL taxonomy.
- A story carries **one** SEL objective. The `knowledge_domain` tag is the
  *setting*, never a second thing to test.

---

## Part 2 — Is extending the stories possible?

Yes. The first course story is the proof: a named character, a friend the child
names, a knowledge setting, one SEL objective, validating clean, with narration,
word timings and six illustrations.

What remains is mechanical:

1. Add a `cast` field to the schema — nothing records which characters appear.
2. Author the seven (Part 5).
3. Build `world_definitions/` beside the knowledge graph, same YAML shape and
   validator, cross-linked by id.
4. Generate one region and check whether the shelf goes flat.

The one real question is **the 144 stories that already exist with invented,
one-off characters**. Rewrite them, leave them as an older shelf, or backfill only
the most-played. Your pilot event data says which get played, so this is a cheap
decision rather than a guess.

---

## Part 3 — SEL sits inside the knowledge graph

**Decided.** An SEL course is set at a `knowledge_domain` topic. The child is
exploring nature, or making something, or tasting sweets — and the feeling happens
there. SEL is embedded in a place, never a place of its own.

This is better than the alternatives because a child browsing for fun will pick
volcanoes and will not pick jealousy. Putting feelings on the map as territory
asks a child to go looking for their own difficulty. Hosting them inside real
places means the child goes for the volcano and meets the feeling on the way.

**A topic can carry more than one kind of story.** The same node hosts:

- `mode: library` — the ordinary story. It need not teach anything.
- `mode: course` — the SEL story, one objective, read-along, with questions.

Both are legitimate stories about that topic. The SEL one does not replace the
ordinary one; it is another shelf on the same node.

**Why this makes the school-to-home transfer work.** A child meets Pip at school
in a course story set in `bridges_and_buildings`. At home, the map shows
`bridges_and_buildings` with more stories on it — the ordinary ones. Same place,
same people, no seam. The child does not experience "the school product" and "the
home product." They experience one world they entered from two doors.

### What this changes concretely

**Filenames are currently backwards.** The first course story is
`frustration__age5to6__d1__course__c41a7b.json`, but its setting is
`bridges_and_buildings`. Under this model the file should be named for the host
topic, as every library story is:

```
bridges_and_buildings__age5to6__d1__course__c41a7b.json
```

The SEL theme is a tag inside the file, not the file's identity. **Action: rename
before more course stories exist.**

**`depth` is not the right dimension for this.** Today `d1`, `d2`, `d3` mean
"same topic, deeper." Library and course are not depths of each other — they are
different purposes at the same depth. `mode` already carries that and should stay
the only thing that does.

**SEL becomes a lens, not a location.** The graph already has four independent
layers and the preview already toggles them. Turn on the feelings layer and
knowledge topics glow by which feelings their course stories carry. The child
still browses volcanoes; a teacher sees coverage — *which feelings has this class
actually met?*

### Open

- Does a pure SEL story — no knowledge topic at all — ever exist? Current answer:
  no. Every SEL story gets a setting. Worth confirming.
- Which knowledge topics are good hosts for which feelings? Not every pairing
  works. Frustration fits building and making. Being left out fits anything with a
  group. Worry fits the dark, the deep, the high. This is a real authoring
  question and probably wants a table.

---

## Part 4 — Pull without obligation, and what games actually do

You asked whether a subtree can compose into a storyline that makes sense under
any traversal, and how good games get goal-reaching satisfaction without points.

### The distinction that unlocks it

**An arc** means the character changes and order matters. Rejected, correctly —
random-access library, so an arc punishes the child who started in the middle.

**A pull** is a reason to come back. It needs no order at all.

### What games do, and which ones apply

**Outer Wilds is the closest match to your problem.** No points, no experience, no
gates, no unlocks. You can fly anywhere in the first five minutes. The only thing
that progresses is *understanding inside the player's head*. Its ship log shows
what you know and — crucially — marks places with **"there's more to explore
here."** The pull is an open question the player is holding, not a task list.

That is exactly transferable: a child who has heard three animal stories
understands something the fourth builds on, without the fourth requiring the first
three.

**Hades** advances its story through character conversations that accumulate with
exposure, regardless of whether you won or lost or in what order. That is your
recurring cast with revealed facets, already decided in Part 1.

**Breath of the Wild** puts 120 shrines anywhere, any order, each a complete small
satisfaction. Partial completion feels good. Nothing is missable.

**Obra Dinn** lets you fill a book of fates in any order and confirms answers in
threes, so partial progress is real progress.

**Metroidvania games** gate by ability rather than points — the reward is
*access*, a door you saw earlier now opening. This one I would **not** borrow: it
requires ordering, which is the thing you rejected.

### The four properties that make this work without rewards

1. **Every unit is complete alone.** Each story satisfies on its own. This you
   already enforce — warm landing, fully resolved, no cliffhangers, on every path.
2. **The pull is an open question, not an unfinished task.** "There is more down
   there" invites. "You have 8 of 12" obliges.
3. **What accumulates lives in the child, not in a save file.** Understanding and
   familiarity, not a counter.
4. **Depth is visible before it is entered.** A child should be able to *see* that
   `spiders` sits under `insects` and that it goes further down.

### So: can a subtree be a storyline?

**Yes — if what the subtree shares is a place and a cast, not a sequence of
events.**

And here is the part I think answers your BFS/DFS question directly: **the tree
shape already supplies the narrative, if you make it visible.**

- **Going down** (`insects` → `spiders` → webs) *is* a felt experience. The child
  is going deeper into one thing. No gate needed — the nesting is the story.
- **Going across** (`spiders` → `ants` → `bees`) is a different felt experience —
  seeing how wide a world is.

A child does not need to be told which they are doing. They need the map to show
it. Down should look like down.

That means the pull is a **map problem, not a plot problem** — and your map
already does most of it, with story-less topics rendered as pale "coming soon"
stars a parent can vote for. Visible absence is a draw. Coverage is a progress bar
that doesn't look like one.

### If you want more than that

**A destination per region.** Each region has a place its stories are heading —
the Deep Burrow, the top of the mountain, the far side of the sea. Every story
mentions it in passing. When a child has heard enough, the arrival story appears.

The gate is a **count, not a sequence**: any six of the twelve animal stories, in
any order. Random access survives, the child gets a real ending, nothing is
missable. This is Breath of the Wild's shrine logic with a story instead of a
reward.

**What to avoid.** Cliffhangers, ongoing mysteries, anything a child can be
*behind* on. A child who does four of twelve should feel they had four good
stories, not that they abandoned something.

**Recommendation.** Build the cast first — it is most of the pull and it comes
free with Part 5. Make the tree shape visible on the map second. Try destinations
only if those two aren't enough.

---

## Part 5 — The cast, and the consciousness question

You asked me to list the layers, because you remembered there being more than two.
There are — and they come from different models that get conflated.

### The models

**Freud's structural model — three parts.** This is the one you're reaching for.

| | What it wants | In a person |
|---|---|---|
| **id** | Now. Pleasure, impulse, appetite. No patience, no plan. | The small child who grabs |
| **ego** | What actually works. Negotiates between wanting and reality. | The practical one who finds a way |
| **super-ego** | What is right. Conscience and ideals — **and the inner critic.** | The voice that judges |

**Freud's topographical model — also three, and different.** Conscious,
preconscious, unconscious. About what you can *access*, not what you *want*.
Frequently mixed up with the structural model. Not useful for a cast.

**Jung.** Ego, personal unconscious, collective unconscious — plus archetypes:
persona, shadow, anima/animus, and the Self. The **Self** is Jung's integrated
whole, and the "wise old" figure belongs here.

**Transactional Analysis (Berne) — Parent, Adult, Child.** Three ego states, and
for your purposes **the most useful of the lot**, because it is explicitly about
how people *relate to each other* — which is what a cast does. Anyone can be in
any state at any moment; a grandparent can be in Child, a five-year-old can be in
Parent. That flexibility is what stops a cast becoming a set of labels.

### One correction worth making before you author anything

**Super-ego is not wisdom. It is the internal critic.**

If you map grandparents onto super-ego, you get a scold — the character who tells
you what you should have done. That is not the elder you want, and for an SEL
product it is actively wrong: your own SEL node for frustration lists *"shaming
the feeling"* and *"adults dismissing it"* in its avoid list.

The wise elder you're imagining is closer to Jung's **Self** — integrated, has
been through it, no longer needs to perform. Warm, not judging.

So: keep the instinct → reflection range as your design axis, borrow Freud for the
*bottom* of it, and take the top from Jung rather than from super-ego.

### Proposed spine for the seven

Seven positions on one range. Ages are a *tendency*, not a rule — the exceptions
are what make the cast interesting.

| # | Position | Wants | Typical age | In a scene |
|---|---|---|---|---|
| 1 | **Impulse** | Now, all of it | youngest | Acts before thinking. Starts the trouble and the fun. |
| 2 | **Appetite with a plan** | Now, but cleverly | young | Wants the same thing, has worked out a route |
| 3 | **Trial and error** | To make it work | middle | Tries, fails, tries differently. The engine of most stories. |
| 4 | **Negotiator** | Everyone to get some | middle | Sees both sides. Where compromise lives. |
| 5 | **Keeper of the rule** | Things done properly | older child / young adult | The fairness voice — and the one who can be *too* rigid |
| 6 | **Steward** | The others to be all right | parent-aged | Holds the frame. Notices who is struggling. |
| 7 | **The one who has been through it** | Nothing, for themselves | eldest | Warm, unhurried, unshockable. Offers, never imposes. |

Two exceptions to build in deliberately, or the cast is a stereotype:

- one small character who sees what everyone else missed
- one elder who still wants to run

### Your casting idea — yes, and it's the mechanism

You said: give each character existing characteristics as a template, then work out
which one leads which stories and which SEL courses. **That is exactly what makes
the cast structural rather than decorative.**

A character's disposition decides which feelings they are the natural protagonist
for. Sketch:

| SEL theme | Natural lead | Why |
|---|---|---|
| frustration, anger | **1 Impulse** | Feels it hardest, fastest. Pip. |
| calming_down | 1 with 7 present | Needs someone unhurried nearby |
| sharing, fairness | **5 Keeper of the rule** | It's their subject — including when they get it wrong |
| jealousy, winning_and_losing | **2 Appetite with a plan** | Wants, compares, schemes |
| worry, shyness | **3 Trial and error** | Hesitates before trying |
| being_left_out, friendship | **4 Negotiator** | Lives at the boundary between people |
| handling_mistakes, saying_sorry | **3 or 5** | Failure and rule-breaking respectively |
| empathy, helping | **6 Steward** | Their default state |
| self_doubt, independence | **older child** | Needs enough self to doubt |
| loss, big_changes | **7** present, child leading | The one who has been through it |

Two rules that fall out of this:

> **A character leads the feelings they are worst at, not best at.** The Keeper of
> the Rule is the interesting lead for a fairness story precisely because they
> will over-apply it. A character who is already good at the lesson has no story.

> **The cast never owns the protagonist in `named_hero` stories.** In those the
> child names the lead — that naming *is* the authorship. Companions, guides,
> rivals, witnesses. Never the hero.
>
> **Exception, deliberate:** in `mode: course` stories a cast member *is* the
> protagonist. The child's role there is witness, and the distance is the
> mechanism — your own policy says it is easier to help *Mira* with her jealousy
> than to be told about your own.

---

## Part 6 — Loose ends

**Blocking:**

- **L1. The seven, actually written.** Names, dispositions, voices, the two
  exceptions. Everything else waits on this.
- **L2. Cast arithmetic.** 7 core + 2 residents × 10 regions = 27. You said 20 max.
  Share residents between neighbouring regions, or give them only to the big ones
  (animals at 42 topics earns two; human_body at 8 may not).
- **L3. `cast` field in the schema.** Nothing records which characters appear.
- **L4. `world_definitions/` registry.** Proposed in v1, still not built.

**Not blocking, but real:**

- **L5. Do `sel_theme` and `value_lesson` merge?** You asked twice; here is an
  answer. **Don't merge the axes — give them a shared spine.** They are genuinely
  different: SEL is what happens *inside* a child, values are how a child *treats
  others*. But the overlap is real — `saying_sorry` (SEL) and `admitting_mistakes`
  (value) are nearly the same story. Map both onto CASEL's five domains as a
  crosswalk. Then a course says "this is Self-Management" without caring which
  axis the node lives on, and near-duplicates become visible because they land in
  the same cell.
- **L6. Host-topic pairing table.** Which knowledge topics host which feelings
  well (Part 3).
- **L7. Illustration at cast scale.** The repeat-the-prompt anchor works for two
  characters in one room — proved on the tower story, though the trousers changed
  colour once and the blocks changed shape twice. Seven to twenty characters
  across ten regions needs **reference images**: two or three approved pictures per
  character passed into every generation. Different API call. Worth knowing before
  the cast is finalised.

**Open, no proposal:**

- Does the cast reach the live voice product, or stay library-only? If Buju in
  conversation knows these characters, they stop being a content device and become
  part of the companion. Much bigger claim, much bigger surface.
- Who authors the seven — by hand, or generated then curated? The core seven seem
  worth doing by hand.
- Does the psychologist review the cast? A recurring character a child forms an
  attachment to is a stronger developmental object than any single story. That
  argues yes, and it has a cost.

---

## Part 7 — Order of work

1. Write the seven (L1). Names, dispositions, the two exceptions.
2. Cast arithmetic (L2), which falls out of 1.
3. `cast` field and `world_definitions/` (L3, L4). Mechanical once 1 is done.
4. Rename the course story to its host topic (Part 3).
5. Author one region end to end. `space` is a good candidate — 18 topics, small
   enough to finish, popular enough to be worth it.
6. Look at whether the shelf went flat: the craft gate's formula detector and the
   multi-model review bench will tell you whether a fixed cast cost you variety.
7. Only then: residents, destinations, and the retrofit question.
