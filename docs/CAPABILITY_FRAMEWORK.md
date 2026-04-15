# Capability Framework

The capability system tracks a child's developmental progress across multiple educational frameworks. It separates **what we define** (YAML item definitions), **what we observe** (immutable observations), and **what we report** (aggregated state).

---

## Three-Layer Model

```
Layer 1: Definitions (YAML, in-memory registry)
  "What capabilities exist and how to evaluate them"
  |
Layer 2: Observations (child_capability_observations table, append-only)
  "What we saw in a specific session"
  |
Layer 3: State (child_capability_state table, upserted)
  "Best-so-far aggregated view per child per capability"
```

---

## Supported Frameworks

| Framework | ID | Description |
|---|---|---|
| CASEL | `casel` | Social-emotional learning (self-awareness, relationship skills, etc.) |
| Developmental Milestones | `developmental_milestones` | Age-appropriate developmental markers |
| NGSS | `ngss` | Next Generation Science Standards |

---

## Capability Definitions (YAML)

Definitions live in `capability_definitions/<framework>/<file>.yaml` and are loaded into an in-memory `CapabilityDefinitionRegistry` at startup.

### Directory Structure

```
capability_definitions/
  casel/
    age_5.yaml
    casel_age_5.yaml
  developmental/
    developmental_age_5.yaml
  ngss/
    age_5.yaml
```

### YAML Format

Each file is a **definition pack** -- one framework at one age level:

```yaml
framework: casel
age: 5

items:
  - id: casel.self_awareness.identify_basic_emotions
    framework: casel
    domain: sel
    subdomain: self_awareness
    title: Identifies basic emotions
    short_label: Emotion identification
    parent_friendly_label: Recognizes feelings
    description: >
      Child can identify and name basic emotions such as
      happy, sad, angry, and scared in themselves and others.
    age_ranges:
      - min_age: 4.5
        max_age: 5.5
        expected: true
    observable_signals:
      - names an emotion directly
      - correctly matches feeling to situation
    example_prompts:
      - "How does that make you feel?"
    positive_evidence_patterns:
      - "I feel happy because..."
    negative_evidence_patterns:
      - no emotional vocabulary used
    evaluation_method:
      type: llm_rubric_with_keyword_support
      rubric_id: sel_emotion_identification_v1
      config: {}
      required_signals: []
    scoring:
      type: ternary
      values: [not_observed, emerging, demonstrated]
    display:
      show_in_parent_app: true
      priority: high
      badge_icon: emotion
    status: active
    version: 1
```

### ID Convention

Item IDs follow dotted namespace: `<framework>.<subdomain>.<capability_name>`

Validated by regex: `^[a-z0-9_]+(\.[a-z0-9_]+)+$`

### Validation Rules

- Item IDs must be unique across all packs
- Item `framework` must match the pack's `framework`
- Item ID must start with the framework prefix
- Each pack must have at least one item
- `scoring.type` must be `"ternary"`
- `age_ranges` must have at least one entry where `min_age <= max_age`

---

## Registry API

```python
from jubu_datastore import load_default_registry

registry = load_default_registry()

# Query by framework and age
pack = registry.get_pack("casel", 5)

# Query single item
item = registry.get_item("casel.self_awareness.identify_basic_emotions")

# All items applicable to a specific age
items = registry.get_items_for_child_age(5)

# Demo items (CASEL + developmental only)
demo_items = registry.get_demo_items(5)

# All items as dicts (for LLM prompts / API responses)
all_defs = registry.get_all_items_definitions()
```

---

## Observation -> State Aggregation

When `insert_capability_observation()` is called, it:

1. **Inserts** the observation row (immutable)
2. **Upserts** the corresponding state row for `(child_id, item_id)`

### Aggregation Rules

**Status** -- best-so-far, never regresses:

```
not_observed (0) < emerging (1) < demonstrated (2)
```

If the new observation status ranks higher than the current state status, the state is upgraded.

**Mastery score** -- monotonically increasing, capped at 1.0:

| Observation Status | Delta |
|---|---|
| `demonstrated` | +0.33 |
| `emerging` | +0.10 |
| `not_observed` | +0.00 |

```
new_mastery = min(current_mastery + delta, 1.0)
```

**Evidence count** -- incremented on every observation regardless of status.

**Timestamps** -- `first_observed_at` set once; `last_observed_at` always updated.

### Example Progression

| Observation # | Status | Mastery After | State Status |
|---|---|---|---|
| 1 | emerging | 0.10 | emerging |
| 2 | not_observed | 0.10 | emerging (no regression) |
| 3 | demonstrated | 0.43 | demonstrated |
| 4 | demonstrated | 0.76 | demonstrated |
| 5 | demonstrated | 1.00 | demonstrated (capped) |

---

## Capability Seeding

When a new child profile is created, call `seed_child_capability_state()` to initialize zero-valued state rows for all defined capabilities:

```python
from jubu_datastore import seed_child_capability_state

seed_child_capability_state(child_id="abc-123", connection_string="postgresql://...")
```

This creates one `child_capability_state` row per item with:
- `current_status = "not_observed"`
- `mastery_score = 0.0`
- `evidence_count = 0`

The function is idempotent -- it deletes existing state before re-seeding.

---

## Data Flow Summary

```
Conversation session
  |
  v
LLM evaluator observes capability signal
  |
  v
insert_capability_observation({
    child_id, session_id, item_id, item_version,
    framework, domain, subdomain,
    observation_status, evaluator_type, observed_at,
    confidence, evidence_text, raw_score_json
})
  |
  +---> child_capability_observations  (append, immutable)
  +---> child_capability_state         (upsert, aggregated)
          |
          v
        Parent app reads get_child_capability_state(child_id)
        -> grouped by framework, shows mastery progress
```
