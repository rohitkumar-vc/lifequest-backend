from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

def get_current_time():
    """Returns the current time in IST."""
    return datetime.now(IST)

def to_ist(dt: datetime):
    """Converts a datetime object to IST."""
    if dt.tzinfo is None:
        # Assume naive datetimes from DB are UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)
