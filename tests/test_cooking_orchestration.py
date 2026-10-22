"""Deterministic extraction-response routing; does not measure live model accuracy."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid5

import pytest

from models.action import Action
from models.orchestration import Actions
from validators.event_validator import EventInput


@pytest.mark.parametrize("message,adjustment,outcome", [
    ("I made lentil soup with less salt and it tasted better.", "less salt", "BETTER"),
    ("I reduced the salt in my lentil soup and it tasted better.", "reduced salt", "BETTER"),
    ("I tried less salt in my lentil soup, but it tasted worse.", "less salt", "WORSE"),
])
def test_cooking_extraction_response_routes_without_promotion(orchestrator, monkeypatch, message, adjustment, outcome):
    action = Action(intent="log_event", domain="cooking", event_type="meal_prepared",
                    subject="lentil soup", attributes={"adjustment": adjustment}, outcome=outcome)
    parse = Mock(return_value=SimpleNamespace(output_parsed=Actions(actions=[action])))
    monkeypatch.setattr(orchestrator.client.responses, "parse", parse)
    tool = AsyncMock(return_value={"success": True, "data": {"created": True}})
    monkeypatch.setattr(orchestrator, "call_mcp_tool", tool)
    monkeypatch.setattr(orchestrator, "generate_natural_response", AsyncMock(return_value="Recorded."))
    request_id = "11111111-2222-3333-4444-555555555555"
    result = asyncio.run(orchestrator.handle_user_message("synthetic-user", message, request_id=request_id))
    parse.assert_called_once()
    assert parse.call_args.kwargs["input"][-1]["content"] == message
    tool.assert_awaited_once_with(tool_name="log_event", args={
        "user_id": "synthetic-user", "domain": "cooking", "event_type": "meal_prepared",
        "subject": "lentil soup", "attributes": {"adjustment": adjustment}, "outcome": outcome,
        "source_utterance": message, "occurred_at": None,
        "request_id": str(uuid5(UUID(request_id), "log_event:0")),
    })
    validated = EventInput(**tool.call_args.kwargs["args"])
    assert validated.attributes["adjustment"] == "less_salt"
    assert validated.occurred_at is None and validated.outcome == outcome
    assert result["actions"][0]["intent"] == "log_event"
