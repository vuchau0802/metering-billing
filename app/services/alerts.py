ALERT_THRESHOLDS = (80, 100)


def crossed_thresholds(
    *,
    used_before: int,
    used_after: int,
    limit: int,
) -> list[int]:
    if used_before < 0 or used_after < 0:
        raise ValueError("usage must be non-negative")

    if limit <= 0:
        raise ValueError("limit must be positive")

    if used_after < used_before:
        raise ValueError("used_after cannot be less than used_before")

    return [
        threshold
        for threshold in ALERT_THRESHOLDS
        if (
            used_before * 100
            < limit * threshold
            <= used_after * 100
        )
    ]