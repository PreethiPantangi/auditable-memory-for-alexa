import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from security.demo_access import require_matching_demo_user
from security.demo_users import is_allowed_demo_user

logger = logging.getLogger(__name__)
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


@router.get("/memories/{claim_id}/explain")
async def get_memory_explanation(
    claim_id: int,
    user_id: str = Depends(require_matching_demo_user),
):
    user_id = validate_demo_user(user_id)

    if not 1 <= claim_id <= 2_147_483_647:
        raise HTTPException(
            status_code=400,
            detail="Invalid claim ID.",
        )

    try:
        async with SessionLocal() as session:
            claim_result = await session.execute(
                text("""
                    SELECT
                        id AS claim_id,
                        user_id,
                        category,
                        memory_key,
                        value,
                        source_type,
                        source_utterance,
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

            claim_row = claim_result.mappings().one_or_none()

            if claim_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Memory claim not found.",
                )

            claim = dict(claim_row)

            if claim["source_type"] != "INFERRED_CONFIRMED":
                return claim

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
                return {
                    **claim,
                    "insight": None,
                    "evidence": [],
                    "evidence_count": 0,
                    "provenance_complete": False,
                }

            insight = dict(insight_row)

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
                    JOIN events e ON e.id = ie.event_id
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

            return {
                **claim,
                "insight": insight,
                "evidence": evidence,
                "evidence_count": len(evidence),
                "provenance_complete": bool(evidence),
            }

    except SQLAlchemyError:
        logger.exception(
            "Failed to retrieve explanation for claim %s",
            claim_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve memory explanation.",
        ) from None
