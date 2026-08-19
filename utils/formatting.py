import time
from datetime import datetime

def format_relative_time(stamp: str) -> str:
    """Convert a timestamp string 'YYYY-MM-DD HH:MM:SS' into a relative string."""
    if not stamp:
        return "Unknown"
    
    try:
        dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = (now - dt).total_seconds()
        
        if diff < 0:
            return "Just now" # Future drift
        if diff < 60:
            return "Just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins} min ago"
        elif diff < 86400:
            hrs = int(diff / 3600)
            return f"{hrs} hr{'s' if hrs > 1 else ''} ago"
        else:
            days = int(diff / 86400)
            return f"{days} day{'s' if days > 1 else ''} ago"
    except ValueError:
        return stamp # Fallback if parsing fails
