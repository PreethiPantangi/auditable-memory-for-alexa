import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from starlette.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


class MCPServiceAuth:
    def __init__(self, app):
        self.app = app

        self.expected_token = os.getenv("MCP_SERVICE_TOKEN", "")

        if len(self.expected_token) < 32:
            raise RuntimeError("MCP_SERVICE_TOKEN must be at least 32 characters long.")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path not in ("/mcp", "/mcp/"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}

        auth_header = headers.get(b"authorization", b"")

        scheme, separator, supplied_token = auth_header.partition(b" ")

        token_is_valid = (
            separator == b" "
            and scheme.lower() == b"bearer"
            and bool(supplied_token)
            and secrets.compare_digest(
                supplied_token,
                self.expected_token.encode("utf-8"),
            )
        )

        logger.warning(
            "MCP AUTH: path=%s "
            "header_present=%s "
            "bearer_scheme=%s "
            "token_length=%s "
            "token_valid=%s",
            path,
            bool(auth_header),
            scheme.lower() == b"bearer",
            len(supplied_token),
            token_is_valid,
        )

        if not token_is_valid:
            response = JSONResponse(
                status_code=401,
                content={
                    "error": "UNAUTHORIZED",
                    "message": "Valid MCP service token required.",
                },
                headers={
                    "WWW-Authenticate": "Bearer",
                },
            )

            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
