from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from insights.insights_service import (
    validate_current_insight_evidence,
)

USER_ID = "adh_correction_test"

BASE_DATE = datetime(2026, 10, 5, 10, tzinfo=UTC)

INSIGHT = {
    "domain": "cooking",
    "insight_type": "REPEATED_ADJUSTMENT",
    "subject": "dal",
    "adjustment": "less_salt",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def cooking_event(
    event_id: int,
    *,
    subject: str = "dal",
    adjustment: str = "less_salt",
    outcome: str = "BETTER",
) -> dict:
    return {
        "id": event_id,
        "user_id": USER_ID,
        "domain": "cooking",
        "event_type": "meal_prepared",
        "subject": subject,
        "attributes": {"adjustment": adjustment},
        "outcome": outcome,
        "occurred_at": (BASE_DATE + timedelta(days=event_id - 1)),
    }


def mock_session(events):
    session = MagicMock()
    result = MagicMock()

    result.mappings.return_value = events
    session.execute = AsyncMock(return_value=result)

    return session


@pytest.mark.anyio
async def test_tc22_matching_worse_blocks_confirmation():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
        cooking_event(4, outcome="WORSE"),
    ]

    result = await validate_current_insight_evidence(
        mock_session(events),
        USER_ID,
        INSIGHT,
    )

    assert result["valid"] is False
    assert result["code"] == "INSIGHT_EVIDENCE_NO_LONGER_VALID"


@pytest.mark.anyio
async def test_tc23_positive_only_allows_confirmation():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
    ]

    result = await validate_current_insight_evidence(
        mock_session(events),
        USER_ID,
        INSIGHT,
    )

    assert result["valid"] is True
    assert result["evidence_count"] == 3
    assert result["evidence_event_ids"] == [1, 2, 3]


@pytest.mark.anyio
async def test_tc24_other_dish_worse_does_not_block():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
        cooking_event(
            4,
            subject="soup",
            outcome="WORSE",
        ),
    ]

    result = await validate_current_insight_evidence(
        mock_session(events),
        USER_ID,
        INSIGHT,
    )

    assert result["valid"] is True
    assert result["evidence_count"] == 3


@pytest.mark.anyio
async def test_tc25_other_adjustment_worse_does_not_block():
    events = [
        cooking_event(1),
        cooking_event(2),
        cooking_event(3),
        cooking_event(
            4,
            adjustment="more_salt",
            outcome="WORSE",
        ),
    ]

    result = await validate_current_insight_evidence(
        mock_session(events),
        USER_ID,
        INSIGHT,
    )

    assert result["valid"] is True
    assert result["evidence_count"] == 3
