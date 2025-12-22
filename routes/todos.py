from fastapi import APIRouter, HTTPException, Depends, Request, Header
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from models.user import User
from models.todo import Todo, TodoCreate, TodoUpdate
from routes.auth import get_current_user
from core.database import db
from core.config import settings
from core.time_utils import get_current_time
from utils.scheduler import schedule_expiry_check, cancel_previous_schedule
from core.leveling import calculate_new_level_and_xp

router = APIRouter(prefix="/todos", tags=["Todos"])

async def verify_scheduler_token(authorization: Optional[str] = Header(None)):
    """Verifies the bearer token for webhook calls."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    scheme, param = authorization.split()
    if scheme.lower() != 'bearer' or param != settings.CROSS_SITE_API_KEY:
         raise HTTPException(status_code=401, detail="Invalid Token")

@router.post("/", response_model=Todo)
async def create_todo(todo_in: TodoCreate, current_user: User = Depends(get_current_user)):
    """
    Create Todo.
    If deadline set: User gets 'Upfront Gold' (Loan). Schedules QStash check.
    """
    now = get_current_time()
    
    # Calculate Rewards
    base_reward = settings.TODO_REWARD_GOLD
    mult = settings.TODO_DIFFICULTY_MULTIPLIERS.get(todo_in.difficulty, 1)
    potential_reward = base_reward * mult
    
    upfront_gold = 0.0
    qstash_id = None
    
    # Create DB Object
    todo = Todo(
        user_id=str(current_user.id),
        title=todo_in.title,
        description=todo_in.description,
        difficulty=todo_in.difficulty,
        deadline=todo_in.deadline,
        created_at=now,
        potential_reward=potential_reward
    )

    if todo_in.deadline and todo_in.deadline > now:
        # Give Upfront Loan
        upfront_gold = potential_reward
        todo.upfront_gold_given = upfront_gold
        
        # Schedule Check (POST /check_validity/{id})
        # Insert first to get ID? No, we need ID for webhook.
        # MongoDB: We can insert, get ID, then update schedule? Or use ObjectId()
        # Let's insert first.
        
    todo_dump = todo.model_dump(by_alias=True, exclude={"id"})
    result = await db.todos.insert_one(todo_dump)
    todo_id = str(result.inserted_id)
    
    # Post-Insert Logic: Schedule if deadline
    if todo_in.deadline and todo_in.deadline > now:
        qstash_id = schedule_expiry_check(todo_id, todo_in.deadline)
        
        # Update Todo with message_id
        await db.todos.update_one(
            {"_id": result.inserted_id},
            {"$set": {"qstash_message_id": qstash_id}}
        )
        
        # Give Gold (Loan)
        new_gold = current_user.stats.gold + upfront_gold
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.gold": new_gold}}
        )
        
        # Log
        await db.activity_logs.insert_one({
            "user_id": str(current_user.id),
            "message": f"Todo Bet Started: {todo.title}",
            "xp_change": 0,
            "gold_change": upfront_gold,
            "type": "todo_create",
            "timestamp": now
        })
        
    # Refetch
    final_todo = await db.todos.find_one({"_id": result.inserted_id})
    return Todo(**final_todo)

@router.get("/", response_model=List[Todo])
async def get_todos(current_user: User = Depends(get_current_user)):
    cursor = db.todos.find({"user_id": str(current_user.id)})
    todos = await cursor.to_list(length=100)
    return [Todo(**t) for t in todos]

@router.post("/check_validity/{todo_id}", dependencies=[Depends(verify_scheduler_token)])
async def check_todo_validity(todo_id: str):
    """
    Webhook called by QStash when deadline acts.
    """
    todo_data = await db.todos.find_one({"_id": ObjectId(todo_id)})
    if not todo_data:
        raise HTTPException(status_code=404, detail="Todo not found")
        
    todo = Todo(**todo_data)
    
    if todo.status == "completed":
        return {"message": "Already completed"}
        
    if todo.status == "active":
        # Mark Overdue
        # Penalty: Lose 2x Upfront (Net loss: -1x Reward)
        penalty = 2 * todo.upfront_gold_given
        
        await db.todos.update_one(
            {"_id": ObjectId(todo_id)},
            {"$set": {"status": "overdue"}}
        )
        
        # Apply Penalty
        user_data = await db.users.find_one({"_id": ObjectId(todo.user_id)})
        if user_data:
            current_gold = user_data["stats"]["gold"]
            new_gold = max(0, current_gold - penalty) # Prevent negative? Or allow debt? Let's prevent negative.
            
            await db.users.update_one(
                {"_id": ObjectId(todo.user_id)},
                {"$set": {"stats.gold": new_gold}}
            )
            
            # Log
            await db.activity_logs.insert_one({
                "user_id": todo.user_id,
                "message": f"Todo Overdue: {todo.title}",
                "xp_change": 0,
                "gold_change": -penalty,
                "type": "todo_overdue",
                "timestamp": get_current_time()
            })
            
    return {"message": "Checked"}

@router.put("/{todo_id}", response_model=Todo)
async def update_todo(todo_id: str, todo_in: TodoUpdate, current_user: User = Depends(get_current_user)):
    """
    Update Todo.
    Handles Deadline changes:
    - If deadline removed: Cancel schedule.
    - If deadline changed: Cancel old -> Schedule new.
    - If deadline added: Schedule new.
    
    Warning: Logic for Gold adjustments on Edit is complex. 
    User Plan: 
    - Deadline Removed: User Gold -= Upfront; Cancel Schedule. (Revert Loan)
    - Deadline Changed: Cancel Old -> Reschedule New. (Loan stays, just time shifts?)
      - If time shifts, we just update QStash.
    - Deadline Added: User Gold += Reward; Schedule New. (New Loan)
    """
    todo_data = await db.todos.find_one({"_id": ObjectId(todo_id), "user_id": str(current_user.id)})
    if not todo_data: raise HTTPException(status_code=404)
    todo = Todo(**todo_data)
    
    if todo.status != 'active':
        raise HTTPException(status_code=400, detail="Cannot edit inactive todo")

    update_data = todo_in.model_dump(exclude_unset=True)
    
    # Handle Deadline Logic
    if "deadline" in update_data:
        new_deadline = update_data["deadline"]
        old_deadline = todo.deadline
        now = get_current_time()
        
        # Case 1: Deadline Removed
        if old_deadline and not new_deadline:
            # Revert Loan (Take back gold)
            if todo.upfront_gold_given > 0:
                gold_to_remove = todo.upfront_gold_given
                new_gold = max(0, current_user.stats.gold - gold_to_remove)
                await db.users.update_one({"_id": current_user.id}, {"$set": {"stats.gold": new_gold}})
                update_data["upfront_gold_given"] = 0.0
            
            # Cancel Schedule
            if todo.qstash_message_id:
                cancel_previous_schedule(todo.qstash_message_id)
                update_data["qstash_message_id"] = None
                
        # Case 2: Deadline Added (was None, now Set)
        elif not old_deadline and new_deadline:
            if new_deadline > now:
                # Give Loan
                reward = todo.potential_reward # calculated on create
                new_gold = current_user.stats.gold + reward
                await db.users.update_one({"_id": current_user.id}, {"$set": {"stats.gold": new_gold}})
                update_data["upfront_gold_given"] = reward
                
                # Schedule
                qid = schedule_expiry_check(todo_id, new_deadline)
                update_data["qstash_message_id"] = qid
                
        # Case 3: Deadline Changed (Set -> Set)
        elif old_deadline and new_deadline:
            if new_deadline > now:
                # Reschedule
                if todo.qstash_message_id:
                    cancel_previous_schedule(todo.qstash_message_id)
                qid = schedule_expiry_check(todo_id, new_deadline)
                update_data["qstash_message_id"] = qid
                
                # Rescheduling fee? Not specified. existing loan covers it.
            
    await db.todos.update_one(
        {"_id": ObjectId(todo_id)},
        {"$set": update_data}
    )
    
    return Todo(**(await db.todos.find_one({"_id": ObjectId(todo_id)})))

@router.post("/{todo_id}/complete", response_model=Todo)
async def complete_todo(todo_id: str, current_user: User = Depends(get_current_user)):
    todo_data = await db.todos.find_one({"_id": ObjectId(todo_id), "user_id": str(current_user.id)})
    if not todo_data:
        raise HTTPException(status_code=404)
        
    todo = Todo(**todo_data)
    if todo.status != "active":
        raise HTTPException(status_code=400, detail="Cannot complete inactive todo")
        
    # Cancel Schedule
    if todo.qstash_message_id:
        cancel_previous_schedule(todo.qstash_message_id)
        
    # Reward Logic (User gets *another* reward?)
    # Plan says: "Complete: User Gold += Reward"
    # Result: If Loan given (+R), and now (+R), Total = +2R.
    # If no Loan (no deadline), just +R.
    # Wait, simple logic:
    reward = todo.potential_reward
    xp_gain = settings.TODO_XP_VALUE * settings.TODO_DIFFICULTY_MULTIPLIERS.get(todo.difficulty, 1)
    
    # Update User
    new_gold = current_user.stats.gold + reward
    new_level, new_xp, new_max_xp = calculate_new_level_and_xp(
        current_user.stats.level, current_user.stats.xp, xp_gain
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
    
    # Update Todo
    now = get_current_time()
    await db.todos.update_one(
        {"_id": ObjectId(todo_id)},
        {"$set": {
            "status": "completed",
            "completed_at": now,
            "qstash_message_id": None # Clear it
        }}
    )
    
    updated_todo = await db.todos.find_one({"_id": ObjectId(todo_id)})
    return Todo(**updated_todo)

@router.delete("/{todo_id}")
async def delete_todo(todo_id: str, current_user: User = Depends(get_current_user)):
    todo_data = await db.todos.find_one({"_id": ObjectId(todo_id), "user_id": str(current_user.id)})
    if not todo_data:
        raise HTTPException(status_code=404)
    todo = Todo(**todo_data)
    
    # Cancel Schedule
    if todo.qstash_message_id:
        cancel_previous_schedule(todo.qstash_message_id)
        
    # Penalty: Return Loan
    penalty = todo.upfront_gold_given
    if penalty > 0:
        new_gold = max(0, current_user.stats.gold - penalty)
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.gold": new_gold}}
        )
        
    await db.todos.delete_one({"_id": ObjectId(todo_id)})
    return {"message": "Deleted"}

@router.post("/{todo_id}/renew", response_model=Todo)
async def renew_todo(todo_id: str, renew_data: TodoUpdate, current_user: User = Depends(get_current_user)):
    """
    Renew an overdue todo.
    Cost: 10% of Reward.
    """
    todo_data = await db.todos.find_one({"_id": ObjectId(todo_id), "user_id": str(current_user.id)})
    if not todo_data: raise HTTPException(status_code=404)
    todo = Todo(**todo_data)
    
    if todo.status != "overdue":
        raise HTTPException(status_code=400, detail="Only overdue todos can be renewed")
        
    if not renew_data.deadline or renew_data.deadline <= get_current_time():
         raise HTTPException(status_code=400, detail="Must provide future deadline")

    # Pay Cost
    cost = 0.10 * todo.potential_reward
    if current_user.stats.gold < cost:
        raise HTTPException(status_code=400, detail="Not enough gold to renew")
        
    # Deduct Cost
    new_gold = current_user.stats.gold - cost
    await db.users.update_one({"_id": current_user.id}, {"$set": {"stats.gold": new_gold}})
    
    # Schedule New Check
    qstash_id = schedule_expiry_check(todo_id, renew_data.deadline)
    
    # Update Todo -> Active
    await db.todos.update_one(
        {"_id": ObjectId(todo_id)},
        {"$set": {
            "status": "active",
            "deadline": renew_data.deadline,
            "qstash_message_id": qstash_id,
            # Reset upfront gold? 
            # If they lost penalty already, do they get loan back?
            # Model implies upfront_gold is static "what was given".
            # If we don't reset it, next overdue might penalize again. 
            # If we assume renewal gives them a 'second chance', maybe we treat it as active again.
            # But they ALREADY paid penalty.
            # Let's verify 'upfront_gold_given'. It remains set.
            # If they fail again -> Lose 2x again. (Harsh but fair for a "Renewed Bet").
        }}
    )
    
    return Todo(**(await db.todos.find_one({"_id": ObjectId(todo_id)})))
