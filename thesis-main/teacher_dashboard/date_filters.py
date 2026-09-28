from datetime import date, datetime


def parse_date_range(start_text, end_text):
    start = date.fromisoformat(start_text.strip()) if start_text.strip() else None
    end = date.fromisoformat(end_text.strip()) if end_text.strip() else None
    if start and end and start > end:
        raise ValueError("Start date must not be after end date.")
    return start, end


def matches_date_range(timestamp, start, end):
    if start is None and end is None:
        return True
    try:
        value = datetime.strptime(str(timestamp)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return (start is None or value >= start) and (end is None or value <= end)
