# Datastore API Reference

All datastores extend `BaseDatastore[T]` and implement the abstract CRUD interface: `create()`, `get()`, `update()`, `delete()`. Most also expose domain-specific methods.

---

## UserDatastore

**Table:** `users` | **Model:** `UserModel` | **DTO:** `User`

Manages parent/guardian accounts. Supports pluggable password hashing.

```python
ds = DatastoreFactory.create_user_datastore(password_hasher=bcrypt_hash_fn)
```

| Method | Description |
|---|---|
| `create(user_data)` | Create user. Checks email uniqueness. Hashes password if hasher provided. |
| `get(user_id)` | Retrieve by ID. |
| `get_by_email(email)` | Retrieve by email address. |
| `update(user_id, data)` | Update attributes. Raises if `password` is passed without a hasher. |
| `delete(user_id)` | **Soft delete** -- sets `is_active=False`. |
| `deactivate(user_id)` | Alias for soft delete. |
| `get_all_users()` | List all users. |

**Special behavior:**
- `password_hasher` is an optional callable `(str) -> str` passed at construction.
- If `password` appears in create/update data and no hasher is configured, an error is raised.

---

## ProfileDatastore

**Table:** `child_profiles` | **Model:** `ChildProfileModel` | **DTO:** `ChildProfile`

Child profiles with GDPR-compliant soft deletion.

| Method | Description |
|---|---|
| `create(data)` / `save_child_profile(data, child_id=None)` | Create or update profile. Requires `name` and `age`. |
| `get(child_id)` / `get_child_profile(child_id)` | Retrieve active profile. |
| `update(child_id, data)` | Update attributes. |
| `delete(child_id)` / `delete_child_data(child_id, hard_delete=False)` | **Soft delete** by default. Pass `hard_delete=True` for permanent removal. |
| `get_profiles_by_parent(parent_id)` | List active profiles for a parent. |
| `update_interests(child_id, interests)` | Replace interests list. |
| `update_preferences(child_id, prefs)` | **Merge** preferences dict with existing values. |
| `update_last_interaction(child_id, timestamp=None)` | Update last interaction timestamp. |

---

## ConversationDatastore

**Tables:** `conversations`, `conversation_turns` | **Models:** `ConversationModel`, `ConversationTurnModel`

Manages conversation sessions and their message history. Turns cascade-delete with their parent conversation.

| Method | Description |
|---|---|
| `create(data)` / `save_conversation(data)` | Create conversation. Requires `child_id`. |
| `get(conversation_id)` | Retrieve conversation as dict. |
| `update(conversation_id, data)` | Update attributes. Auto-sets `last_interaction_time`. |
| `delete(conversation_id)` / `delete_conversation(conversation_id)` | **Soft delete** -- archives and sets state to ENDED. |
| `hard_delete_conversation(conversation_id)` | Permanent delete (turns cascade). |
| `update_conversation_state(conversation_id, state)` | Transition state. Auto-sets `end_time` for ENDED/FLAGGED. |
| `set_conversation_parent_summary(conversation_id, summary)` | Store parent-facing summary text. |
| `add_conversation_turn(conversation_id, turn_data)` | Add a turn. Requires `child_message` and `interaction_type`. Updates `last_interaction_time`. |
| `update_conversation_turn(conversation_id, turn_id, updates)` | Update turn (allowed fields: `safety_evaluation`, `child_message`). |
| `delete_turn(conversation_id, turn_id)` | Delete a specific turn. |
| `get_conversation_history(conversation_id, limit=None)` | Get turns in chronological order. |
| `get_conversations_by_child(child_id, state=None)` | List conversations with turn counts. |
| `get_all_conversations()` | List all conversations with turn counts. |
| `archive_old_conversations(days_threshold=90)` | Auto-archive stale conversations. |
| `get_conversation_statistics(child_id=None, days=None)` | State counts and avg turns per conversation. |

**Conversation states:** `active` -> `paused` -> `ended` | `flagged` (from any state)

---

## FactsDatastore

**Table:** `child_facts` | **Model:** `ChildFactModel`

Facts extracted from conversations with confidence scoring and expiration lifecycle.

| Method | Description |
|---|---|
| `create(data)` / `save_child_fact(child_id, data)` | Create fact. Requires `content` and `confidence`. Default expiration: +30 days. |
| `get(fact_id)` | Retrieve fact model. |
| `update(fact_id, data)` | Update attributes. |
| `delete(fact_id)` | **Hard delete.** |
| `get_active_facts_for_child(child_id)` | Non-expired, active facts. |
| `get_child_facts(child_id, active_only, verified_only, min_confidence)` | Filtered query, ordered by confidence descending. |
| `get_facts_by_source_turn(turn_id)` | All facts extracted from a specific conversation turn. |
| `update_fact_confidence(fact_id, confidence)` | Update confidence score. |
| `verify_fact(fact_id)` | Mark fact as verified. |
| `expire_old_facts()` | Deactivate all facts past their expiration date. |
| `extend_fact_expiration(fact_id, days=30)` | Extend expiration date. |
| `get_facts_statistics(child_id=None)` | Total, active, verified counts; avg confidence; expiring-soon count. |

**Lifecycle:** Created (active=True) -> Expired (active=False, via `expire_old_facts()`)

---

## StoryDatastore

**Table:** `stories` | **Model:** `StoryModel`

Stories generated during conversations.

| Method | Description |
|---|---|
| `create(data)` / `save_story(data)` | Create story. Requires `child_id`, `conversation_id`, `title`, `content`. |
| `get(story_id)` | Retrieve story model. |
| `update(story_id, data)` / `save_story(data, story_id)` | Update story. |
| `delete(story_id)` | **Hard delete.** |
| `get_stories_by_child(child_id, favorites_only, limit, offset)` | Paginated query, ordered by created desc. |
| `mark_as_favorite(story_id, is_favorite=True)` | Toggle favorite flag. |
| `record_story_view(story_id)` | Update `last_viewed_at`. |
| `search_stories(child_id, search_term, limit=10)` | Case-insensitive search on title and content. |

---

## CapabilityDatastore

**Tables:** `child_capability_observations`, `child_capability_state` | **Models:** `ChildCapabilityObservationModel`, `ChildCapabilityStateModel` | **DTOs:** `CapabilityObservation`, `ChildCapabilityState`

Append-only observation log with aggregated state. See [CAPABILITY_FRAMEWORK.md](CAPABILITY_FRAMEWORK.md) for the full aggregation model.

| Method | Description |
|---|---|
| `create(data)` / `insert_capability_observation(data)` | Insert observation **and** update aggregated state. See required fields below. |
| `get(observation_id)` | Retrieve observation as DTO. |
| `update(observation_id, data)` | **No-op.** Observations are immutable. |
| `delete(observation_id)` | **No-op.** Observations are never deleted. |
| `update_capability_state(data)` | Manually update a state row (for recalculation). |
| `get_child_capability_state(child_id)` | Get all capability states, grouped by framework. |

**Required fields for `insert_capability_observation`:**

| Field | Type | Example |
|---|---|---|
| `child_id` | str | `"abc-123"` |
| `session_id` | str | `"conv-456"` |
| `item_id` | str | `"casel.self_awareness.identify_basic_emotions"` |
| `item_version` | int | `1` |
| `framework` | str | `"casel"` |
| `domain` | str | `"sel"` |
| `subdomain` | str | `"self_awareness"` |
| `observation_status` | str | `"demonstrated"`, `"emerging"`, or `"not_observed"` |
| `evaluator_type` | str | `"llm_rubric"` |
| `observed_at` | datetime | |

---

## InteractionContextsDatastore

**Table:** `interaction_contexts` | **Model:** `InteractionContextModel`

Stores structured context per interaction type within a conversation (e.g., pretend play state, quiz progress).

| Method | Description |
|---|---|
| `create(data)` / `save_interaction_context(data)` | Create or update context. Requires `conversation_id` and `interaction_type`. |
| `get(context_id)` | Retrieve context model. |
| `update(context_id, data)` | Update context. |
| `delete(context_id)` | **Hard delete.** |
| `get_context_for_conversation(conversation_id, interaction_type=None)` | Get contexts (optionally filtered by type). |
| `update_context_data(conversation_id, interaction_type, updates)` | **Merge** updates into existing `context_data` JSON. |

**Special behavior:** `context_data` is always merge-updated, never replaced. This allows multiple parts of the system to store context without overwriting each other.
