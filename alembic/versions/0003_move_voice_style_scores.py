"""data: move voice_style_scores out of child_profiles.preferences.

Converts migrations/inferred_traits_001_move_voice_style_scores.py (the one
DATA migration among the manual scripts) into the Alembic history: the
system-learned voice-style bandit state stored under
child_profiles.preferences["voice_style_scores"] moves into the child's
inferred_traits row (ENG-347 Phase 3d). The parent-declared
preferences["voice_style"] override stays put.

Unlike the original script this does not import jubu_datastore — it works on
the bound connection with lightweight table constructs — and it fixes a latent
bug in the original: the script read `row.child_id` from ChildProfileModel,
which has no such attribute (the profile PK `id` IS the child id), so the
script crashed on any database that actually had scores to move.

Upsert semantics mirror InferredTraitsDatastore.upsert_inferred_traits:
insert with evidence_count=1, or update voice_style_scores/preferred_style
and bump evidence_count.

On a fresh database there are no rows, so both directions are no-ops.
downgrade() is a true inverse for data moved by upgrade(): scores found in
inferred_traits are put back into the profile's preferences blob and cleared
from the traits row.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03

"""

from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


child_profiles = sa.table(
    "child_profiles",
    sa.column("id", sa.String(36)),
    sa.column("preferences", sa.JSON()),
    sa.column("updated_at", sa.DateTime()),
)

inferred_traits = sa.table(
    "inferred_traits",
    sa.column("child_id", sa.String(36)),
    sa.column("curiosity_mode_by_kind", sa.JSON()),
    sa.column("preferred_style", sa.String(64)),
    sa.column("preferred_style_confidence", sa.Float()),
    sa.column("voice_style_scores", sa.JSON()),
    sa.column("evidence_count", sa.Integer()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)


def _best_learned_style(scores):
    seen = [
        (codename, entry.get("score", 0.0))
        for codename, entry in (scores or {}).items()
        if int(entry.get("n", 0) or 0) > 0
    ]
    return max(seen, key=lambda pair: pair[1])[0] if seen else None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("child_profiles") or not insp.has_table("inferred_traits"):
        return

    now = datetime.utcnow()
    profiles = bind.execute(
        sa.select(child_profiles.c.id, child_profiles.c.preferences)
    ).fetchall()

    for child_id, preferences in profiles:
        prefs = dict(preferences or {})
        scores = prefs.get("voice_style_scores")
        if not scores:
            continue

        existing = bind.execute(
            sa.select(
                inferred_traits.c.child_id, inferred_traits.c.evidence_count
            ).where(inferred_traits.c.child_id == child_id)
        ).first()
        if existing is None:
            bind.execute(
                sa.insert(inferred_traits).values(
                    child_id=child_id,
                    curiosity_mode_by_kind={},
                    preferred_style=_best_learned_style(scores),
                    preferred_style_confidence=None,
                    voice_style_scores=scores,
                    evidence_count=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            bind.execute(
                sa.update(inferred_traits)
                .where(inferred_traits.c.child_id == child_id)
                .values(
                    voice_style_scores=scores,
                    preferred_style=_best_learned_style(scores),
                    evidence_count=(existing.evidence_count or 0) + 1,
                    updated_at=now,
                )
            )

        prefs.pop("voice_style_scores", None)
        bind.execute(
            sa.update(child_profiles)
            .where(child_profiles.c.id == child_id)
            .values(preferences=prefs, updated_at=now)
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("child_profiles") or not insp.has_table("inferred_traits"):
        return

    now = datetime.utcnow()
    traits = bind.execute(
        sa.select(inferred_traits.c.child_id, inferred_traits.c.voice_style_scores)
    ).fetchall()

    for child_id, scores in traits:
        if not scores:
            continue
        profile = bind.execute(
            sa.select(child_profiles.c.id, child_profiles.c.preferences).where(
                child_profiles.c.id == child_id
            )
        ).first()
        if profile is None:
            continue

        prefs = dict(profile.preferences or {})
        prefs["voice_style_scores"] = scores
        bind.execute(
            sa.update(child_profiles)
            .where(child_profiles.c.id == child_id)
            .values(preferences=prefs, updated_at=now)
        )
        bind.execute(
            sa.update(inferred_traits)
            .where(inferred_traits.c.child_id == child_id)
            .values(voice_style_scores={}, preferred_style=None, updated_at=now)
        )
