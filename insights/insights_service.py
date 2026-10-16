from sqlalchemy import text

from database import SessionLocal
from insights.evidence_validation import (
    validate_current_insight_evidence,
    validate_insight_evidence,
)
from insights.repeated_adjustment import (
    derive_repeated_adjustments,
)


async def save_insight_candidates(user_id: str) -> dict:
    async with SessionLocal() as session, session.begin():
        rows = await session.execute(
            text("""
                    SELECT id, user_id, domain, event_type,
                           subject, attributes, outcome,
                           source_utterance, occurred_at
                    FROM events
                    WHERE user_id = :user_id
                      AND domain = 'cooking'
                      AND event_type = 'meal_prepared'
                    ORDER BY occurred_at, id
                """),
            {"user_id": user_id},
        )

        events = [dict(row) for row in rows.mappings()]

        candidates = derive_repeated_adjustments(events)
        saved = []

        for candidate in candidates:
            result = await session.execute(
                text("""
                        INSERT INTO insights (
                            user_id, domain, insight_type,
                            subject, adjustment, statement
                        )
                        VALUES (
                            :user_id, :domain, :insight_type,
                            :subject, :adjustment, :statement
                        )
                        ON CONFLICT (
                            user_id, domain, insight_type,
                            subject, adjustment
                        ) DO NOTHING
                        RETURNING id
                    """),
                {
                    "user_id": user_id,
                    "domain": candidate["domain"],
                    "insight_type": candidate["insight_type"],
                    "subject": candidate["subject"],
                    "adjustment": candidate["adjustment"],
                    "statement": candidate["statement"],
                },
            )

            inserted_id = result.scalar_one_or_none()

            # Existing insight: preserve its evidence snapshot
            # and its prior confirmation/rejection decision.
            if inserted_id is None:
                continue

            for event_id in candidate["evidence_event_ids"]:
                await session.execute(
                    text("""
                            INSERT INTO insight_evidence (
                                insight_id, event_id
                            )
                            VALUES (:insight_id, :event_id)
                        """),
                    {
                        "insight_id": inserted_id,
                        "event_id": event_id,
                    },
                )

            saved.append(
                {
                    "insight_id": inserted_id,
                    **candidate,
                }
            )

        return {
            "created": saved,
            "created_count": len(saved),
        }


async def _create_confirmed_claim(
    session,
    user_id: str,
    insight_id: int,
    insight,
) -> int:
    # Confirmed inferences receive their own memory key.
    # They do not silently replace explicit memories.
    import uuid

    memory_key = str(uuid.uuid4())

    claim_result = await session.execute(
        text("""
                    INSERT INTO claims (
                        user_id, category, value,
                        source_type, source_utterance,
                        memory_key, status
                    )
                    VALUES (
                        :user_id, 'food_preference', :value,
                        'INFERRED_CONFIRMED', :source,
                        :memory_key, 'ACTIVE'
                    )
                    RETURNING id
                """),
        {
            "user_id": user_id,
            "value": insight["statement"],
            "source": (f"Confirmed derived insight #{insight_id}"),
            "memory_key": memory_key,
        },
    )

    claim_id = claim_result.scalar_one()

    return claim_id


async def confirm_insight(
    user_id: str,
    insight_id: int,
) -> dict:
    async with SessionLocal() as session, session.begin():
        result = await session.execute(
            text("""
                SELECT
                    id,
                    domain,
                    insight_type,
                    subject,
                    adjustment,
                    statement,
                    status,
                    confirmed_claim_id
                FROM insights
                WHERE id = :insight_id
                AND user_id = :user_id
                FOR UPDATE
            """),
            {
                "user_id": user_id,
                "insight_id": insight_id,
            },
        )

        insight = result.mappings().one_or_none()

        if insight is None:
            return {
                "success": False,
                "error": {
                    "code": "INSIGHT_NOT_FOUND",
                    "message": "Insight not found.",
                },
            }

        if insight["status"] == "CONFIRMED":
            return {
                "success": True,
                "data": {
                    "insight_id": insight_id,
                    "claim_id": insight["confirmed_claim_id"],
                    "already_confirmed": True,
                },
            }

        if insight["status"] == "REJECTED":
            return {
                "success": False,
                "error": {
                    "code": "INSIGHT_ALREADY_REJECTED",
                    "message": "Rejected insight cannot be confirmed.",
                },
            }

        evidence = await validate_insight_evidence(
            session,
            user_id,
            insight_id,
        )

        if not evidence["valid"]:
            return {
                "success": False,
                "error": {
                    "code": "INSUFFICIENT_INDEPENDENT_EVIDENCE",
                    "message": (
                        "This insight needs observations "
                        "from at least three distinct cooking dates."
                    ),
                },
            }

        # Verify that newly recorded cooking events have not
        # contradicted this pending insight.
        current_validation = await validate_current_insight_evidence(
            session,
            user_id,
            insight,
        )

        if not current_validation["valid"]:
            return {
                "success": False,
                "error": {
                    "code": current_validation["code"],
                    "message": current_validation["message"],
                },
            }

        claim_id = await _create_confirmed_claim(
            session=session,
            user_id=user_id,
            insight_id=insight_id,
            insight=insight,
        )

        await session.execute(
            text("""
                    UPDATE insights
                    SET status = 'CONFIRMED',
                        confirmed_claim_id = :claim_id,
                        decided_at = NOW()
                    WHERE id = :insight_id
                      AND user_id = :user_id
                """),
            {
                "claim_id": claim_id,
                "insight_id": insight_id,
                "user_id": user_id,
            },
        )

        return {
            "success": True,
            "data": {
                "insight_id": insight_id,
                "claim_id": claim_id,
                "status": "CONFIRMED",
                "already_confirmed": False,
            },
        }


async def reject_insight(
    user_id: str,
    insight_id: int,
) -> dict:
    async with SessionLocal() as session, session.begin():
        result = await session.execute(
            text("""
                    SELECT status
                    FROM insights
                    WHERE id = :insight_id
                      AND user_id = :user_id
                    FOR UPDATE
                """),
            {
                "insight_id": insight_id,
                "user_id": user_id,
            },
        )

        current = result.scalar_one_or_none()

        if current is None:
            return {
                "success": False,
                "error": {
                    "code": "INSIGHT_NOT_FOUND",
                    "message": "Insight not found.",
                },
            }

        if current == "CONFIRMED":
            return {
                "success": False,
                "error": {
                    "code": "INSIGHT_ALREADY_CONFIRMED",
                    "message": "Confirmed insight cannot be rejected.",
                },
            }

        if current == "REJECTED":
            return {
                "success": True,
                "data": {
                    "insight_id": insight_id,
                    "status": "REJECTED",
                    "already_rejected": True,
                },
            }

        await session.execute(
            text("""
                    UPDATE insights
                    SET status = 'REJECTED',
                        decided_at = NOW()
                    WHERE id = :insight_id
                      AND user_id = :user_id
                """),
            {
                "insight_id": insight_id,
                "user_id": user_id,
            },
        )

        return {
            "success": True,
            "data": {
                "insight_id": insight_id,
                "status": "REJECTED",
                "already_rejected": False,
            },
        }
