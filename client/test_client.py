import asyncio

from .mcp_client import call_mcp_tool

async def main():
    result = await call_mcp_tool("remember", {
            "user_id": "demo-user",
            "category": "travel",
            "value": "aisle seat",
            "source_utterance": "I prefer sitting on the aisle seat"
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
