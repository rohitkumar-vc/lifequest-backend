from fastapi import APIRouter, HTTPException, status, Depends
from core.leveling import calculate_new_level_and_xp
from typing import List, Optional, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel
from models.task import Task
from models.user import User
from models.common import PyObjectId
from routes.auth import get_current_user
from core.database import db
from bson import ObjectId
from core.time_utils import get_current_time

from core.config import settings

router = APIRouter(prefix="/tasks", tags=["Tasks"])

class HabitTrigger(BaseModel):
    direction: Literal["positive", "negative"]

@router.post("/", response_model=Task)
async def create_task(task_in: Task, current_user: User = Depends(get_current_user)):
    """
    Create a task.
    Logic:
    - If deadline is set: User Gold += Reward_Value (Advance Payment).
    - User XP += 0.
    """
    task_in.user_id = str(current_user.id)
    task_in.created_at = get_current_time()
    
    # Logic: Upfront Gold
    if task_in.deadline:
        task_in.upfront_gold_given = True
        # Calculate Reward based on Difficulty
        mult = settings.TODO_DIFFICULTY_MULTIPLIERS.get(task_in.difficulty, 1)
        reward = settings.TODO_REWARD_GOLD * mult
        
        # Add Gold to User
        new_gold = current_user.stats.gold + reward
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.gold": new_gold}}
        )
    
    task_dump = task_in.model_dump(by_alias=True, exclude={"id"})
    result = await db.tasks.insert_one(task_dump)
    created_task = await db.tasks.find_one({"_id": result.inserted_id})
    return Task(**created_task)



@router.get("/", response_model=List[Task])
async def get_tasks(current_user: User = Depends(get_current_user)):
    # No sync needed, handled by scheduler
    tasks_cursor = db.tasks.find({"user_id": str(current_user.id)})
    tasks = await tasks_cursor.to_list(length=100)
    return [Task(**task) for task in tasks]

@router.post("/{task_id}/complete", response_model=Task)
async def complete_task(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Generic Completion (Mainly for Todos).
    Logic:
    - User Gold += Reward_Value.
    - User XP += XP_Value.
    - Dishonor Check: If is_dishonorable=True, XP = 0.
    """
    task_data = await db.tasks.find_one({"_id": ObjectId(task_id), "user_id": str(current_user.id)})
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = Task(**task_data)
    if task.completed:
        raise HTTPException(status_code=400, detail="Task already completed")

    # Update Stats
    mult = settings.TODO_DIFFICULTY_MULTIPLIERS.get(task.difficulty, 1)
    
    gold_increase = settings.TODO_REWARD_GOLD * mult
    xp_increase = (settings.TODO_XP_VALUE * mult) if not task.is_dishonorable else 0
    
    new_gold = current_user.stats.gold + gold_increase
    
    # Scaling Level Logic
    new_level, new_xp = calculate_new_level_and_xp(
        current_user.stats.level, 
        current_user.stats.xp, 
        xp_increase
    )
    
    # Update User
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {
            "stats.gold": new_gold,
            "stats.xp": new_xp,
            "stats.level": new_level
        }}
    )

    # Log Activity
    await db.activity_logs.insert_one({
        "user_id": str(current_user.id),
        "message": f"Completed task: {task.title}",
        "xp_change": xp_increase,
        "type": "completion",
        "timestamp": get_current_time()
    })
    
    # Update Task (No Streak for Todos)
    await db.tasks.update_one(
        {"_id": task.id},
        {"$set": {"completed": True, "status": "completed"}}
    )
    
    updated_task = await db.tasks.find_one({"_id": task.id})
    return Task(**updated_task)

@router.post("/{task_id}/renew", response_model=Task)
async def renew_task(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Renewing (Redemption):
    - User pays Renewal Fee (e.g., 10% of reward).
    - Deadline is extended. Status -> ACTIVE.
    """
    task_data = await db.tasks.find_one({"_id": ObjectId(task_id), "user_id": str(current_user.id)})
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = Task(**task_data)
    
    # Renewal Based on Difficulty Reward
    mult = settings.TODO_DIFFICULTY_MULTIPLIERS.get(task.difficulty, 1)
    base_reward = settings.TODO_REWARD_GOLD * mult
    renewal_fee = base_reward * settings.TODO_RENEWAL_FEE_PERCENT
    
    if current_user.stats.gold < renewal_fee:
        raise HTTPException(status_code=400, detail="Not enough gold to renew")
        
    # Deduct Gold
    await db.users.update_one(
        {"_id": current_user.id},
        {"$inc": {"stats.gold": -renewal_fee}}
    )
    
    # Extend Deadline (e.g., by 1 day)
    new_deadline = None
    if task.deadline:
         new_deadline = task.deadline + timedelta(days=1)
         
    await db.tasks.update_one(
        {"_id": task.id},
        {"$set": {
            "status": "active", 
            "deadline": new_deadline
        }}
    )
    
    updated_task = await db.tasks.find_one({"_id": task.id})
    return Task(**updated_task)

@router.delete("/{task_id}")
async def delete_task(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Handle Dishonor Logic:
    If task gave upfront gold and is deleted before completion, take back gold?
    Or just normal delete.
    Implementing strict catch: If upfront gold was given and task not completed, 
    user must pay it back (deduct gold).
    """
    task_data = await db.tasks.find_one({"_id": ObjectId(task_id), "user_id": str(current_user.id)})
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = Task(**task_data)
    
    if task.upfront_gold_given and not task.completed:
        # Penalty: Pay back the gold (Based on difficulty)
        mult = settings.TODO_DIFFICULTY_MULTIPLIERS.get(task.difficulty, 1)
        refund_amount = settings.TODO_REWARD_GOLD * mult
        
        await db.users.update_one(
            {"_id": current_user.id},
            {"$inc": {"stats.gold": -refund_amount}}
        )
        
    await db.tasks.delete_one({"_id": task.id})
    return {"message": "Task deleted"}

@router.post("/{task_id}/habit-toggle", response_model=Task)
async def toggle_habit_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Habit Logic (Robust):
    - Uses last_completed_date to determine validity.
    - If completing (Done):
        - If already done Today: Ignore/Error.
        - If done Yesterday: Streak += 1.
        - If done < Yesterday: Streak = 1.
        - Update last_completed_date = Today.
    - If undoing (Not Done):
         - Allow undo only if done Today.
         - Revert rewards.
         - Streak:
            - If Streak was > 1, decrement (e.g. 5 -> 4).
            - If Streak was 1, it becomes 0.
         - Reset last_completed_date to Yesterday (if Streak > 0) or None?
           Complexity: If we undo, we don't know exactly when the *previous* completion was without history.
           Simplification: If Undo, just decrement Streak.
           last_completed_date -> Set to Yesterday? 
           If the user did it Yesterday, Streak > 0.
           If we set it to Yesterday, scheduler won't penalize.
           If we really want to Undo "Today's" action, we revert to state "Before Today".
    """
    task_data = await db.tasks.find_one({"_id": ObjectId(task_id), "user_id": str(current_user.id)})
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    task = Task(**task_data)
    
    if task.type != 'habit':
        raise HTTPException(status_code=400, detail="Not a habit")

    mult_map = {"easy": 1, "medium": 2, "hard": 4}
    mult = mult_map.get(task.difficulty, 1)
    
    gold_gain = mult * 1.0
    xp_gain = mult * 5
    
    now_ist = get_current_time()
    today_date = now_ist.date()
    yesterday_date = today_date - timedelta(days=1)
    
    last_completed_date = task.last_completed_date
    # Migration/Fallback logic
    if not last_completed_date and task.completed_today:
         # Assume it was done today if flag matches
         last_completed_date = now_ist
    
    # Check if performing "Done" or "Undo" depends on if it's already done today
    # We use 'completed_today' as the quick UI flag, but verify with date
    is_done_today = False
    if last_completed_date:
        if last_completed_date.date() == today_date:
            is_done_today = True
            
    if not is_done_today:
        # --- ACTION: MARK DONE ---
        new_completed_today = True
        new_last_completed_date = now_ist
        
        # Streak Logic
        if last_completed_date and last_completed_date.date() == yesterday_date:
            # Done yesterday -> Streak continues
            new_streak = task.streak + 1
        elif last_completed_date and last_completed_date.date() == today_date:
            # Should be caught by is_done_today check, but just in case
            new_streak = task.streak 
        else:
            # Missed yesterday (or first time) -> Streak resets to 1 (Start of new streak)
            # Or if streak was 0, it becomes 1.
            # Wait, if I missed yesterday, my streak IS broken.
            # This action starts a NEW streak.
            new_streak = 1
        
        # Award Rewards
        new_gold = current_user.stats.gold + gold_gain
        
        new_level, new_xp = calculate_new_level_and_xp(
            current_user.stats.level,
            current_user.stats.xp,
            xp_gain
        )
        
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.gold": new_gold, "stats.xp": new_xp, "stats.level": new_level}}
        )
        
        # Log
        await db.activity_logs.insert_one({
            "user_id": str(current_user.id),
            "message": f"Habit Done: {task.title}",
            "xp_change": xp_gain,
            "type": "habit",
            "timestamp": now_ist
        })
        
    else:
        # --- ACTION: UNDO ---
        new_completed_today = False
        # We can't know definitively when the previous completion was.
        # But we must ensure 'last_completed_date' is NOT Today anymore.
        # Safest bet: Set it to Yesterday.
        # Why? Because if we set it to None, Streak -> 0.
        # If the user HAD a streak properly yesterday, we want to preserve it so they can "Redo" today if they want.
        # If they truly didn't do it yesterday, setting it to Yesterday is "cheating" but acceptable for Undo logic limitation.
        # A better approach: Look at current streak.
        # If Streak > 1: It implies they did it yesterday. So set date = Yesterday.
        # If Streak == 1: It implies this was the first day. Set date = None (or very old).
        
        if task.streak > 1:
            new_last_completed_date = now_ist - timedelta(days=1)
            new_streak = task.streak - 1
        else:
            new_last_completed_date = None # Or old date
            new_streak = 0
            
        # Revert stats
        # Revert stats (Use scaling logic to handle potential de-leveling)
        new_level, new_xp = calculate_new_level_and_xp(
            current_user.stats.level,
            current_user.stats.xp,
            -xp_gain
        )
        
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.gold": current_user.stats.gold - gold_gain, "stats.xp": new_xp, "stats.level": new_level}}
        )

    # Update Task
    await db.tasks.update_one(
        {"_id": task.id},
        {"$set": {
            "completed_today": new_completed_today,
            "last_completed_date": new_last_completed_date,
            "streak": new_streak
        }}
    )

    updated_task = await db.tasks.find_one({"_id": task.id})
    return Task(**updated_task)

@router.post("/{task_id}/daily-toggle", response_model=Task)
async def toggle_daily(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Daily Logic:
    Complete: User Gold += Reward. User XP += Reward. Task completed = True. Streak += 1.
    Undo: User Gold -= Reward. User XP -= Reward. Task completed = False. Streak -= 1.
    """
    task_data = await db.tasks.find_one({"_id": ObjectId(task_id), "user_id": str(current_user.id)})
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    task = Task(**task_data)
    
    if task.type != 'daily':
        raise HTTPException(status_code=400, detail="Not a daily")

    gold_change = settings.DAILY_REWARD_GOLD
    xp_change = settings.DAILY_XP_VALUE
    
    if not task.completed:
        # Marking Complete
        new_completed = True
        streak_change = 1
        status_val = "completed"
    else:
        # Undo
        new_completed = False
        gold_change = -gold_change
        xp_change = -xp_change
        streak_change = -1
        status_val = "active"
        
    # Update User
    new_gold = current_user.stats.gold + gold_change
    new_xp = current_user.stats.xp + xp_change
    # Scaling Level Logic (Handles both gain and loss)
    new_level, new_xp = calculate_new_level_and_xp(
        current_user.stats.level,
        current_user.stats.xp,
        xp_change
    )
    
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {
            "stats.gold": new_gold,
            "stats.xp": new_xp, 
            "stats.level": new_level
        }}
    )
    
    # Update Task
    new_streak = max(0, task.streak + streak_change)
    await db.tasks.update_one(
        {"_id": task.id},
        {"$set": {
            "completed": new_completed, 
            "status": status_val,
            "streak": new_streak
        }}
    )
    
    updated_task = await db.tasks.find_one({"_id": task.id})
    return Task(**updated_task)
