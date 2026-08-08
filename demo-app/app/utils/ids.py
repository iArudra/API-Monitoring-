"""ID and timestamp helpers."""

from datetime import datetime, timezone
from uuid import uuid4


def new_id(prefix: str) -> str:
    """Generate a short, readable id like ``ord_4f8a2c9b1d3e``."""
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    """UTC timestamp in ISO-8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
