"""
Telemetry-events datastore.

Persists every `telemetry.emit()` call as a row in `telemetry_events`,
so the stats.buju.ai dashboard can query engagement events in near-real
time alongside the conversation tables.

Design notes:
- Inserts are **best-effort**: any exception is swallowed and logged.
  Telemetry must never break a turn.
- Caller is expected to invoke `insert()` from a background thread (see
  `jubu_chat.chat.core.telemetry`).  This datastore does not own a
  thread pool — keeping it simple and stateless.
- Table is auto-created via `_ensure_schema` on first init.  No migration
  script is needed for fresh deploys; existing deploys get the table on
  the next backend restart (idempotent `CREATE TABLE IF NOT EXISTS`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.logging import get_logger

logger = get_logger(__name__)


class TelemetryEventModel(BaseDatastore.Base):
    """One row per `telemetry.emit()` call."""

    __tablename__ = "telemetry_events"

    id = sa.Column(sa.String(36), primary_key=True)
    ts = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow, index=True)
    event = sa.Column(sa.String(64), nullable=False, index=True)
    conversation_id = sa.Column(sa.String(36), nullable=True, index=True)
    child_id = sa.Column(sa.String(36), nullable=True, index=True)
    fields = sa.Column(sa.JSON, nullable=False, default=dict)

    __table_args__ = (
        sa.Index("idx_events_event_ts", "event", "ts"),
    )


class TelemetryDatastore(BaseDatastore):
    """Best-effort writer for `telemetry_events`. SELECTs are out of scope —
    the dashboard reads the table directly via the Postgres datasource."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ):
        super().__init__(
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
            model_class=TelemetryEventModel,
        )
        self._ensure_schema()

    # ------------------------------------------------------------------
    # BaseDatastore abstract surface
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any]) -> TelemetryEventModel:
        """Generic create — unused by the production telemetry path; insert()
        is the typed entry point."""
        return self.insert(
            event=data["event"],
            conversation_id=data.get("conversation_id"),
            child_id=data.get("child_id"),
            fields=data.get("fields", {}),
        )

    def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        with self.session_scope() as session:
            row = session.query(TelemetryEventModel).filter(
                TelemetryEventModel.id == record_id
            ).first()
            return _to_dict(row) if row else None

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        # Telemetry rows are append-only; no updates.
        raise NotImplementedError("telemetry_events rows are immutable")

    def delete(self, record_id: str) -> bool:
        # Retention deletes happen via the Phase-3 cron, not this method.
        raise NotImplementedError("use the retention cron, not delete()")

    # ------------------------------------------------------------------
    # Public API — the only method telemetry.emit() actually calls.
    # ------------------------------------------------------------------

    def insert(
        self,
        event: str,
        conversation_id: Optional[str] = None,
        child_id: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[TelemetryEventModel]:
        """Insert one row.  Returns None on any error (best-effort)."""
        try:
            with self.session_scope() as session:
                row = TelemetryEventModel(
                    id=str(uuid.uuid4()),
                    event=event,
                    conversation_id=conversation_id,
                    child_id=child_id,
                    fields=fields or {},
                )
                session.add(row)
                # Flush so we can return a populated id even though we
                # don't actually use it on the hot path.
                session.flush()
                return row
        except Exception as exc:
            # Stay quiet: telemetry must never break a turn.
            logger.warning(f"telemetry insert failed for event={event!r}: {exc}")
            return None

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Used by tests / manual debugging only.  Production reads happen
        through Grafana's Postgres datasource."""
        with self.session_scope() as session:
            rows = (
                session.query(TelemetryEventModel)
                .order_by(TelemetryEventModel.ts.desc())
                .limit(limit)
                .all()
            )
            return [_to_dict(r) for r in rows]


def _to_dict(row: TelemetryEventModel) -> Dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts,
        "event": row.event,
        "conversation_id": row.conversation_id,
        "child_id": row.child_id,
        "fields": row.fields or {},
    }
