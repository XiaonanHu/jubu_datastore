# Story Studio Pivot — Workstream Map

Buju pivots from a live conversational companion to a **Story Studio**: parents commission personalized stories; children listen to and steer pre-vetted adventures. Boundaries are regulatory (CA SB 243, NY GBL Art. 47, NY S9408A) and enforced in architecture, not prompts. Source spec: `story-mode-implementation-prompt-v3.md`.

## The three workstreams

| Doc | Run as | Produces | Depends on |
|---|---|---|---|
| `KNOWLEDGE_GRAPH_WORKSTREAM.md` | **Cowork session** on `jubu_datastore` | Draft graph YAML packs (4 axes × age bands, per-year treatments), `jubu_datastore/knowledge_graph/` loader/validator/age-view/coverage program, HTML preview for psychologist review | nothing — start now |
| `STORY_TEMPLATE_SPEC.md` | Input spec for content-authoring Cowork sessions + normative for schema | Template YAML format, slot grammar, cast packs; authored Library story templates | Graph (for tags/briefs); can draft in parallel |
| `IMPLEMENTATION_WORKSTREAM.md` | **Claude Code `/goal` session** with `jubu_backend` + `jubu_parent_app` + `jubu_datastore` (+ `jubu-deploy`) | `MIGRATION_PLAN.md` first (human review gate), then: publishing gate + worker, published-content store, playback service, session clock/disclosures, parent-api endpoints, full parent-app UX redesign, lints + red-team CI, `COMPLIANCE_MAP.md` | Consumes A + B outputs; gate/schema/app-shell phases can start with stubs |

## Suggested sequence

1. Kick off **A** (graph) — its YAML + age-view JSON unblock everything else and are pure content/tooling.
2. Start **C** with `/goal` — it must produce `MIGRATION_PLAN.md` and stop for your review before code. Review it while A runs.
3. Author Library stories per **B** once A's briefs exist; feed them through C's gate as soon as Phase 1 (gate + store) lands.
4. Psychologist review of A's draft taxonomy proceeds asynchronously via the HTML preview + `REVIEW_GUIDE.md`.

## Invariants that span all workstreams

- **Prime Directive:** no raw model output ever reaches a child; children only hear published content.
- **Preserve, don't delete:** the live-conversation capability is kept fully working, relocated to rung I4 (`child_sessions/open_conversation/`, flag `I4_COMPANION` OFF, no parent-facing UI). The migration turns "conversation is the only mode" into "conversation is one of five rungs, currently unavailable" — see `IMPLEMENTATION_WORKSTREAM.md` §0.1 and §2.1.
- **No child-keyed records** anywhere new; account-level data keys to `parent_account_id`.
- **Framing constraint:** exploration/territories/coverage language only — never assessment, scores, behind/ahead.
- **Narrator, not friend** string bans apply to every child-facing template, script, and app string.
- One primary graph tag per axis per story.
- Obey `jubu_backend/CLAUDE.md` (naming, tunables-in-YAML, child-data lifetime declarations, hot-path rules).
