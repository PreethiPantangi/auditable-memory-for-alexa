import os
from mcp.server.mcpserver import MCPServer

from database import SessionLocal
from sqlalchemy import text

from responseformat import success_response, error_response

mcp = MCPServer("auditable-memory-for-alexa")

@mcp.tool()
async def server_status() -> dict:
    try: 
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return success_response(data="Server and database are healthy.")
    except Exception as e:
        return error_response(code="DATABASE_CONNECTION_FAILED", message="Database connection failed.")


@mcp.tool()
async def recall(user_id: str, category: str) -> dict:
    async with SessionLocal() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id 
                    FROM claims 
                    WHERE user_id =:user_id AND 
                    status = 'ACTIVE' AND 
                    category = :category
                    ORDER BY created_at desc;
                """), {"user_id": user_id, "category": category}
            )

            row = result.mappings().one_or_none()
            if row is None:
                return error_response(code="NO_ACTIVE_CLAIM", message="No active claim exists for this category.")
            return success_response(data=dict(row))
        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def remember(user_id: str, category: str, value: str, source_utterance: str) -> dict:
    async with SessionLocal() as session:
        try:
            category_active_claims = await session.execute(
                text("""
                    SELECT * FROM claims 
                    WHERE user_id = :user_id AND category = :category AND status = 'ACTIVE'
                """), {"user_id": user_id, "category": category}
            )
            row = category_active_claims.mappings().one_or_none()
            if row is None:
                results = await session.execute(
                    text("""
                        INSERT INTO claims (user_id, category, value, source_type, source_utterance, status) 
                        VALUES (:user_id, :category, :value, :source_type, :source_utterance, :status)
                        RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                    """), {"user_id": user_id, "category": category, "value": value, "source_type": "EXPLICIT", "source_utterance": source_utterance, "status": "ACTIVE"}
                )
                row = results.mappings().one()
                await session.commit()
                return success_response(data=dict(row))
            else:
                return error_response(code="ACTIVE_CLAIM_EXISTS", message="An active claim already exists, please correct memory")
        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def explain(claim_id: int, user_id: str) -> dict:
    async with SessionLocal() as session:
        try:
            results = await session.execute(
                text("""
                    SELECT id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id 
                    FROM claims 
                    WHERE id =:claim_id AND user_id = :user_id;
                """), {"claim_id": claim_id, "user_id": user_id}
            )
            row = results.mappings().one_or_none()
            if row is None:
                return error_response(code="CLAIM_NOT_FOUND", message="Claim not found")
                
            return success_response(data=dict(row))
        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def correct_memory(
    user_id: str,
    category: str,
    value: str,
    source_utterance: str
) -> dict:

    async with SessionLocal() as session:
        try:
            # 1. Find current active claim
            active_result = await session.execute(
                text("""
                    SELECT id FROM claims 
                    WHERE user_id = :user_id AND category = :category 
                    AND status = 'ACTIVE' FOR UPDATE
                """), {"user_id": user_id, "category": category}
            )

            active_claim = active_result.mappings().one_or_none()

            if active_claim is None:
                return error_response(
                    code="NO_ACTIVE_CLAIM",
                    message="No active claim exists for this category."
                )

            old_claim_id = active_claim["id"]

            # 2. Temporarily supersede old claim
            await session.execute(
                text("""
                    UPDATE claims SET status = 'SUPERSEDED' WHERE id = :old_claim_id
                """), {"old_claim_id": old_claim_id}
            )

            # 3. Insert new active claim
            insert_result = await session.execute(
                text("""
                    INSERT INTO claims (user_id, category, value, source_type, source_utterance, status)
                    VALUES (:user_id, :category, :value, 'EXPLICIT', :source_utterance, 'ACTIVE')
                    RETURNING id AS claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                """), {"user_id": user_id, "category": category, "value": value, "source_utterance": source_utterance}
            )

            new_claim = dict(insert_result.mappings().one())
            new_claim_id = new_claim["claim_id"]

            # 4. Link old claim to new claim
            old_result = await session.execute(
                text("""
                    UPDATE claims
                    SET superseded_by_claim_id = :new_claim_id
                    WHERE id = :old_claim_id
                    RETURNING id AS claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                """),{"new_claim_id": new_claim_id,"old_claim_id": old_claim_id}
            )

            superseded_claim = dict(old_result.mappings().one())

            await session.commit()

            return success_response(data={"new_claim": new_claim,"superseded_claim": superseded_claim})

        except Exception:
            await session.rollback()
            raise
@mcp.tool()
async def forget(user_id: str, category: str) -> dict:
    async with SessionLocal() as session:
        try: 
            results = await session.execute(
                text("""
                    UPDATE claims SET status = 'FORGOTTEN'
                    WHERE user_id = :user_id AND category = :category AND status = 'ACTIVE'
                    RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                """), {"user_id": user_id, "category": category}
            )
            row = results.mappings().one_or_none()
            if row is None:
                return error_response(code="NO_ACTIVE_CLAIM",message="No active claim exists for this category.")
            await session.commit()
            return success_response(data=dict(row))
        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def memory_history(user_id: str, category: str) -> dict:
    async with SessionLocal() as session:
        try:
            results = await session.execute(
                text("""
                    SELECT id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id 
                    FROM claims 
                    WHERE user_id =:user_id AND category = :category
                    ORDER BY created_at desc;
                """), {"user_id": user_id, "category": category}
            )
            rows = results.mappings().all()
            return success_response(data=[dict(row) for row in rows])
        except Exception:
            await session.rollback()
            raise


if __name__ == "__main__":
    
    port = int(os.environ.get("PORT", 8000))

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
        json_response=True
    )