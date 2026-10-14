from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

MIN_EVIDENCE = 3


def parse_occurred_at(value):
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value)
        else:
            return None

        if dt.tzinfo is None:
            return None

        return dt.astimezone(UTC)

    except ValueError:
        return None


def derive_repeated_adjustments(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped = defaultdict(list)

    for event in events:
        if event.get("domain") != "cooking":
            continue

        if event.get("event_type") != "meal_prepared":
            continue

        outcome = event.get("outcome")

        if outcome not in {"BETTER", "WORSE"}:
            continue

        attributes = event.get("attributes") or {}
        adjustment = attributes.get("adjustment")
        subject = event.get("subject")

        if not isinstance(subject, str) or not subject.strip():
            continue

        if not isinstance(adjustment, str) or not adjustment.strip():
            continue

        occurred_at = parse_occurred_at(event.get("occurred_at"))

        if occurred_at is None:
            continue

        event_id = event.get("id")

        if event_id is None:
            continue

        dish_key = " ".join(subject.lower().split())
        adjustment_key = adjustment.strip().lower()

        grouped[(dish_key, adjustment_key)].append((event, occurred_at))

    insights = []

    for (dish, adjustment), evidence in grouped.items():
        unique_events = {
            event["id"]: (event, occurred_at)
            for event, occurred_at in evidence
            if event.get("id") is not None
        }

        positive_events = []
        negative_events = []

        for event, occurred_at in unique_events.values():
            if event["outcome"] == "BETTER":
                positive_events.append((event, occurred_at))
            elif event["outcome"] == "WORSE":
                negative_events.append((event, occurred_at))

        # Conservative contradiction rule:
        # Any matching negative observation blocks
        # the positive inference.
        if negative_events:
            continue

        # One representative event per UTC date.
        # For a production app, use a declared cooking
        # date or cooking_session_id instead.
        distinct_dates = {}

        for event, occurred_at in sorted(
            positive_events,
            key=lambda item: (item[1], item[0]["id"]),
        ):
            day = occurred_at.date()

            if day not in distinct_dates:
                distinct_dates[day] = event

        if len(distinct_dates) < MIN_EVIDENCE:
            continue

        selected = list(distinct_dates.values())

        insights.append(
            {
                "insight_type": "REPEATED_ADJUSTMENT",
                "domain": "cooking",
                "subject": dish,
                "adjustment": adjustment,
                "statement": (
                    f"You seem to prefer "
                    f"{adjustment.replace('_', ' ')} "
                    f"when preparing {dish}."
                ),
                "status": "PENDING_CONFIRMATION",
                "evidence_count": len(selected),
                "evidence_event_ids": [event["id"] for event in selected],
            }
        )

    return insights
