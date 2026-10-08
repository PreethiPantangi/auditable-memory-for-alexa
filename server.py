import os
from mcp.server.mcpserver import MCPServer

from database import SessionLocal
from sqlalchemy import text

from responseformat import success_response, error_response

import uuid

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
async def recall(user_id: str, category: str, memory_key: str | None = None) -> dict:
    async with SessionLocal() as session:
        try:
            query = """
                        SELECT id as claim_id, user_id, category, value, source_type, 
                        source_utterance, memory_key, status, created_at, superseded_by_claim_id 
                        FROM claims 
                        WHERE user_id =:user_id AND status = 'ACTIVE' 
                        AND category = :category
                    """
            params = {"user_id": user_id, "category": category, "memory_key": memory_key}
            
            if memory_key is not None:
                query += " AND memory_key = :memory_key"
                params["memory_key"] = memory_key

            query += " ORDER BY created_at DESC"
            result = await session.execute(text(query), params)

            claims = [
               dict(row)
                for row in result.mappings().all()
            ]
            return success_response(data=claims)
        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def remember(user_id: str, category: str, value: str, source_utterance: str) -> dict:
    async with SessionLocal() as session:
        try:
            memory_key = str(uuid.uuid4())
            
            results = await session.execute(
                text("""
                    INSERT INTO claims (user_id, category, value, source_type, source_utterance, memory_key, status) 
                    VALUES (:user_id, :category, :value, :source_type, :source_utterance, :memory_key, :status)
                    RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, memory_key, status, created_at, superseded_by_claim_id
                """), {"user_id": user_id, "category": category, "value": value, "source_type": "EXPLICIT", "source_utterance": source_utterance, "memory_key": memory_key, "status": "ACTIVE"}
            )
            row = results.mappings().one()
            await session.commit()
            return success_response(data=dict(row))
            
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
async def correct_memory(user_id: str, category: str, value: str, source_utterance: str, memory_key: str) -> dict:

    async with SessionLocal() as session:
        try:
            active_result = await session.execute(
                text("""
                    SELECT id, category FROM claims
                    WHERE user_id = :user_id 
                    AND category = :category AND memory_key = :memory_key 
                    AND status = 'ACTIVE'
                    FOR UPDATE
                """), {"user_id": user_id, "category": category, "memory_key": memory_key}
            )

            active_claim = active_result.mappings().one_or_none()

            if active_claim is None:
                return error_response(code="NO_ACTIVE_CLAIM",message="No active claim found for this memory.")

            old_claim_id = active_claim["id"]

            # 1: Supersede old claim.
            await session.execute(
                text("""
                    UPDATE claims
                    SET status = 'SUPERSEDED'
                    WHERE id = :old_claim_id
                """),
                {"old_claim_id": old_claim_id}
            )

            # Step 2: Insert replacement with same memory_key.
            result = await session.execute(
                text("""
                    INSERT INTO claims (user_id, category, value, source_type, source_utterance, memory_key, status)
                    VALUES (:user_id, :category, :value, 'EXPLICIT', :source_utterance, :memory_key, 'ACTIVE')
                    RETURNING *
                """), {"user_id": user_id, "category": category, "value": value, "source_utterance": source_utterance, "memory_key": memory_key}
            )

            new_claim = dict(result.mappings().one())

            # Step 3: Link old claim to new claim.
            await session.execute(
                text("""
                    UPDATE claims
                    SET superseded_by_claim_id = :new_id
                    WHERE id = :old_id
                """), {"new_id": new_claim["id"], "old_id": old_claim_id}
            )

            await session.commit()

            return success_response(
                data={
                    "new_claim": new_claim,
                    "superseded_claim_id": old_claim_id
                }
            )

        except Exception:
            await session.rollback()
            raise

@mcp.tool()
async def forget(user_id: str, category: str, memory_key: str) -> dict:
    async with SessionLocal() as session:
        try: 
            results = await session.execute(
                text("""
                    UPDATE claims SET status = 'FORGOTTEN'
                    WHERE user_id = :user_id AND category = :category AND status = 'ACTIVE' AND memory_key = :memory_key
                    RETURNING id as claim_id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
                """), {"user_id": user_id, "category": category, "memory_key": memory_key}
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
async def memory_history(user_id: str, category: str, memory_key: str | None = None) -> dict:

    async with SessionLocal() as session:
        try:
            query = """
                SELECT id AS claim_id, user_id, category, value, source_type, source_utterance, status, memory_key, created_at, superseded_by_claim_id
                FROM claims
                WHERE user_id = :user_id
                AND category = :category
            """

            params = {"user_id": user_id,"category": category}

            if memory_key is not None:
                query += " AND memory_key = :memory_key"
                params["memory_key"] = memory_key

            query += " ORDER BY created_at DESC"

            result = await session.execute(text(query), params)

            claims = [dict(row) for row in result.mappings().all()]

            return success_response(data=claims)

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