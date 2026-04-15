# Database Schema

All tables share a single `declarative_base()` and are created via `Base.metadata.create_all()` on first use.

**Production** runs on PostgreSQL (`postgresql://jubu:<password>@<host>:5432/jubu`) deployed on Google Cloud. Local development should also use PostgreSQL (via Docker) to match the production dialect. The SQLite fallback (`sqlite:///kidschat.db`) exists only as a last-resort default and is used in unit tests (`sqlite:///:memory:`).

---

## Entity-Relationship Diagram

```
users (1) ----< child_profiles (N)
                     |
                     | child_id (logical, no FK)
                     v
              conversations (1) ----< conversation_turns (N)  [cascade delete]
                     |
                     +----< interaction_contexts (N)
                     +----< stories (N)
                     
              child_facts              (child_id, no FK)
              child_capability_observations  (child_id, no FK)
              child_capability_state         (child_id, no FK)
```

> **Note:** Most child-related tables reference `child_id` by value (String(36)) rather than a foreign key constraint. Only `child_profiles.parent_id -> users.id`, `conversation_turns.conversation_id -> conversations.id`, `stories.conversation_id -> conversations.id`, and `interaction_contexts.conversation_id -> conversations.id` are enforced FKs.

---

## Table Definitions

### `users`

Parent/guardian accounts.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK, default uuid | |
| `email` | String(255) | UNIQUE, indexed | Login identifier |
| `full_name` | String(255) | | |
| `hashed_password` | String(255) | | Stored via pluggable hasher |
| `is_active` | Boolean | default True | Soft-delete flag |
| `created_at` | DateTime | default utcnow | |
| `updated_at` | DateTime | default/onupdate utcnow | |

**Indexes:** `idx_email_active(email, is_active)`

---

### `child_profiles`

One row per child. Linked to a parent user.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `name` | String(100) | | |
| `age` | Integer | | |
| `interests` | JSON | default [] | List of interest strings |
| `preferences` | JSON | default {} | Arbitrary key-value preferences |
| `parent_id` | String(36) | FK -> users.id, nullable | |
| `is_active` | Boolean | default True, indexed | Soft-delete (GDPR) |
| `last_interaction` | DateTime | nullable | Last conversation timestamp |
| `created_at` | DateTime | default utcnow | |
| `updated_at` | DateTime | default/onupdate utcnow | |

**Indexes:** `idx_active_parent(is_active, parent_id)`  
**Relationships:** `parent` -> UserModel (back_populates `child_profiles`)

---

### `conversations`

One row per conversation session between the system and a child.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `child_id` | String(36) | indexed | |
| `state` | String(20) | indexed | `active`, `paused`, `ended`, `flagged` |
| `start_time` | DateTime | default utcnow, indexed | |
| `end_time` | DateTime | nullable | Set when state -> ended/flagged |
| `last_interaction_time` | DateTime | default utcnow | Updated on each turn |
| `conv_metadata` | JSON | nullable | Arbitrary session metadata |
| `is_archived` | Boolean | default False, indexed | Soft-delete for old conversations |
| `parent_summary` | Text | nullable | Human-readable summary for parent app |

**Indexes:** `idx_child_state_time(child_id, state, start_time)`, `idx_archived_time(is_archived, start_time)`  
**Relationships:** `turns` -> ConversationTurnModel (cascade all, delete-orphan)

---

### `conversation_turns`

Individual messages within a conversation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `conversation_id` | String(36) | FK -> conversations.id, indexed | |
| `timestamp` | DateTime | default utcnow, indexed | |
| `child_message` | Text | | What the child said |
| `system_message` | Text | nullable | System's response |
| `interaction_type` | String(50) | | e.g. chitchat, pretend_play |
| `safety_evaluation` | JSON | nullable | Safety check results |

**Indexes:** `idx_conversation_time(conversation_id, timestamp)`  
**Relationships:** `conversation` -> ConversationModel

---

### `child_facts`

Facts extracted from conversations. Facts have a lifecycle: created -> active -> expired.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `child_id` | String(36) | indexed | |
| `source_turn_id` | String(36) | nullable | Conversation turn that produced this fact |
| `content` | Text | | The fact statement |
| `confidence` | Float | | 0.0 - 1.0 extraction confidence |
| `timestamp` | DateTime | default utcnow | |
| `expiration` | DateTime | indexed | When fact becomes inactive (default: +30 days) |
| `verified` | Boolean | default False | Manually confirmed |
| `active` | Boolean | default True, indexed | |
| `created_at` | DateTime | default utcnow | |

**Indexes:** `idx_child_active_expiration(child_id, active, expiration)`, `idx_expiration(expiration)`

---

### `stories`

Stories generated during conversations.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `child_id` | String(36) | indexed | |
| `conversation_id` | String(36) | FK -> conversations.id, indexed | |
| `title` | String(200) | | |
| `content` | Text | | Full story text |
| `created_at` | DateTime | default utcnow | |
| `is_favorite` | Boolean | default False | Parent/child can mark favorites |
| `tags` | JSON | nullable | Categorization tags |
| `last_viewed_at` | DateTime | nullable | |

**Indexes:** `idx_child_favorite(child_id, is_favorite)`, `idx_created_at(created_at)`

---

### `child_capability_observations`

**Immutable** audit trail of capability evaluation events. Never deleted -- used for ML training and compliance.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `child_id` | String(36) | indexed | |
| `session_id` | String(255) | indexed | Conversation/evaluation session |
| `item_id` | String(255) | | Dotted capability ID (e.g. `casel.self_awareness.identify_basic_emotions`) |
| `item_version` | Integer | | Definition version at observation time |
| `framework` | String(64) | indexed | `casel`, `developmental_milestones`, `ngss` |
| `domain` | String(64) | | |
| `subdomain` | String(64) | | |
| `observation_status` | String(64) | | `demonstrated`, `emerging`, `not_observed` |
| `confidence` | Float | nullable | Evaluator's confidence |
| `evidence_text` | Text | nullable | Supporting evidence from conversation |
| `evaluator_type` | String(64) | | e.g. `llm_rubric` |
| `evaluator_version` | String(64) | nullable | |
| `raw_score_json` | JSON | nullable | Full evaluator output |
| `observed_at` | DateTime | indexed | When the observation occurred |
| `created_at` | DateTime | default utcnow | |

**Indexes:** `idx_obs_child_item(child_id, item_id)`, `idx_obs_child_framework(child_id, framework)`, `idx_obs_session(session_id)`, `idx_obs_item_id(item_id)`

---

### `child_capability_state`

Aggregated "best-so-far" state per child per capability item. Upserted from observations.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `child_id` | String(36) | indexed | |
| `item_id` | String(255) | indexed | |
| `item_version` | Integer | | |
| `framework` | String(64) | indexed | |
| `domain` | String(64) | | |
| `subdomain` | String(64) | | |
| `current_status` | String(64) | | Best status seen (never regresses) |
| `confidence` | Float | nullable | |
| `mastery_score` | Float | default 0.0 | 0.0 - 1.0, monotonically increasing |
| `evidence_count` | Integer | default 0 | Total observations recorded |
| `first_observed_at` | DateTime | nullable | |
| `last_observed_at` | DateTime | nullable | |
| `last_session_id` | String(255) | nullable | |
| `created_at` | DateTime | default utcnow | |
| `updated_at` | DateTime | default/onupdate utcnow | |

**Constraints:** `UNIQUE(child_id, item_id)`, `CHECK(mastery_score BETWEEN 0 AND 1)`  
**Indexes:** `idx_state_child_item(child_id, item_id)`, `idx_state_child_framework(child_id, framework)`

---

### `interaction_contexts`

Per-conversation, per-interaction-type context. Stores structured state for a specific interaction mode within a conversation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | String(36) | PK | |
| `conversation_id` | String(36) | FK -> conversations.id, indexed | |
| `interaction_type` | String(50) | indexed | e.g. chitchat, pretend_play, edutainment |
| `context_data` | JSON | default {} | Structured context (merge-updated) |
| `created_at` | DateTime | default utcnow | |
| `updated_at` | DateTime | default/onupdate utcnow | |

**Indexes:** `idx_conversation_interaction(conversation_id, interaction_type)`
