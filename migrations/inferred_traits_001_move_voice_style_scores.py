"""
SUPERSEDED: converted to Alembic — see alembic/versions/ (baseline 0001,
legacy bridge 0002, data move 0003) and scripts/verify_migrations.py.
Kept only until the Alembic history is verified against production
databases; do not add new migration scripts to this folder.
NOTE: this script has a latent bug — it reads `row.child_id` from
ChildProfileModel, which only has `id`, so it crashes on any database
that actually has scores to move. Alembic revision 0003 fixes this.

Move learned voice-style bandit state out of `child_profiles.preferences` into the
`inferred_traits` row (ENG-347 Phase 3d).

Why: `preferences["voice_style_scores"]` is SYSTEM-LEARNED data that was living inside
the PARENT-DECLARED preferences blob — the exact declared/learned mixing ENG-347
removes. The parent OVERRIDE `preferences["voice_style"]` is genuinely parent-declared
and STAYS put; only `voice_style_scores` moves.

Unlike the schema migrations in this folder, this is a DATA migration and therefore
imports jubu_datastore (it needs JSON handling + the inferred_traits upsert). Requires
DATABASE_URL and ENCRYPTION_KEY in the environment. Idempotent: rows whose
`voice_style_scores` key is already gone are skipped, so re-running is safe.

Run from repo root:
  DATABASE_URL=... ENCRYPTION_KEY=... python migrations/inferred_traits_001_move_voice_style_scores.py
"""

from __future__ import annotations


def _best_learned_style(scores):
    seen = [
        (codename, entry.get("score", 0.0))
        for codename, entry in (scores or {}).items()
        if int(entry.get("n", 0) or 0) > 0
    ]
    return max(seen, key=lambda pair: pair[1])[0] if seen else None


def run():
    from jubu_datastore.datastore_factory import DatastoreFactory
    from jubu_datastore.profile_datastore import ChildProfileModel

    profile_ds = DatastoreFactory.create_profile_datastore()
    # Constructing the traits datastore ensures the `inferred_traits` table exists.
    traits_ds = DatastoreFactory.create_inferred_traits_datastore()

    moved = 0
    with profile_ds.session_scope() as session:
        rows = session.query(ChildProfileModel).all()
        for row in rows:
            prefs = dict(row.preferences or {})
            scores = prefs.get("voice_style_scores")
            if not scores:
                continue
            traits_ds.upsert_inferred_traits(
                row.child_id,
                {
                    "voice_style_scores": scores,
                    "preferred_style": _best_learned_style(scores),
                },
            )
            prefs.pop("voice_style_scores", None)
            row.preferences = prefs  # reassign so SQLAlchemy marks the JSON dirty
            moved += 1
        session.commit()

    print(f"moved voice_style_scores into inferred_traits for {moved} child(ren).")


if __name__ == "__main__":
    run()
