# WORKSTREAM B — Story Templates: Swappable Names & Characters

> **How to use this doc:** input to both content generation (Cowork sessions that write Library stories) and Workstream C (which implements the data model and instantiation code). Read `KNOWLEDGE_GRAPH_WORKSTREAM.md` first — every template is tagged to graph nodes and generated against a per-age brief (`build_generation_brief`).

## 1. Why templates

Every story is authored as a **template with typed slots** rather than a fixed text. One gated story then yields many personalized variants — swap the hero's name to the child's, swap a sidekick for the family dog — making Library content feel commissioned, and making Commissioned content reusable. Crucially, this makes personalization **cheap and safe**: the expensive Publishing Gate runs on the template; instantiation is deterministic substitution, not generation.

Two-layer model:

- **`StoryTemplate`** — the gated artifact. Full text (or branch tree) with slot placeholders, slot registry, default cast, graph tags, style profile, provenance. Versioned + immutable once published (corrections publish a new version).
- **`StoryInstance`** — a rendering of a template with a concrete cast, belonging to one family shelf (or to the Library's default cast). No LLM involved.

## 2. Slot grammar

Placeholders in template text: `{{slot_id}}` plus derived forms.

```yaml
slots:
  hero:
    kind: character
    archetype: brave_kid           # constrains what can fill it
    default: {name: "Milo", pronouns: he_him}
    swappable: [name, pronouns]    # species/role are NOT swappable — they'd break the plot
  sidekick:
    kind: character
    archetype: loyal_animal_companion
    default: {name: "Pip", species: squirrel, pronouns: she_her}
    swappable: [name, species, pronouns]
  hometown:
    kind: place
    default: {name: "Maple Hollow"}
    swappable: [name]
```

Derived forms handle grammar without free generation: `{{hero.name}}`, `{{hero.they}}/{{hero.them}}/{{hero.their}}/{{hero.theirs}}`, `{{hero.they_verb:run}}` (→ "he runs"/"they run"). Pronoun sets are a **fixed enum** (`he_him`, `she_her`, `they_them`); the renderer conjugates from a small table. No other inflection machinery in v1 — authors must write sentences that survive substitution (the template lint checks every slot's derived forms are drawn from this set).

**Authoring rule for audio efficiency:** keep slot mentions in short, self-contained sentences where feasible, and never inside rhymes or wordplay that depend on the default name's sound. Lint warns when a slot appears in a sentence > 20 words.

## 3. What may fill a slot

Substitution values come from two sources, with different safety treatment:

1. **Vetted value sets** — curated cast packs (names, species, places) shipped with the product. Instantiation from packs requires no re-review.
2. **Family-provided values** (child's name, pet's name, "Grandma Rosa's house") — parent-entered at commissioning/recast time. These pass a **name-safety lint** (profanity/PII-pattern/length checks + TTS pronounceability heuristic), not the full gate. Parent sees a preview before the instance is created.

**Compliance note (do not blur this):** a hero sharing the child's name is *parent-directed content personalization*, which is allowed. It must never interact with the narrator-not-friend rule: the narrator never addresses the listener, never says "just like you," never greets by name. The string lint from the v3 prompt applies to template text; add `"just like you"` and second-person address outside dialogue to the banned list for templates.

## 4. Gate and provenance implications

- The **full Publishing Gate** (generate → evaluate → revise → publish, safety + style-adherence evals) runs on the template rendered with its **default cast**, plus a **slot-stress render**: an adversarial render using the longest/most awkward vetted values, to catch sentences that only work with "Milo."
- For **branch trees**, the whole tree is one template; every leaf path is gate-evaluated; slots are consistent across branches.
- Gate provenance records (`prompt_version, model, eval_scores, reviewer, timestamp`) attach to the **template version**. Instances record `{template_version_id, cast, rendered_at, renderer_version}` — enough to reproduce any audio a child heard.
- Instantiation triggers **TTS re-render** of affected audio. v1: re-render the full story per instance (async commissioning already tolerates ~30s; show the progress loop). Optimization for later, enabled by the authoring rule in §2: segment audio at sentence boundaries and re-render only slot-bearing sentences.

## 5. Relationship to Community de-personalization (Phase 2)

Templates make the mandatory de-personalization stage nearly free: a commissioned story is *already* a template + family cast. "Publish to community" = strip the family cast, restore/choose a default cast, have the parent review the default-cast render, re-run the gate on it. The de-personalization pipeline in the v3 prompt reduces to **cast removal + a sweep for family specifics that leaked into non-slot text** (that sweep still needs an LLM pass + parent approval — names appear in prose the author didn't slot).

## 6. Data model (implemented in Workstream C, stated here for alignment)

`story_templates` (template + slot registry + tags + style, versioned) → `story_template_versions` (immutable text/tree + gate provenance) → `story_instances` (cast + owning `parent_account_id` + shelf) → `audio_assets` (per instance, per segment). The existing `stories` table (`jubu_datastore/story_datastore.py::StoryModel`) is modeled for live-captured conversation stories (NOT-NULL `conversation_id` FK, no status/audio/provenance) and does **not** fit; Workstream C decides migrate-vs-replace.

## 7. Deliverables when authoring content with this spec

1. Each story delivered as template YAML: metadata (graph tags — one primary per axis; age band; style profile id; interaction shape: linear or branch tree), slot registry, template text with placeholders, default cast.
2. A cast pack file: ~40 vetted first names (diverse, TTS-friendly), ~15 animal companions, ~15 places.
3. Template lint checklist run before handoff: all placeholders registered; derived forms valid; no banned strings; slot-stress render reads naturally; branch trees join correctly.
