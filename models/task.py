from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.common import PyObjectId

from core.time_utils import get_current_time

class Task(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    title: str = Field(..., max_length=100)
    type: str # 'habit', 'daily', 'todo'
    difficulty: str # 'easy', 'medium', 'hard'
    description: Optional[str] = None
    
    # State
    completed: bool = False
    deadline: Optional[datetime] = None
    status: str = "active" # active, expired, completed
    
    # Logic Flags
    upfront_gold_given: bool = False
    is_dishonorable: bool = False
    streak: int = 0
    created_at: datetime = Field(default_factory=get_current_time)
    completed_today: bool = False # For Habits: Track if done today for strike update
    last_completed_date: Optional[datetime] = None # Reliable timestamp for streak logic

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
