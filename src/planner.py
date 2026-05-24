from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from .store import get_last_run

DAYS = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}


def is_due(config: dict) -> bool:
    if not config.get('enabled', True):
        return False
    schedule = config['schedule']
    tz = ZoneInfo(schedule.get('timezone', 'UTC'))
    now = datetime.now(tz)
    last_run = get_last_run(config['id'])

    stype = schedule.get('type', 'weekly')
    if stype == 'weekly':
        wanted_day = DAYS[schedule['day_of_week'].lower()]
        if now.weekday() != wanted_day:
            return False
        if (now.hour, now.minute) < (schedule.get('hour', 0), schedule.get('minute', 0)):
            return False
        if last_run:
            last_local = last_run.astimezone(tz)
            return last_local.date() != now.date()
        return True

    if stype == 'daily':
        if (now.hour, now.minute) < (schedule.get('hour', 0), schedule.get('minute', 0)):
            return False
        if last_run:
            last_local = last_run.astimezone(tz)
            return last_local.date() != now.date()
        return True

    return False
