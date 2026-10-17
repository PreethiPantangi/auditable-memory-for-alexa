"""CC-01 contextual operation tests: all external I/O mocked, no API calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from client.context_reference import (
    looks_like_contextual_operation,
    verify_active_context_claim,
)

KEY = "12345678-1234-1234-1234-1234567890ab"
CLAIM = {
    "memory_key": KEY, "claim_id": 31, "status": "ACTIVE",
    "category": "seat_preference", "value": "prefers aisle seats",
}
CTX = {"memory_key": KEY, "category": "seat_preference"}


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("message,expected", [
    ("Change that to window", True),
    ("Forget it", True),
    ("Why do you remember that?", True),
    ("Where did that come from?", True),
    ("Make this a window preference", True),
    ("What is my seat preference?", False),
    ("Forget my seat preference", False),
    ("I now prefer window seats", False),
    ("hello", False),
])
def test_candidate_gate(message, expected):
    assert looks_like_contextual_operation(message) is expected


def test_active_claim_selection_checks_key_category_and_status():
    assert verify_active_context_claim(CTX, [CLAIM]) is CLAIM
    assert verify_active_context_claim(CTX, [{**CLAIM, "status": "FORGOTTEN"}]) is None
    assert verify_active_context_claim(CTX, [{**CLAIM, "category": "diet"}]) is None
    assert verify_active_context_claim(CTX, [{**CLAIM, "memory_key": "other"}]) is None
    assert verify_active_context_claim(CTX, [CLAIM, CLAIM]) is None
    assert verify_active_context_claim(CTX, [{**CLAIM, "user_id": "foreign"}], "user-a") is None


@pytest.fixture
def ctx(orchestrator, monkeypatch):
    m = orchestrator
    m._cc01_unmocked_classifier = m.classify_context_operation
    methods = {
        "get_memory_context": CTX,
        "call_mcp_tool": {"success": True, "data": [CLAIM]},
        "clear_memory_context": None,
        "classify_context_operation": SimpleNamespace(
            status="MATCHED", operation="FORGET", replacement_value=None,
        ),
        "save_pending_correction": None,
        "generate_natural_response": "generated",
    }
    for key, value in methods.items():
        monkeypatch.setattr(m, key, AsyncMock(return_value=value))
    return m


def attempt(ctx, message="Forget that", user_id="user-a", conversation_id="thread-a"):
    return run(ctx.try_contextual_operation(user_id, conversation_id, message))


def test_no_context_stops_before_memory_or_llm(ctx):
    ctx.get_memory_context.return_value = None
    assert attempt(ctx) is None
    ctx.call_mcp_tool.assert_not_awaited()
    ctx.classify_context_operation.assert_not_awaited()


def test_explicit_operation_uses_existing_path(ctx):
    assert attempt(ctx, "Forget my seat preference") is None
    ctx.get_memory_context.assert_not_awaited()


@pytest.mark.parametrize("changed", [
    [{**CLAIM, "status": "SUPERSEDED"}],
    [{**CLAIM, "category": "diet"}],
    [{**CLAIM, "memory_key": "other"}],
    [CLAIM, CLAIM],
    [],
])
def test_stale_or_ambiguous_context_never_writes(ctx, changed):
    ctx.call_mcp_tool.return_value = {"success": True, "data": changed}
    response = attempt(ctx)
    assert "no longer active" in response["message"]
    ctx.classify_context_operation.assert_not_awaited()
    ctx.clear_memory_context.assert_awaited_once_with("user-a", "thread-a")
    ctx.call_mcp_tool.assert_awaited_once_with(
        tool_name="recall", args={"user_id": "user-a", "category": "seat_preference"},
    )


def test_failed_recall_is_fail_closed(ctx):
    ctx.call_mcp_tool.return_value = {"success": False, "error": {"code": "FAILED"}}
    assert "couldn't verify" in attempt(ctx)["message"]
    ctx.classify_context_operation.assert_not_awaited()
    ctx.clear_memory_context.assert_not_awaited()


@pytest.mark.parametrize("status", ["UNCLEAR", "NEW_REQUEST"])
def test_unmatched_operation_cannot_write(ctx, status):
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status=status, operation="NONE", replacement_value=None,
    )
    result = attempt(ctx)
    if status == "NEW_REQUEST":
        assert "exact memory" in result["message"]
    else:
        assert "Which memory" in result["message"]
    ctx.call_mcp_tool.assert_awaited_once()
    ctx.clear_memory_context.assert_not_awaited()


def test_contextual_forget_uses_verified_category_and_key(ctx):
    ctx.call_mcp_tool.side_effect = [
        {"success": True, "data": [CLAIM]},
        {"success": True, "data": {"forgotten": True}},
    ]
    answer = attempt(ctx)
    assert answer["message"] == "generated"
    assert answer["actions"][0]["intent"] == "forget"
    assert ctx.call_mcp_tool.await_args_list == [
        call(tool_name="recall", args={"user_id": "user-a", "category": "seat_preference"}),
        call(tool_name="forget", args={
            "user_id": "user-a", "category": "seat_preference", "memory_key": KEY,
        }),
    ]
    ctx.clear_memory_context.assert_awaited_once_with("user-a", "thread-a")


def test_contextual_correction_uses_verified_target_and_source(ctx):
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="MATCHED", operation="CORRECT_MEMORY", replacement_value="prefers window seats",
    )
    ctx.call_mcp_tool.side_effect = [
        {"success": True, "data": [CLAIM]},
        {"success": True, "data": {"claim_id": 32}},
    ]
    answer = attempt(ctx, "Change that to window")
    assert answer["actions"][0]["intent"] == "correct_memory"
    assert ctx.call_mcp_tool.await_args_list[1] == call(
        tool_name="correct_memory", args={
            "user_id": "user-a", "category": "seat_preference", "memory_key": KEY,
            "value": "prefers window seats", "source_utterance": "Change that to window",
        },
    )
    ctx.clear_memory_context.assert_awaited_once()


def test_incomplete_contextual_correction_creates_pending(ctx):
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="MATCHED", operation="CORRECT_MEMORY", replacement_value=None,
    )
    answer = attempt(ctx, "Change that")
    assert "complete updated" in answer["message"]
    assert answer["actions"][0]["result"]["error"]["code"] == "CLARIFICATION_REQUIRED"
    ctx.save_pending_correction.assert_awaited_once_with(
        conversation_id="thread-a", user_id="user-a", original_question="Change that",
        category="seat_preference", target_memory_key=KEY,
        clarification_question=answer["message"],
    )
    ctx.call_mcp_tool.assert_awaited_once()
    ctx.clear_memory_context.assert_not_awaited()


def test_contextual_explain_requires_claim_id_and_never_writes(ctx):
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="MATCHED", operation="EXPLAIN", replacement_value=None,
    )
    ctx.call_mcp_tool.side_effect = [
        {"success": True, "data": [CLAIM]},
        {"success": True, "data": {"claim_id": 31}},
    ]
    answer = attempt(ctx, "Why do you remember that?")
    assert answer["actions"][0]["intent"] == "explain"
    assert ctx.call_mcp_tool.await_args_list[1] == call(
        tool_name="explain", args={"user_id": "user-a", "claim_id": 31},
    )
    ctx.clear_memory_context.assert_not_awaited()


def test_failed_mutation_preserves_context(ctx):
    ctx.call_mcp_tool.side_effect = [
        {"success": True, "data": [CLAIM]},
        {"success": False, "error": {"code": "CONFLICT"}},
    ]
    result = attempt(ctx)
    assert result["actions"][0]["result"]["success"] is False
    ctx.clear_memory_context.assert_not_awaited()


def test_validator_rejects_unmatched_write_and_unexpected_replacement(ctx, monkeypatch):
    # Mock only the remote model's parse response; exercise local validation.
    parsed = SimpleNamespace(status="UNCLEAR", operation="FORGET", replacement_value=None)
    monkeypatch.setattr(ctx.client.responses, "parse", Mock(
        return_value=SimpleNamespace(output_parsed=parsed),
    ))
    with pytest.raises(ValueError, match="Unmatched context"):
        run(ctx._cc01_unmocked_classifier("Forget that", CLAIM))


def test_route_integrates_before_existing_read_recall(orchestrator, monkeypatch):
    m = orchestrator
    monkeypatch.setattr(m, "get_pending_clarification", AsyncMock(return_value=None))
    operation = {"message": "deleted", "actions": []}
    contextual = AsyncMock(return_value=operation)
    old_read = AsyncMock(return_value=None)
    monkeypatch.setattr(m, "try_contextual_operation", contextual)
    monkeypatch.setattr(m, "try_contextual_recall", old_read)
    assert run(m.handle_user_message("user-a", "Forget that", conversation_id="thread-a")) is operation
    contextual.assert_awaited_once()
    old_read.assert_not_awaited()


@pytest.mark.parametrize("category,old_value,new_value", [
    ("hiking", "likes trails with views", "prefers forest trails"),
    ("fitness", "walks 2 miles daily", "walks 3 miles daily"),
    ("residence", "lives in Seattle", "lives in Bellevue"),
    ("diet", "prefers mild food", "prefers spicy food"),
    ("work_arrangement", "works remotely", "works hybrid"),
])
def test_context_mutation_is_category_independent(ctx, category, old_value, new_value):
    stored = {**CLAIM, "category": category, "value": old_value}
    ctx.get_memory_context.return_value = {"memory_key": KEY, "category": category}
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="MATCHED", operation="CORRECT_MEMORY", replacement_value=new_value,
    )
    ctx.call_mcp_tool.side_effect = [
        {"success": True, "data": [stored]},
        {"success": True, "data": {}},
    ]
    attempt(ctx, "Change that")
    assert ctx.call_mcp_tool.await_args_list[1] == call(
        tool_name="correct_memory", args={
            "user_id": "user-a", "category": category, "memory_key": KEY,
            "value": new_value, "source_utterance": "Change that",
        },
    )


def test_user_scope_is_passed_to_both_context_and_mcp(ctx):
    attempt(ctx, "Forget that", user_id="user-b", conversation_id="thread-b")
    ctx.get_memory_context.assert_awaited_once_with("user-b", "thread-b")
    ctx.call_mcp_tool.assert_awaited_with(
        tool_name="forget", args={
            "user_id": "user-b", "category": "seat_preference", "memory_key": KEY,
        },
    )


def test_different_users_context_cannot_be_reused(ctx):
    ctx.get_memory_context.return_value = None
    assert attempt(ctx, user_id="other-user", conversation_id="stolen-id") is None
    ctx.call_mcp_tool.assert_not_awaited()
    ctx.classify_context_operation.assert_not_awaited()


def test_explicit_new_subject_never_redirects_referential_write(ctx):
    # When the old memory is a seat preference, "forget that hiking thing"
    # cannot be redirected to the seat preference OR guessed by a fallback.
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="NEW_REQUEST", operation="NONE", replacement_value=None,
    )
    response = attempt(ctx, "Forget that hiking thing")
    assert "exact memory" in response["message"]
    ctx.call_mcp_tool.assert_awaited_once()


def test_unrelated_provenance_question_can_fall_through(ctx):
    ctx.classify_context_operation.return_value = SimpleNamespace(
        status="NEW_REQUEST", operation="NONE", replacement_value=None,
    )
    assert attempt(ctx, "Where did that recipe come from?") is None
    ctx.call_mcp_tool.assert_awaited_once()


def test_reported_recall_then_change_routes_to_correct_memory(orchestrator, monkeypatch):
    """Regression for the user's 'Change that to window' live failure."""
    m = orchestrator
    monkeypatch.setattr(m, "get_pending_clarification", AsyncMock(return_value=None))
    monkeypatch.setattr(m, "get_memory_context", AsyncMock(return_value=CTX))
    monkeypatch.setattr(m, "call_mcp_tool", AsyncMock(side_effect=[
        {"success": True, "data": [CLAIM]},
        {"success": True, "data": {"claim_id": 32}},
    ]))
    monkeypatch.setattr(m, "classify_context_operation", AsyncMock(return_value=SimpleNamespace(
        status="MATCHED", operation="CORRECT_MEMORY",
        replacement_value="prefers window seats on flights",
    )))
    monkeypatch.setattr(m, "clear_memory_context", AsyncMock())
    monkeypatch.setattr(m, "generate_natural_response", AsyncMock(return_value="Preference updated."))
    old_read = AsyncMock(side_effect=AssertionError("must not route a write to read follow-up"))
    monkeypatch.setattr(m, "try_contextual_recall", old_read)
    result = run(m.handle_user_message("adh_correction_test", "Change that to window",
                                       conversation_id="a12dca78-d7a7-4064-b6e6-3e50ad6d57af"))
    assert result["actions"][0]["intent"] == "correct_memory"
    assert m.call_mcp_tool.await_args_list[-1].kwargs["tool_name"] == "correct_memory"
    old_read.assert_not_awaited()
