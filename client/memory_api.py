from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from database import SessionLocal
from security.demo_access import require_matching_demo_user
from security.demo_users import is_allowed_demo_user

router = APIRouter()


def validate_demo_user(user_id: str) -> str:
    if not is_allowed_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Demo user not allowed.")

    return user_id


@router.get("/memories")
async def list_memories(user_id: str = Depends(require_matching_demo_user)):

    user_id = validate_demo_user(user_id)

    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT DISTINCT ON (memory_key) id AS claim_id, memory_key, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                FROM claims
                WHERE user_id = :user_id
                ORDER BY
                    memory_key,
                    created_at DESC,
                    id DESC
            """),
            {"user_id": user_id},
        )

        claims = [dict(row) for row in result.mappings().all()]

        return {"memories": claims}


@router.get("/memories/{memory_key}/history")
async def get_memory_history(
    memory_key: str, user_id: str = Depends(require_matching_demo_user)
):

    user_id = validate_demo_user(user_id)

    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id AS claim_id, memory_key, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                FROM claims
                WHERE user_id = :user_id
                AND memory_key = :memory_key
                ORDER BY created_at ASC, id ASC
            """),
            {"user_id": user_id, "memory_key": memory_key},
        )

        claims = [dict(row) for row in result.mappings().all()]

        if not claims:
            raise HTTPException(status_code=404, detail="Memory not found")

        return {"history": claims}
