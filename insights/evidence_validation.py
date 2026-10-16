from sqlalchemy import text

from insights.repeated_adjustment import derive_repeated_adjustments


async def validate_insight_evidence(
    session,
    user_id: str,
    insight_id: int,
) -> dict:
    result = await session.execute(
        text("""
            SELECT
                e.id,
                e.occurred_at,
                e.outcome,
                e.subject,
                e.attributes
            FROM insight_evidence ie
            JOIN events e ON e.id = ie.event_id
            WHERE ie.insight_id = :insight_id
              AND e.user_id = :user_id
              AND e.domain = 'cooking'
              AND e.event_type = 'meal_prepared'
            ORDER BY e.occurred_at, e.id
        """),
        {
            "insight_id": insight_id,
            "user_id": user_id,
        },
    )

    events = [dict(row) for row in result.mappings()]

    valid_events = [
        event
        for event in events
        if event["outcome"] == "BETTER" and event["occurred_at"] is not None
    ]

    independent_dates = {event["occurred_at"].date() for event in valid_events}

    return {
        "valid": len(independent_dates) >= 3,
        "evidence_count": len(valid_events),
        "independent_dates": len(independent_dates),
    }


async def validate_current_insight_evidence(
    session,
    user_id: str,
    insight,
) -> dict:
    result = await session.execute(
        text("""
            SELECT id, user_id, domain, event_type,
                   subject, attributes, outcome, occurred_at
            FROM events
            WHERE user_id = :user_id
              AND domain = 'cooking'
              AND event_type = 'meal_prepared'
            ORDER BY occurred_at, id
        """),
        {"user_id": user_id},
    )

    events = [dict(row) for row in result.mappings()]

    candidates = derive_repeated_adjustments(events)

    matching_candidate = next(
        (
            candidate
            for candidate in candidates
            if candidate["domain"] == insight["domain"]
            and candidate["insight_type"] == insight["insight_type"]
            and candidate["subject"] == insight["subject"]
            and candidate["adjustment"] == insight["adjustment"]
        ),
        None,
    )

    if matching_candidate is None:
        return {
            "valid": False,
            "code": "INSIGHT_EVIDENCE_NO_LONGER_VALID",
            "message": ("The current cooking history no longer supports this insight."),
        }

    return {
        "valid": True,
        "evidence_count": matching_candidate["evidence_count"],
        "evidence_event_ids": matching_candidate["evidence_event_ids"],
    }


# Preserve the existing public function identities for imports and pickle references.
validate_insight_evidence.__module__ = "insights.insights_service"
validate_current_insight_evidence.__module__ = "insights.insights_service"
