import os
from datetime import datetime
from qstash import QStash
from core.config import settings

def schedule_expiry_check(todo_id: str, deadline: datetime) -> str:
    """
    Schedules a webhook call to check todo expiry via QStash.
    Returns: message_id
    """
    try:
        client = QStash(settings.QSTASH_TOKEN)
        
        # Convert deadline to Unix Timestamp
        not_before = int(deadline.timestamp())
        
        # Public URL for webhook (In dev, user must use ngrok/tunnel and update BACKEND_URL)
        url = f"{settings.BACKEND_URL}/todos/check_validity/{todo_id}"
        
        response = client.message.publish_json(
            url=url,
            not_before=not_before,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.CROSS_SITE_API_KEY}",
                "Content-Type": "application/json"
            }
        )
        return response.message_id
    except Exception as e:
        print(f"Failed to schedule QStash: {e}")
        # Return a dummy ID or handle error appropriately. 
        # For now, returning None or empty string might break strict types, let's return Error string or raise.
        # But to keep app running if QStash fails (e.g. no token), we might log and continue.
        # However, functionality depends on it.
        return f"error-{datetime.now().timestamp()}"

def cancel_previous_schedule(message_id: str) -> str:
    """
    Cancels a scheduled QStash message.
    """
    if not message_id or message_id.startswith("error-"):
        return "skipped"

    try:
        client = QStash(settings.QSTASH_TOKEN)
        client.message.cancel(message_id)
        return "success"
    except Exception as e:
        print(f"Failed to cancel QStash message {message_id}: {e}")
        return "failed"
