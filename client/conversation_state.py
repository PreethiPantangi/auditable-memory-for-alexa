import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from database import SessionLocal


async def save_pending_clarification(
    conversation_id: str,
    user_id: str,
    original_question: str,
    category: str,
    candidate_memory_keys: list[str],
    clarification_question: str,
) -> None:
    if not candidate_memory_keys:
        raise ValueError("Clarification candidates cannot be empty.")

    async with SessionLocal() as session, session.begin():
        await session.execute(
            text("""
                INSERT INTO pending_clarifications (
                    conversation_id,
                    user_id,
                    operation,
                    original_question,
                    category,
                    candidate_memory_keys,
                    clarification_question,
                    expires_at,
                    target_memory_key
                )
                VALUES (
                    :conversation_id,
                    :user_id,
                    'recall',
                    :original_question,
                    :category,
                    CAST(:candidate_memory_keys AS JSONB),
                    :clarification_question,
                    :expires_at,
                    NULL
                )
                ON CONFLICT (conversation_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    operation = EXCLUDED.operation,
                    original_question = EXCLUDED.original_question,
                    category = EXCLUDED.category,
                    candidate_memory_keys = EXCLUDED.candidate_memory_keys,
                    clarification_question = EXCLUDED.clarification_question,
                    created_at = NOW(),
                    expires_at = EXCLUDED.expires_at,
                    target_memory_key = NULL
            """),
            {
                "conversation_id": UUID(conversation_id),
                "user_id": user_id,
                "original_question": original_question,
                "category": category,
                "candidate_memory_keys": json.dumps(candidate_memory_keys),
                "clarification_question": clarification_question,
                "expires_at": datetime.now(UTC) + timedelta(minutes=15),
            },
        )


async def get_pending_clarification(
    conversation_id: str,
    user_id: str,
) -> dict | None:
    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
    operation,
    original_question,
    category,
    candidate_memory_keys,
    target_memory_key,
    clarification_question,
    expires_at
FROM pending_clarifications
WHERE conversation_id = :conversation_id
  AND user_id = :user_id
  AND expires_at > NOW()
            """),
            {
                "conversation_id": UUID(conversation_id),
                "user_id": user_id,
            },
        )

        row = result.mappings().one_or_none()

        if row is None:
            return None

        pending = dict(row)

        keys = pending["candidate_memory_keys"]

        target_key = pending["target_memory_key"]

        pending["target_memory_key"] = (
            str(target_key) if target_key is not None else None
        )

        if pending["operation"] == "correct_memory":
            if not pending["target_memory_key"]:
                raise ValueError("Pending correction has no target.")

        elif pending["operation"] != "recall":
            raise ValueError("Unsupported pending operation.")

        if isinstance(keys, str):
            keys = json.loads(keys)

        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise ValueError("Invalid pending clarification keys.")

        pending["candidate_memory_keys"] = keys

        return pending


async def clear_pending_clarification(
    conversation_id: str,
    user_id: str,
) -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            text("""
                DELETE FROM pending_clarifications
                WHERE conversation_id = :conversation_id
                  AND user_id = :user_id
            """),
            {
                "conversation_id": UUID(conversation_id),
                "user_id": user_id,
            },
        )


async def save_pending_correction(
    conversation_id: str,
    user_id: str,
    original_question: str,
    category: str,
    target_memory_key: str,
    clarification_question: str,
) -> None:
    if not target_memory_key:
        raise ValueError("Correction target is required.")

    async with SessionLocal() as session, session.begin():
        await session.execute(
            text("""
                INSERT INTO pending_clarifications (
                    conversation_id,
                    user_id,
                    operation,
                    original_question,
                    category,
                    candidate_memory_keys,
                    target_memory_key,
                    clarification_question,
                    expires_at
                )
                VALUES (
                    :conversation_id,
                    :user_id,
                    'correct_memory',
                    :original_question,
                    :category,
                    CAST('[]' AS JSONB),
                    :target_memory_key,
                    :clarification_question,
                    :expires_at
                )
                ON CONFLICT (conversation_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    operation = EXCLUDED.operation,
                    original_question = EXCLUDED.original_question,
                    category = EXCLUDED.category,
                    candidate_memory_keys = EXCLUDED.candidate_memory_keys,
                    target_memory_key = EXCLUDED.target_memory_key,
                    clarification_question = EXCLUDED.clarification_question,
                    created_at = NOW(),
                    expires_at = EXCLUDED.expires_at
            """),
            {
                "conversation_id": UUID(conversation_id),
                "user_id": user_id,
                "original_question": original_question,
                "category": category,
                "target_memory_key": UUID(target_memory_key),
                "clarification_question": clarification_question,
                "expires_at": datetime.now(UTC) + timedelta(minutes=15),
            },
        )
