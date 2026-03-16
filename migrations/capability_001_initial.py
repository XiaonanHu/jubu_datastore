"""
Initial migration for capability tables.

Creates child_capability_observations first, then child_capability_state.
Run with: python -m jubu_datastore.migrations.capability_001_initial [DATABASE_URL]
"""

from __future__ import annotations

import os
import sys

# Ensure package is importable when run as script
if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if parent not in sys.path:
        sys.path.insert(0, parent)

from sqlalchemy import create_engine

from jubu_datastore.models.capability_schema import (
    ChildCapabilityObservationModel,
    ChildCapabilityStateModel,
)


def run(engine=None):
    if engine is None:
        url = os.environ.get("DATABASE_URL", "sqlite:///kidschat.db")
        engine = create_engine(url)
    # Order: observations first, then state (no FK between them; for clarity)
    ChildCapabilityObservationModel.__table__.create(engine, checkfirst=True)
    ChildCapabilityStateModel.__table__.create(engine, checkfirst=True)
    print("Capability tables created (or already exist).")


if __name__ == "__main__":
    run()
