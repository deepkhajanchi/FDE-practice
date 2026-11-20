"""Reminder timing."""

from datetime import datetime, timezone


def to_utc(event):
    """Return the event's start time as a UTC-aware datetime.

    A timezone-aware start is converted to UTC; a naive start is assumed to
    already be UTC. If the start is a string, it is parsed first.
    """
    start = event["start"]
    
    # Ensure start is a datetime object
    if isinstance(start, str):
        start = datetime.fromisoformat(start)

    if start.tzinfo is None:
        return start.replace(tzinfo=timezone.utc)
    return start.astimezone(timezone.utc)


def reminder_hour_utc(event):
    """The UTC hour at which to fire the event's reminder."""
    return to_utc(event).hour
