from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from core.database import PyObjectId

class Todo(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    title: str
    description: Optional[str] = None
    difficulty: str = "medium" # 'easy', 'medium', 'hard'
    
    # Scheduling & Status
    deadline: Optional[datetime] = None
    status: Literal["active", "completed", "overdue"] = "active"
    completed_at: Optional[datetime] = None
    
    # QStash Integration
    qstash_message_id: Optional[str] = None
    
    # Economy Tracking (The "Loan")
    upfront_gold_given: float = 0.0
    potential_reward: float = 0.0
    
    created_at: datetime = Field(default_factory=datetime.now)

class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: str = "medium"
    deadline: Optional[datetime] = None

class TodoUpdate(BaseModel):
    deadline: Optional[datetime] = None
