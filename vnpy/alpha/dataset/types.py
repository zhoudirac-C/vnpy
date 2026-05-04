from datetime import datetime
from enum import Enum


def to_datetime(arg: datetime | str) -> datetime:
    """Convert time data type"""
    if isinstance(arg, str):
        if "-" in arg:
            fmt: str = "%Y-%m-%d"
        else:
            fmt = "%Y%m%d"

        return datetime.strptime(arg, fmt)
    else:
        return arg


class Segment(Enum):
    """Data segment enumeration values"""

    TRAIN = 1
    VALID = 2
    TEST = 3
