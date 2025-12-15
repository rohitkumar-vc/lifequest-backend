from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from core.database import db
from datetime import datetime
import asyncio

from core.config import settings
from core.time_utils import get_current_time, to_ist
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()

async def run_daily_maintenance():
    """
    Checks all users to see if the day has rolled over since their last check.
    If so:
    1. Update Habit streaks/penalties.
    2. Reset Dailies.
    3. Update last_cron_check.
    """
    now_ist = get_current_time()
    print(f"[{now_ist}] Checking Daily Maintenance for Users...")
    
    users_cursor = db.users.find({})
    async for user in users_cursor:
        try:
            # Check date difference
            last_check = user.get("last_cron_check")
            
            # Handle missing last_cron_check
            if not last_check:
                # If missing, set to a past time so it triggers
                last_check = datetime.min.replace(tzinfo=now_ist.tzinfo)
            else:
                # Ensure last_check is timezone aware (IST)
                last_check = to_ist(last_check)
            
            if now_ist.date() > last_check.date():
                print(f"Running daily update for user {user['username']}...")
                user_id_str = str(user["_id"])
                
                # --- 1. Process Habits ---
                # We need to verify if the user completed their habits for the "Closed Day" (Yesterday relative to Now).
                # Closed Day = last_check.date() (roughly).
                # Actually, simpler: We check if they did it Yesterday (now - 1 day).
                
                yesterday_date = (now_ist - timedelta(days=1)).date()
                today_date = now_ist.date()

                all_habits = db.tasks.find({"user_id": user_id_str, "type": "habit"})
                
                total_damage = 0
                
                async for habit in all_habits:
                    habit_id = habit["_id"]
                    
                    # Migration: If last_completed_date is missing, infer from completed_today ??
                    # No, completed_today is unreliable if overwritten.
                    # Use last_completed_date if available.
                    last_done = habit.get("last_completed_date")
                    
                    # Determine Status for Yesterday
                    missed_yesterday = True
                    if last_done:
                        # Ensure timezone aware
                        last_done = to_ist(last_done)
                        if last_done.date() == yesterday_date:
                            missed_yesterday = False
                        elif last_done.date() == today_date:
                            # If done Today, it implies they kept the streak alive?
                            # Not necessarily. If they missed yesterday, streak reset to 1 Today.
                            # So we trust the 'streak' value?
                            # If they did it Today, they are active.
                            # If they missed Yesterday, the toggle logic (run Today) would have reset streak to 1.
                            # So the scheduler doesn't need to punish them again?
                            # YES. If they missed yesterday, but did it today *before* scheduler ran:
                            # The toggle logic set streak=1.
                            # Logic: "if last_completed_date < Yesterday: Streak=1".
                            # So "Streak 0" logic is handled by Toggle if user is active.
                            # Scheduler only needs to catch INACTIVE users.
                            missed_yesterday = False # Handled by user activity or is safe.
                            pass
                    else:
                        # Legacy fallback: If completed_today is True, assume done Yesterday?
                        if habit.get("completed_today") is True:
                             # This flag might be from Yesterday.
                             missed_yesterday = False
                    
                    # If Missed Yesterday AND Streak > 0 -> Penalty
                    if missed_yesterday and habit.get("streak", 0) > 0:
                        await db.tasks.update_one({"_id": habit_id}, {"$set": {"streak": 0}})
                        
                        # Calculate Penalty
                        diff = habit.get("difficulty", "medium")
                        penalty_map = {
                            "easy": settings.HP_PENALTY_EASY,
                            "medium": settings.HP_PENALTY_MEDIUM,
                            "hard": settings.HP_PENALTY_HARD
                        }
                        dmg = penalty_map.get(diff, settings.HP_PENALTY_MEDIUM)
                        total_damage += dmg
                        
                        await db.activity_logs.insert_one({
                            "user_id": user_id_str,
                            "message": f"Missed Habit: {habit['title']} (HP -{dmg})",
                            "xp_change": 0,
                            "type": "penalty",
                            "timestamp": now_ist
                        })

                    # Reset 'completed_today' Flag
                    # Logic: If last_completed_date == Today, KEEP True.
                    # Else: Set False.
                    should_be_completed = False
                    if last_done:
                         # Re-verify last_done (already cast to IST above)
                         if last_done.date() == today_date:
                             should_be_completed = True
                             
                    # Optimization: Only update if different
                    if habit.get("completed_today") != should_be_completed:
                        await db.tasks.update_one(
                            {"_id": habit_id},
                            {"$set": {"completed_today": should_be_completed}}
                        )

                # Apply Total Damage
                if total_damage > 0:
                    current_hp = user.get("stats", {}).get("hp", 100)
                    new_hp = max(0, current_hp - total_damage)
                    await db.users.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"stats.hp": new_hp}}
                    )

                # --- 2. Process Dailies ---
                # Reset 'completed' to False
                await db.tasks.update_many(
                    {"user_id": user_id_str, "type": "daily", "completed": True},
                    {"$set": {"completed": False}}
                )
                
                # --- 3. Update Last Check ---
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"last_cron_check": now_ist}}
                )
                
        except Exception as e:
            print(f"Error processing maintenance for user {user.get('username')}: {e}")

    print(f"[{now_ist}] Daily Maintenance Check Completed.")

def start_scheduler():
    # Run periodically to catch day rollovers without restart
    # Check every hour
    scheduler.add_job(run_daily_maintenance, IntervalTrigger(hours=1))
    scheduler.start()
