import ast
import asyncio
import hashlib
import importlib
import inspect
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "tests/fixtures/server_baseline.json").read_text(encoding="utf-8"))
EVENT_ARGS = {
    "user_id": "allowed", "domain": "cooking", "event_type": "meal_prepared",
    "subject": "soup", "attributes": {"adjustment": "less_salt"},
    "source_utterance": "I used less salt", "request_id": "11111111-2222-3333-4444-555555555555",
    "outcome": "BETTER", "occurred_at": "2026-10-13T10:00:00Z",
}
ARGUMENTS = {
    "server_status": {},
    "recall": {"user_id": "allowed", "category": "food_preference"},
    "recall_all": {"user_id": "allowed"},
    "remember": {"user_id": "allowed", "category": "food_preference", "value": "soup", "source_utterance": "source"},
    "explain": {"claim_id": 1, "user_id": "allowed"},
    "correct_memory": {"user_id": "allowed", "category": "food_preference", "value": "new", "source_utterance": "source", "memory_key": "key"},
    "forget": {"user_id": "allowed", "category": "food_preference", "memory_key": "key"},
    "memory_history": {"user_id": "allowed", "category": "food_preference"},
    "log_event": EVENT_ARGS,
    "list_events": {"user_id": "allowed", "domain": "cooking"},
    "derive_insights": {"user_id": "allowed"},
    "save_insight_candidates": {"user_id": "allowed"},
    "confirm_insight": {"user_id": "allowed", "insight_id": 1},
    "reject_insight": {"user_id": "allowed", "insight_id": 1},
    "list_insights": {"user_id": "allowed"},
    "get_insight_evidence": {"user_id": "allowed", "insight_id": 1},
}
DB_TOOLS = [name for name in ARGUMENTS if name not in {
    "save_insight_candidates", "confirm_insight", "reject_insight",
}]
ERRORS = {
    "server_status": ("DATABASE_CONNECTION_FAILED", "Database connection failed."),
    "explain": ("EXPLAIN_FAILED", "Unable to retrieve memory explanation."),
    "log_event": ("EVENT_SAVE_FAILED", "Unable to save event."),
    "list_events": ("EVENT_RETRIEVAL_FAILED", "Unable to retrieve events."),
    "derive_insights": ("INSIGHT_DERIVATION_FAILED", "Unable to derive insights."),
    "list_insights": ("INSIGHT_LIST_FAILED", "Unable to retrieve insights."),
    "get_insight_evidence": ("INSIGHT_EVIDENCE_FAILED", "Unable to retrieve insight evidence."),
}


@pytest.fixture(scope="module")
def server_module():
    database = ModuleType("database")
    database.SessionLocal = None
    with (
        patch.dict(sys.modules, {"database": database}),
        patch.dict(os.environ, {"ALLOWED_DEMO_USERS": "allowed"}),
        patch("dotenv.load_dotenv"),
    ):
        yield importlib.import_module("server")


def rows(*records):
    result = MagicMock()
    mapping = result.mappings.return_value
    mapping.all.return_value = list(records)
    mapping.__iter__.return_value = iter(records)
    mapping.one.return_value = records[0] if records else None
    mapping.one_or_none.return_value = records[0] if records else None
    return result


@pytest.fixture
def db(server_module, monkeypatch):
    session = MagicMock()
    session.execute = AsyncMock(return_value=rows({"id": 1, "source_type": "EXPLICIT"}))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__.return_value = session
    factory = Mock(return_value=session)
    auth = Mock(return_value=True)
    logger = Mock()
    trace = Mock()
    for name, mock in {
        "auth": auth, "factory": factory, "enter": session.__aenter__,
        "execute": session.execute, "commit": session.commit, "rollback": session.rollback,
        "exit": session.__aexit__, "info": logger.info, "exception": logger.exception,
    }.items():
        trace.attach_mock(mock, name)
    monkeypatch.setattr(server_module, "SessionLocal", factory)
    monkeypatch.setattr(server_module, "is_allowed_demo_user", auth)
    monkeypatch.setattr(server_module, "logger", logger)
    for name in ("save_candidates_service", "confirm_insight_service", "reject_insight_service"):
        mock = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(server_module, name, mock)
        trace.attach_mock(mock, name)
    return SimpleNamespace(server=server_module, session=session, factory=factory,
                           auth=auth, logger=logger, trace=trace)


def run(db, name, **overrides):
    return asyncio.run(getattr(db.server, name)(**{**ARGUMENTS[name], **overrides}))


def error(code, message):
    return {"success": False, "error": {"code": code, "message": message}}


def trace_names(db):
    return [item[0] for item in db.trace.mock_calls if "." not in item[0]]


def operation_module(server, name):
    if name in {"recall", "recall_all", "remember", "explain", "correct_memory", "forget", "memory_history"}:
        return getattr(server, "memory_service", server)
    if name in {"log_event", "list_events", "event_payload_hash"}:
        return getattr(server, "events_service", server)
    if name in {"derive_insights", "list_insights", "get_insight_evidence"}:
        return getattr(server, "insight_queries", server)
    return server


def test_registered_tool_contracts_and_order(server_module):
    tools = asyncio.run(server_module.mcp.list_tools())
    assert [tool.model_dump(mode="json") for tool in tools] == BASELINE["tools"]


@pytest.mark.parametrize("name", BASELINE["signatures"])
def test_existing_public_signatures(server_module, name):
    assert str(inspect.signature(getattr(server_module, name))) == BASELINE["signatures"][name]


@pytest.mark.parametrize("name", BASELINE["sql_sha256"])
def test_sql_literals_are_unchanged(server_module, name):
    source = inspect.getsource(getattr(operation_module(server_module, name), name))
    tree = ast.parse(source)
    actual = [hashlib.sha256(node.value.encode()).hexdigest() for node in ast.walk(tree)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)
              and "\n" in node.value and any(token in node.value for token in ("SELECT", "INSERT", "UPDATE"))]
    assert actual == BASELINE["sql_sha256"][name]


@pytest.mark.parametrize("name", [name for name in ARGUMENTS if name != "server_status"])
def test_authorization_precedes_validation_and_all_operations(db, name):
    db.auth.return_value = False
    overrides = {"user_id": "forbidden"}
    if name == "explain":
        overrides["claim_id"] = 0
    elif name in {"list_events", "derive_insights", "log_event"}:
        overrides["domain"] = "unsupported"
    assert run(db, name, **overrides) == error("DEMO_USER_NOT_ALLOWED", "Demo user not allowed.")
    assert trace_names(db) == ["auth"]


@pytest.mark.parametrize("name", DB_TOOLS)
def test_database_error_policy(db, name):
    failure = SQLAlchemyError("unchanged")
    db.session.execute.side_effect = failure
    if name in ERRORS:
        assert run(db, name) == error(*ERRORS[name])
    else:
        with pytest.raises(SQLAlchemyError) as raised:
            run(db, name)
        assert raised.value is failure
    db.session.commit.assert_not_awaited()
    if name == "server_status":
        db.session.rollback.assert_not_awaited()
    else:
        db.session.rollback.assert_awaited_once()
        sequence = trace_names(db)
        assert sequence.index("execute") < sequence.index("rollback") < sequence.index("exit")
    if name in ERRORS and name != "server_status":
        db.logger.exception.assert_called_once()
        assert trace_names(db).index("rollback") < trace_names(db).index("exception")


@pytest.mark.parametrize("name", DB_TOOLS)
def test_non_database_errors_propagate_without_rollback(db, name):
    failure = ValueError("unchanged")
    db.session.execute.side_effect = failure
    with pytest.raises(ValueError) as raised:
        run(db, name)
    assert raised.value is failure
    db.session.rollback.assert_not_awaited()
    db.session.commit.assert_not_awaited()


@pytest.mark.parametrize("name", DB_TOOLS)
def test_session_entry_remains_outside_operation_catch(db, name):
    failure = SQLAlchemyError("entry failed")
    db.session.__aenter__.side_effect = failure
    if name == "server_status":
        assert run(db, name) == error(*ERRORS[name])
    else:
        with pytest.raises(SQLAlchemyError) as raised:
            run(db, name)
        assert raised.value is failure
    db.session.execute.assert_not_awaited()
    db.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("name", ["recall", "memory_history"])
@pytest.mark.parametrize("key", [None, "", "key"])
def test_memory_queries_preserve_filter_and_parameters(db, name, key):
    records = [{"claim_id": 2}, {"claim_id": 1}]
    db.session.execute.return_value = rows(*records)
    assert run(db, name, memory_key=key) == {"success": True, "data": records}
    query, params = db.session.execute.await_args.args
    expected = {"user_id": "allowed", "category": "food_preference"}
    if name == "recall" or key is not None:
        expected["memory_key"] = key
    assert params == expected
    assert ("AND memory_key = :memory_key" in str(query)) is (key is not None)
    assert str(query).endswith(" ORDER BY created_at DESC")
    db.session.commit.assert_not_awaited()


def test_remember_preserves_uuid_generation_and_commit_order(db, monkeypatch):
    generated = Mock(return_value="generated-key")
    monkeypatch.setattr(db.server.uuid, "uuid4", generated)
    db.trace.attach_mock(generated, "uuid")
    record = {"claim_id": 1, "value": "soup"}
    db.session.execute.return_value = rows(record)
    assert run(db, "remember") == {"success": True, "data": record}
    assert trace_names(db) == ["auth", "factory", "enter", "uuid", "execute", "commit", "exit"]
    assert db.session.execute.await_args.args[1] == {
        "user_id": "allowed", "category": "food_preference", "value": "soup",
        "source_type": "EXPLICIT", "source_utterance": "source", "memory_key": "generated-key", "status": "ACTIVE",
    }


@pytest.mark.parametrize("fail_at", [None, 1, 2, 3, 4, "commit"])
def test_correction_preserves_transaction_and_link_order(db, fail_at):
    replacement = {"id": 20, "value": "new"}
    results = [rows({"id": 10, "category": "food_preference"}), rows(), rows(replacement), rows()]
    failure = SQLAlchemyError("failed")
    if isinstance(fail_at, int):
        results[fail_at - 1] = failure
    elif fail_at == "commit":
        db.session.commit.side_effect = failure
    db.session.execute.side_effect = results
    if fail_at is None:
        assert run(db, "correct_memory") == {"success": True, "data": {
            "memory_key": "key", "claim_id": 20, "new_claim_id": 20,
            "superseded_claim_id": 10, "new_claim": replacement,
        }}
        calls = db.session.execute.await_args_list
        assert "FOR UPDATE" in str(calls[0].args[0])
        assert "SET status = 'SUPERSEDED'" in str(calls[1].args[0])
        assert calls[1].args[1] == {"old_claim_id": 10}
        assert calls[2].args[1]["memory_key"] == "key"
        assert calls[3].args[1] == {"new_id": 20, "old_id": 10}
        assert trace_names(db) == ["auth", "factory", "enter", "execute", "execute", "execute", "execute", "commit", "exit"]
    else:
        with pytest.raises(SQLAlchemyError) as raised:
            run(db, "correct_memory")
        assert raised.value is failure
        db.session.rollback.assert_awaited_once()
        assert db.session.execute.await_count == (4 if fail_at == "commit" else fail_at)


@pytest.mark.parametrize("name,message", [
    ("correct_memory", "No active claim found for this memory."),
    ("forget", "No active claim exists for this category."),
])
def test_missing_active_claim_returns_without_commit(db, name, message):
    db.session.execute.return_value = rows()
    assert run(db, name) == error("NO_ACTIVE_CLAIM", message)
    assert trace_names(db) == ["auth", "factory", "enter", "execute", "exit"]


def test_forget_returns_updated_claim_after_commit(db):
    record = {"claim_id": 10, "status": "FORGOTTEN"}
    db.session.execute.return_value = rows(record)
    assert run(db, "forget") == {"success": True, "data": record}
    assert db.session.execute.await_args.args[1] == {"user_id": "allowed", "category": "food_preference", "memory_key": "key"}
    assert trace_names(db) == ["auth", "factory", "enter", "execute", "commit", "exit"]


@pytest.mark.parametrize("claim_id", [0, -1, 2_147_483_648])
def test_explain_invalid_claim_id_before_database(db, claim_id):
    assert run(db, "explain", claim_id=claim_id) == error("INVALID_CLAIM_ID", "Claim ID must be a positive 32-bit integer.")
    assert trace_names(db) == ["auth"]


@pytest.mark.parametrize("case", ["missing", "explicit", "missing_insight", "empty_evidence", "evidence"])
def test_explanation_preserves_provenance_shapes_and_query_order(db, case):
    claim = {"claim_id": 1, "source_type": "EXPLICIT" if case == "explicit" else "INFERRED_CONFIRMED"}
    insight = {"id": 5}
    evidence = [{"event_id": 9}] if case == "evidence" else []
    db.session.execute.side_effect = [rows() if case == "missing" else rows(claim),
                                      rows() if case == "missing_insight" else rows(insight), rows(*evidence)]
    result = run(db, "explain")
    if case == "missing":
        assert result == error("CLAIM_NOT_FOUND", "Claim not found.")
    elif case == "explicit":
        assert result == {"success": True, "data": claim}
    elif case == "missing_insight":
        assert result == {"success": True, "data": {**claim, "insight": None, "evidence": [], "provenance_complete": False}}
    else:
        assert result == {"success": True, "data": {**claim, "insight": insight, "evidence": evidence,
                                                   "evidence_count": len(evidence), "provenance_complete": bool(evidence)}}
    params = [item.args[1] for item in db.session.execute.await_args_list]
    assert params == ([{"claim_id": 1, "user_id": "allowed"}] * (1 if case in {"missing", "explicit"} else 2)
                      + ([{"insight_id": 5, "user_id": "allowed"}] if case in {"empty_evidence", "evidence"} else []))
    db.session.commit.assert_not_awaited()


@pytest.mark.parametrize("overrides", [
    {"domain": "other"}, {"event_type": "other"}, {"subject": "  "},
    {"attributes": {"adjustment": 1}}, {"request_id": "invalid"}, {"occurred_at": "invalid"},
])
def test_event_validation_before_database(db, overrides):
    assert run(db, "log_event", **overrides) == error("INVALID_EVENT", "Invalid event data.")
    assert trace_names(db) == ["auth"]


def test_event_insert_payload_and_commit(db):
    record = {"id": 9}
    db.session.execute.return_value = rows(record)
    assert run(db, "log_event") == {"success": True, "data": {"event": record, "created": True, "duplicate": False}}
    params = db.session.execute.await_args.args[1]
    assert params == {
        "user_id": "allowed", "domain": "cooking", "event_type": "meal_prepared", "subject": "soup",
        "attributes": '{"adjustment": "less_salt"}', "outcome": "BETTER", "source_utterance": "I used less salt",
        "occurred_at": datetime(2026, 10, 13, 10, tzinfo=UTC), "request_id": EVENT_ARGS["request_id"],
        "request_hash": db.server.event_payload_hash(db.server.EventInput(**EVENT_ARGS)),
    }
    assert trace_names(db) == ["auth", "info", "factory", "enter", "execute", "commit", "exit"]
    db.logger.info.assert_called_once_with("Validated event adjustment: %s", "less_salt")


def test_event_default_time_is_generated_inside_database_operation(db, monkeypatch):
    fixed = datetime(2026, 10, 14, 10, tzinfo=UTC)
    now = Mock(return_value=fixed)
    monkeypatch.setattr(operation_module(db.server, "log_event"), "datetime", SimpleNamespace(now=now))
    db.trace.attach_mock(now, "now")
    result = run(db, "log_event", occurred_at=None)
    assert result["success"] is True
    assert db.session.execute.await_args.args[1]["occurred_at"] is fixed
    assert trace_names(db) == ["auth", "info", "factory", "enter", "now", "execute", "commit", "exit"]
    now.assert_called_once_with(UTC)


@pytest.mark.parametrize("name", ["remember", "forget", "log_event"])
def test_commit_errors_keep_existing_rollback_policy(db, name):
    failure = SQLAlchemyError("commit failed")
    db.session.commit.side_effect = failure
    if name == "log_event":
        assert run(db, name) == error(*ERRORS[name])
    else:
        with pytest.raises(SQLAlchemyError) as raised:
            run(db, name)
        assert raised.value is failure
    assert trace_names(db).index("commit") < trace_names(db).index("rollback") < trace_names(db).index("exit")


@pytest.mark.parametrize("case", ["duplicate", "missing", "conflict"])
def test_event_retry_keeps_original_snapshot_and_conflict_outcomes(db, case):
    event_hash = db.server.event_payload_hash(db.server.EventInput(**EVENT_ARGS))
    record = {"id": 5, "request_hash": event_hash if case == "duplicate" else "different"}
    db.session.execute.side_effect = [rows(), rows() if case == "missing" else rows(record)]
    result = run(db, "log_event")
    assert db.session.execute.await_args_list[1].args[1] == {"user_id": "allowed", "request_id": EVENT_ARGS["request_id"]}
    if case == "duplicate":
        assert result == {"success": True, "data": {"event": record, "created": False, "duplicate": True}}
        db.session.commit.assert_awaited_once()
        db.session.rollback.assert_not_awaited()
    else:
        assert result == (error("EVENT_RETRY_FAILED", "Unable to resolve the original event.") if case == "missing"
                          else error("IDEMPOTENCY_CONFLICT", "This request ID was already used with different event data."))
        db.session.rollback.assert_awaited_once()
        db.session.commit.assert_not_awaited()


def test_event_hash_ignores_request_id_and_preserves_unicode_and_key_order(server_module):
    args = {**EVENT_ARGS, "subject": "dal 🍲", "attributes": {"adjustment": "less_salt", "note": "é"}}
    first = server_module.EventInput(**args)
    second = server_module.EventInput(**{**args, "request_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                                        "attributes": {"note": "é", "adjustment": "less_salt"}})
    payload = first.model_dump(mode="json", exclude={"request_id"})
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert server_module.event_payload_hash(first) == server_module.event_payload_hash(second) == expected


@pytest.mark.parametrize("overrides,code,message", [
    ({"domain": "other", "limit": 0}, "UNSUPPORTED_DOMAIN", "Unsupported event domain."),
    ({"limit": 0, "subject": ""}, "INVALID_LIMIT", "Limit must be between 1 and 100."),
    ({"limit": 101}, "INVALID_LIMIT", "Limit must be between 1 and 100."),
    ({"subject": "  "}, "INVALID_SUBJECT", "Subject cannot be empty."),
])
def test_event_list_validation_order(db, overrides, code, message):
    assert run(db, "list_events", **overrides) == error(code, message)
    assert trace_names(db) == ["auth"]


@pytest.mark.parametrize("subject,limit", [(None, 1), ("  Soup  ", 100)])
def test_event_list_filters_and_response(db, subject, limit):
    records = [{"id": 3}, {"id": 1}]
    db.session.execute.return_value = rows(*records)
    assert run(db, "list_events", subject=subject, limit=limit) == {"success": True, "data": {"events": records, "count": 2}}
    query, params = db.session.execute.await_args.args
    assert params == {"user_id": "allowed", "domain": "cooking", "limit": limit,
                      **({"subject": "Soup"} if subject is not None else {})}
    assert ("LOWER(subject) = LOWER(:subject)" in str(query)) is (subject is not None)
    assert "ORDER BY occurred_at DESC, id DESC" in str(query)


def test_unsupported_insight_domain_before_database(db):
    assert run(db, "derive_insights", domain="other") == error("UNSUPPORTED_DOMAIN", "Only cooking insights are supported.")
    assert trace_names(db) == ["auth"]


def test_insight_derivation_uses_existing_algorithm_and_response(db):
    events = [{"id": i, "user_id": "allowed", "domain": "cooking", "event_type": "meal_prepared",
               "subject": "soup", "attributes": {"adjustment": "less_salt"}, "outcome": "BETTER",
               "occurred_at": datetime(2026, 10, i, tzinfo=UTC)} for i in (1, 2, 3)]
    db.session.execute.return_value = rows(*events)
    expected = db.server.derive_repeated_adjustments(events)
    assert run(db, "derive_insights") == {"success": True, "data": {"insights": expected, "count": 1, "events_examined": 3}}
    assert db.session.execute.await_args.args[1] == {"user_id": "allowed", "domain": "cooking"}


def test_insight_listing_preserves_rows_and_count(db):
    records = [{"insight_id": 2}, {"insight_id": 1}]
    db.session.execute.return_value = rows(*records)
    assert run(db, "list_insights") == {"success": True, "data": {"insights": records, "count": 2}}
    assert db.session.execute.await_args.args[1] == {"user_id": "allowed"}


@pytest.mark.parametrize("missing", [True, False])
def test_insight_evidence_checks_ownership_before_events(db, missing):
    insight = {"id": 1, "status": "PENDING_CONFIRMATION", "statement": "statement"}
    events = [{"id": 4}, {"id": 2}]
    db.session.execute.side_effect = [rows() if missing else rows(insight), rows(*events)]
    if missing:
        assert run(db, "get_insight_evidence") == error("INSIGHT_NOT_FOUND", "Insight not found.")
        assert db.session.execute.await_count == 1
    else:
        assert run(db, "get_insight_evidence") == {"success": True, "data": {
            "insight_id": 1, "status": insight["status"], "statement": "statement", "events": events, "count": 2,
        }}
        assert [item.args[1] for item in db.session.execute.await_args_list] == [{"insight_id": 1, "user_id": "allowed"}] * 2
