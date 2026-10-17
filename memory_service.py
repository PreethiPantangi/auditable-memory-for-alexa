import uuid

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from responseformat import error_response, success_response


async def recall(
    session_factory,
    user_id: str,
    category: str,
    memory_key: str | None = None,
) -> dict:
    async with session_factory() as session:
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


async def recall_all(session_factory, user_id: str) -> dict:
    """Read only this user's ACTIVE claims across all categories."""
    async with session_factory() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT id AS claim_id, user_id, category, value,
                           source_type, source_utterance, memory_key,
                           status, created_at, superseded_by_claim_id
                    FROM claims
                    WHERE user_id = :user_id AND status = 'ACTIVE'
                    ORDER BY created_at DESC, id DESC
                """),
                {"user_id": user_id},
            )
            return success_response(data=[dict(row) for row in result.mappings().all()])
        except SQLAlchemyError:
            await session.rollback()
            raise


async def remember(
    session_factory,
    user_id: str,
    category: str,
    value: str,
    source_utterance: str,
) -> dict:
    async with session_factory() as session:
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


async def explain(
    session_factory,
    logger,
    claim_id: int,
    user_id: str,
) -> dict:
    if not 1 <= claim_id <= 2_147_483_647:
        return error_response(
            code="INVALID_CLAIM_ID",
            message="Claim ID must be a positive 32-bit integer.",
        )

    async with session_factory() as session:
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


async def correct_memory(
    session_factory,
    user_id: str,
    category: str,
    value: str,
    source_utterance: str,
    memory_key: str,
) -> dict:
    async with session_factory() as session:
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


async def forget(
    session_factory,
    user_id: str,
    category: str,
    memory_key: str,
) -> dict:
    async with session_factory() as session:
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


async def memory_history(
    session_factory,
    user_id: str,
    category: str,
    memory_key: str | None = None,
) -> dict:
    async with session_factory() as session:
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
