import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID

import pytest

from client import conversation_state

CONVERSATION = "11111111-2222-3333-4444-555555555555"
KEY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def state(monkeypatch):
    result = Mock()
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.__aenter__.return_value = session
    monkeypatch.setattr(conversation_state, "SessionLocal", Mock(return_value=session))
    return SimpleNamespace(result=result, session=session)


def read(state, row):
    state.result.mappings.return_value.one_or_none.return_value = row
    return asyncio.run(conversation_state.get_pending_clarification(CONVERSATION, "synthetic-user"))


def test_missing_pending_clarification_is_user_and_expiry_scoped(state):
    assert read(state, None) is None
    query, params = state.session.execute.await_args.args
    assert params == {"conversation_id": UUID(CONVERSATION), "user_id": "synthetic-user"}
    assert "user_id = :user_id" in str(query)
    assert "expires_at > NOW()" in str(query)


@pytest.mark.parametrize("keys", [[KEY], '["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]'])
def test_pending_recall_normalizes_candidate_keys(state, keys):
    row = {"operation": "recall", "candidate_memory_keys": keys, "target_memory_key": None}
    assert read(state, row) == {**row, "candidate_memory_keys": [KEY]}


def test_pending_correction_normalizes_target_uuid(state):
    row = {"operation": "correct_memory", "candidate_memory_keys": [], "target_memory_key": UUID(KEY)}
    assert read(state, row) == {**row, "target_memory_key": KEY}


@pytest.mark.parametrize("row,error", [
    ({"operation": "correct_memory", "candidate_memory_keys": [], "target_memory_key": None}, "no target"),
    ({"operation": "invalid", "candidate_memory_keys": [], "target_memory_key": None}, "Unsupported pending"),
    ({"operation": "recall", "candidate_memory_keys": [123], "target_memory_key": None}, "Invalid pending"),
])
def test_invalid_pending_state_is_rejected(state, row, error):
    with pytest.raises(ValueError, match=error):
        read(state, row)
