from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_serializer
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
    upfront_gold_given: int = 0
    potential_reward: int = 0
    
    created_at: datetime = Field(default_factory=datetime.now)

    @field_serializer('deadline', 'created_at', 'completed_at')
    def serialize_dt(self, dt: Optional[datetime], _info):
        if dt is None: return None
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.isoformat()

class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: str = "medium"
    deadline: Optional[datetime] = None

class TodoUpdate(BaseModel):
    deadline: Optional[datetime] = None
