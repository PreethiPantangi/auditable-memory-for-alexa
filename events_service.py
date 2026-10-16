import hashlib
import json
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from responseformat import error_response, success_response
from validators.event_validator import EventInput


async def log_event(
    session_factory,
    logger,
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

    async with session_factory() as session:
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


async def list_events(
    session_factory,
    logger,
    user_id: str,
    domain: str,
    subject: str | None = None,
    limit: int = 50,
) -> dict:
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

    async with session_factory() as session:
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
