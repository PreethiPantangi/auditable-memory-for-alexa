import hashlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from insights.insights_service import (
    confirm_insight as confirm_insight_service,
)
from insights.insights_service import (
    reject_insight as reject_insight_service,
)
from insights.insights_service import (
    save_insight_candidates as save_candidates_service,
)
from insights.repeated_adjustment import (
    derive_repeated_adjustments,
)
from responseformat import error_response, success_response
from security.demo_users import is_allowed_demo_user
from validators.event_validator import EventInput

logger = logging.getLogger(__name__)
mcp = MCPServer("auditable-memory-for-alexa")

ALLOWED_DEMO_USERS = os.getenv("ALLOWED_DEMO_USERS")


def validate_demo_user(user_id: str) -> dict | None:
    if not is_allowed_demo_user(user_id):
        return error_response(
            code="DEMO_USER_NOT_ALLOWED", message="Demo user not allowed."
        )

    return None


@mcp.tool()
async def server_status() -> dict:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return success_response(data="Server and database are healthy.")
    except SQLAlchemyError:
        return error_response(
            code="DATABASE_CONNECTION_FAILED", message="Database connection failed."
        )


@mcp.tool()
async def recall(user_id: str, category: str, memory_key: str | None = None) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
        try:
            query = """
                        SELECT id as claim_id, user_id, category, value, source_type, 
                        source_utterance, memory_key, status, created_at, superseded_by_claim_id 
                        FROM claims 
                        WHERE user_id =:user_id AND status = 'ACTIVE' 
                        AND category = :category
                    """
            params = {
                "user_id": user_id,
                "category": category,
                "memory_key": memory_key,
            }

            if memory_key is not None:
                query += " AND memory_key = :memory_key"
                params["memory_key"] = memory_key

            query += " ORDER BY created_at DESC"
            result = await session.execute(text(query), params)

            claims = [dict(row) for row in result.mappings().all()]
            return success_response(data=claims)
        except SQLAlchemyError:
            await session.rollback()
            raise


@mcp.tool()
async def remember(
    user_id: str, category: str, value: str, source_utterance: str
) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
        try:
            memory_key = str(uuid.uuid4())

            results = await session.execute(
                text("""
                    INSERT INTO claims (user_id, category, value, source_type, source_utterance, memory_key, status) 
                    VALUES (:user_id, :category, :value, :source_type, :source_utterance, :memory_key, :status)
                    RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, memory_key, status, created_at, superseded_by_claim_id
                """),
                {
                    "user_id": user_id,
                    "category": category,
                    "value": value,
                    "source_type": "EXPLICIT",
                    "source_utterance": source_utterance,
                    "memory_key": memory_key,
                    "status": "ACTIVE",
                },
            )
            row = results.mappings().one()
            await session.commit()
            return success_response(data=dict(row))

        except SQLAlchemyError:
            await session.rollback()
            raise


@mcp.tool()
async def explain(claim_id: int, user_id: str) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    if not 1 <= claim_id <= 2_147_483_647:
        return error_response(
            code="INVALID_CLAIM_ID",
            message="Claim ID must be a positive 32-bit integer.",
        )

    async with SessionLocal() as session:
        try:
            # Step 1: Retrieve the requested claim.
            result = await session.execute(
                text("""
                    SELECT
                        id AS claim_id,
                        user_id,
                        category,
                        value,
                        source_type,
                        source_utterance,
                        memory_key,
                        status,
                        created_at,
                        superseded_by_claim_id
                    FROM claims
                    WHERE id = :claim_id
                      AND user_id = :user_id
                """),
                {
                    "claim_id": claim_id,
                    "user_id": user_id,
                },
            )

            claim_row = result.mappings().one_or_none()

            if claim_row is None:
                return error_response(
                    code="CLAIM_NOT_FOUND",
                    message="Claim not found.",
                )

            claim = dict(claim_row)

            # Preserve the existing behavior for explicit
            # memories and other non-inferred source types.
            if claim["source_type"] != "INFERRED_CONFIRMED":
                return success_response(data=claim)

            # Step 2: Resolve the originating insight using
            # its confirmed_claim_id, not source text.
            insight_result = await session.execute(
                text("""
                    SELECT
                        id,
                        domain,
                        insight_type,
                        subject,
                        adjustment,
                        statement,
                        status,
                        decided_at
                    FROM insights
                    WHERE confirmed_claim_id = :claim_id
                      AND user_id = :user_id
                """),
                {
                    "claim_id": claim_id,
                    "user_id": user_id,
                },
            )

            insight_row = insight_result.mappings().one_or_none()

            if insight_row is None:
                # Do not fabricate provenance when
                # the source relationship is missing.
                claim["insight"] = None
                claim["evidence"] = []
                claim["provenance_complete"] = False

                return success_response(data=claim)

            insight = dict(insight_row)

            # Step 3: Retrieve original cooking observations.
            evidence_result = await session.execute(
                text("""
                    SELECT
                        e.id AS event_id,
                        e.user_id,
                        e.domain,
                        e.event_type,
                        e.subject,
                        e.attributes,
                        e.outcome,
                        e.source_type,
                        e.source_utterance,
                        e.occurred_at
                    FROM insight_evidence ie
                    JOIN events e
                      ON e.id = ie.event_id
                    WHERE ie.insight_id = :insight_id
                      AND e.user_id = :user_id
                    ORDER BY e.occurred_at, e.id
                """),
                {
                    "insight_id": insight["id"],
                    "user_id": user_id,
                },
            )

            evidence = [dict(row) for row in evidence_result.mappings().all()]

            claim["insight"] = insight
            claim["evidence"] = evidence
            claim["evidence_count"] = len(evidence)
            claim["provenance_complete"] = bool(evidence)

            return success_response(data=claim)

        except SQLAlchemyError:
            await session.rollback()
            logger.exception(
                "Failed to explain claim %s",
                claim_id,
            )
            return error_response(
                code="EXPLAIN_FAILED",
                message="Unable to retrieve memory explanation.",
            )


@mcp.tool()
async def correct_memory(
    user_id: str, category: str, value: str, source_utterance: str, memory_key: str
) -> dict:

    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
        try:
            active_result = await session.execute(
                text("""
                    SELECT id, category FROM claims
                    WHERE user_id = :user_id 
                    AND category = :category AND memory_key = :memory_key 
                    AND status = 'ACTIVE'
                    FOR UPDATE
                """),
                {"user_id": user_id, "category": category, "memory_key": memory_key},
            )

            active_claim = active_result.mappings().one_or_none()

            if active_claim is None:
                return error_response(
                    code="NO_ACTIVE_CLAIM",
                    message="No active claim found for this memory.",
                )

            old_claim_id = active_claim["id"]

            # 1: Supersede old claim.
            await session.execute(
                text("""
                    UPDATE claims
                    SET status = 'SUPERSEDED'
                    WHERE id = :old_claim_id
                """),
                {"old_claim_id": old_claim_id},
            )

            # Step 2: Insert replacement with same memory_key.
            result = await session.execute(
                text("""
                    INSERT INTO claims (user_id, category, value, source_type, source_utterance, memory_key, status)
                    VALUES (:user_id, :category, :value, 'EXPLICIT', :source_utterance, :memory_key, 'ACTIVE')
                    RETURNING *
                """),
                {
                    "user_id": user_id,
                    "category": category,
                    "value": value,
                    "source_utterance": source_utterance,
                    "memory_key": memory_key,
                },
            )

            new_claim = dict(result.mappings().one())

            # Step 3: Link old claim to new claim.
            await session.execute(
                text("""
                    UPDATE claims
                    SET superseded_by_claim_id = :new_id
                    WHERE id = :old_id
                """),
                {"new_id": new_claim["id"], "old_id": old_claim_id},
            )

            await session.commit()

            return success_response(
                data={
                    "memory_key": memory_key,
                    "claim_id": new_claim["id"],
                    "new_claim_id": new_claim["id"],
                    "superseded_claim_id": old_claim_id,
                    "new_claim": new_claim,
                }
            )

        except SQLAlchemyError:
            await session.rollback()
            raise


@mcp.tool()
async def forget(user_id: str, category: str, memory_key: str) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
        try:
            results = await session.execute(
                text("""
                    UPDATE claims SET status = 'FORGOTTEN'
                    WHERE user_id = :user_id AND category = :category AND status = 'ACTIVE' AND memory_key = :memory_key
                    RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, memory_key, status, created_at, superseded_by_claim_id
                """),
                {"user_id": user_id, "category": category, "memory_key": memory_key},
            )
            row = results.mappings().one_or_none()
            if row is None:
                return error_response(
                    code="NO_ACTIVE_CLAIM",
                    message="No active claim exists for this category.",
                )
            await session.commit()
            return success_response(data=dict(row))
        except SQLAlchemyError:
            await session.rollback()
            raise


@mcp.tool()
async def memory_history(
    user_id: str,
    category: str,
    memory_key: str | None = None,
) -> dict:

    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
        try:
            query = """
                SELECT id AS claim_id, user_id, category, value, source_type, source_utterance, status, memory_key, created_at, superseded_by_claim_id
                FROM claims
                WHERE user_id = :user_id
                AND category = :category
            """

            params = {"user_id": user_id, "category": category}

            if memory_key is not None:
                query += " AND memory_key = :memory_key"
                params["memory_key"] = memory_key

            query += " ORDER BY created_at DESC"

            result = await session.execute(text(query), params)

            claims = [dict(row) for row in result.mappings().all()]

            return success_response(data=claims)

        except SQLAlchemyError:
            await session.rollback()
            raise


@mcp.tool()
async def log_event(
    user_id: str,
    domain: str,
    event_type: str,
    subject: str,
    attributes: dict,
    source_utterance: str,
    request_id: str,
    outcome: str | None = None,
    occurred_at: str | None = None,
) -> dict:

    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    try:
        event = EventInput(
            user_id=user_id,
            domain=domain,
            event_type=event_type,
            subject=subject,
            attributes=attributes,
            source_utterance=source_utterance,
            outcome=outcome,
            occurred_at=occurred_at,
            request_id=request_id,
        )
        logger.info(
            "Validated event adjustment: %s",
            event.attributes.get("adjustment"),
        )
    except ValidationError:
        return error_response(
            code="INVALID_EVENT",
            message="Invalid event data.",
        )

    payload_hash = event_payload_hash(event)

    async with SessionLocal() as session:
        try:
            result = await session.execute(
                text("""
                    INSERT INTO events (
                        user_id,
                        domain,
                        event_type,
                        subject,
                        attributes,
                        outcome,
                        source_type,
                        source_utterance,
                        occurred_at,
                        request_id,
                        request_hash
                    )
                    VALUES (
                        :user_id,
                        :domain,
                        :event_type,
                        :subject,
                        CAST(:attributes AS JSONB),
                        :outcome,
                        'EXPLICIT',
                        :source_utterance,
                        :occurred_at,
                        :request_id,
                        :request_hash
                    )
                    ON CONFLICT (user_id, request_id)
                    WHERE request_id IS NOT NULL
                    DO NOTHING
                    RETURNING *
                """),
                {
                    "user_id": event.user_id,
                    "domain": event.domain,
                    "event_type": event.event_type,
                    "subject": event.subject,
                    "attributes": json.dumps(event.attributes),
                    "outcome": event.outcome,
                    "source_utterance": (event.source_utterance),
                    "occurred_at": (event.occurred_at or datetime.now(UTC)),
                    "request_id": str(event.request_id),
                    "request_hash": payload_hash,
                },
            )

            inserted = result.mappings().one_or_none()

            if inserted is not None:
                await session.commit()

                return success_response(
                    data={
                        "event": dict(inserted),
                        "created": True,
                        "duplicate": False,
                    }
                )

            # Insert was skipped because this user already submitted the same request ID.
            existing_result = await session.execute(
                text("""
                    SELECT *
                    FROM events
                    WHERE user_id = :user_id
                      AND request_id = :request_id
                """),
                {
                    "user_id": event.user_id,
                    "request_id": str(event.request_id),
                },
            )

            existing = existing_result.mappings().one_or_none()

            if existing is None:
                await session.rollback()
                return error_response(
                    code="EVENT_RETRY_FAILED",
                    message="Unable to resolve the original event.",
                )

            if existing["request_hash"] != payload_hash:
                await session.rollback()

                return error_response(
                    code="IDEMPOTENCY_CONFLICT",
                    message=(
                        "This request ID was already used with different event data."
                    ),
                )

            await session.commit()

            return success_response(
                data={
                    "event": dict(existing),
                    "created": False,
                    "duplicate": True,
                }
            )

        except SQLAlchemyError:
            await session.rollback()

            logger.exception("Failed to persist idempotent event")

            return error_response(
                code="EVENT_SAVE_FAILED",
                message="Unable to save event.",
            )


@mcp.tool()
async def list_events(
    user_id: str,
    domain: str,
    subject: str | None = None,
    limit: int = 50,
) -> dict:

    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    if domain != "cooking":
        return error_response(
            code="UNSUPPORTED_DOMAIN",
            message="Unsupported event domain.",
        )

    if limit < 1 or limit > 100:
        return error_response(
            code="INVALID_LIMIT",
            message="Limit must be between 1 and 100.",
        )

    query = """
        SELECT
            id,
            user_id,
            domain,
            event_type,
            subject,
            attributes,
            outcome,
            source_type,
            source_utterance,
            occurred_at,
            created_at
        FROM events
        WHERE user_id = :user_id
          AND domain = :domain
    """

    params = {
        "user_id": user_id,
        "domain": domain,
        "limit": limit,
    }

    if subject is not None:
        subject = subject.strip()

        if not subject:
            return error_response(
                code="INVALID_SUBJECT",
                message="Subject cannot be empty.",
            )

        query += " AND LOWER(subject) = LOWER(:subject)"
        params["subject"] = subject

    query += """
        ORDER BY occurred_at DESC, id DESC
        LIMIT :limit
    """

    async with SessionLocal() as session:
        try:
            result = await session.execute(
                text(query),
                params,
            )

            events = [dict(row) for row in result.mappings().all()]

            return success_response(
                data={
                    "events": events,
                    "count": len(events),
                }
            )

        except SQLAlchemyError:
            await session.rollback()

            logger.exception("Failed to retrieve events")

            return error_response(
                code="EVENT_RETRIEVAL_FAILED",
                message="Unable to retrieve events.",
            )


@mcp.tool()
async def derive_insights(
    user_id: str,
    domain: str = "cooking",
) -> dict:

    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    if domain != "cooking":
        return error_response(
            code="UNSUPPORTED_DOMAIN",
            message="Only cooking insights are supported.",
        )

    async with SessionLocal() as session:
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


@mcp.tool()
async def save_insight_candidates(user_id: str) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    try:
        result = await save_candidates_service(user_id)
        return success_response(data=result)
    except SQLAlchemyError:
        logger.exception("Failed to save insights")
        return error_response(
            code="INSIGHT_SAVE_FAILED",
            message="Unable to save insights.",
        )


@mcp.tool()
async def confirm_insight(
    user_id: str,
    insight_id: int,
) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    try:
        return await confirm_insight_service(user_id, insight_id)
    except SQLAlchemyError:
        logger.exception("Failed to confirm insight")
        return error_response(
            code="INSIGHT_CONFIRM_FAILED",
            message="Unable to confirm insight.",
        )


@mcp.tool()
async def reject_insight(
    user_id: str,
    insight_id: int,
) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    try:
        return await reject_insight_service(user_id, insight_id)
    except SQLAlchemyError:
        logger.exception("Failed to reject insight")
        return error_response(
            code="INSIGHT_REJECT_FAILED",
            message="Unable to reject insight.",
        )


@mcp.tool()
async def list_insights(user_id: str) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
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


@mcp.tool()
async def get_insight_evidence(
    user_id: str,
    insight_id: int,
) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    async with SessionLocal() as session:
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


def event_payload_hash(event: EventInput) -> str:
    payload = event.model_dump(
        mode="json",
        exclude={"request_id"},
    )

    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import uvicorn

    from security.mcp_auth import MCPServiceAuth

    port = int(os.environ.get("PORT", "8000"))

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            "auditable-memory-for-alexa.onrender.com",
            "auditable-memory-for-alexa.onrender.com:*",
        ],
    )

    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )

    protected_app = MCPServiceAuth(mcp_app)

    uvicorn.run(
        protected_app,
        host="0.0.0.0",
        port=port,
    )
