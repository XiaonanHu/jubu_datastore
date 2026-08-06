# Knowledge Graph — Reviewer's Guide

> Policy and growth rules for people *extending* the graph live in
> `KNOWLEDGE_GRAPH_POLICY.md`; this guide is for reviewing content.

For the developmental psychologist reviewing this draft taxonomy. Everything in
this folder is `status: draft` and was machine-authored for you to correct —
edit freely; your edits are tracked as ordinary file diffs.

## What this is (and is not)

The graph maps **story content territories** across four independent layers:

- `knowledge_domain/` — knowledge territories (volcanoes, ancient Egypt)
- `sel_theme/` — social-emotional themes (frustration, courage)
- `value_lesson/` — things parents want to teach (honesty, perseverance)
- `story_element/` — discovery hooks kids pick (dragons, pirates); not curriculum

It describes **what stories exist about**, never a child. There are no scores,
no "behind/ahead", no per-child inference anywhere — the validator rejects
that language automatically.

## How to review

Open `preview/knowledge_graph_preview.html` in any browser (no internet
needed). Use the age slider to watch a territory change from 5 → 10, toggle
the four layers, and click any node to read its per-age treatment. Then edit
the corresponding YAML file and ask an engineer to regenerate the preview
(`python -m jubu_datastore.knowledge_graph.preview` — or just send them the
YAML edits).

Per node, please check:

1. **Age bands** — should this topic exist at this age at all? Bands are
   `5-6`, `7-8`, `9-10`; remove or add a band and its treatment years together.
2. **Per-year treatments** — `age_treatments` has one entry per year. Does the
   `framing` (one sentence of story-generation guidance, also shown to
   parents) fit the year? Do the six years actually progress?
3. **`depth`** — the named lens ladder per layer:
   - knowledge_domain: `sensory` (what it looks/feels like) → `mechanism` (how it works)
     → `system` (how it connects to everything else)
   - sel_theme: `naming_the_feeling` → `navigating_the_feeling` →
     `understanding_others`
   - value_lesson: `concrete_example` → `gray_areas`
   - story_element: no ladder (hooks, not curriculum)
4. **`avoid`** — the do-not-include list for story generation wherever a topic
   has sharp edges (predators, illness, loss, disasters, historical violence).
   This is the highest-value field for you to tighten.
5. **`vocabulary`** — 2–5 words a story at that age should use naturally.
6. **Edges** — `adjacent` = "next territory" suggestions on the parent map;
   `prerequisite` = rare "gentler entry first" links (e.g. fractions before
   ratios). Flag any that feel wrong.

Open questions we left for you are in `milestones.note` on the node — search
the YAML files for `note: "` with text after it.

## How to edit

Edit the YAML in place. Keep these invariants (CI enforces them):

- `id` = axis name + `label` (`knowledge_domain.volcanoes`,
  `sel_theme.courage`); labels are snake_case topic nouns, never sentences.
- Every year inside a node's bands needs an `age_treatments` entry
  (story_element excepted).
- When you're satisfied with a node, set `status: reviewed` and put your name
  in `milestones.reviewed_by`. (`published` is refused without `reviewed_by`.)
- Don't write "assessment", "score", "mastery", "is behind", "ahead of" etc.
  in display text — the validator will flag it.

An engineer can check your edits any time with
`python scripts/verify_knowledge_graph.py`.
