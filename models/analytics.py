from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from .common import PyObjectId

from core.time_utils import get_current_time

class ActivityLog(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    user_id: str
    message: str
    xp_change: int = 0
    type: str = "general" # 'completion', 'habit', 'level_up', 'penalty'
    timestamp: datetime = Field(default_factory=get_current_time)
