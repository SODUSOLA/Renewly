"""Date helpers. "Today" always means today in the user's own timezone."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.modules.auth.models import User


# func to get today's date in a user's timezone
def today_for(user: User) -> date:
    """Return the current calendar date where `user` lives.

    A user in Lagos and one in Los Angeles can be on different dates at the
    same instant, so expiry maths must never use the server's date.
    """
    return datetime.now(ZoneInfo(user.timezone)).date()
