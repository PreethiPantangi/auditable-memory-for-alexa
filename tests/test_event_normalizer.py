import pytest

from validators.event_normalizer import normalize_adjustment


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("less salt", "less_salt"),
        ("reduced salt", "less_salt"),
        ("decreased salt", "less_salt"),
        ("less_salt", "less_salt"),
        ("extra salt", "more_salt"),
        ("reduced sugar", "less_sugar"),
        ("less oil", "less_oil"),
        ("  LESS   SALT  ", "less_salt"),
    ],
)
def test_normalize_adjustment(raw, expected):
    assert normalize_adjustment(raw) == expected
