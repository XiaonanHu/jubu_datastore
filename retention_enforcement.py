"""
Daily retention-enforcement job (ENG-333).

Enforces the promises in the privacy policy that no request-path code
enforces:

1. Expired facts:     soft-expire (active=False) immediately, hard-delete
                      after a grace window (facts_datastore.delete_expired_facts).
2. Telemetry window:  hard-delete telemetry rows older than the retention
                      window (telemetry_datastore.delete_events_older_than).
                      Grafana reads this table directly, so this also bounds
                      what dashboards can show.
3. Orphan sweep:      finish any partially-failed deletion. The account /
                      profile deletion cascades are sequential and not wrapped
                      in one transaction; if a step fails midway, child rows
                      can survive their profile. This sweep finds child_ids
                      that exist in data tables but not in child_profiles and
                      re-runs the standard per-store deletes for them.

Run daily via cron / Cloud Scheduler:

    python -m jubu_datastore.retention_enforcement

Every purge is logged as a structured [RETENTION_AUDIT] line for the
compliance audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

import sqlalchemy as sa

from jubu_datastore.datastore_factory import DatastoreFactory
from jubu_datastore.logging import get_logger

logger = get_logger(__name__)

TELEMETRY_RETENTION_DAYS = 90
EXPIRED_FACTS_GRACE_DAYS = 30

# Tables scanned for orphaned child rows. consent_events is intentionally
# absent: it is append-only, PII-nulled on deletion, and retained >= 3 years
# as legal evidence that consent existed.
ORPHAN_SCAN_TABLES = (
    "conversations",
    "child_facts",
    "stories",
    "child_capability_observations",
    "child_capability_state",
    "observed_interests",
    "inferred_traits",
    "telemetry_events",
)


class RetentionEnforcer:
    """One run() per day. Stateless; safe to re-run (idempotent deletes)."""

    def __init__(self) -> None:
        self.profile_ds = DatastoreFactory.create_profile_datastore()
        self.conversation_ds = DatastoreFactory.create_conversation_datastore()
        self.facts_ds = DatastoreFactory.create_facts_datastore()
        self.story_ds = DatastoreFactory.create_story_datastore()
        self.capability_ds = DatastoreFactory.create_capability_datastore()
        self.parent_chat_ds = DatastoreFactory.create_parent_chat_datastore()
        self.observed_interests_ds = (
            DatastoreFactory.create_observed_interests_datastore()
        )
        self.inferred_traits_ds = DatastoreFactory.create_inferred_traits_datastore()
        self.telemetry_ds = DatastoreFactory.create_telemetry_datastore()

    # ------------------------------------------------------------------
    # Orphan detection
    # ------------------------------------------------------------------

    def _existing_child_ids(self) -> Set[str]:
        with self.profile_ds.session_scope() as session:
            rows = session.execute(sa.text("SELECT id FROM child_profiles")).fetchall()
        return {row[0] for row in rows}

    def _child_ids_in_table(self, table_name: str) -> Set[str]:
        with self.profile_ds.session_scope() as session:
            rows = session.execute(
                sa.text(
                    f"SELECT DISTINCT child_id FROM {table_name} "
                    f"WHERE child_id IS NOT NULL"
                )
            ).fetchall()
        return {row[0] for row in rows}

    def _orphaned_parent_chat_pairs(self) -> List[Tuple[str, str]]:
        """(parent_id, child_id) pairs in parent_chat whose child is gone."""
        existing = self._existing_child_ids()
        with self.profile_ds.session_scope() as session:
            rows = session.execute(
                sa.text(
                    "SELECT DISTINCT parent_id, child_id FROM parent_chat_sessions "
                    "UNION "
                    "SELECT DISTINCT parent_id, child_id FROM parent_chat_rolling_summary"
                )
            ).fetchall()
        return [(row[0], row[1]) for row in rows if row[1] not in existing]

    def sweep_orphaned_child_rows(self) -> Dict[str, Any]:
        """Delete data rows whose child profile no longer exists.

        Reuses the same per-store delete methods as the deletion cascades so
        dependent rows (conversation turns, parent chat messages) are removed
        correctly, rather than issuing raw table deletes.
        """
        existing = self._existing_child_ids()
        orphaned: Set[str] = set()
        for table_name in ORPHAN_SCAN_TABLES:
            orphaned |= self._child_ids_in_table(table_name) - existing

        for child_id in sorted(orphaned):
            self.conversation_ds.delete_all_for_child(child_id)
            self.facts_ds.delete_all_for_child(child_id)
            self.story_ds.delete_all_for_child(child_id)
            self.capability_ds.delete_all_for_child(child_id)
            self.observed_interests_ds.delete_all_for_child(child_id)
            self.inferred_traits_ds.delete_all_for_child(child_id)
            # Telemetry keeps rows for aggregate counts; identifying fields
            # are nulled — same treatment the deletion cascade applies.
            self.telemetry_ds.scrub_child_data(child_id)

        orphaned_pairs = self._orphaned_parent_chat_pairs()
        for parent_id, child_id in orphaned_pairs:
            self.parent_chat_ds.delete_all_for_child(parent_id, child_id)

        return {
            "orphaned_child_ids_swept": len(orphaned),
            "orphaned_parent_chat_pairs_swept": len(orphaned_pairs),
        }

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"ran_at": datetime.utcnow().isoformat()}

        # 1. Facts: soft-expire now, hard-delete past the grace window.
        summary["facts_soft_expired"] = self.facts_ds.expire_old_facts()
        summary["facts_hard_deleted"] = self.facts_ds.delete_expired_facts(
            grace_days=EXPIRED_FACTS_GRACE_DAYS
        )

        # 2. Telemetry retention window.
        summary["telemetry_rows_deleted"] = self.telemetry_ds.delete_events_older_than(
            TELEMETRY_RETENTION_DAYS
        )

        # 3. Orphan sweep (partial-deletion safety net).
        summary.update(self.sweep_orphaned_child_rows())

        # Compliance audit trail: one structured line per run.
        logger.info(f"[RETENTION_AUDIT] {json.dumps(summary)}")
        return summary


def main() -> None:
    summary = RetentionEnforcer().run()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
