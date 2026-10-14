from datetime import UTC, datetime, timedelta

import pytest

from insights.repeated_adjustment import (
    derive_repeated_adjustments,
)


def cooking_event(
    event_id: int,
    dish: str = "dal",
    adjustment: str = "less_salt",
    outcome: str = "BETTER",
    occurred_at: datetime | None = None,
) -> dict:
    return {
        "id": event_id,
        "domain": "cooking",
        "event_type": "meal_prepared",
        "subject": dish,
        "attributes": {"adjustment": adjustment},
        "outcome": outcome,
        "occurred_at": (
            occurred_at
            if occurred_at is not None
            else datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=event_id)
        ),
    }


@pytest.mark.parametrize("count", [0, 1, 2])
def test_insufficient_evidence(count):
    events = [cooking_event(i) for i in range(1, count + 1)]

    assert derive_repeated_adjustments(events) == []


def test_three_positive_events_create_insight():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
    ]

    result = derive_repeated_adjustments(events)

    assert len(result) == 1
    assert result[0]["insight_type"] == "REPEATED_ADJUSTMENT"
    assert result[0]["status"] == "PENDING_CONFIRMATION"
    assert result[0]["evidence_count"] == 3
    assert result[0]["evidence_event_ids"] == [1, 2, 3]


def test_negative_event_not_counted():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3, outcome="WORSE"),
    ]

    assert derive_repeated_adjustments(events) == []


def test_different_adjustments_not_combined():
    events = [
        cooking_event(1, adjustment="less_salt"),
        cooking_event(2, adjustment="less_salt"),
        cooking_event(3, adjustment="less_sugar"),
    ]

    assert derive_repeated_adjustments(events) == []


def test_different_dishes_not_combined():
    events = [
        cooking_event(1, dish="dal"),
        cooking_event(2, dish="dal"),
        cooking_event(3, dish="soup"),
    ]

    assert derive_repeated_adjustments(events) == []


def test_same_event_id_not_counted_twice():
    event = cooking_event(1)

    assert derive_repeated_adjustments([event, event, cooking_event(2)]) == []


def test_normalizes_dish_case_and_whitespace():
    events = [
        cooking_event(1, dish="Dal"),
        cooking_event(2, dish=" dal "),
        cooking_event(3, dish="DAL"),
    ]

    result = derive_repeated_adjustments(events)

    assert len(result) == 1
    assert result[0]["subject"] == "dal"


def test_multiple_independent_patterns():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
        cooking_event(4, dish="halwa", adjustment="less_sugar"),
        cooking_event(5, dish="halwa", adjustment="less_sugar"),
        cooking_event(6, dish="halwa", adjustment="less_sugar"),
    ]

    result = derive_repeated_adjustments(events)

    assert len(result) == 2


def test_same_day_events_not_independent():
    same_day = datetime(2026, 10, 12, 10, tzinfo=UTC)

    events = [
        cooking_event(1, occurred_at=same_day),
        cooking_event(
            2,
            occurred_at=same_day + timedelta(hours=2),
        ),
        cooking_event(
            3,
            occurred_at=same_day + timedelta(hours=4),
        ),
    ]

    result = derive_repeated_adjustments(events)

    assert result == []


def test_three_distinct_dates_generate_insight():
    events = [
        cooking_event(
            1,
            occurred_at=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        cooking_event(
            2,
            occurred_at=datetime(2026, 10, 8, tzinfo=UTC),
        ),
        cooking_event(
            3,
            occurred_at=datetime(2026, 10, 12, tzinfo=UTC),
        ),
    ]

    result = derive_repeated_adjustments(events)

    assert len(result) == 1
    assert result[0]["evidence_count"] == 3
    assert result[0]["evidence_event_ids"] == [1, 2, 3]


def test_mixed_outcomes_suppress_insight():
    events = [
        cooking_event(1, outcome="BETTER"),
        cooking_event(2, outcome="BETTER"),
        cooking_event(3, outcome="BETTER"),
        cooking_event(4, outcome="WORSE"),
    ]

    result = derive_repeated_adjustments(events)

    assert result == []


def test_unrelated_negative_does_not_suppress_insight():
    events = [
        cooking_event(1, dish="dal", outcome="BETTER"),
        cooking_event(2, dish="dal", outcome="BETTER"),
        cooking_event(3, dish="dal", outcome="BETTER"),
        cooking_event(4, dish="soup", outcome="WORSE"),
    ]

    result = derive_repeated_adjustments(events)

    assert len(result) == 1
    assert result[0]["subject"] == "dal"
    assert result[0]["evidence_event_ids"] == [1, 2, 3]
