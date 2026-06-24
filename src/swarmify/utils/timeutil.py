import time


def now_ms() -> int:
    """Wall-clock time in integer milliseconds, matching exchange timestamps."""
    return int(time.time() * 1000)
