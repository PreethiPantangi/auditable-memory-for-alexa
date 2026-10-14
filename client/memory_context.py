from uuid import UUID

from sqlalchemy import text

from database import SessionLocal


async def save_memory_context(
    user_id: str,
    conversation_id: str,
    claim: dict,
) -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            text("""
                INSERT INTO conversation_memory_context (
                    user_id, conversation_id,
                    memory_key, category
                )
                VALUES (
                    :user_id, :conversation_id,
                    :memory_key, :category
                )
                ON CONFLICT (user_id, conversation_id)
                DO UPDATE SET
                    memory_key = EXCLUDED.memory_key,
                    category = EXCLUDED.category,
                    updated_at = NOW()
            """),
            {
                "user_id": user_id,
                "conversation_id": UUID(conversation_id),
                "memory_key": UUID(claim["memory_key"]),
                "category": claim["category"],
            },
        )


async def get_memory_context(
    user_id: str,
    conversation_id: str,
) -> dict | None:
    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT memory_key, category
                FROM conversation_memory_context
                WHERE user_id = :user_id
                  AND conversation_id = :conversation_id
            """),
            {
                "user_id": user_id,
                "conversation_id": UUID(conversation_id),
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None


async def clear_memory_context(
    user_id: str,
    conversation_id: str,
) -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            text("""
                DELETE FROM conversation_memory_context
                WHERE user_id = :user_id
                  AND conversation_id = :conversation_id
            """),
            {
                "user_id": user_id,
                "conversation_id": UUID(conversation_id),
            },
        )
