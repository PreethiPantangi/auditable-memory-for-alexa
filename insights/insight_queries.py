from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from insights.repeated_adjustment import derive_repeated_adjustments
from responseformat import error_response, success_response


async def derive_insights(
    session_factory,
    logger,
    user_id: str,
    domain: str = "cooking",
) -> dict:
    if domain != "cooking":
        return error_response(
            code="UNSUPPORTED_DOMAIN",
            message="Only cooking insights are supported.",
        )

    async with session_factory() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT
                        id,
                        user_id,
                        domain,
                        event_type,
                        subject,
                        attributes,
                        outcome,
                        source_utterance,
                        occurred_at
                    FROM events
                    WHERE user_id = :user_id
                      AND domain = :domain
                      AND event_type = 'meal_prepared'
                    ORDER BY occurred_at ASC, id ASC
                """),
                {
                    "user_id": user_id,
                    "domain": domain,
                },
            )

            events = [dict(row) for row in result.mappings().all()]

            insights = derive_repeated_adjustments(events)

            return success_response(
                data={
                    "insights": insights,
                    "count": len(insights),
                    "events_examined": len(events),
                }
            )

        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Insight derivation failed")

            return error_response(
                code="INSIGHT_DERIVATION_FAILED",
                message="Unable to derive insights.",
            )


async def list_insights(
    session_factory,
    logger,
    user_id: str,
) -> dict:
    async with session_factory() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT
                        i.id AS insight_id,
                        i.domain,
                        i.insight_type,
                        i.subject,
                        i.adjustment,
                        i.statement,
                        i.status,
                        i.confirmed_claim_id,
                        i.created_at,
                        i.decided_at,
                        COUNT(ie.event_id) AS evidence_count
                    FROM insights i
                    LEFT JOIN insight_evidence ie
                      ON ie.insight_id = i.id
                    WHERE i.user_id = :user_id
                    GROUP BY i.id
                    ORDER BY i.created_at DESC, i.id DESC
                """),
                {"user_id": user_id},
            )

            insights = [dict(row) for row in result.mappings()]

            return success_response(
                data={
                    "insights": insights,
                    "count": len(insights),
                }
            )
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Failed to list insights")
            return error_response(
                code="INSIGHT_LIST_FAILED",
                message="Unable to retrieve insights.",
            )


async def get_insight_evidence(
    session_factory,
    logger,
    user_id: str,
    insight_id: int,
) -> dict:
    async with session_factory() as session:
        try:
            insight_result = await session.execute(
                text("""
                    SELECT id, statement, status
                    FROM insights
                    WHERE id = :insight_id
                      AND user_id = :user_id
                """),
                {
                    "insight_id": insight_id,
                    "user_id": user_id,
                },
            )

            insight = insight_result.mappings().one_or_none()

            if insight is None:
                return error_response(
                    code="INSIGHT_NOT_FOUND",
                    message="Insight not found.",
                )

            result = await session.execute(
                text("""
                    SELECT
                        e.id,
                        e.subject,
                        e.attributes,
                        e.outcome,
                        e.source_utterance,
                        e.occurred_at
                    FROM insight_evidence ie
                    JOIN events e ON e.id = ie.event_id
                    JOIN insights i ON i.id = ie.insight_id
                    WHERE i.id = :insight_id
                      AND i.user_id = :user_id
                      AND e.user_id = :user_id
                    ORDER BY e.occurred_at, e.id
                """),
                {
                    "insight_id": insight_id,
                    "user_id": user_id,
                },
            )

            events = [dict(row) for row in result.mappings()]

            return success_response(
                data={
                    "insight_id": insight_id,
                    "status": insight["status"],
                    "statement": insight["statement"],
                    "events": events,
                    "count": len(events),
                }
            )
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Failed to retrieve insight evidence")
            return error_response(
                code="INSIGHT_EVIDENCE_FAILED",
                message="Unable to retrieve insight evidence.",
            )
