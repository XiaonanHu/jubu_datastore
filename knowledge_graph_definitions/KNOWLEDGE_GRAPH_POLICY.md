# Knowledge Graph Master Policy

**What this document is.** The rulebook for everyone — developers, AI
sessions, and reviewers — who works on the Story Studio knowledge graph. Read
it before adding topics, changing the schema, or building anything that uses
the graph. When this document and an older prompt disagree, this document
wins.

**How to read it.** Every defined record type appears in `code font` and is
defined once, in §3. After §3, the plain word **topic** always means one
`KnowledgeGraphNode` — they are the same thing; "topic" is just the readable
word. Anything that is an idea under discussion (not a committed design) is
marked **[open design note]**.

**Every section below starts with three lines: what it's for, who provides
the input, and who uses the output.**

---

## 1. Where to find things

*For:* finding the important files. *Input from:* n/a. *Output used by:*
anyone working in this repo.

| What | Where |
|---|---|
| This policy | `knowledge_graph_definitions/KNOWLEDGE_GRAPH_POLICY.md` |
| Reviewer's guide (for the psychologist) | `knowledge_graph_definitions/REVIEW_GUIDE.md` |
| Graph content (YAML, one folder per axis) | `knowledge_graph_definitions/{knowledge_domain,sel_theme,value_lesson,story_element}/` |
| Schema (the `KnowledgeGraphNode` definition) | `knowledge_graph/graph_schema.py` |
| Loader / registry | `knowledge_graph/graph_loader.py` |
| Validator (all graph rules, runs in CI) | `knowledge_graph/graph_validator.py`, run via `python scripts/verify_knowledge_graph.py` |
| Per-age projection + story-generation briefs | `knowledge_graph/age_view.py` |
| Coverage report (which topics have stories) | `knowledge_graph/coverage_report.py` |
| Interactive map preview (open in a browser) | `knowledge_graph_definitions/preview/knowledge_graph_preview.html`; regenerate: `python -m jubu_datastore.knowledge_graph.preview` |
| Example age-view JSON | `knowledge_graph_definitions/samples/` |
| Tests | `tests/test_knowledge_graph_*.py` |
| CI wiring | `.github/workflows/test.yml` (last step) |
| Story Creation Master Policy | `jubu_datastore/story_definitions/STORY_CREATION_POLICY.md` |
| Naming rules (apply here too) | `jubu_backend/CLAUDE.md` |
| Family records (exploration, choices, recommendations) | **Not in this repo** — app-backend tables, Workstream C; requirements in §7 |

## 2. The big picture: one shared graph, many family records

*For:* the one architectural rule everything else follows from.
*Input from:* this design conversation. *Output used by:* every other section.

Picture a game world map with fog of war: there is **one world map, the same
for all players**, and each player has **their own fog** — what they have
explored, what is dimly visible nearby, what is still hidden.

We keep these as two strictly separate kinds of data:

**The shared graph** (this repo). Which topics exist, what each topic means
at each age, and how topics connect. Written by developers and AI sessions,
reviewed by the psychologist, stored as YAML under version control. Identical
for every family. Contains zero information about any child or family — the
validator even rejects evaluation-flavored wording.

**Family records** (app-backend database, keyed by `parent_account_id`).
One family's journey through that shared map: which topics they explored,
which stories they played, which branch each child picked, which suggestions
we showed and what they did with them. Written by the app as families play;
read by the recommendation job and the parent dashboard.

The one rule: family records refer to topics **by id string**
(`knowledge_domain.volcanoes`) and never copy or extend the
`KnowledgeGraphNode` class. A topic definition must never grow family fields.

The Topic Map screen in the app = the shared graph, drawn through one
family's fog.

## 3. Definitions

*For:* the exact names to use in code, docs, and PRs — one name per concept.
*Input from:* this design. *Output used by:* everyone; drift from these names
is treated as a bug.

### Shared-graph records (this repo, implemented unless marked)

| Name | Plain meaning | Written by | Read by |
|---|---|---|---|
| `KnowledgeGraphNode` | One topic: its label, per-age treatments, connections, review status. The plain word "topic" in this doc always means one of these. | Developers/AI sessions, edited by the psychologist | Everything |
| `AgeTreatment` | How one topic should be handled at one age: depth, framing sentence, vocabulary, things stories must avoid. | Same as above | Story generation, the app |
| `AgeGraphView` | The whole graph filtered to one age — what the app backend serves to the Topic Map. | Built by `age_view.py` | App backend |
| `GenerationBrief` | The instructions handed to story generation for one topic at one age. | Built by `age_view.py` | Story generation |
| curriculum topic | A topic with `tier: curriculum`: the default map, full per-age treatments, reviewed. *(tier field pending)* | — | — |
| deep-dive topic | A topic with `tier: deep_dive`: a fine-grained child of a curriculum topic (`spider` under `insects`), revealed when a family expands it. *(pending)* | — | — |
| facet | One aspect of a deep-dive topic, as a plain list entry ("webs" on `spider`). Lets ten spider stories be ten different stories. *(pending)* | — | — |

### Family records (app backend, Workstream C — vocabulary agreed here, built there)

| Name | Plain meaning | Written by | Read by |
|---|---|---|---|
| `AccountTopicExploration` | For one family and one topic: explored / one-step-away / still-hidden, whether they expanded it, story count, first/last played dates. | App backend, as stories are played | Topic Map, recommendation job |
| `AccountTopicInterest` | For one family and one topic: a number for **how much the child seems to enjoy this topic lately**. Rises with plays, replays, expansions, explicit requests; fades over weeks when untouched. It measures enjoyment only — never how "good" a child is at anything. | Recommendation job (background) | Recommendation job, parent dashboard |
| `StoryPlaythrough` | One play of one story by one family, including who started it: `child_pick` / `parent_pick` / `recommendation` / `replay`. | App | Recommendation job, dashboard |
| `StoryBranchChoice` | One decision at one branch point inside one playthrough. | App | Recommendation job, story generation (for variety) |
| `RecommendationList` | One ready-to-show, ranked list of suggested next topics for one family, prepared in the background so opening the app is instant. | Recommendation job | App (home screen), and written back to with outcomes |
| `RecommendationListEntry` | One suggestion on that list: topic id, rank, the stated reason it was suggested (§7.2), and what happened to it (accepted by child / accepted by parent / dismissed / expired). | Recommendation job; outcome by app | Recommendation job (it must not re-show a fresh dismissal) |
| `GraphGrowthRequest` | A queued request to create new shared content because one family's child is running out of map (§7.3). Carries the boundary topic and aggregate counts — never the child's identity. | Recommendation job | Content pipeline (§6, §8) |

## 4. What one topic looks like

*For:* the structure and categorization of a `KnowledgeGraphNode`.
*Input from:* authors (developers/AI sessions). *Output used by:* the
validator, story generation, the app.

- Id = axis name + `.` + label: `knowledge_domain.volcanoes`,
  `sel_theme.courage`, `value_lesson.honesty`, `story_element.dragons`.
  Labels are short snake_case nouns, never sentences. No abbreviations.
- Age bands `3-4`, `5-6`, `7-8`, `9-10`, with one `AgeTreatment` per year.
  (The 3-4 band exists in the schema; its content is not written yet. When
  writing it, use the youngest depth level and shorter, simpler framings.)
- Depth ladders per axis: knowledge_domain `sensory → mechanism → system`;
  sel_theme `naming_the_feeling → navigating_the_feeling →
  understanding_others`; value_lesson `concrete_example → gray_areas`;
  story_element has no ladder.
- Connections: `adjacent` (two topics that make natural neighbors on the
  map; undirected) and `prerequisite` (rare, directed: "this one first").
  Regions are display grouping only.
- **`status` records editing progress, not usage**: `draft → reviewed →
  published`; `published` requires `milestones.reviewed_by`. There is
  deliberately no `used` status, because "used" immediately asks "used by
  whom?" — that is family data, and the coverage report computes it on
  demand. Mixing usage into these reviewed files would make them change with
  daily traffic.

### The categorization dimensions of a topic (complete list)

| Dimension | Question it answers | Values |
|---|---|---|
| `axis` | What kind of learning is this? | knowledge_domain / sel_theme / value_lesson / story_element |
| `region` | Where does it sit on the map, in parent-friendly terms? | e.g. nature_and_earth, fantasy_and_magic |
| `tier` | Default map or expandable detail? | curriculum / deep_dive *(pending)* |
| `label` | What is the topic, in one noun? | e.g. volcanoes, spider |
| `depth` (per year) | Which lens at this age? | that axis's ladder |
| `facets` (deep-dive only) | Which aspects can stories rotate through? | e.g. spider: webs, hunting, senses *(pending)* |

We deliberately stop here. No formal ontology (no is-a hierarchies beyond
`subtopic_of`, no attribute-relation triples): every extra dimension costs
psychologist review time and validator complexity, so a new dimension must
name the code that will consume it before it gets added.

## 5. Two sizes of topics

*For:* deciding whether something becomes a curriculum topic, a deep-dive
topic, or no topic at all. *Input from:* anyone proposing topics.
*Output used by:* §6 and §8.

**The test:** does this subject earn its *own* per-age treatments and its own
avoid list — or would they be a copy of its parent category? Only the former
becomes a curriculum topic.

- **Curriculum topics** (~183 today): the default map every family sees.
  Full per-age treatments, at least 2 `adjacent` connections, reviewed.
  Individual species or characters do not belong here: a seal story is
  generated under `ocean_animals`, and the seal is the story's own choice.
- **Deep-dive topics** (pending schema): for the child who wants everything
  about spiders, then ants, then bees. Each points at exactly one curriculum
  parent via `subtopic_of`, inherits the parent's bands/treatments/avoid list
  as fallback, and only writes what is distinctive plus its `facets`. Lighter
  validation, reviewed in a batch together with the parent, counted inside
  the parent in coverage reports.

## 6. How the shared graph grows

*For:* the rule that growth is always shared, and what triggers it.
*Input from:* aggregated family demand (§7.3) or planning decisions.
*Output used by:* content authors (§8), then every family.

**All growth is shared-graph growth.** Even when one specific child's
enthusiasm triggers it, the new topics join the one shared map — reviewed
once, safe for everyone, useful for every future child with the same
enthusiasm. There is no per-family graph. What is per-family is *whether and
when the new topics are shown* (§7.3). Personalization = visibility, never
existence.

The cycle: family demand accumulates (topic-level counts only — family
identity never reaches content work) → authors write deeper (new deep-dive
topics under the hot topic) and wider (more stories on the topic's existing
`adjacent` neighbors) → everything lands as YAML here, `status: draft`,
validator-clean, then psychologist review → topics whose deep-dive children
get crowded are promoted into curriculum topics of their own.

Topics are never created at serving time. The programs in
`knowledge_graph/` only load, validate, project, and report.

## 7. Personalization: what the family records must make possible

*For:* the three product behaviors, and which records carry each.
*Input from:* family records (§3). *Output used by:* Workstream C as its
requirements; the app's home screen and Topic Map.

### 7.1 A ranked list of "what next", where parent or child picks

Every family walks the map on their own path. The background recommendation
job prepares a `RecommendationList`: suggested next topics, ranked, most
important first. Either the parent or the child picks from it (or ignores it
and picks from the map directly). Who picked is recorded — on the entry's
outcome, and as `initiated_by` on the resulting `StoryPlaythrough` — because
a parent's pick and a child's pick are different signals and neither should
silently overwrite the other.

The ranking is fed by `AccountTopicInterest` (what the child has been
enjoying lately) and `AccountTopicExploration` (what is already explored vs
one step away).

### 7.2 Open-the-app suggestions: mostly familiar, sometimes far

Each prepared `RecommendationList` mixes near and far. Every entry carries
one stated reason:

- `more_of_a_favorite` — deeper into a topic the child clearly enjoys (a
  deep-dive child, or a fresh story on it);
- `one_step_away` — a map neighbor of something explored;
- `different_topic_similar_appeal` — a topic far from everything explored
  **but chosen for a stated connection**: it tends to delight children in
  the same way the child's favorites do (same kind of wonder, similar way of
  engaging). Never a random jump — the connection is recorded on the entry;
- `parent_suggested` — pinned by the parent, always shown distinctly.

Every list contains at least one `different_topic_similar_appeal` entry so a
child's world keeps widening. The near/far mix is a tunable setting (config,
not code).

**[open design note]** How to compute "similar appeal": start by taking
candidate topics at moderate map distance (far, but not maximally far), then
score them by similarity of *how the topic is enjoyed* rather than what it is
about — for example, embedding similarity between short descriptions of each
topic's learning style or feeling. Not committed; needs experiments and
tuning. Until then a hand-made "kindred topics" table is an acceptable
placeholder.

Lists are prepared in the background (nightly and after notable events), so
opening the app is a fast read. Past entries keep their outcomes so the job
never re-shows something freshly dismissed.

### 7.3 Growing the map ahead of a fast explorer

When a child keeps asking for more at the edge of what exists (a
high-interest topic whose neighbors are all explored and whose deep-dive
children are exhausted), the recommendation job files a
`GraphGrowthRequest`. The content pipeline picks it up **offline**: new
deep-dive topics and stories are authored through the normal §6/§8 route —
shared, reviewed — and when they land, the requesting family's map
pre-expands that area and their next `RecommendationList` features it as
`more_of_a_favorite`. To the family it feels personal; in the files it is
ordinary shared growth.

The same record with `reason: predicted` covers growing ahead of a child who
has *not* hit the edge yet but is clearly heading somewhere — one pipeline,
not two.

## 8. Recipe: generating one piece of the graph for one child's interests

*For:* the step-by-step procedure for demand-driven authoring.
*Run by:* **a developer (or an AI session a developer starts) — today this
is manual.** Later, the content pipeline runs it automatically off the
`GraphGrowthRequest` queue. Parents and children never run this; their
behavior only creates the demand signals.
*Output used by:* the shared graph (new YAML), then the psychologist (review).

**Inputs allowed:** interest subjects as plain nouns ("insects", "trains"),
an age or band, optionally which axes. **Never** the child's name, account,
or any identifying detail — not in YAML, not in notes, not in commit
messages.

1. Match each interest to existing curriculum topics (search the YAML; the
   registry is the source of truth). Only if nothing fits, apply the §5 test
   before creating a new curriculum topic.
2. Write 6–8 deep-dive topics under the matched curriculum topic: the
   distinctive framing, `facets`, and any extra avoid entries; everything
   else is inherited. (Requires the pending tier schema — build it first.)
3. Connect the new deep-dive topics to each other with `adjacent`, and check
   the parent's existing neighbors already offer the "go wider" path.
4. Follow every rule in §9. Everything lands as `status: draft`.
5. Run `python scripts/verify_knowledge_graph.py`; fix until clean. If code
   changed, run the full gate (ruff, mypy, pytest).
6. Regenerate the preview; regenerate sample JSON if views changed.
7. Put open questions for the psychologist in `milestones.note`.

## 9. Writing rules for all topics

*For:* the non-negotiable quality bar. *Input from:* authors. *Output used
by:* the validator (most rules are enforced automatically).

- Naming: id = axis + label; labels are short nouns (≤5 words); no version
  suffixes; `jubu_backend/CLAUDE.md` rules apply.
- Treatments: each year genuinely different (no copy-paste); vocabulary 2–5
  age-appropriate words; framings guide story generation *and* are shown to
  parents.
- `avoid` lists are required wherever a subject has sharp edges (predators,
  illness, death, disasters, historical violence, fear).
- Banned in all display text (validator-enforced): assessment, mastery,
  score, milestone, "your child", is/are/falling behind, ahead of, delayed,
  gifted, grade level. The same spirit applies to family-record naming:
  interest means enjoyment, never ability.
- Connections: every curriculum topic has ≥2 `adjacent` neighbors, at least
  one in each of its age bands; connections never cross axes; prerequisites
  stay rare and cycle-free.
- Sensitive feelings/values content keeps its established guardrails (e.g.
  `kindness_to_strangers` never undermines stranger-safety rules; `loss`
  avoids graphic death and dying-parent plots).

## 10. What happens next (in order)

*For:* sequencing the follow-up work. *Input from:* this design. *Output
used by:* whoever runs the next sessions.

1. **Tier schema extension**: `tier`, `subtopic_of`, `facets`, inheritance,
   relaxed validation for deep-dive topics, map-distance helper, preview
   expansion, tests.
2. **First interest-seeded piece of the graph** per §8 (real case: one
   child's interests, given as subjects + age only).
3. **Story creation master doc** — drafted: see
   `story_definitions/STORY_CREATION_POLICY.md` (branch structure, tagging
   rules, tone, quality gates; defines what `StoryPlaythrough` and
   `StoryBranchChoice` must record).
4. **Family-records master doc for Workstream C**: table designs and update
   rules for every §3 family record, list-mix and interest-fade tunables.
   §7 is the requirements; that doc is the implementation spec.
5. **3-4 band content** for a starter subset of curriculum topics.
6. **Pilot review round** with the psychologist using the preview.
7. Wire real story-tag data (Workstream C) into the coverage report.
