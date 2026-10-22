import json
from uuid import uuid4

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

pytestmark = pytest.mark.anyio


async def test_mcp_http_lifecycle(cooking_mcp):
    target = cooking_mcp
    db = target.db
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {target.token}"}) as http:
        async with streamable_http_client(target.url, http_client=http) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.server_info.name == "auditable-memory-for-alexa"
                tools = await client.list_tools()
                required = {"log_event", "derive_insights", "save_insight_candidates", "list_insights",
                            "get_insight_evidence", "confirm_insight", "reject_insight", "explain"}
                assert required <= {tool.name for tool in tools.tools}
                async def call(name, **args):
                    result = await client.call_tool(name, {"user_id": db.user, **args})
                    assert not result.is_error
                    structured = result.structured_content
                    texts = [block.text for block in result.content if block.type == "text"]
                    assert texts
                    payload = json.loads(texts[0])
                    if structured is not None:
                        assert isinstance(structured, dict) and structured == payload
                    # These tools declare no output schema and support JSON text fallback.
                    assert isinstance(payload, dict) and payload["success"] is True
                    return payload["data"]
                ids = set()
                for day in (17, 18, 19):
                    result = await call("log_event", domain="cooking", event_type="meal_prepared",
                                        subject="lentil soup", attributes={"adjustment": "reduced salt"},
                                        outcome="BETTER", source_utterance="Synthetic MCP cooking event",
                                        request_id=str(uuid4()), occurred_at=f"2026-10-{day}T12:00:00Z")
                    ids.add(result["event"]["id"])
                assert (await call("derive_insights"))["count"] == 1
                assert (await call("save_insight_candidates"))["created_count"] == 1
                insight = (await call("list_insights"))["insights"][0]
                insight_id = insight["insight_id"]
                assert insight["status"] == "PENDING_CONFIRMATION"
                evidence = await call("get_insight_evidence", insight_id=insight_id)
                assert {e["id"] for e in evidence["events"]} == ids
                confirmed = await call("confirm_insight", insight_id=insight_id)
                explanation = await call("explain", claim_id=confirmed["claim_id"])
                assert explanation["provenance_complete"] is True
                assert {e["event_id"] for e in explanation["evidence"]} == ids
                # A second pattern supplies the pending insight required for rejection.
                for day in (17, 18, 19):
                    await call("log_event", domain="cooking", event_type="meal_prepared",
                               subject="rice", attributes={"adjustment": "less salt"}, outcome="BETTER",
                               source_utterance="Synthetic rejection event", request_id=str(uuid4()),
                               occurred_at=f"2026-10-{day}T12:00:00Z")
                saved = await call("save_insight_candidates")
                rejected = await call("reject_insight", insight_id=saved["created"][0]["insight_id"])
                assert rejected["status"] == "REJECTED"
    # The production bridge also decodes the real server's response.
    result = await target.bridge.call_mcp_tool("list_insights", {"user_id": db.user})
    assert result["success"] and result["data"]["count"] == 2
    async with httpx2.AsyncClient() as http:
        assert (await http.post(target.url, json={})).status_code == 401
