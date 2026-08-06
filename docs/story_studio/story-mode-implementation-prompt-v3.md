# PROMPT: Refactor Buju into a Story Studio — Publishing-Gate Architecture (v3)

You are working on Buju, a voice AI system for children ages 5–10, currently built as a conversational companion (LiveKit voice pipeline, backend + parent-api services, Postgres/Redis, Gemini on Vertex AI, TTS via Cartesia/ElevenLabs). We are pivoting the launch product to a **Story Studio**: parents commission personalized stories; children listen and steer pre-vetted adventures. The refactor is regulatory-driven (CA SB 243, NY GBL Art. 47, NY S9408A) and its boundaries must be enforced **in architecture, not in prompts**.

Read the existing codebase first. Produce a migration plan before writing code. Then implement in the phase order below, behind feature flags, with tests at every boundary.

---

## THE PRIME DIRECTIVE

**No raw model output ever streams to a child. Children only ever hear published content.**

All story generation happens offline and asynchronously. Every piece of child-facing content passes the Publishing Gate (generate → evaluate → revise → publish) before it can play in any child session. There is no code path from an LLM response to a child's speaker. Enforce structurally: the child playback service has no dependency on, network route to, or credentials for the generation service — it reads only from the published-content store. An architecture test fails CI if such a dependency is introduced.

---

## THE TWO-AXIS MODEL

The system separates **where content comes from** (Content Shelves) from **how much the child can express** (Interaction Ladder). These vary independently: any story on any shelf may be linear or branched; any interaction rung applies regardless of shelf. Do not conflate them in code — shelf is a property of content; rung is a property of the child session.

### AXIS 1 — Content Shelves (all behind the same Publishing Gate)

**Shelf 1 — LIBRARY** (Buju-generated, press-and-play)
- Pre-generated against the Knowledge Graph by age band, full gate, human-spot-checked (100% sampling at launch, ratchet with data), published to all accounts.
- One-tap playback is the launch-default child experience. Optimize for a tired parent at 9pm: open → tap → hand phone to kid.
- Published content is versioned and immutable; corrections publish new versions and depublish old ones.

**Shelf 2 — COMMISSIONED** (this family's requests, async)
- Parent commissions via voice/text (theme, lesson, this week's obsession, style). Generation runs async server-side; story appears on the family shelf only after passing the gate. Minutes, not seconds — show "Buju is writing your story…"; (Xia speaking: or sub minute like 30 seconds, which we could incorporate a looping buffering simple to show the progress.) latency is anticipation.
- Stories failing the gate after N revision cycles go to human review, never to a shelf.
- Parents may construct branched stories at commissioning time ("make it a choose-your-path adventure") — the full branch tree generates and publishes as a unit.

**Shelf 3 — COMMUNITY** (parent-published; PHASE 2, flag `COMMUNITY_SHELF` OFF at launch)
- A parent may publish a commissioned story to the community. Publishing is a pipeline, not a toggle:
  a. **De-personalization stage (mandatory):** automatically generalize family specifics — child names → archetypes, family details → universal ones. The parent reviews and approves the generalized version; only that version can enter the community pipeline.
  b. Re-run the full Publishing Gate on the generalized version.
  c. Tag mapping to Knowledge Graph nodes (parent proposes; gate validates against the one-primary-per-axis rule below).
- **Appreciation, not ranking law:** hearts / "this helped our family" signals exist, but discovery ranking = curation function over gate scores + graph coverage needs + completion rates + appreciation. No public downvotes; "not relevant" is a private skip/hide signal.
- Build the data model and ToS hooks now (license grant for distribution and print), ship the feature only when a few hundred gate-passed stories can seed it.

**Branch trees are a content property, not a shelf.** Choose-your-path stories pre-generate the **entire tree** (2–3 choice points, 2–3 options each, branches may re-join; ~8–20 leaves) and publish all segments as a unit. Child choices select among published audio segments — zero runtime generation, instant transitions.

### AXIS 2 — Child Interaction Ladder (escalating expressiveness; each rung structurally incapable of the rung above)

**I0 — LISTEN.** Playback only. Mic path disabled in device state, not just muted. Telemetry: playback progress only, parent-keyed.

**I1 — STEER.** At authored choice points, the narrator offers explicit story-world options; child speech is intent-classified against the offered options only (A/B/C/unclear → re-offer once → default). Audio + transcript deleted immediately after classification; log only `{story_id, branch_id, choice_taken, timestamp}` keyed to parent account. The classifier has no generation capability; the playback service never receives free text. (Xia: we really need to think of what if kids don't like any of the options. What do we do?)

**I2 — WISH (one-shot monologue).** Flag `I2_WISH`, target first post-launch update. The child gets a single uninterrupted turn: "tell me everything you want in your story — say 'the end' when you're done!" The system only listens — no follow-ups, no adaptive responses; one scripted acknowledgment ("Got it! Buju is writing your story…"). The monologue becomes a commissioning request into the async gate; audio transcribed, safety-scanned, deleted. **Parent approves the resulting story before it appears on the family shelf.** One turn ≠ sustained dialogue; a system that never responds adaptively provides no adaptive human-like responses; nothing is remembered.

**I3 — STRUCTURED EXCHANGE.** Flag `I3_STRUCTURED`, OFF, no UI wiring until legal review. Fixed-script, ≤90s slot-filling intake (hero, setting, one wish, one lesson) — the first rung where the system responds to the child, hence the legal gate. Scripts as reviewable YAML; output is a commissioning request into the async gate, never live continuation.

**I4 — OPEN CONVERSATION.** Flag `I4_COMPANION`, OFF. The original companion, kept built and compliance-hardened (disclosures, session clock, safety protocols per the prior spec), awaiting the November 2026 regulatory outcome. No child-keyed memory even here unless explicitly re-approved.

Rung selection is server-side per session; a session at rung N must be architecturally unable to invoke rung N+1 capabilities.

**`STRICT_CONTENT_MODE`:** server-side survival switch restricting all child sessions to published content at rungs I0–I1 and pausing commissioned delivery pending elevated review. Deployable as config in minutes; covered by an integration test.

---

## THE KNOWLEDGE GRAPH (curriculum + dashboard engine)

- **Multi-axis schema.** Distinct tag axes, not one flat topic list:
  - **Domain** (science, nature, history, how-things-work…)
  - **SEL theme** (courage, sharing, frustration, empathy, loss…)
  - **Values/lessons** (parent's "what I want to teach" vocabulary)
  - **Story elements** (dinosaurs, pirates, space — discovery hooks, not curriculum)
  Nodes carry age-band applicability (5–6, 7–8, 9–10), adjacency/prerequisite edges, and developmental-milestone annotation fields (to be populated with our developmental psychologist; seed with a DRAFT taxonomy for her review; build admin tooling).
- **One primary tag per axis per story** (e.g., Domain=volcanoes, SEL=courage), optional secondaries. Enforce in the tagging API — unlimited tags inflate the map and destroy coverage meaning. Community-proposed tags pass the same rule.
- Story↔node mapping is many-to-many across axes; expose a coverage report per age band to drive Library content planning; aggregate anonymous cross-account popularity informs where to invest polish.
- **Parent dashboard — Topic Map:** one map with togglable axis layers (Domain layer, SEL layer…), showing nodes explored via stories played/commissioned on this account, with adjacent-territory suggestions.
- **FRAMING CONSTRAINT (copy lint + API design):** the map represents **topics explored through stories on this account** — content coverage, never child assessment. Banned in parent-facing strings: "your child is behind/ahead," "assessment," "development score," any per-child inference. Allowed: exploration, territories, coverage, "themes your family keeps returning to." All graph interaction data keys to `parent_account_id`; no child-keyed records anywhere (schema lint applies).

---

## PARENT COMMISSIONING (Tier 0, unchanged in spirit)

Full adaptive voice/text dialogue with the **parent**; persistent parent-keyed memory of preferences, topics, styles; feeds the Topic Map and the commissioning pipeline. Parent authentication required; rung/shelf configuration lives here.

---

## STORYBOOKS (PHASE 3, flag `PRINT_BOOKS`, schema only for now)

Print-on-demand illustrated books of a family's stories (and, later, community favorites). For this refactor: reserve the data model (story → illustration set → print artifact), note that illustration generation requires its own gate stage (image-model evals differ from text), and ensure the ToS license grant covers print. No implementation yet.

---

## DESIGN PRINCIPLES (encode as tests and lint rules)

1. **Narrator, not friend.** Child-facing voice is a storyteller with no relational identity. String lint bans, in all child-facing templates/scripts: "your friend," "I missed you," "welcome back," "remember when," "how do YOU feel," questions about the child's life or identity, name-greetings from memory, and "companion" anywhere child- or store-facing. CI-blocking.
2. **Capability-based compliance.** Boundaries are impossible, not instructed. No child-keyed store exists; the child pipeline cannot reach a model; I1 selects, never generates; I2 listens, never responds. Prefer deleting a code path over guarding it.
3. **Published content only** (Prime Directive). Carve-out: required disclosures and safety scripts are themselves pre-recorded published assets.
4. **Safety pipeline always on, every rung and shelf.** Self-harm/harm-disclosure detection runs on all transcribed child speech before deletion (I1 intents, I2 monologues, I3 intake), on parent inputs, and inside the Publishing Gate on all generated and community content. Detection → parent-api escalation → parent notification → durable minimal safety-event log (`{event_type, rung, timestamp, action_taken}`; retention per counsel). Never removed to strengthen a classification argument.
5. **Server-side session clock.** 60-minute daily default per account; graceful narrative wind-down, then auto-shutdown; parent-adjustable downward only; survives restarts and device swaps; all reminder/shutdown events audited.
6. **Disclosures as published assets.** Age-appropriate session-start AI disclosure before any story audio; recurring reminder per clock; versioned scripts with per-session play records.
7. **Compliance as tested code.** Red-team CI: attempts to elicit open dialogue at I0–I2, emotion questions, memory claims ("do you remember me?" → scripted "Every story is brand new!"), roleplay drift, branch-prompt injection via child speech, rung-escalation attempts. Boundary regressions are release blockers.
8. **Flags gate law, config gates product.** Every rung, shelf, cadence, COMMUNITY_SHELF, PRINT_BOOKS, and STRICT_CONTENT_MODE is a server-side flag with owner + written rationale.
9. **Audit everything compliance-relevant, nothing child-personal.** Append-only stream: disclosures, reminders, shutdowns, escalations, gate decisions, publications/depublications, de-personalization approvals, flag changes. Crisis-referral counter designed now (CA reporting, July 2027). Gate provenance records (`prompt_version, model, eval_scores, reviewer, timestamp`) are audit artifacts, not debug logs.
10. **Story quality is the product.** Route the literary style system (author-voice YAML profiles) through the gate as a scored dimension; add style-adherence evals so compliance never silently flattens the prose; track eval-score trends per prompt version.

---

## DELIVERABLES, IN ORDER

1. **MIGRATION_PLAN.md** — current-state map; what moves where; what gets deleted (all child-keyed memory paths, all live child-facing generation paths); schema changes; rollout sequence. Wait for my review before implementing.
2. Publishing Gate pipeline + published-content store + provenance records.
3. Shelf 1 Library end-to-end at I0: batch generation against draft graph, gate, one-tap playback, session clock, disclosures, wind-down shutdown.
4. Knowledge Graph multi-axis schema + admin tooling + story↔node mapping + Topic Map dashboard with axis layers (parent-api).
5. Shelf 2 Commissioned: parent commissioning flow → async generation → gate → family shelf, "writing your story" states, branched-commission support.
6. I1 Steer: branch-tree generation/publishing, choice-point playback, ephemeral intent classification, safety hook.
7. STRICT_CONTENT_MODE + architecture/schema/string/copy lints + rung-boundary red-team CI.
8. I2 Wish behind flag: one-shot monologue capture → safety scan → commissioning request → parent approval flow.
9. Community Shelf data model + de-personalization pipeline + ToS hooks, behind OFF flag (no UI).
10. I3 YAML scripts + flagged-off implementation, no UI. Storybook schema reservation.
11. **COMPLIANCE_MAP.md** — table mapping each statutory duty (SB 243 §22602/§22602.5/§22603; NY GBL §1701/§1702) to code path, flag, test, and audit event. Maintained in every PR touching a boundary.

Throughout: plan before coding, small PRs per phase, and flag any point where a product requirement would weaken a compliance boundary — never silently resolve that tradeoff yourself.
