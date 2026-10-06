import os
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("auditable-memory-for-alexa")

@mcp.tool()
def server_status() -> dict:
    return {
        "healthy": True,
        "message": "Server is healthy and running."
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