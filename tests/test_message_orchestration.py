import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture
def flow(orchestrator, monkeypatch):
    calls = Mock()
    defaults = {
        "get_pending_clarification": None,
        "handle_pending_correction": None,
        "try_contextual_recall": None,
        "call_mcp_tool": {"success": True, "data": []},
        "resolve_pending_reply": SimpleNamespace(status="NEW_REQUEST"),
        "clear_pending_clarification": None,
        "save_memory_context": None,
        "save_pending_correction": None,
        "save_pending_clarification": None,
        "resolve_correction_target": SimpleNamespace(status="MATCHED", memory_key="a"),
        "fallback_food_memory_recall": {"success": True, "data": []},
        "generate_natural_response": "answer",
        "execute_action": {"success": True, "data": {}},
    }
    for name, value in defaults.items():
        mock = AsyncMock(return_value=value)
        monkeypatch.setattr(orchestrator, name, mock)
        calls.attach_mock(mock, name)
    parse = Mock(return_value=SimpleNamespace(output_parsed=orchestrator.Actions(actions=[])))
    monkeypatch.setattr(orchestrator.client.responses, "parse", parse)
    calls.attach_mock(parse, "parse")
    monkeypatch.setattr(orchestrator, "logger", Mock())
    return SimpleNamespace(module=orchestrator, calls=calls)


def run(flow, message="hello", conversation_id="conversation"):
    return asyncio.run(flow.module.handle_user_message(
        user_id="user", message=message, request_id="request",
        conversation_id=conversation_id,
    ))


def pending_recall():
    return {
        "operation": "recall", "category": "food_preference",
        "candidate_memory_keys": ["a", "b"],
        "original_question": "Which recipe?", "clarification_question": "Which one?",
    }


def claim(key="a", status="ACTIVE"):
    return {"memory_key": key, "status": status}


def set_actions(flow, **overrides):
    action = flow.module.Action(
        intent="correct_memory", category="food_preference", attributes=None,
        **overrides,
    )
    flow.module.client.responses.parse.return_value.output_parsed = flow.module.Actions(
        actions=[action]
    )
    return action


def names(flow):
    return [item[0] for item in flow.calls.mock_calls]


@pytest.mark.parametrize("success", [False, None])
def test_pending_recall_failure_returns_without_other_calls(flow, success):
    flow.module.get_pending_clarification.return_value = pending_recall()
    flow.module.call_mcp_tool.return_value = {"success": success}
    assert run(flow) == {
        "message": "I couldn't retrieve the saved memories right now.", "actions": [],
    }
    assert names(flow) == ["get_pending_clarification", "call_mcp_tool"]
    flow.module.call_mcp_tool.assert_awaited_once_with(
        tool_name="recall", args={"user_id": "user", "category": "food_preference"},
    )


@pytest.mark.parametrize("selected_count", [0, 1, 2])
def test_pending_selected_filters_candidates_and_preserves_state_order(flow, selected_count):
    pending = pending_recall()
    flow.module.get_pending_clarification.return_value = pending
    selected = [claim() for _ in range(selected_count)]
    candidates = selected + [claim("b")]
    flow.module.call_mcp_tool.return_value = {
        "success": True, "data": candidates + [claim("other"), claim("a", "FORGOTTEN")],
    }
    flow.module.resolve_pending_reply.return_value = SimpleNamespace(status="SELECTED", memory_key="a")
    result = run(flow, "the first")
    flow.module.resolve_pending_reply.assert_awaited_once_with(
        latest_message="the first", pending=pending, candidate_claims=candidates,
    )
    if selected_count != 1:
        assert result == {"message": "That memory has changed. Please ask again.", "actions": []}
        assert names(flow) == [
            "get_pending_clarification", "call_mcp_tool", "resolve_pending_reply",
            "clear_pending_clarification",
        ]
    else:
        actions = [{"intent": "recall", "category": "food_preference",
                    "result": {"success": True, "data": selected}}]
        assert result == {"message": "answer", "actions": actions}
        assert flow.calls.mock_calls[-3:] == [
            call.save_memory_context(user_id="user", conversation_id="conversation", claim=selected[0]),
            call.clear_pending_clarification(conversation_id="conversation", user_id="user"),
            call.generate_natural_response(user_message="Which recipe? User clarified: the first", results=actions),
        ]


def test_pending_recall_stays_ambiguous_without_writes(flow):
    flow.module.get_pending_clarification.return_value = pending_recall()
    candidates = [claim(), claim("b")]
    flow.module.call_mcp_tool.return_value = {"success": True, "data": candidates}
    flow.module.resolve_pending_reply.return_value = SimpleNamespace(status="STILL_AMBIGUOUS")
    assert run(flow) == {
        "message": "Which one?", "actions": [{
            "intent": "recall", "category": "food_preference", "result": {
                "success": False, "error": {"code": "AMBIGUOUS_MEMORY", "message": "Which one?"},
                "data": candidates,
            },
        }],
    }
    assert names(flow) == ["get_pending_clarification", "call_mcp_tool", "resolve_pending_reply"]


def test_pending_new_request_clears_before_context_and_intent_extraction(flow):
    flow.module.get_pending_clarification.return_value = pending_recall()
    assert run(flow) == {"message": "answer", "actions": []}
    assert names(flow) == [
        "get_pending_clarification", "call_mcp_tool", "resolve_pending_reply",
        "clear_pending_clarification", "try_contextual_recall", "parse",
        "generate_natural_response",
    ]


@pytest.mark.parametrize("response", [None, {"message": "pending", "actions": []}])
def test_pending_correction_keeps_its_precedence(flow, response):
    flow.module.get_pending_clarification.return_value = {"operation": "correct_memory"}
    flow.module.handle_pending_correction.return_value = response
    result = run(flow)
    if response is None:
        assert result == {"message": "answer", "actions": []}
        assert names(flow) == ["get_pending_clarification", "handle_pending_correction",
                               "try_contextual_recall", "parse", "generate_natural_response"]
    else:
        assert result is response
        assert names(flow) == ["get_pending_clarification", "handle_pending_correction"]


def test_context_response_precedes_intent_extraction(flow):
    response = {"message": "context", "actions": []}
    flow.module.try_contextual_recall.return_value = response
    assert run(flow) is response
    assert names(flow) == ["get_pending_clarification", "try_contextual_recall"]


@pytest.mark.parametrize("value", [None, "", "  "])
def test_incomplete_correction_saves_target_without_executing_action(flow, value):
    set_actions(flow, value=value)
    result = run(flow)
    question = "Would you like me to forget that preference or replace it? If replacing it, tell me the new preference."
    assert result == {"message": question, "actions": [{
        "intent": "correct_memory", "category": "food_preference", "result": {
            "success": False, "error": {"code": "CLARIFICATION_REQUIRED", "message": question},
        },
    }]}
    assert names(flow) == ["get_pending_clarification", "try_contextual_recall", "parse",
                           "call_mcp_tool", "resolve_correction_target", "save_pending_correction"]
    flow.module.save_pending_correction.assert_awaited_once_with(
        conversation_id="conversation", user_id="user", original_question="hello",
        category="food_preference", target_memory_key="a", clarification_question=question,
    )


@pytest.mark.parametrize("case,expected", [
    ("multiple", "Please handle the correction separately from your other requests."),
    ("category", "Which preference would you like to change?"),
    ("conversation", "I need an active conversation to continue this correction."),
    ("recall", "I couldn't retrieve the existing memory."),
    ("NOT_FOUND", "I couldn't identify an existing memory to correct. Which one do you mean?"),
    ("AMBIGUOUS", "Multiple memories might match. Please identify the specific one to change."),
])
def test_incomplete_correction_early_returns(flow, case, expected):
    set_actions(flow)
    actions = flow.module.client.responses.parse.return_value.output_parsed.actions
    conversation = "conversation"
    if case == "multiple":
        actions.append(actions[0])
        actions[0].category = None
    elif case == "category":
        actions[0].category = None
    elif case == "conversation":
        conversation = None
    elif case == "recall":
        flow.module.call_mcp_tool.return_value = {"success": False}
    else:
        flow.module.resolve_correction_target.return_value = SimpleNamespace(status=case)
    assert run(flow, conversation_id=conversation) == {"message": expected, "actions": []}
    flow.module.save_pending_correction.assert_not_awaited()
    flow.module.execute_action.assert_not_awaited()
    if case in {"multiple", "category", "conversation"}:
        flow.module.call_mcp_tool.assert_not_awaited()


@pytest.mark.parametrize("message,recall", [
    ("", False), ("hello", False), ("what", False), ("  WHAT recipe  ", True),
    ("which recipe", True), ("who cooked", True), ("where is it", True),
    ("when did I cook", True), ("how much", True), ("why that dish", True),
    ("do you remember", True), ("can you recall", True), ("tell me", True),
    ("remind me", True), ("recipe?  ", True),
])
def test_no_actions_preserves_question_detection_and_prints(flow, capsys, message, recall):
    result = run(flow, message=message, conversation_id=None)
    actions = ([{"intent": "recall", "category": "food_preference",
                 "result": {"success": True, "data": []}}] if recall else [])
    assert result == {"message": "answer", "actions": actions}
    assert names(flow) == (["parse", "fallback_food_memory_recall", "generate_natural_response"]
                           if recall else ["parse", "generate_natural_response"])
    assert capsys.readouterr().out == f"USER MESSAGE: {message}\nEXTRACTED ACTIONS: []\nNO ACTIONS EXTRACTED\n"


@pytest.mark.parametrize("count,success", [(0, True), (1, True), (2, True), (1, 1), (1, False)])
def test_fallback_context_only_saved_for_one_claim_and_literal_success(flow, count, success):
    claims = [claim() for _ in range(count)]
    flow.module.fallback_food_memory_recall.return_value = {"success": success, "data": claims}
    result = run(flow, message="what recipe")
    assert result["actions"][0]["result"] == {"success": success, "data": claims}
    if count == 1 and success is True:
        assert names(flow)[-2:] == ["save_memory_context", "generate_natural_response"]
        flow.module.save_memory_context.assert_awaited_once_with(
            user_id="user", conversation_id="conversation", claim=claims[0],
        )
    else:
        flow.module.save_memory_context.assert_not_awaited()


@pytest.mark.parametrize("count,conversation", [(1, "conversation"), (2, "conversation"), (2, None)])
def test_fallback_ambiguity_saves_only_with_enough_candidates_and_conversation(flow, count, conversation):
    claims = [claim(str(i)) for i in range(count)]
    result = {"success": False, "error": {"code": "AMBIGUOUS_MEMORY", "message": "Which?"}, "data": claims}
    flow.module.fallback_food_memory_recall.return_value = result
    assert run(flow, message="what recipe", conversation_id=conversation)["actions"][0]["result"] is result
    if count >= 2 and conversation is not None:
        flow.module.save_pending_clarification.assert_awaited_once_with(
            conversation_id=conversation, user_id="user", original_question="what recipe",
            category="food_preference", candidate_memory_keys=["0", "1"], clarification_question="Which?",
        )
        assert names(flow)[-2:] == ["save_pending_clarification", "generate_natural_response"]
    else:
        flow.module.save_pending_clarification.assert_not_awaited()


@pytest.mark.parametrize("conflicts", [[], [
    {"attribute": "salt", "subject": "soup", "conflicting_values": ["more", "less"]},
    {"attribute": "unused", "subject": "unused", "conflicting_values": []},
]])
def test_fallback_conflict_uses_first_supplied_conflict(flow, conflicts):
    result = {"success": False, "error": {"code": "CONFLICTING_MEMORIES"}, "conflicts": conflicts}
    flow.module.fallback_food_memory_recall.return_value = result
    response = run(flow, message="what recipe")
    assert response["actions"] == [{"intent": "recall", "category": "food_preference", "result": result}]
    if conflicts:
        assert response["message"] == "I found conflicting saved information about salt for soup: more versus less. Which value should I use?"
        flow.module.generate_natural_response.assert_not_awaited()
    else:
        assert response["message"] == "answer"


@pytest.mark.parametrize("error_type", [ValueError, TimeoutError, SQLAlchemyError, RuntimeError])
@pytest.mark.parametrize("stage", ["fallback_food_memory_recall", "save_memory_context", "generate_natural_response"])
def test_fallback_exception_boundary_is_preserved(flow, error_type, stage):
    flow.module.fallback_food_memory_recall.return_value = {"success": True, "data": [claim()]}
    error = error_type("failed")
    getattr(flow.module, stage).side_effect = error
    if error_type is RuntimeError:
        with pytest.raises(RuntimeError) as raised:
            run(flow, message="what recipe")
        assert raised.value is error
        flow.module.logger.exception.assert_not_called()
    else:
        assert run(flow, message="what recipe") == {
            "message": "I couldn't retrieve your memories right now.", "actions": [],
        }
        flow.module.logger.exception.assert_called_once_with("Fallback memory recall failed")


@pytest.mark.parametrize("stage,message", [
    ("resolve_pending_reply", "hello"),
    ("resolve_correction_target", "hello"),
    ("generate_natural_response", "hello"),
])
def test_errors_outside_fallback_propagate(flow, stage, message):
    if stage == "resolve_pending_reply":
        flow.module.get_pending_clarification.return_value = pending_recall()
    elif stage == "resolve_correction_target":
        set_actions(flow)
    error = ValueError("unchanged")
    getattr(flow.module, stage).side_effect = error
    with pytest.raises(ValueError) as raised:
        run(flow, message=message)
    assert raised.value is error


def test_missing_intent_result_keeps_exception(flow):
    flow.module.client.responses.parse.return_value.output_parsed = None
    with pytest.raises(ValueError, match="^Intent extraction returned no result\\.$"):
        run(flow)


def test_normal_actions_keep_execution_order_and_indexes(flow):
    actions = [
        flow.module.Action(intent="remember", category="food_preference", value="a", attributes=None),
        flow.module.Action(intent="log_event", subject="soup", attributes=None),
        flow.module.Action(intent="forget", attributes=None),
    ]
    flow.module.client.responses.parse.return_value.output_parsed = flow.module.Actions(actions=actions)
    result = run(flow)
    assert flow.module.execute_action.await_args_list == [
        call(user_id="user", message="hello", action=actions[0], request_id="request", action_index=0),
        call(user_id="user", message="hello", action=actions[1], request_id="request", action_index=1),
    ]
    assert [item["intent"] for item in result["actions"]] == ["remember", "log_event", "forget"]
    assert result["actions"][2] == {
        "intent": "forget", "category": None, "result": {"success": False, "error": {
            "code": "CLARIFICATION_REQUIRED",
            "message": "Which memory are you referring to? Please mention the preference or fact you want me to explain or modify.",
        }},
    }
