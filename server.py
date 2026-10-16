import logging
import os
import uuid as uuid

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import events_service
import memory_service
from database import SessionLocal
from insights import insight_queries
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
    derive_repeated_adjustments as derive_repeated_adjustments,
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

    return await memory_service.recall(
        session_factory=SessionLocal,
        user_id=user_id,
        category=category,
        memory_key=memory_key,
    )


@mcp.tool()
async def remember(
    user_id: str, category: str, value: str, source_utterance: str
) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    return await memory_service.remember(
        session_factory=SessionLocal,
        user_id=user_id,
        category=category,
        value=value,
        source_utterance=source_utterance,
    )


@mcp.tool()
async def explain(claim_id: int, user_id: str) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    return await memory_service.explain(
        session_factory=SessionLocal,
        logger=logger,
        claim_id=claim_id,
        user_id=user_id,
    )


@mcp.tool()
async def correct_memory(
    user_id: str, category: str, value: str, source_utterance: str, memory_key: str
) -> dict:

    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    return await memory_service.correct_memory(
        session_factory=SessionLocal,
        user_id=user_id,
        category=category,
        value=value,
        source_utterance=source_utterance,
        memory_key=memory_key,
    )


@mcp.tool()
async def forget(user_id: str, category: str, memory_key: str) -> dict:
    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    return await memory_service.forget(
        session_factory=SessionLocal,
        user_id=user_id,
        category=category,
        memory_key=memory_key,
    )


@mcp.tool()
async def memory_history(
    user_id: str,
    category: str,
    memory_key: str | None = None,
) -> dict:

    validation_error = validate_demo_user(user_id)

    if validation_error is not None:
        return validation_error

    return await memory_service.memory_history(
        session_factory=SessionLocal,
        user_id=user_id,
        category=category,
        memory_key=memory_key,
    )


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

    return await events_service.log_event(
        session_factory=SessionLocal,
        logger=logger,
        user_id=user_id,
        domain=domain,
        event_type=event_type,
        subject=subject,
        attributes=attributes,
        source_utterance=source_utterance,
        request_id=request_id,
        outcome=outcome,
        occurred_at=occurred_at,
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

    return await events_service.list_events(
        session_factory=SessionLocal,
        logger=logger,
        user_id=user_id,
        domain=domain,
        subject=subject,
        limit=limit,
    )


@mcp.tool()
async def derive_insights(
    user_id: str,
    domain: str = "cooking",
) -> dict:

    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    return await insight_queries.derive_insights(
        session_factory=SessionLocal,
        logger=logger,
        user_id=user_id,
        domain=domain,
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

    return await insight_queries.list_insights(
        session_factory=SessionLocal,
        logger=logger,
        user_id=user_id,
    )


@mcp.tool()
async def get_insight_evidence(
    user_id: str,
    insight_id: int,
) -> dict:
    validation_error = validate_demo_user(user_id)
    if validation_error is not None:
        return validation_error

    return await insight_queries.get_insight_evidence(
        session_factory=SessionLocal,
        logger=logger,
        user_id=user_id,
        insight_id=insight_id,
    )


def event_payload_hash(event: EventInput) -> str:
    return events_service.event_payload_hash(event)


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
