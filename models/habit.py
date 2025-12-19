from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.common import PyObjectId
from core.time_utils import get_current_time

class Milestone(BaseModel):
    label: str
    day_count: int
    unlocked_at: datetime = Field(default_factory=get_current_time)

class Habit(BaseModel):
    """
    Represents a Habit in the system.
    
    Types:
    - 'positive' (Building): Reward for doing it, Penalty for skipping.
    - 'negative' (Breaking): Reward for avoiding it, Penalty for indulging.
    
    Attributes:
    - current_streak: Consecutive days handling the habit correctly.
    - best_streak: All-time high streak.
    - milestones: List of unlocked badges.
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: Optional[str] = None
    title: str = Field(..., max_length=100)
    type: str = "positive" # 'positive' or 'negative'
    difficulty: str = "medium" # 'easy', 'medium', 'hard'
    description: Optional[str] = None
    
    # Streak Tracking
    # For Positive: "Current consecutive days done"
    # For Negative: "Current consecutive days avoided"
    current_streak: int = 0
    best_streak: int = 0
    
    # Tracking
    last_completed_date: Optional[datetime] = None # When last action (Performed/Avoided) happened
    
    # Gamification
    milestones: List[Milestone] = []
    created_at: datetime = Field(default_factory=get_current_time)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
