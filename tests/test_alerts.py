import pytest

from app.services.alerts import crossed_thresholds


@pytest.mark.parametrize(
    ("used_before", "used_after", "expected"),
    [
        (79, 80, [80]),
        (79, 100, [80, 100]),
        (80, 99, []),
        (100, 110, []),
    ],
)
def test_crossed_thresholds(
    used_before: int,
    used_after: int,
    expected: list[int],
) -> None:
    assert crossed_thresholds(
        used_before=used_before,
        used_after=used_after,
        limit=100,
    ) == expected