from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from datetime import datetime, timedelta
from routes.auth import get_current_user
from models.user import User
from core.database import db
from core.time_utils import get_current_time, to_ist

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/recent")
async def get_recent_activity(current_user: User = Depends(get_current_user)):
    """Get last 20 activity logs."""
    logs = await db.activity_logs.find(
        {"user_id": str(current_user.id)}
    ).sort("timestamp", -1).limit(20).to_list(20)
    
    # Format for simple consumption
    return [
        {
            "id": str(log["_id"]),
            "message": log["message"],
            "xp_change": log.get("xp_change", 0),
            "timestamp": to_ist(log["timestamp"])
        }
        for log in logs
    ]

@router.get("/weekly")
async def get_weekly_xp(current_user: User = Depends(get_current_user)):
    """Get XP gained per day for the last 7 days."""
    now = get_current_time()
    seven_days_ago = now - timedelta(days=6)
    
    # Initialize dictionary for last 7 days
    days = {}
    for i in range(7):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        days[d] = 0
        
    # Aggregate XP from activity logs
    logs = await db.activity_logs.find({
        "user_id": str(current_user.id),
        "timestamp": {"$gte": seven_days_ago},
        "xp_change": {"$gt": 0} # Only gains
    }).to_list(1000)
    
    for log in logs:
        # Ensure log timestamp is IST before checking date
        log_time = to_ist(log["timestamp"])
        day_str = log_time.strftime("%Y-%m-%d")
        if day_str in days:
            days[day_str] += log["xp_change"]
            
    # Format for chart (Reverse to show oldest to newest)
    result = []
    # Sort dates
    sorted_dates = sorted(days.keys())
    for d in sorted_dates:
        # Format day name (e.g. "Mon")
        date_obj = datetime.strptime(d, "%Y-%m-%d")
        day_name = date_obj.strftime("%a")
        result.append({
            "day": day_name,
            "xp_gained": days[d]
        })
        
    return result
