# WORKSTREAM C — Story Studio Implementation (jubu_backend + parent-api + jubu_parent_app)

> **How to use this doc:** start a Claude Code session with `/goal` and access to `jubu_backend`, `jubu_parent_app`, `jubu_datastore` (and `jubu-deploy` for compose/nginx changes). This doc merges the backend and parent-app workstreams because they share one data model and ship together. Companion docs in this folder: `KNOWLEDGE_GRAPH_WORKSTREAM.md` (graph schema + generator — may run in parallel; stub its outputs if not ready) and `STORY_TEMPLATE_SPEC.md` (slot/template model — normative for the schema here). The regulatory framing, two-axis model, interaction ladder, and design principles come from the v3 prompt ("Refactor Buju into a Story Studio — Publishing-Gate Architecture"); this doc grounds them in the actual code.
>
> **First deliverable is `MIGRATION_PLAN.md` — current-state map, what moves where, what gets deleted, schema changes, rollout sequence. Stop for human review before implementing.** Then implement phase by phase, behind flags, small PRs, tests at every boundary. Obey `jubu_backend/CLAUDE.md` throughout (naming rules, tunables in YAML not code, lifetime/owner/writer/reader/visibility declarations on every persisted child attribute, hot-path invariants).

---

## 0. Prime Directive (restated, enforced structurally)

**No raw model output ever streams to a child. Children only hear published content.** All generation is offline/async behind the Publishing Gate (generate → evaluate → revise → publish). The child playback path has no dependency on, route to, or credentials for the generation path — it reads only the published-content store. An architecture test fails CI if that dependency appears.

Today the codebase violates this by design: `jubu_thinker.py` streams Gemini tokens through `_safe_token_gen` into `_stream_tts` live to the child. That entire path becomes rung **I4** (flag `I4_COMPANION`, OFF) — kept, compliance-hardened later, never reachable at launch.

### 0.1 Preservation requirement (this shapes the whole migration)

**This is a re-framing, not a replacement.** Every existing capability is preserved. The current codebase is written as if open conversation is the default and only mode; the migration *extrapolates* it into exactly one option — the top rung of the interaction ladder — while the other rungs are built beside it. Nothing conversational is deleted: `ConversationManager`, `TurnState`, the recorder (`summarizer.run_delta_update`), style selection, capability evaluation, end-of-session consolidation all survive intact, relocated so that they belong to rung I4 and only rung I4. "Unavailable" is expressed as: (a) flag `I4_COMPANION` OFF, (b) rung selection server-side, (c) the parent app never rendering a conversation mode. The migration plan must contain a **move-don't-rewrite table** (old path → new path, behavior unchanged) for every conversation-mode file, and CI must stay green through the move.

---

## 1. Current state (verified against the repos)

**jubu_backend** — four processes over Redis pub/sub: `livekit_api.py` (FastAPI, port 8001, `initialize_conversation`), `bot_manager.py` (spawns `livekit_bot.py` per conversation), `livekit_bot.py` (VAD/STT/audio, publishes transcripts to `jubu_tasks`), `jubu_thinker.py` (LLM→TTS hot path, publishes audio chunks to `jubu_tts_stream`). Conversation brain: `jubu_chat/` — `conversation_manager.py` (ThreadPoolExecutor runs safety eval + generation concurrently; safety is next-turn via `[SAFETY OVERRIDE]`), `system_prompt_builder.assemble_system_prompt` (cached prefix + `[STATE]`/`[PLAN]` suffix), `summarizer.run_delta_update` (off-hot-path recorder), `turn_state.py` (`TurnState`, `SceneMemory{setting, situation, character_want, dramatic_tension}`), `opener_generator.py` (`OpenerConfig`, `configs/openers.yaml`), style system (`configs/styles/{cozy_honey_voice,plain_barn_voice,whimsy_inventor_voice}.yaml`, `style_config.py::StyleConfig`, `style_selector.py`, `style_leak_filter.py`), `topic_policy.plan_exploration`, `interest_dedup.py`, `parent_summary.py`, `parent_chat_manager.py` (**text-only LLM path already proven outside the voice loop** — the generation worker reuses this model stack: `jubu_chat/chat/models/`, `model_factory.py`, `failover_model.py`, `model_routing.yaml`).

**jubu_datastore** — shared SQLAlchemy layer + Alembic. Two-umbrella child model per ENG-347 (`child_aggregate.py`: `DeclaredProfile` / `LearnedProfile`; `TurnState` session-only). Tables include `users, child_profiles, conversations, conversation_turns, child_facts, observed_interests, inferred_traits, child_capability_state, consent_events, telemetry_events, parent_chat_*`, and `stories` (`story_datastore.py::StoryModel` — live-capture shaped: NOT-NULL `conversation_id` FK, no status/audio/provenance; see §3). `retention_enforcement.py` is the existing scheduled-batch-job template. Known bug to resolve before keying anything off conversation ids: the API/Redis `conversation_id` differs from the DB UUID (`ARCHITECTURE.md`, "conversation-ID split").

**jubu_parent_app** — Expo/RN 0.81, Redux Toolkit, axios against parent-api (`https://app.buju.ai`), LiveKit voice client against `api.buju.ai`. Five tabs (`src/navigation/MainNavigator.tsx`): Dashboard (highlights, `StatisticsScreen` with NGSS/mastery framing, `InterestsMapScreen` → `src/components/InterestMindMap/`), Voice (`VoiceChatScreen`, Kids Mode gate in `settingsSlice.kidsModeActive`), Parent (guidance content, forum, `ParentChatScreen` SSE, hardcoded `BookReviewScreen`), Conversations (transcripts), Settings (time-limit slider, parental controls, COPPA data rights). Effectively single-child (`profiles[0]`).

**jubu-deploy** — single GCP VM, Docker Compose: nginx, certbot, livekit, `migrate` (one-shot alembic), `retention` (daily loop), backend (8001/8002), parent-api (8000), redis, postgres 16, grafana. Hot-editable `config-overrides/model_routing.yaml`. No job queue anywhere.

**Gaps vs. the v3 prompt:** no publishing gate, no published-content store, no session clock (only idle timeouts in `base_config.yaml::user_experience`), no AI disclosures, no feature-flag registry, no knowledge-graph tagging, no branch playback, no commissioning.

---

## 2. Target architecture

```
                    PARENT SIDE (adaptive, parent-keyed)          CHILD SIDE (published content only)
┌─────────────┐   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐
│ parent app  │──▶│ parent-api (8000)            │   │ playback service (child sessions)    │
│  commission │   │  shelves/commission/approve/  │   │  reads published_content store ONLY  │
│  topic map  │   │  topic-map endpoints          │   │  session clock · disclosures ·       │
└─────────────┘   └──────┬───────────────────────┘   │  I0 play · I1 choice classifier      │
                         │ enqueue (DB table)        └──────────────▲───────────────────────┘
                  ┌──────▼───────────────────────┐                  │ read-only
                  │ story_studio worker (NEW)     │   ┌─────────────┴─────────────┐
                  │ generate → gate → revise →    │──▶│ published-content store    │
                  │ publish · TTS render · tags   │   │ (Postgres + audio files)   │
                  └──────────────────────────────┘   └───────────────────────────┘
```

- **`story_studio` worker** — new process in `jubu_backend` (own top-level package `story_studio/`, own compose service in `jubu-deploy`). Queue = a Postgres table (`story_generation_jobs`) polled by the worker — durable, transactional with publishes, inspectable in Grafana; Redis pub/sub may additionally signal "wake up" but is not the source of truth. Reuses `jubu_chat` models/styles/prompt assembly; **imports nothing from** `livekit_*`/`jubu_thinker`.
- **Playback service** — the child-facing voice session becomes: LiveKit session that streams **pre-rendered audio segments** + runs the I1 intent classifier. Implement inside the existing bot process family but as a distinct module (`playback/`) with an import-boundary test: `playback/*` must not import `jubu_chat.chat.models`, `story_studio/*`, or any LLM client. `initialize_conversation` gains `session_kind: story_playback` and `story_instance_id`; the thinker is not spawned for playback sessions.
- **Publishing Gate** — pipeline stages inside the worker: `generate` (template per `STORY_TEMPLATE_SPEC.md`, against the graph brief) → `evaluate` (safety evals to completion on full text — strictly stronger than today's stream-then-check; plus style-adherence evals so compliance never flattens prose; scores recorded) → `revise` (≤ N cycles, tunable in YAML) → `publish` (immutable version + TTS render + provenance) or `human_review`. Route the existing style YAML profiles through the gate as a scored dimension; track eval-score trends per prompt version.
- **STRICT_CONTENT_MODE** — server-side switch: all child sessions restricted to published content at I0–I1, commissioned delivery paused. Config deployable in minutes (env + hot-reload à la `model_routing.yaml`); covered by an integration test.

### 2.1 Code organization — the interaction ladder IS the package structure

The ladder must be legible from `ls`. Reorganize `jubu_backend` so each rung is a package containing everything unique to that rung and nothing else, with directories **named by meaning, not index** (CLAUDE.md rule 10 — I0–I4 remain the flag/doc shorthand):

```
jubu_backend/
  child_sessions/                    # everything a child session can be — one subpackage per rung
    rung_policy.py                   # server-side rung resolution per session (flags + account config);
                                     # constructs exactly ONE rung engine per session
    listen/                          # I0 — playback only. Default child experience.
      playback_engine.py             # streams published audio segments; mic disabled in session state
      session_clock.py               # wind-down + shutdown (shared upward by all rungs)
      disclosure_player.py           # published disclosure assets
    steer/                           # I1 — authored choice points. Flag I1_STEER (ON at launch).
      choice_intent_classifier.py    # constrained A/B/C/unclear; structurally cannot generate
      choice_transcript_lifecycle.py # safety-scan → log {story_id,branch_id,choice,ts} → delete
    wish/                            # I2 — one-shot monologue. Flag I2_WISH (OFF).
      monologue_capture.py           # listen-only; scripted ack is a published asset
      wish_commission_writer.py      # transcript → safety scan → commissioning request → delete audio
    structured_exchange/             # I3 — YAML-scripted intake. Flag I3_STRUCTURED (OFF, no UI).
      intake_scripts/*.yaml
      slot_filling_engine.py         # responses are script-selected published assets, never generated
    open_conversation/               # I4 — the current companion, PRESERVED INTACT. Flag I4_COMPANION (OFF).
      conversation_engine.py         # thin adapter over today's JubuAdapter + ConversationManager turn loop
      thinker.py                     # jubu_thinker.py's LLM→TTS loop moves here (spawned only for I4)
      session_learning/              # the child-keyed learning writers move here: end-of-session
                                     # consolidation, observed-interest ledger writes, capability_evaluator,
                                     # inferred_traits — they run ONLY inside this package
  story_studio/                      # offline generation + publishing gate worker (parent-side)
  jubu_chat/                         # shared LLM brain (models, prompts, styles). Importable ONLY by
                                     # story_studio, parent chat, and child_sessions.open_conversation
  speech_services/                   # shared audio providers (transport-level, rung-agnostic)
  livekit_bot.py / bot_manager.py    # audio transport; rung-agnostic — wires audio to whichever engine
                                     # rung_policy constructed
```

**Escalating imports = escalating capability, enforced in CI** (import-linter contracts + the architecture test):

| Rung package | May import | Must NOT import |
|---|---|---|
| `listen` | published-content reader, audio transport | any STT, `jubu_chat`, `story_studio` |
| `steer` | listen's deps + STT + intent classifier + safety scanner | any generative model class |
| `wish` | steer's deps + commissioning-request writer | response generation of any kind |
| `structured_exchange` | wish's deps + script engine | free generation |
| `open_conversation` | full `jubu_chat` conversation stack | `story_studio` internals |

This is capability-based compliance made physical: a rung-N session cannot invoke rung-N+1 behavior because the code is not importable from its package, not because a guard declined. Rung engines share one small interface (`ChildSessionEngine`: start/handle_audio/tick/shutdown) so `livekit_bot.py` stays rung-agnostic. Session flow: `initialize_conversation` → `rung_policy.resolve(account, flags, session_kind)` → construct that engine only; no code path constructs a different rung's engine mid-session.

**Migration Phase 0 (mechanical, zero behavior change):** create `child_sessions/open_conversation/`, move the live-conversation code into it (git mv + import updates; the move-don't-rewrite table in `MIGRATION_PLAN.md`), gate its entry behind `I4_COMPANION` defaulting ON temporarily so production is unchanged, land import contracts as warnings. All existing tests pass. Only after Phase 0 does Story Studio work begin; the flag flips OFF when `listen` ships. This ordering guarantees the conversation product keeps working while the ladder grows around it — and if regulators permit it in November 2026, re-enabling conversation is a flag flip plus its compliance-hardening backlog (disclosures, session clock — which it inherits from `listen` — and safety protocols), not a resurrection.

---

## 3. Schema (jubu_datastore, Alembic migrations)

New tables (every persisted child-adjacent field declares lifetime/owner/writer/reader/visibility in comments per CLAUDE.md):

- `story_templates` — id, title, axis tags (**one primary per axis enforced in the tagging API**, secondaries JSON), age_band, style_profile_id, interaction_shape (`linear`|`branch_tree`), slot_registry JSON, default_cast JSON, status.
- `story_template_versions` — immutable text/branch-tree JSON, `gate_provenance` (`prompt_version, model, eval_scores, reviewer, timestamp`), published_at, depublished_at. Corrections = new version + depublish old.
- `story_instances` — template_version_id, cast JSON, `parent_account_id`, shelf (`library`|`family`), created_from (`library_recast`|`commission`|`wish`), parent_approval fields.
- `story_segments` / `audio_assets` — per version and per instance: segment id, branch node id (nullable), audio file ref, tts_provider/voice, rendered_at. Branch trees publish all segments as a unit.
- `story_generation_jobs` — queue: kind (`library_batch`|`commission`|`wish`), request payload, status, attempts, gate_cycle_count, error.
- `knowledge_graph_story_tags` — story_template_id ↔ node_id, axis, is_primary. (Graph definitions themselves are YAML in-repo per Workstream A; only tags + account exploration state are DB.)
- `account_topic_exploration` — `parent_account_id`, node_id, first/last played, story count. **Schema lint: no child-keyed columns here or in any new table** except `story_instances.cast` which may contain a hero name — that is parent-entered content, not a child record; document this explicitly.
- `feature_flags` — name, enabled, owner, written rationale, updated_by/at (flags gate law; config gates product).
- `audit_events` — append-only: disclosures played, clock reminders/shutdowns, escalations, gate decisions, publish/depublish, de-personalization approvals, flag changes. Crisis-referral counter field reserved now.
- `safety_events` — `{event_type, rung, timestamp, action_taken}`, minimal, retention per counsel.
- Reserved, schema-only (Phase 3): `story_illustration_sets`, `print_artifacts` (flag `PRINT_BOOKS`); community fields on `story_templates` (`COMMUNITY_SHELF`, ToS license-grant hooks in consent flow).

Existing `stories` table: **do not extend** — it is live-capture shaped (NOT-NULL `conversation_id`). Keep it read-only for historical data; new world uses the tables above; plan its retirement in `MIGRATION_PLAN.md`.

Quarantine, not deletion (per §0.1; enumerate precisely in `MIGRATION_PLAN.md`): all code paths that *write durable child-keyed learning* (end-of-session consolidation into `observed_interests`/`inferred_traits`/`child_facts`, `capability_evaluator`) move intact into `child_sessions/open_conversation/session_learning/`, where the import contracts make them structurally unreachable from rungs I0–I3 — preserved and tested for I4's possible return, incapable of firing at launch. Playback telemetry is parent-keyed playback progress only. Actual deletion is reserved for genuinely dead code (e.g. `api_server/obsolete_*.py`, `obsolete_jubu_datastore/`, the hardcoded `BookReviewScreen`).

---

## 4. Backend phases (each = flag + tests + small PRs)

0. **Ladder restructure (mechanical)** — the Phase 0 move described in §2.1: relocate the live-conversation stack into `child_sessions/open_conversation/` unchanged, introduce `rung_policy.py` + the `ChildSessionEngine` interface, land import contracts. Production behavior identical; CI green throughout.
1. **Publishing Gate + store** — worker skeleton, jobs table, gate stages, provenance, TTS rendering via existing `speech_services/text_to_speech` providers, template renderer + name-safety lint per `STORY_TEMPLATE_SPEC.md`. Red-team the gate with adversarial generation fixtures.
2. **Shelf 1 Library at I0** — batch generation CLI against the draft graph (`build_generation_brief`), 100% human spot-check queue, one-tap playback end-to-end: `initialize_conversation(session_kind=story_playback)` → segment streaming through the existing bot audio path (mic path **disabled in device/session state** at I0, not muted) → **server-side session clock** (60-min/day per account default, parent-adjustable downward only, survives restarts — persist in Postgres, enforce in playback service, graceful narrative wind-down asset then shutdown, all events audited) → **disclosures as published assets** (pre-recorded, versioned, session-start + recurring per clock, per-session play records).
3. **Knowledge Graph integration** — tagging API (one-primary-per-axis), coverage report endpoint, `account_topic_exploration` updates on playback/commission, admin tooling per Workstream A.
4. **Shelf 2 Commissioned** — parent-api commissioning endpoint (voice via existing parent chat stack or text), job enqueue, "writing your story" status (target sub-minute for linear stories; progress states for the app's looping animation), gate-fail → human review never a shelf, branched commissions publish whole trees.
5. **I1 Steer** — choice-point playback: narrator offers authored options; child speech → intent classifier (constrained classification against offered options only — a small model call that **cannot** generate; A/B/C/unclear → re-offer once → default). Audio+transcript deleted post-classification; log `{story_id, branch_id, choice_taken, timestamp}` parent-keyed. Safety scan on transcript before deletion → escalation → parent notification → `safety_events`. **Open design point (Xia):** when the child likes none of the options — v1: re-offer once with "or should I pick?" then narrator-picks default; additionally log an anonymous `no_option_matched` counter per choice point so authors learn which choice points fail; consider an authored "surprise me" third option as standard practice.
6. **STRICT_CONTENT_MODE + lints + red-team CI** — architecture/import tests; schema lint (no child-keyed records); string lint on all child-facing templates/scripts (ban: "your friend", "I missed you", "welcome back", "remember when", "how do YOU feel", name-greetings from memory, "companion", "just like you"); red-team suite (open-dialogue elicitation at I0–I2, memory claims → scripted "Every story is brand new!", roleplay drift, branch-prompt injection, rung escalation). Release blockers.
7. **I2 Wish** (flag `I2_WISH`, post-launch) — one-shot monologue capture, scripted acknowledgment, transcribe → safety scan → delete audio, commissioning request, **parent approval before family shelf**.
8. **Deferred, schema/flag only:** Community shelf + de-personalization (= cast removal + LLM leak-sweep + parent approval + full re-gate, per `STORY_TEMPLATE_SPEC.md` §5), I3 YAML scripts, storybooks.

Rung selection is server-side per session; a session at rung N is architecturally unable to invoke rung N+1 (rung N+1's engine lives in a package rung N cannot import and is never constructed — not flags checked at call sites).

---

## 5. Parent app — UX redesign (this is a product redesign, not a reskin)

### 5.1 Design principles

Elegant, simple, fast. The primary persona is a tired parent at 9pm. Hard budgets: **≤ 2 taps from app open to a story playing**; one primary action per screen; the knowledge graph is the app's centerpiece and identity; no assessment language anywhere (copy lint applies to the app too); progressive disclosure — power features (branch commissioning, style choice) never crowd the happy path.

### 5.2 New information architecture — 5 tabs → 3

| New tab | Replaces | Content |
|---|---|---|
| **Tonight** (home) | VoiceTab + parts of Dashboard | Play now: resume card, Tonight's Picks (3 recommendations), family shelf row, in-flight "Buju is writing…" cards, one-tap **Kid Mode handoff** |
| **Explore** (the graph) | InterestsMap + Statistics + Conversations | Full-screen Topic Map with axis layers; node → story browser; commission entry point lives *inside the map* |
| **Family** | Parent + Settings tabs | Approvals queue, playback history (replaces transcripts), session clock & controls, profile, guidance content, account/COPPA |

**Rung availability is server-driven and invisible when off:** the app fetches enabled interaction modes from the flag registry and renders only those. At launch that means Stories (listen/steer) — the conversation mode (`I4_COMPANION`) has no UI surface at all, no greyed-out teaser, no settings toggle; parents cannot see or enable it. If it is ever re-enabled server-side, its UI ships as a normal app update. Kid Mode is a mode, not a tab: full-screen player launched from Tonight (existing hold-to-exit + math gate from `VoiceChatScreen` is good — keep it). `ConversationsTab` (transcript review) has no meaning at I0–I1 — playback history (which stories, when, choices made count) replaces it; transcripts return only if/when I4 ships. `BookReviewScreen` is deleted and reborn as the story preview screen in commissioning/approval. `ParentForum`/guidance content moves under Family, de-emphasized.

### 5.3 Tonight (home) — the 9pm screen

Top to bottom: (1) **Hero card** — last unfinished or most recent story, giant play button; tap = Kid Mode with that story. (2) **Tonight's Picks** — three cards from the recommender (§5.6) with a one-line *why* ("New territory next to volcanoes, which you've explored 4 times"). (3) **Family shelf** — horizontal row of commissioned/recast stories, cover art + duration badge + `branched` badge. (4) **Writing-in-progress card** when a commission is in flight: looping animation, ~30s expectation set, replaced by a "ready — listen first or shelve it" card on publish. (5) Quiet footer link: "Commission a story" (also reachable from Explore).

### 5.4 Explore — the knowledge graph as the product's center

Evolve `src/components/InterestMindMap/` (pan/pinch/clustered layout already built) into the **Topic Map**:

- **Axis layers** as segmented control: Domains / Feelings / Values / Story Worlds (parent-legible names for domain/sel_theme/value_lesson/story_element). One layer visible at a time (no overlay soup).
- **Node states:** explored (filled, count badge), frontier (glowing outline — adjacent to explored), unexplored (dim). Data = `account_topic_exploration` + age view from Workstream A. The map morphs with the child's age (age view endpoint), which parents *see* on the birthday — the graph literally grows with the child.
- **Node tap → bottom sheet:** node display name + per-age framing line ("At 6, volcanoes are about the BOOM"), then **Stories here** (playable now — Library + family, instant), then **Commission about this** (pre-fills the commissioning form with this node). This is the core browse-and-pick loop: *see territory → pick story → play*, or *see gap → commission*.
- **Search bar** over nodes and story titles for parents who know what they want ("dinosaurs").
- Keep the old interests bubble map's *observed interests* signal as an overlay chip ("Ava keeps returning to: space, foxes") sourced from declared interests + played-story tags — **not** from live-conversation inference at I0–I1.

### 5.5 Commissioning — one screen, three decisions

Form: **Topic** (chip, pre-filled if entered from the map; free text allowed), **Hero** (child's name, sibling, or default cast — this is the template cast picker; name-safety lint inline), **Optional:** lesson (value_lesson vocabulary chips), style (the three voice styles with 5s audio samples via existing `/voice/preview` pattern), "make it a choose-your-path adventure" toggle. Submit → Tonight shows the writing card. Voice commissioning ("just tell Buju what you want") reuses the `parentChatApi` SSE stack as a later enhancement — text form ships first.

### 5.6 Recommendations ("the system knows what to suggest")

Simple, explainable scorer in parent-api — no ML infra: `score(node/story) = w1·frontier_adjacency (unexplored node adjacent to explored) + w2·declared_interest_match (DeclaredProfile.parent_declared_interests ↔ node/story tags) + w3·completion_signal (finished stories on similar tags; skipped = negative) + w4·age_fit + w5·recency_variety (penalize same region three nights running)`. Weights in YAML (tunables per CLAUDE.md). Every pick carries its top factor as the human-readable *why*. Anonymous cross-account popularity may inform Library planning server-side but is not a personal ranking input at launch.

### 5.7 Statistics/Insights screen — reframe or cut

`StatisticsScreen`'s mastery scores / NGSS tiers / demonstrated-emerging language is **assessment framing, banned** by the framing constraint. Replace with an **Exploration** summary inside Explore: territories visited this month, minutes listened, themes the family keeps returning to, coverage by region. No per-child capability inference in the app at launch (`capability_evaluator` output stays out of the UI; it belongs to the flagged-off I4 world).

### 5.8 Implementation mapping

New: `src/api/storiesApi.ts`, `storiesSlice`, `src/api/topicMapApi.ts`; screens `TonightScreen`, `TopicMapScreen` (from `InterestMindMap` + `layout.ts`), `NodeSheet`, `CommissionScreen`, `StoryPlayerScreen` (Kid Mode; extends `useConversationEngine` state machine for segment playback + I1 choice moments), `ApprovalsScreen`, `PlaybackHistoryScreen`. Update `MainNavigator.tsx` + `navigation/types.ts` to the 3-tab IA. Playback session via `src/voice/api/initConversation.ts` with `session_kind: 'story_playback'`, `story_instance_id`. Delete: `BookReviewScreen` (hardcoded), Conversations stack (after history replacement), forum seed content if unused. Copy lint (banned strings) wired into app CI over `src/content/` and all user-facing string literals.

---

## 6. parent-api endpoints (new)

`GET /api/v1/shelf` (library + family, age-filtered) · `GET /api/v1/topic-map?age=N` (age view + account exploration overlay) · `GET /api/v1/topic-map/nodes/{id}/stories` · `POST /api/v1/commissions` / `GET /api/v1/commissions/{id}` (status for the writing card) · `POST /api/v1/story-instances` (recast library story) · `GET/POST /api/v1/approvals` · `GET /api/v1/recommendations?slot=tonight` · `GET /api/v1/playback-history` · session-clock config under existing settings endpoints. All keyed to the authenticated parent account; no child-keyed reads.

---

## 7. CI & compliance artifacts

- Architecture/import-boundary tests (playback ↛ models/generation), schema lint, string/copy lint (backend templates + app strings), red-team suite — all release blockers in `jubu_backend` CI (`ci.yml`/`test.yml`) and the app's CI.
- **`COMPLIANCE_MAP.md`** (final deliverable): table mapping each statutory duty (CA SB 243 §22602/§22602.5/§22603; NY GBL §1701/§1702) → code path, flag, test, audit event. Maintained in every boundary-touching PR.
- Flags registry seeded: `I1_STEER` (ON), `I2_WISH`, `I3_STRUCTURED`, `I4_COMPANION` (ON during Phase 0, OFF once `listen` ships), `COMMUNITY_SHELF`, `PRINT_BOOKS`, `STRICT_CONTENT_MODE` — each with owner + written rationale.
- Never silently resolve a product-vs-compliance tradeoff — surface it in the PR.

## 8. Deploy notes (jubu-deploy)

New compose service `story-studio-worker` (image `jubu-backend:local`, command `python -m story_studio.worker`), audio asset volume (or GCS bucket — decide in `MIGRATION_PLAN.md`; single VM disk is fine at launch), nginx route for audio segment delivery, Grafana panel on `story_generation_jobs`. `STRICT_CONTENT_MODE` and flag registry readable via hot-reload like `config-overrides/model_routing.yaml`.
