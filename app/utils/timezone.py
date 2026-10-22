from datetime import datetime
from zoneinfo import ZoneInfo

VE_TIMEZONE = ZoneInfo("America/Caracas")
VENEZUELA_TZ = VE_TIMEZONE  # Alias for backward compatibility


def get_ve_now() -> datetime:
    """
    Return current datetime aware of Venezuela timezone (America/Caracas).
    """
    return datetime.now(VE_TIMEZONE)
