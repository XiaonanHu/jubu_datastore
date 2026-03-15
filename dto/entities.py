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
