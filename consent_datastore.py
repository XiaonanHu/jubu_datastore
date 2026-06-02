"""
Datastore for COPPA consent events and Apple IAP subscriptions.

consent_events is append-only — rows are never updated or deleted.
On account deletion, PII fields are nulled but event_id + apple_transaction_id
are retained for at least 3 years (legal defence requirement).
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from jubu_datastore.logging import get_logger
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)

# Exhaustive set of valid event_type values. Validated before every insert.
VALID_EVENT_TYPES = {
    "account_created",
    "direct_notice_acknowledged",
    "consent_obtained",
    "consent_failed",
    "child_profile_created",
    "consent_revoked",
}


class ConsentEventModel(BaseDatastore.Base):
    __tablename__ = "consent_events"

    event_id = sa.Column(sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = sa.Column(sa.String(36), nullable=False, index=True)
    # account_created | direct_notice_acknowledged | consent_obtained |
    # consent_failed | child_profile_created | consent_revoked
    event_type = sa.Column(sa.String(64), nullable=False, index=True)
    timestamp = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow, index=True)
    ip_address = sa.Column(sa.String(64), nullable=True)
    user_agent = sa.Column(sa.Text, nullable=True)
    direct_notice_version = sa.Column(sa.String(64), nullable=True)
    privacy_policy_version = sa.Column(sa.String(32), nullable=True)
    vpc_method = sa.Column(sa.String(32), nullable=True)
    apple_transaction_id = sa.Column(sa.String(255), nullable=True)
    child_id = sa.Column(sa.String(36), nullable=True)
    failure_reason = sa.Column(sa.String(255), nullable=True)
    # Named event_metadata to avoid shadowing SQLAlchemy's reserved 'metadata' attribute
    event_metadata = sa.Column(sa.JSON, nullable=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)


class SubscriptionModel(BaseDatastore.Base):
    __tablename__ = "subscriptions"

    subscription_id = sa.Column(sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = sa.Column(sa.String(36), nullable=False, index=True)
    apple_transaction_id = sa.Column(sa.String(255), nullable=False, unique=True)
    apple_original_transaction_id = sa.Column(sa.String(255), nullable=False)
    product_id = sa.Column(sa.String(128), nullable=False)
    purchase_date = sa.Column(sa.DateTime, nullable=False)
    expires_date = sa.Column(sa.DateTime, nullable=True)
    # active | expired | cancelled | refunded
    status = sa.Column(sa.String(32), nullable=False, default="active")
    # Fernet-encrypted receipt data for re-verification
    receipt_data = sa.Column(sa.Text, nullable=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)


class ConsentDatastore(BaseDatastore):
    """
    Datastore for consent events and subscriptions.

    consent_events rows are APPEND-ONLY. This class intentionally does not
    expose update() or delete() methods for that table.
    """

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
            model_class=ConsentEventModel,
        )
        self._ensure_schema()
        logger.debug("ConsentDatastore initialized")

    # -------------------------------------------------------------------------
    # Required abstract method stubs (BaseDatastore enforces these)
    # -------------------------------------------------------------------------

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Use log_event() or create_subscription() instead."""
        raise NotImplementedError("Use log_event() for consent events.")

    def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Use get_events_for_parent() instead."""
        raise NotImplementedError("Use get_events_for_parent().")

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Consent events are append-only; updates are not permitted."""
        raise NotImplementedError("consent_events is append-only.")

    def delete(self, record_id: str) -> bool:
        """Consent events are append-only; deletion is not permitted."""
        raise NotImplementedError("consent_events is append-only.")

    # -------------------------------------------------------------------------
    # Consent event methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_event_row(parent_id: str, event_type: str, **kwargs) -> "ConsentEventModel":
        """Build a ConsentEventModel without adding it to a session."""
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{event_type}'. Must be one of: {sorted(VALID_EVENT_TYPES)}"
            )
        now = datetime.utcnow()
        return ConsentEventModel(
            event_id=str(uuid.uuid4()),
            parent_id=parent_id,
            event_type=event_type,
            timestamp=now,
            ip_address=kwargs.get("ip_address"),
            user_agent=kwargs.get("user_agent"),
            direct_notice_version=kwargs.get("direct_notice_version"),
            privacy_policy_version=kwargs.get("privacy_policy_version"),
            vpc_method=kwargs.get("vpc_method"),
            apple_transaction_id=kwargs.get("apple_transaction_id"),
            child_id=kwargs.get("child_id"),
            failure_reason=kwargs.get("failure_reason"),
            event_metadata=kwargs.get("event_metadata"),
            created_at=now,
        )

    def log_event(self, parent_id: str, event_type: str, **kwargs) -> str:
        """
        Append a consent event row. Returns the new event_id.

        Accepts keyword args matching column names:
          ip_address, user_agent, direct_notice_version, privacy_policy_version,
          vpc_method, apple_transaction_id, child_id, failure_reason, event_metadata
        """
        row = self._build_event_row(parent_id, event_type, **kwargs)
        with self.session_scope() as session:
            session.add(row)
        logger.info(f"Logged consent event: {event_type} for parent {parent_id}")
        return row.event_id

    def log_event_in_session(self, session, parent_id: str, event_type: str, **kwargs) -> str:
        """
        Add a consent event to an existing session without committing.
        Use this when the event must commit atomically with another write
        (e.g. user creation at signup, child profile creation).
        """
        row = self._build_event_row(parent_id, event_type, **kwargs)
        session.add(row)
        logger.info(f"Staged consent event: {event_type} for parent {parent_id}")
        return row.event_id

    def get_events_for_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """Return all consent events for a parent, ordered by timestamp ascending."""
        with self.session_scope() as session:
            rows = (
                session.query(ConsentEventModel)
                .filter(ConsentEventModel.parent_id == parent_id)
                .order_by(ConsentEventModel.timestamp.asc())
                .all()
            )
            return [self._event_to_dict(r) for r in rows]

    def has_active_consent(self, parent_id: str) -> bool:
        """
        Return True only when ALL three conditions hold:
          1. A consent_obtained event exists for this parent.
          2. No consent_revoked event exists with a timestamp AFTER the latest consent_obtained.
          3. The parent has at least one subscription with status='active'.

        This is the authoritative check used by the consent gate middleware.
        """
        with self.session_scope() as session:
            # Latest consent_obtained
            latest_obtained = (
                session.query(ConsentEventModel)
                .filter(
                    ConsentEventModel.parent_id == parent_id,
                    ConsentEventModel.event_type == "consent_obtained",
                )
                .order_by(ConsentEventModel.timestamp.desc())
                .first()
            )
            if latest_obtained is None:
                return False

            # Any revocation after the latest consent_obtained?
            revoked_after = (
                session.query(ConsentEventModel)
                .filter(
                    ConsentEventModel.parent_id == parent_id,
                    ConsentEventModel.event_type == "consent_revoked",
                    ConsentEventModel.timestamp > latest_obtained.timestamp,
                )
                .first()
            )
            if revoked_after is not None:
                return False

            # Active subscription: status='active' AND (no expiry date OR not yet expired).
            # expires_date is the source of truth — don't rely solely on status, because
            # Apple delivers expiration webhooks asynchronously and status may lag.
            now = datetime.utcnow()
            active_sub = (
                session.query(SubscriptionModel)
                .filter(
                    SubscriptionModel.parent_id == parent_id,
                    SubscriptionModel.status == "active",
                    sa.or_(
                        SubscriptionModel.expires_date.is_(None),
                        SubscriptionModel.expires_date > now,
                    ),
                )
                .first()
            )
            return active_sub is not None

    # -------------------------------------------------------------------------
    # Subscription methods
    # -------------------------------------------------------------------------

    def create_subscription(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write a new subscription row.

        Encrypts receipt_data before storage.
        data keys: parent_id, apple_transaction_id, apple_original_transaction_id,
                   product_id, purchase_date, expires_date (optional), receipt_data (optional)
        """
        sub_id = str(uuid.uuid4())
        receipt_raw = data.get("receipt_data", "")
        receipt_encrypted = (
            self.encrypt_data(receipt_raw).decode("utf-8") if receipt_raw else None
        )

        with self.session_scope() as session:
            row = SubscriptionModel(
                subscription_id=sub_id,
                parent_id=data["parent_id"],
                apple_transaction_id=data["apple_transaction_id"],
                apple_original_transaction_id=data["apple_original_transaction_id"],
                product_id=data["product_id"],
                purchase_date=data["purchase_date"],
                expires_date=data.get("expires_date"),
                status="active",
                receipt_data=receipt_encrypted,
                created_at=datetime.utcnow(),
            )
            session.add(row)

        logger.info(
            f"Created subscription {sub_id} for parent {data['parent_id']} "
            f"(txn: {data['apple_transaction_id']})"
        )
        return {"subscription_id": sub_id, "status": "active"}

    def create_subscription_and_log_consent(
        self, sub_data: Dict[str, Any], **event_kwargs
    ) -> Dict[str, Any]:
        """
        Write subscription row + consent_obtained event in a single transaction.

        Use this instead of calling create_subscription() + log_event() separately.
        If either write fails, both roll back.
        """
        sub_id = str(uuid.uuid4())
        receipt_raw = sub_data.get("receipt_data", "")
        receipt_encrypted = (
            self.encrypt_data(receipt_raw).decode("utf-8") if receipt_raw else None
        )
        event_row = self._build_event_row(
            sub_data["parent_id"], "consent_obtained", **event_kwargs
        )

        with self.session_scope() as session:
            sub_row = SubscriptionModel(
                subscription_id=sub_id,
                parent_id=sub_data["parent_id"],
                apple_transaction_id=sub_data["apple_transaction_id"],
                apple_original_transaction_id=sub_data["apple_original_transaction_id"],
                product_id=sub_data["product_id"],
                purchase_date=sub_data["purchase_date"],
                expires_date=sub_data.get("expires_date"),
                status="active",
                receipt_data=receipt_encrypted,
                created_at=datetime.utcnow(),
            )
            session.add(sub_row)
            session.add(event_row)

        logger.info(
            f"Created subscription {sub_id} + consent_obtained event "
            f"for parent {sub_data['parent_id']} (txn: {sub_data['apple_transaction_id']})"
        )
        return {"subscription_id": sub_id, "status": "active"}

    def get_active_subscription(self, parent_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recently created active subscription for a parent, or None.
        Requires status='active' AND (no expiry date OR not yet expired).
        """
        with self.session_scope() as session:
            now = datetime.utcnow()
            row = (
                session.query(SubscriptionModel)
                .filter(
                    SubscriptionModel.parent_id == parent_id,
                    SubscriptionModel.status == "active",
                    sa.or_(
                        SubscriptionModel.expires_date.is_(None),
                        SubscriptionModel.expires_date > now,
                    ),
                )
                .order_by(SubscriptionModel.created_at.desc())
                .first()
            )
            if row is None:
                return None
            return self._sub_to_dict(row)

    def update_subscription_status(self, apple_transaction_id: str, status: str) -> bool:
        """Update a subscription's status (for App Store Server Notification webhooks)."""
        with self.session_scope() as session:
            row = (
                session.query(SubscriptionModel)
                .filter(SubscriptionModel.apple_transaction_id == apple_transaction_id)
                .first()
            )
            if row is None:
                logger.warning(
                    f"update_subscription_status: txn {apple_transaction_id} not found"
                )
                return False
            row.status = status
        logger.info(f"Updated subscription {apple_transaction_id} status → {status}")
        return True

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _event_to_dict(row: ConsentEventModel) -> Dict[str, Any]:
        return {
            "event_id": row.event_id,
            "parent_id": row.parent_id,
            "event_type": row.event_type,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "direct_notice_version": row.direct_notice_version,
            "privacy_policy_version": row.privacy_policy_version,
            "vpc_method": row.vpc_method,
            "apple_transaction_id": row.apple_transaction_id,
            "child_id": row.child_id,
            "failure_reason": row.failure_reason,
            "event_metadata": row.event_metadata,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _sub_to_dict(row: SubscriptionModel) -> Dict[str, Any]:
        return {
            "subscription_id": row.subscription_id,
            "parent_id": row.parent_id,
            "apple_transaction_id": row.apple_transaction_id,
            "apple_original_transaction_id": row.apple_original_transaction_id,
            "product_id": row.product_id,
            "purchase_date": row.purchase_date.isoformat() if row.purchase_date else None,
            "expires_date": row.expires_date.isoformat() if row.expires_date else None,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
