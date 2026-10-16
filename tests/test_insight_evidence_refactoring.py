import asyncio
import inspect
import pickle
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from insights import insights_service as service

INSIGHT = {
    "id": 7, "domain": "cooking", "insight_type": "REPEATED_ADJUSTMENT",
    "subject": "soup", "adjustment": "less_salt", "statement": "Prefers less salt",
    "status": "PENDING_CONFIRMATION", "confirmed_claim_id": None,
}


def evidence_session(events):
    result = Mock()
    result.mappings.return_value = events
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_snapshot_validation_counts_distinct_dates(count):
    events = [{"outcome": "BETTER", "occurred_at": datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=i)}
              for i in range(count)]
    session = evidence_session(events)
    assert asyncio.run(service.validate_insight_evidence(session, "user", 7)) == {
        "valid": count >= 3, "evidence_count": count, "independent_dates": count,
    }
    query, params = session.execute.await_args.args
    assert params == {"insight_id": 7, "user_id": "user"}
    assert "e.user_id = :user_id" in str(query)
    assert "ORDER BY e.occurred_at, e.id" in str(query)


def test_snapshot_validation_keeps_raw_date_and_duplicate_semantics():
    events = [
        {"outcome": "BETTER", "occurred_at": datetime(2026, 10, 1, 23, tzinfo=UTC)},
        {"outcome": "BETTER", "occurred_at": datetime(2026, 10, 2, 1, tzinfo=timezone(timedelta(hours=2)))},
        {"outcome": "BETTER", "occurred_at": datetime(2026, 10, 3)},
        {"outcome": "BETTER", "occurred_at": datetime(2026, 10, 3)},
        {"outcome": "BETTER", "occurred_at": None},
        {"outcome": "WORSE"},
    ]
    assert asyncio.run(service.validate_insight_evidence(evidence_session(events), "user", 7)) == {
        "valid": True, "evidence_count": 4, "independent_dates": 3,
    }


@pytest.mark.parametrize("event,exception", [
    ({}, KeyError), ({"outcome": "BETTER"}, KeyError),
    ({"outcome": "BETTER", "occurred_at": "2026-10-01"}, AttributeError),
])
def test_snapshot_validation_keeps_malformed_event_exceptions(event, exception):
    with pytest.raises(exception):
        asyncio.run(service.validate_insight_evidence(evidence_session([event]), "user", 7))


@pytest.mark.parametrize("field", ["domain", "insight_type", "subject", "adjustment"])
def test_current_validation_matches_all_four_fields_and_first_candidate(monkeypatch, field):
    nonmatching = {key: INSIGHT[key] for key in ("domain", "insight_type", "subject", "adjustment")}
    nonmatching.update(evidence_count=99, evidence_event_ids=[99])
    nonmatching[field] = "different"
    first = {**INSIGHT, "evidence_count": 3, "evidence_event_ids": [1, 2, 3]}
    second = {**INSIGHT, "evidence_count": 4, "evidence_event_ids": [1, 2, 3, 4]}
    derive = Mock(return_value=[nonmatching, first, second])
    monkeypatch.setitem(service.validate_current_insight_evidence.__globals__, "derive_repeated_adjustments", derive)
    events = [{"id": 1}]
    session = evidence_session(events)
    assert asyncio.run(service.validate_current_insight_evidence(session, "user", INSIGHT)) == {
        "valid": True, "evidence_count": 3, "evidence_event_ids": [1, 2, 3],
    }
    derive.assert_called_once_with(events)
    assert session.execute.await_args.args[1] == {"user_id": "user"}


@pytest.mark.parametrize("name,expected", [
    ("validate_insight_evidence", "(session, user_id: str, insight_id: int) -> dict"),
    ("validate_current_insight_evidence", "(session, user_id: str, insight) -> dict"),
])
def test_validator_import_signatures_and_pickle_identity(name, expected):
    from insights import evidence_validation

    validator = getattr(service, name)
    assert getattr(evidence_validation, name) is validator
    assert str(inspect.signature(validator)) == expected
    assert validator.__module__ == "insights.insights_service"
    assert pickle.loads(pickle.dumps(validator)) is validator


@pytest.fixture
def confirmation(monkeypatch):
    session = MagicMock()
    transaction = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.begin.return_value = transaction
    transaction.__aexit__.return_value = False
    selected = Mock()
    selected.mappings.return_value.one_or_none.return_value = dict(INSIGHT)
    inserted = Mock()
    inserted.scalar_one.return_value = 42
    session.execute = AsyncMock(side_effect=[selected, inserted, Mock()])
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    factory = Mock(return_value=session)
    evidence = AsyncMock(return_value={"valid": True})
    current = AsyncMock(return_value={"valid": True})
    generated = Mock(return_value="new-key")
    monkeypatch.setattr(service, "SessionLocal", factory)
    monkeypatch.setattr(service, "validate_insight_evidence", evidence)
    monkeypatch.setattr(service, "validate_current_insight_evidence", current)
    monkeypatch.setattr("uuid.uuid4", generated)
    trace = Mock()
    for name, mock in {
        "factory": factory, "enter": session.__aenter__, "begin": session.begin,
        "transaction_enter": transaction.__aenter__, "execute": session.execute,
        "evidence": evidence, "current": current, "uuid": generated,
        "transaction_exit": transaction.__aexit__, "exit": session.__aexit__,
    }.items():
        trace.attach_mock(mock, name)
    return SimpleNamespace(session=session, transaction=transaction, selected=selected,
                           inserted=inserted, evidence=evidence, current=current,
                           generated=generated, trace=trace)


def confirm():
    return asyncio.run(service.confirm_insight("user", 7))


def names(confirmation):
    return [item[0] for item in confirmation.trace.mock_calls if "." not in item[0]]


@pytest.mark.parametrize("status,expected", [
    (None, {"success": False, "error": {"code": "INSIGHT_NOT_FOUND", "message": "Insight not found."}}),
    ("CONFIRMED", {"success": True, "data": {"insight_id": 7, "claim_id": 10, "already_confirmed": True}}),
    ("REJECTED", {"success": False, "error": {"code": "INSIGHT_ALREADY_REJECTED", "message": "Rejected insight cannot be confirmed."}}),
])
def test_confirmation_terminal_statuses_skip_validation_and_writes(confirmation, status, expected):
    confirmation.selected.mappings.return_value.one_or_none.return_value = (
        None if status is None else {**INSIGHT, "status": status, "confirmed_claim_id": 10}
    )
    assert confirm() == expected
    assert names(confirmation) == ["factory", "enter", "begin", "transaction_enter", "execute", "transaction_exit", "exit"]


def test_confirmation_requires_snapshot_evidence_before_current_validation(confirmation):
    confirmation.evidence.return_value = {"valid": False}
    assert confirm() == {"success": False, "error": {
        "code": "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "message": "This insight needs observations from at least three distinct cooking dates.",
    }}
    confirmation.current.assert_not_awaited()
    confirmation.generated.assert_not_called()
    assert confirmation.session.execute.await_count == 1


def test_confirmation_preserves_current_validation_error(confirmation):
    confirmation.current.return_value = {"valid": False, "code": "original-code", "message": "original-message"}
    assert confirm() == {"success": False, "error": {"code": "original-code", "message": "original-message"}}
    confirmation.generated.assert_not_called()
    assert names(confirmation)[-4:] == ["evidence", "current", "transaction_exit", "exit"]


def test_confirmation_validation_claim_and_decision_share_transaction(confirmation):
    assert confirm() == {"success": True, "data": {
        "insight_id": 7, "claim_id": 42, "status": "CONFIRMED", "already_confirmed": False,
    }}
    assert names(confirmation) == ["factory", "enter", "begin", "transaction_enter", "execute",
                                   "evidence", "current", "uuid", "execute", "execute", "transaction_exit", "exit"]
    confirmation.evidence.assert_awaited_once_with(confirmation.session, "user", 7)
    confirmation.current.assert_awaited_once_with(confirmation.session, "user", INSIGHT)
    queries = confirmation.session.execute.await_args_list
    assert "FOR UPDATE" in str(queries[0].args[0])
    assert queries[0].args[1] == {"user_id": "user", "insight_id": 7}
    assert "'INFERRED_CONFIRMED'" in str(queries[1].args[0])
    assert queries[1].args[1] == {"user_id": "user", "value": INSIGHT["statement"],
                                "source": "Confirmed derived insight #7", "memory_key": "new-key"}
    assert queries[2].args[1] == {"claim_id": 42, "insight_id": 7, "user_id": "user"}
    confirmation.session.begin.assert_called_once()
    confirmation.session.commit.assert_not_awaited()
    confirmation.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("exception", [SQLAlchemyError, ValueError])
@pytest.mark.parametrize("stage", ["read", "evidence", "current", "uuid", "insert", "scalar", "update"])
def test_confirmation_errors_propagate_through_same_transaction(confirmation, exception, stage):
    failure = exception("unchanged")
    if stage in {"read", "insert", "update"}:
        results = [confirmation.selected, confirmation.inserted, Mock()]
        results[{"read": 0, "insert": 1, "update": 2}[stage]] = failure
        confirmation.session.execute.side_effect = results
    elif stage == "scalar":
        confirmation.inserted.scalar_one.side_effect = failure
    else:
        {"evidence": confirmation.evidence, "current": confirmation.current,
         "uuid": confirmation.generated}[stage].side_effect = failure
    with pytest.raises(exception) as raised:
        confirm()
    assert raised.value is failure
    assert confirmation.transaction.__aexit__.await_args.args[1] is failure
    assert confirmation.session.__aexit__.await_args.args[1] is failure
    assert names(confirmation)[-2:] == ["transaction_exit", "exit"]


def test_missing_statement_still_generates_uuid_before_raising(confirmation):
    insight = {key: value for key, value in INSIGHT.items() if key != "statement"}
    confirmation.selected.mappings.return_value.one_or_none.return_value = insight
    with pytest.raises(KeyError) as raised:
        confirm()
    assert raised.value.args == ("statement",)
    confirmation.generated.assert_called_once()
    assert confirmation.session.execute.await_count == 1
