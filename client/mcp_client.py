import json
import os
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MCP_URL = os.getenv("MCP_URL")
MCP_SERVICE_TOKEN = os.getenv("MCP_SERVICE_TOKEN")


async def call_mcp_tool(tool_name: str, args: dict) -> dict:
    if not MCP_URL:
        raise RuntimeError("MCP_URL is not configured.")

    if not MCP_SERVICE_TOKEN or len(MCP_SERVICE_TOKEN) < 32:
        raise RuntimeError("MCP_SERVICE_TOKEN is missing or too short.")

    headers = {"Authorization": f"Bearer {MCP_SERVICE_TOKEN}"}

    async with (
        httpx2.AsyncClient(
            headers=headers, timeout=httpx2.Timeout(30.0, read=300.0)
        ) as http_client,
        streamable_http_client(MCP_URL, http_client=http_client) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        result = await session.call_tool(tool_name, arguments=args)

        if result.is_error:
            messages = [
                block.text
                for block in result.content
                if getattr(block, "type", None) == "text"
            ]

            raise RuntimeError("; ".join(messages) or "MCP tool execution failed.")

        text_blocks = [
            block.text
            for block in result.content
            if getattr(block, "type", None) == "text"
        ]

        if not text_blocks:
            raise RuntimeError("MCP returned no text response.")

        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as exc:
            raise RuntimeError("MCP returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise TypeError("Unexpected MCP response format.")

        return payload
