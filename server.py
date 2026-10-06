import os
from mcp.server.mcpserver import MCPServer

from database import SessionLocal
from sqlalchemy import text

mcp = MCPServer("auditable-memory-for-alexa")

@mcp.tool()
async def server_status() -> dict:
    try: 
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "healthy": True,
            "message": "Server and database are healthy."
        }            
    except Exception as e:
        return {
            "healthy": False,
            "message": f"Database connection failed: {str(e)}"
        }  


@mcp.tool()
async def recall(user_id: str, category: str) -> dict:
    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id 
                FROM claims 
                WHERE user_id =:user_id AND 
                status = 'ACTIVE' AND 
                category = :category;
            """), {"user_id": user_id, "category": category}
        )

        rows = result.mappings().all()
        return {
            "status": "Fetched",
            "result": [dict(row) for row in rows]
        }

@mcp.tool()
async def remember(user_id: str, category: str, value: str, source_uttrance: str) -> dict:
    async with SessionLocal() as session:
        results = await session.execute(
            text("""
                INSERT INTO claims (user_id, category, value, source_type, source_utterance, status) 
                VALUES (:user_id, :category, :value, :source_type, :source_utterance, :status)
                RETURNING id, user_id, category, value, source_type, source_utterance, status, created_at, superseded_by_claim_id
            """), {"user_id": user_id, "category": category, "value": value, "source_type": "EXPLICIT", "source_utterance": source_uttrance, "status": "ACTIVE"}
        )
        row = results.mappings().one()
        await session.commit()
        return {
            "status": "Inserted",
            "result": dict(row)
        }


if __name__ == "__main__":
    
    port = int(os.environ.get("PORT", 8000))

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
        json_response=True
    )