from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel
from models.habit import Habit, Milestone
from models.user import User
from routes.auth import get_current_user
from core.database import db
from bson import ObjectId
from core.time_utils import get_current_time
from core.leveling import calculate_new_level_and_xp
from core.config import settings

router = APIRouter(prefix="/habits", tags=["Habits"])

class HabitTrigger(BaseModel):
    action: Literal["success", "failure"]

@router.post("/", response_model=Habit)
async def create_habit(habit_in: Habit, current_user: User = Depends(get_current_user)):
    habit_in.user_id = str(current_user.id)
    habit_in.created_at = get_current_time()
    
    habit_dump = habit_in.model_dump(by_alias=True, exclude={"id"})
    result = await db.habits.insert_one(habit_dump)
    created_habit = await db.habits.find_one({"_id": result.inserted_id})
    return Habit(**created_habit)

@router.get("/", response_model=List[Habit])
async def get_habits(current_user: User = Depends(get_current_user)):
    cursor = db.habits.find({"user_id": str(current_user.id)})
    habits = await cursor.to_list(length=100)
    return [Habit(**h) for h in habits]

@router.delete("/{habit_id}")
async def delete_habit(habit_id: str, current_user: User = Depends(get_current_user)):
    result = await db.habits.delete_one({"_id": ObjectId(habit_id), "user_id": str(current_user.id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"message": "Habit deleted"}

@router.post("/{habit_id}/trigger", response_model=dict)
async def trigger_habit(habit_id: str, trigger: HabitTrigger, current_user: User = Depends(get_current_user)):
    """
    Trigger a Habit Action (The Core Gamification Logic).

    Implements the 4-State System:
    1. Positive + Success (Performed):
       - User performed a good habit.
       - Result: +XP, +Gold, +Streak. Check Milestones.
    
    2. Positive + Failure (Skipped):
       - User missed a good habit.
       - Result: -HP (Penalty), Streak Resets to 0.

    3. Negative + Success (Avoided):
       - User successfully resisted a bad habit.
       - Result: +XP, +Gold, +Streak. Check Milestones.

    4. Negative + Failure (Indulged):
       - User gave in to a bad habit.
       - Result: -HP (Heavy Penalty), Streak Resets to 0.

    Returns:
        dict: {
            "habit": Updated Habit Object,
            "badge_unlocked": bool (True if a new milestone was reached),
            "badge_label": str (Name of the badge, e.g., "7-Day Streak!")
        }
    """
    habit_data = await db.habits.find_one({"_id": ObjectId(habit_id), "user_id": str(current_user.id)})
    if not habit_data:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    habit = Habit(**habit_data)
    now_ist = get_current_time()
    
    # 1. Determine Effect based on Type & Action
    xp_change = 0
    gold_change = 0
    streak_change = 0 # 0, 1 (increment), -Reset (set to 0)
    hp_loss = 0
    
    is_positive = habit.type == "positive"
    action = trigger.action
    
    # Logic Table
    if is_positive and action == "success":
        # "Performed" -> Reward
        xp_change = 10
        gold_change = 5
        streak_change = 1
    elif is_positive and action == "failure":
        # "Skipped" -> Penalty
        hp_loss = 10
        streak_change = -100 # Reset to 0 (Indicator)
        
    elif not is_positive and action == "success":
        # "Avoided" -> Reward
        xp_change = 10
        gold_change = 5
        streak_change = 1
    elif not is_positive and action == "failure":
        # "Indulged/Relapsed" -> Penalty
        hp_loss = 20 # Higher penalty for breaking a resistance
        streak_change = -100 # Reset
        
    # difficulty multiplier
    mult_map = {"easy": 1, "medium": 1.5, "hard": 2} # Slightly different from Todo
    mult = mult_map.get(habit.difficulty, 1)
    
    xp_change *= mult
    gold_change *= mult
    hp_loss *= mult
    
    # 2. Update Streak
    new_streak = habit.current_streak
    if streak_change == 1:
        new_streak += 1
    elif streak_change < 0:
        new_streak = 0
        
    new_best_streak = max(habit.best_streak, new_streak)
    
    # 3. Check Milestones (Only on Success)
    badge_unlocked = False
    badge_label = ""
    
    MILESTONES = [7, 21, 30, 66, 100, 365]
    if streak_change == 1: # Only if streak increased
        if new_streak in MILESTONES:
            # Check if already awarded (simple check in existing milestones)
            existing_labels = [m.label for m in habit.milestones]
            label = f"{new_streak}-Day Streak!"
            if label not in existing_labels:
                badge_unlocked = True
                badge_label = label
                # Add to milestone list
                new_milestone = Milestone(label=label, day_count=new_streak, unlocked_at=now_ist)
                habit.milestones.append(new_milestone)
                
                # Bonus for Milestone
                xp_change += (new_streak * 5) * mult
                gold_change += (new_streak * 2) * mult

    # 4. Update User Stats
    if hp_loss > 0:
        # Deduct HP logic would go here if we tracked HP on user. 
        # For now, we assume pure XP/Gold economy or maybe HP is planned.
        # Assuming we just subtract XP as a penalty proxy if HP doesn't exist?
        # User model has 'hp'? Let's check user model later. Assuming NO HP for now, reducing XP slightly.
        xp_change -= 5 # Minor XP penalty
    
    new_gold = current_user.stats.gold + gold_change
    new_level, new_xp, new_max_xp = calculate_new_level_and_xp(
        current_user.stats.level,
        current_user.stats.xp,
        xp_change
    )
    
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {
            "stats.gold": new_gold,
            "stats.xp": new_xp,
            "stats.level": new_level,
            "stats.max_xp": new_max_xp
        }}
    )

    # 5. Update Habit
    milestone_dicts = [m.model_dump() for m in habit.milestones]
    
    await db.habits.update_one(
        {"_id": ObjectId(habit_id)},
        {"$set": {
            "current_streak": new_streak,
            "best_streak": new_best_streak,
            "last_completed_date": now_ist,
            "milestones": milestone_dicts
        }}
    )
    
    # Refetch
    updated_habit = await db.habits.find_one({"_id": ObjectId(habit_id)})
    
    # Log
    log_msg = f"Habit {habit.title}: {action.upper()}"
    if badge_unlocked:
        log_msg += f" (Badge: {badge_label})"
        
    await db.activity_logs.insert_one({
        "user_id": str(current_user.id),
        "message": log_msg,
        "xp_change": xp_change,
        "type": "habit_trigger",
        "timestamp": now_ist
    })

    return {
        "habit": Habit(**updated_habit),
        "badge_unlocked": badge_unlocked,
        "badge_label": badge_label
    }
