# WORKSTREAM A — Knowledge Graph: Schema, Seed Content, Generator Program

> **How to use this doc:** open a Claude (Cowork or Code) session with access to `jubu_datastore`, point it at this file, and ask it to produce the deliverables in §7. This workstream has **no dependency** on the backend/app refactor (Workstream C) — it can run first and in parallel. Its outputs (YAML graph definitions + a generator/validator program) are consumed by Workstream C's tagging API, coverage reports, and the parent-app Topic Map.

## 1. Context

Buju is pivoting from a live conversational companion to a **Story Studio** (see `story-studio-implementation-prompt-v3`, the two-axis model). The Knowledge Graph is the curriculum + dashboard engine:

- Every published story is tagged to graph nodes (**one primary tag per axis per story**, optional secondaries — enforced in the tagging API, this workstream only defines the rule's data shape).
- The parent dashboard renders the graph as a **Topic Map** with togglable axis layers, showing territories explored through stories on this account.
- Coverage reports per age drive Library content planning ("we have nothing on `frustration` for 5-year-olds").
- **Framing constraint:** the graph represents *content coverage*, never child assessment. No "behind/ahead," no scores, no per-child inference. All downstream interaction data keys to `parent_account_id`.

### Existing assets to build on (do not reinvent)

- `jubu_datastore/capability_definitions/{casel,developmental,ngss}/age_5.yaml` + `loaders/capability_loader.py` — an existing YAML-defined, age-banded taxonomy with a loader pattern. **Follow this pattern** (YAML packs + typed loader + validation), and add a crosswalk field so SEL nodes can reference CASEL codes and Domain nodes can reference NGSS codes where they exist.
- `jubu_parent_app/src/types/parentInsight.ts` — framework → subsection → item hierarchy already rendered in the app; the Topic Map will replace its assessment framing but can reuse its shape intuitions.

## 2. Multi-axis schema

Four independent axes. **Axes are not node types within one tree — they are separate layers** that only meet at stories (story↔node mapping is many-to-many across axes).

| Axis | id prefix | What it holds | Examples |
|---|---|---|---|
| `domain` | `dom.` | Knowledge territories | volcanoes, ocean_animals, simple_machines, ancient_egypt |
| `sel_theme` | `sel.` | Social-emotional themes | courage, sharing, frustration, empathy, loss |
| `value_lesson` | `val.` | Parent's "what I want to teach" vocabulary | honesty, perseverance, kindness_to_strangers |
| `story_element` | `elem.` | Discovery hooks, not curriculum | dinosaurs, pirates, space, talking_animals, magic_doors |

Node labels are **canonical topic nouns** (`volcanoes`), never sentences — per `jubu_backend/CLAUDE.md` naming rule 5.

### Node schema (YAML)

```yaml
id: dom.volcanoes
axis: domain
label: volcanoes                # canonical noun, parent-facing display via display_name
display_name: "Volcanoes"
age_bands: [5-6, 7-8, 9-10]     # bands where this node exists at all
age_treatments:                  # PER-YEAR modifiers within the bands (see §3)
  5: {depth: sensory, framing: "big mountains that go BOOM; hot orange rivers", vocabulary: [lava, rumble, smoke], avoid: [death tolls, Pompeii casualties]}
  6: {depth: sensory, framing: "why mountains sometimes explode; lava vs. smoke", vocabulary: [lava, erupt, ash]}
  7: {depth: mechanism, framing: "pressure under the ground; magma vs. lava", vocabulary: [magma, pressure, crust]}
  8: {depth: mechanism, framing: "plate boundaries; why volcanoes cluster", vocabulary: [tectonic plates, vent]}
  9: {depth: system, framing: "ring of fire; volcanoes shaping ecosystems and islands", vocabulary: [geothermal, dormant, extinct]}
  10: {depth: system, framing: "prediction, monitoring, living near volcanoes; historical eruptions handled factually", vocabulary: [seismology, eruption column]}
edges:
  adjacent: [dom.earthquakes, dom.rocks_and_minerals, dom.islands]
  prerequisite: []               # e.g. dom.plate_tectonics might list dom.volcanoes as a gentler entry
crosswalk:                       # optional links into existing frameworks
  ngss: ["4-ESS1-1"]
  casel: []
milestones:                      # DRAFT annotations for the developmental psychologist — leave notes, she edits
  note: ""
  reviewed_by: null
status: draft                    # draft | reviewed | published
```

`depth` is a small named enum per axis, **named by meaning, not index** (CLAUDE.md rule 10). Suggested: `domain`: `sensory → mechanism → system`; `sel_theme`: `naming_the_feeling → navigating_the_feeling → understanding_others`; `value_lesson`: `concrete_example → gray_areas`; `story_element`: usually age-invariant, treatments optional.

### Edge semantics

- `adjacent` — undirected "next territory" suggestions; drives the Topic Map's adjacent-territory hints and the recommender.
- `prerequisite` — directed, sparse, used only where genuinely needed (e.g. `dom.fractions_in_cooking` before `dom.ratios`). Validator enforces acyclicity.

## 3. Age model: band + per-year treatments (decided)

Nodes are **authored at band level** (5–6, 7–8, 9–10 — matches the v3 prompt and the psychologist-review workflow) but carry **per-year `age_treatments`** so the graph *looks different at every age*:

1. **Existence filter:** a node appears in the age-N view iff N falls inside one of its `age_bands`.
2. **Treatment lens:** the age-N view annotates each visible node with its `age_treatments[N]` (fallback: nearest year within band). This changes what story generation is told to do and what the parent sees ("at 6, volcanoes = the BOOM; at 9, volcanoes = the ring of fire").
3. **Edge morphing:** an edge renders in the age-N view only if both endpoints exist at N. Prerequisite edges surface progressively (a 5-year-old view shows no prerequisite chains — everything is an entry point).
4. **Frontier computation:** per account, the recommender marks nodes `explored` (stories played/commissioned on this account tagged to them), `adjacent_frontier` (adjacent to explored), `unexplored`. This is per-account data, computed in parent-api, **not stored in the graph files**.

This gives smooth per-year morphing without forcing the psychologist to review six full graphs — she reviews three band graphs plus per-year treatment lines.

## 4. Seed content targets

Generate a **DRAFT taxonomy** (marked `status: draft` throughout) for psychologist review. Aim for launch-viable coverage, not encyclopedic:

| Axis | 5–6 | 7–8 | 9–10 | Notes |
|---|---|---|---|---|
| domain | ~50 | ~70 | ~80 | Cluster into 8–12 parent-legible regions (Nature, How Things Work, Long Ago, Space, Human Body, …). Regions are display grouping, not schema. |
| sel_theme | ~15 | ~20 | ~25 | Ground in CASEL where crosswalk exists |
| value_lesson | ~12 | ~15 | ~18 | Use parent vocabulary, not clinical terms |
| story_element | ~40 shared | | | Mostly age-invariant; flag the few that aren't (e.g. `elem.mild_spookiness` starts at 7) |

Quality bar per node: real per-year treatments (not copy-paste across years), at least 2 adjacent edges, `avoid` lists wherever a topic has sharp edges (natural disasters, predators, illness, historical violence).

## 5. Generator program

A Python package in this repo: **`jubu_datastore/knowledge_graph/`**, with YAML packs in **`knowledge_graph_definitions/{domain,sel_theme,value_lesson,story_element}/*.yaml`** — mirroring how `capability_definitions/` + `loaders/capability_loader.py` already work. Follow repo conventions: typed loaders, ruff/mypy clean, tests in `tests/`, no magic numbers inline.

### Components

1. **`graph_loader.py`** — load + validate all packs into typed objects (`KnowledgeGraphNode`, `KnowledgeGraphEdge`, `AgeTreatment`). Pydantic or dataclasses matching `dto/entities.py` style.
2. **`graph_validator.py`** — CI-runnable (wire into `.github/workflows/test.yml` like `verify_migrations.py`): unique ids; id prefix matches axis; labels are canonical nouns (lint: no spaces→underscores violations, no sentences); every `age_bands` entry has treatments for its years; adjacency endpoints exist; prerequisite graph is a DAG; no orphan nodes (every node reachable via ≥1 adjacency within its axis+band); banned-language lint on all display strings (`assessment`, `behind`, `ahead`, `score`, `mastery`, …).
3. **`age_view.py`** — `build_age_view(age: int) -> AgeGraphView`: applies §3 rules, returns the exact JSON the parent-api will serve to the Topic Map (`nodes[], edges[], regions[]` with treatments inlined). Also `build_generation_brief(node_id, age)` — the per-node, per-age brief handed to the story-generation pipeline (framing + vocabulary + avoid list).
4. **`coverage_report.py`** — given the graph plus a story→tags mapping (interface only for now; Workstream C supplies real data), emit per-band coverage: nodes with 0 stories, thin regions, over-concentration. CLI: `python -m jubu_datastore.knowledge_graph.coverage_report --age-band 5-6`.
5. **`preview.py` (optional but recommended)** — emit a self-contained HTML preview (force-directed, axis-layer toggles, an age slider 5→10 to eyeball the morphing). This is the admin tool the psychologist reviews with, and a de-risking prototype for the app's Topic Map.

### Definition of "generate"

The seed graphs are **authored by the LLM session, reviewed by humans** — the generator program does not invent nodes at runtime. Its job is loading, validating, age-view projection, coverage math, and preview. Keep node authorship in YAML under version control so psychologist edits are diffs.

## 6. Guardrails

- Never store child-keyed data in or alongside the graph. Account-level exploration state lives in parent-api tables keyed to `parent_account_id` (Workstream C).
- Banned in any parent-facing string this workstream produces: "your child is behind/ahead", "assessment", "development score", any per-child inference. Allowed: exploration, territories, coverage.
- Every YAML node carries `status: draft` until the psychologist flips it; the validator refuses `published` without `reviewed_by`.

## 7. Deliverables for this session

1. `knowledge_graph_definitions/` — full draft YAML packs per §4 targets, all four axes, all bands, per-year treatments.
2. `jubu_datastore/knowledge_graph/` — loader, validator, age-view builder, coverage-report CLI, tests.
3. HTML preview tool (§5.5) + a short `REVIEW_GUIDE.md` for the developmental psychologist (what to check, how to edit YAML, what `depth`/`avoid` mean).
4. A generated sample: `build_age_view(6)` and `build_age_view(9)` JSON outputs checked in as fixtures, demonstrating the per-age morphing.
