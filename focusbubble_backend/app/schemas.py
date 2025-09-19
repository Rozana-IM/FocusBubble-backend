from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
  
class UserCreate(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
  
class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str]
    picture: Optional[str]

    model_config = {
        "from_attributes": True
    }
  
class ScheduleCreate(BaseModel):
    label: str = "Focus"
    duration_minutes: int = 25
    apps: List[str] = []
    is_active: bool = False
  
class ScheduleOut(BaseModel):
    id: int
    label: str
    duration_minutes: int
    apps: List[str]
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
  
class BlockedAppCreate(BaseModel):
    package_name: str
    app_name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
  
class BlockedAppOut(BaseModel):
    id: int
    package_name: str
    app_name: Optional[str]
    start_time: datetime
    end_time: datetime
    is_active: bool

    model_config = {
        "from_attributes": True
    }
  
class SessionCreate(BaseModel):
    user_id: int
    schedule_id: Optional[int] = None
    duration_minutes: int
  
class SessionOut(BaseModel):
    id: int
    user_id: int
    schedule_id: Optional[int]
    start_time: datetime
    end_time: datetime
    paused: bool
    remaining_seconds: Optional[int]
    status: str

    model_config = {
        "from_attributes": True
    }
  
# Simple token input for google ID token
class TokenIn(BaseModel):
    id_token: str
