import os
from pathlib import Path
import json

from dotenv import load_dotenv

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()

MCP_URL = os.getenv("MCP_URL")

async def call_mcp_tool(tool_name: str, args: dict):
    async with streamable_http_client(MCP_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(tool_name, arguments=args)

            if result.is_error:
                raise RuntimeError(result.content[0].text)

            return json.loads(result.content[0].text)
