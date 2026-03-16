from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


class User(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    hashed_password: Optional[str] = None

    class Config:
        from_attributes = True


class ChildProfile(BaseModel):
    id: str
    name: str
    age: int
    interests: List[str] = []
    preferences: Dict[str, Any] = {}
    parent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class CapabilityObservation(BaseModel):
    """One evaluation event (one row in child_capability_observations)."""

    id: str
    child_id: str
    session_id: str
    item_id: str
    item_version: int
    framework: str
    domain: str
    subdomain: str
    observation_status: str
    confidence: Optional[float] = None
    evidence_text: Optional[str] = None
    evaluator_type: str
    evaluator_version: Optional[str] = None
    raw_score_json: Optional[Dict[str, Any]] = None
    observed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ChildCapabilityState(BaseModel):
    """Current skill state for one (child_id, item_id) (one row in child_capability_state)."""

    id: str
    child_id: str
    item_id: str
    item_version: int
    framework: str
    domain: str
    subdomain: str
    current_status: str
    confidence: Optional[float] = None
    mastery_score: float = 0.0
    evidence_count: int = 0
    first_observed_at: Optional[datetime] = None
    last_observed_at: Optional[datetime] = None
    last_session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
