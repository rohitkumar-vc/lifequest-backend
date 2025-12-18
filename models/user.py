from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from models.common import PyObjectId
from datetime import datetime

from core.time_utils import get_current_time

class UserStats(BaseModel):
    hp: int = 100
    xp: int = 0
    gold: float = 0.0
    level: int = 1
    max_xp: int = 100 # Scaling requirement for next level

class User(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    full_name: str = "Adventurer"
    username: str
    email: EmailStr
    hashed_password: str
    is_active: bool = True
    role: str = "user" # 'user' or 'admin'
    status: str = "active" # active, inactive, invited
    change_password_required: bool = False
    
    # Game Stats
    stats: UserStats = Field(default_factory=UserStats)
    
    # Auth
    reset_token: Optional[str] = None
    last_cron_check: datetime = Field(default_factory=get_current_time)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
