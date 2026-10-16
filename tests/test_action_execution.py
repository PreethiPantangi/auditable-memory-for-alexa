import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from sqlalchemy.exc import SQLAlchemyError

REQUEST_ID = "11111111-2222-3333-4444-555555555555"
CLAIMS = [
    {"memory_key": "a", "claim_id": 1, "status": "ACTIVE"},
    {"memory_key": "b", "claim_id": 2, "status": "FORGOTTEN"},
]


@pytest.fixture
def execution(orchestrator, monkeypatch):
    calls = Mock()
    result = {"success": True, "data": {"unchanged": True}}
    tool = AsyncMock(side_effect=[{"success": True, "data": CLAIMS}, result])
    resolver = AsyncMock(return_value=orchestrator.MemoryResolution(
        status="MATCHED", memory_key="a", claim_id=1,
    ))
    monkeypatch.setattr(orchestrator, "call_mcp_tool", tool)
    monkeypatch.setattr(orchestrator, "resolve_memory", resolver)
    calls.attach_mock(tool, "tool")
    calls.attach_mock(resolver, "resolve")
    return SimpleNamespace(module=orchestrator, tool=tool, resolver=resolver,
                           calls=calls, result=result)


def action(execution, intent, **overrides):
    values = {"intent": intent, "category": "food_preference", "value": "new value",
              "attributes": None}
    if intent == "log_event":
        values.update(domain="cooking", event_type="meal_prepared", subject=" soup ")
    values.update(overrides)
    return execution.module.Action(**values)


def run(execution, selected_action, request_id=REQUEST_ID, action_index=0):
    return asyncio.run(execution.module.execute_action(
        user_id="user", message="original message", action=selected_action,
        request_id=request_id, action_index=action_index,
    ))


def error(code, message):
    return {"success": False, "error": {"code": code, "message": message}}


@pytest.mark.parametrize("overrides", [
    {}, {"domain": "other"}, {"event_type": "other"}, {"subject": None},
])
def test_log_event_requires_request_id_before_other_validation(execution, overrides):
    assert run(execution, action(execution, "log_event", **overrides), request_id=None) == error(
        "REQUEST_ID_REQUIRED", "A request ID is required to log an event.",
    )
    assert execution.calls.mock_calls == []


@pytest.mark.parametrize("overrides", [
    {"domain": None}, {"domain": "other"}, {"event_type": None},
    {"event_type": "other"}, {"subject": None}, {"subject": ""}, {"subject": "  "},
])
def test_log_event_validation_precedes_uuid_parsing(execution, overrides):
    assert run(execution, action(execution, "log_event", **overrides), request_id="bad") == error(
        "INVALID_EVENT", "A supported cooking event and dish are required.",
    )
    assert execution.calls.mock_calls == []


@pytest.mark.parametrize("request_id", ["", "not-a-uuid"])
def test_log_event_invalid_request_id_propagates(execution, request_id):
    with pytest.raises(ValueError):
        run(execution, action(execution, "log_event"), request_id=request_id)
    assert execution.calls.mock_calls == []


@pytest.mark.parametrize("index,expected_id", [
    (0, "22578721-86ec-5768-969d-44b0f1a41f7f"),
    (3, "0204a6b2-39a7-547f-9870-0307089d978c"),
    (-1, "897a91ac-51ae-54b6-9091-29d0fd216baf"),
])
@pytest.mark.parametrize("attributes,expected_attributes", [
    (None, {}), ({"adjustment": None}, {}),
    ({"adjustment": "less_salt"}, {"adjustment": "less_salt"}),
])
def test_log_event_preserves_uuid_and_payload(execution, index, expected_id, attributes, expected_attributes):
    execution.tool.side_effect = None
    execution.tool.return_value = execution.result
    selected = action(execution, "log_event", attributes=attributes, outcome="BETTER",
                      occurred_at="2026-10-13T10:00:00Z")
    assert run(execution, selected, action_index=index) is execution.result
    assert execution.calls.mock_calls == [call.tool(tool_name="log_event", args={
        "user_id": "user", "domain": "cooking", "event_type": "meal_prepared",
        "subject": " soup ", "attributes": expected_attributes, "outcome": "BETTER",
        "source_utterance": "original message", "occurred_at": "2026-10-13T10:00:00Z",
        "request_id": expected_id,
    })]


def test_log_event_optional_payload_and_defaults(execution):
    execution.tool.side_effect = None
    execution.tool.return_value = execution.result
    result = asyncio.run(execution.module.execute_action(
        "user", "original message", action(execution, "log_event"), REQUEST_ID,
    ))
    assert result is execution.result
    args = execution.tool.await_args.kwargs["args"]
    assert args["outcome"] is None
    assert args["occurred_at"] is None
    assert args["request_id"] == "22578721-86ec-5768-969d-44b0f1a41f7f"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_correction_replacement_validation_precedes_category_access(execution, value):
    assert run(execution, action(execution, "correct_memory", value=value, category=None)) == error(
        "CLARIFICATION_REQUIRED", "What would you like to change this preference to?",
    )
    assert execution.calls.mock_calls == []


@pytest.mark.parametrize("intent", ["correct_memory", "forget", "explain"])
def test_failed_retrieval_returns_original_response(execution, intent):
    failed = error("UNAVAILABLE", "original failure")
    execution.tool.side_effect = [failed]
    assert run(execution, action(execution, intent)) is failed
    assert len(execution.calls.mock_calls) == 1


@pytest.mark.parametrize("intent,code,message", [
    ("correct_memory", "NO_ACTIVE_CLAIM", "I couldn't find an existing memory to correct. Would you like me to save this as a new memory?"),
    ("forget", "NO_ACTIVE_CLAIM", "No active memory found."),
    ("explain", "MEMORY_NOT_FOUND", "No matching memory exists."),
])
@pytest.mark.parametrize("claims", [[], None])
def test_empty_retrieval_preserves_branch_specific_error(execution, intent, code, message, claims):
    execution.tool.side_effect = [{"success": True, "data": claims}]
    assert run(execution, action(execution, intent)) == error(code, message)
    assert len(execution.calls.mock_calls) == 1


@pytest.mark.parametrize("intent", ["correct_memory", "forget", "explain"])
@pytest.mark.parametrize("reason", [None, "", "Which memory?"])
def test_clarification_precedes_resolution_status(execution, intent, reason):
    execution.resolver.return_value = execution.module.MemoryResolution(
        status="AMBIGUOUS", requires_clarification=True, clarification_reason=reason,
    )
    assert run(execution, action(execution, intent)) == error(
        "CLARIFICATION_REQUIRED", reason or "Please specify what you would like to change your preference to.",
    )
    assert [item[0] for item in execution.calls.mock_calls] == ["tool", "resolve"]


@pytest.mark.parametrize("intent,status,code,message", [
    ("correct_memory", "AMBIGUOUS", "AMBIGUOUS_MEMORY", "Multiple memories could match. Please specify which one to correct."),
    ("correct_memory", "NO_MATCH", "MEMORY_NOT_FOUND", "I couldn't identify which existing memory you want to correct."),
    ("forget", "AMBIGUOUS", "AMBIGUOUS_MEMORY", "Could not identify which memory to forget."),
    ("forget", "NO_MATCH", "MEMORY_NOT_FOUND", "Could not identify which memory to forget."),
    ("explain", "AMBIGUOUS", "AMBIGUOUS_MEMORY", "Could not uniquely identify the memory."),
    ("explain", "NO_MATCH", "MEMORY_NOT_FOUND", "Could not uniquely identify the memory."),
])
def test_unmatched_resolution_errors_remain_distinct(execution, intent, status, code, message):
    execution.resolver.return_value = execution.module.MemoryResolution(status=status)
    assert run(execution, action(execution, intent)) == error(code, message)
    assert [item[0] for item in execution.calls.mock_calls] == ["tool", "resolve"]


@pytest.mark.parametrize("intent,message", [
    ("correct_memory", "Memory resolution failed."), ("forget", "Resolved memory was not found."),
])
@pytest.mark.parametrize("key", [None, "unknown"])
def test_invalid_write_target_blocks_write(execution, intent, message, key):
    execution.resolver.return_value = execution.module.MemoryResolution(status="MATCHED", memory_key=key)
    assert run(execution, action(execution, intent)) == error("INVALID_MEMORY_KEY", message)
    assert [item[0] for item in execution.calls.mock_calls] == ["tool", "resolve"]


@pytest.mark.parametrize("intent", ["correct_memory", "forget"])
@pytest.mark.parametrize("key", ["a", "b"])
def test_write_payload_and_call_order_preserve_unfiltered_keys(execution, intent, key):
    execution.resolver.return_value = execution.module.MemoryResolution(status="MATCHED", memory_key=key)
    selected = action(execution, intent, value=" new value ")
    assert run(execution, selected) is execution.result
    args = {"user_id": "user", "category": "food_preference", "memory_key": key}
    if intent == "correct_memory":
        args.update(value=" new value ", source_utterance="original message")
    assert execution.calls.mock_calls == [
        call.tool(tool_name="recall", args={"user_id": "user", "category": "food_preference"}),
        call.resolve(user_message="original message", claims=CLAIMS, intent=selected.intent),
        call.tool(tool_name=intent, args=args),
    ]


@pytest.mark.parametrize("scope,source", [("current", "recall"), ("historical", "memory_history"), (None, "memory_history")])
def test_explanation_scope_preserves_claim_selection_and_tool_calls(execution, scope, source):
    claims = [
        {"memory_key": "a", "claim_id": 10, "status": "ACTIVE"},
        {"memory_key": "a", "claim_id": 11, "status": "SUPERSEDED"},
        {"memory_key": "other", "claim_id": 11, "status": "ACTIVE"},
    ]
    execution.tool.side_effect = [{"success": True, "data": claims}, execution.result]
    execution.resolver.return_value = execution.module.MemoryResolution(status="MATCHED", memory_key="a", claim_id=11)
    selected = action(execution, "explain", explain_scope=scope)
    assert run(execution, selected) is execution.result
    assert execution.calls.mock_calls == [
        call.tool(tool_name=source, args={"user_id": "user", "category": "food_preference"}),
        call.resolve(user_message="original message", claims=claims, intent=selected.intent),
        call.tool(tool_name="explain", args={"claim_id": 10 if scope == "current" else 11, "user_id": "user"}),
    ]


@pytest.mark.parametrize("scope", ["current", "historical"])
@pytest.mark.parametrize("count", [0, 2])
def test_explanation_requires_exactly_one_claim_version(execution, scope, count):
    claims = [dict(CLAIMS[0]) for _ in range(count)] + [CLAIMS[1]]
    execution.tool.side_effect = [{"success": True, "data": claims}]
    assert run(execution, action(execution, "explain", explain_scope=scope)) == error(
        "AMBIGUOUS_CLAIM_VERSION", "Could not uniquely identify the claim version.",
    )
    assert [item[0] for item in execution.calls.mock_calls] == ["tool", "resolve"]


@pytest.mark.parametrize("intent", ["correct_memory", "forget", "explain"])
@pytest.mark.parametrize("payload,key", [({}, "success"), ({"success": True}, "data")])
def test_missing_retrieval_fields_keep_key_errors(execution, intent, payload, key):
    execution.tool.side_effect = [payload]
    with pytest.raises(KeyError) as raised:
        run(execution, action(execution, intent))
    assert raised.value.args == (key,)
    assert len(execution.calls.mock_calls) == 1


@pytest.mark.parametrize("intent", ["correct_memory", "forget", "explain"])
def test_missing_category_still_raises_without_external_calls(execution, intent):
    with pytest.raises(AttributeError):
        run(execution, action(execution, intent, category=None))
    assert execution.calls.mock_calls == []


@pytest.mark.parametrize("intent", ["correct_memory", "forget", "explain"])
@pytest.mark.parametrize("stage", ["retrieval", "resolution", "operation"])
@pytest.mark.parametrize("exception", [ValueError, TimeoutError, SQLAlchemyError, RuntimeError])
def test_dispatch_preserves_exception_identity_and_call_boundary(execution, intent, stage, exception):
    failure = exception("unchanged")
    if stage == "retrieval":
        execution.tool.side_effect = failure
    elif stage == "resolution":
        execution.resolver.side_effect = failure
    else:
        execution.tool.side_effect = [{"success": True, "data": CLAIMS}, failure]
    with pytest.raises(exception) as raised:
        run(execution, action(execution, intent, explain_scope="current"))
    assert raised.value is failure
    assert [item[0] for item in execution.calls.mock_calls] == {
        "retrieval": ["tool"], "resolution": ["tool", "resolve"],
        "operation": ["tool", "resolve", "tool"],
    }[stage]


@pytest.mark.parametrize("exception", [ValueError, TimeoutError, SQLAlchemyError, RuntimeError])
def test_log_event_tool_exceptions_propagate(execution, exception):
    failure = exception("unchanged")
    execution.tool.side_effect = failure
    with pytest.raises(exception) as raised:
        run(execution, action(execution, "log_event"))
    assert raised.value is failure
    assert len(execution.calls.mock_calls) == 1


@pytest.mark.parametrize("intent", ["remember", "recall", "memory_history"])
def test_short_dispatch_branches_stay_compatible(execution, intent):
    execution.tool.side_effect = None
    execution.tool.return_value = execution.result
    selected = action(execution, intent)
    assert run(execution, selected) is execution.result
    args = {"user_id": "user", "category": "food_preference"}
    if intent == "remember":
        args.update(value="new value", source_utterance="original message")
    assert execution.calls.mock_calls == [call.tool(tool_name=intent, args=args)]


def test_unknown_intent_returns_original_error(execution):
    selected = SimpleNamespace(intent="unknown")
    assert run(execution, selected) == error("UNKNOWN_INTENT", "Unknown intent: unknown")
    assert execution.calls.mock_calls == []
