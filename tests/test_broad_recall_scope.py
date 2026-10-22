import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from memory_service import recall_all
from models.action import Action


def test_action_accepts_broad_recall_without_category():
    action = Action(intent="recall", category=None, recall_scope="ALL", attributes=None)
    assert action.category is None
    assert action.recall_scope == "ALL"


def test_action_keeps_existing_specific_category():
    action = Action(intent="recall", category="hiking", attributes=None)
    assert action.recall_scope is None
    assert action.category.value == "hiking"


def test_read_all_routes_to_user_scoped_mcp(orchestrator, monkeypatch):
    tool = AsyncMock(return_value={"success": True, "data": []})
    monkeypatch.setattr(orchestrator, "call_mcp_tool", tool)
    action = Action(intent="recall", category=None, recall_scope="ALL", attributes=None)
    result = asyncio.run(orchestrator.execute_action("alice", "What do I enjoy?", action))
    assert result["success"]
    tool.assert_awaited_once_with(tool_name="recall_all", args={"user_id": "alice"})


def test_category_recall_unchanged(orchestrator, monkeypatch):
    tool = AsyncMock(return_value={"success": True, "data": []})
    monkeypatch.setattr(orchestrator, "call_mcp_tool", tool)
    action = Action(intent="recall", category="hiking", attributes=None)
    asyncio.run(orchestrator.execute_action("alice", "What is my hiking preference?", action))
    tool.assert_awaited_once_with(tool_name="recall", args={"user_id": "alice", "category": "hiking"})


def test_no_actions_fallback_queries_all_categories(orchestrator, monkeypatch):
    tool = AsyncMock(return_value={"success": True, "data": []})
    decision = SimpleNamespace(status="NOT_FOUND", claims=[], clarification_question=None)
    relevance = AsyncMock(return_value=decision)
    apply_decision = AsyncMock(return_value={"success": True, "data": []})
    monkeypatch.setattr(orchestrator, "call_mcp_tool", tool)
    monkeypatch.setattr(orchestrator, "filter_relevant_memories", relevance)
    monkeypatch.setattr(orchestrator, "apply_recall_decision", apply_decision)
    asyncio.run(orchestrator.fallback_food_memory_recall("alice", "What do I enjoy?"))
    tool.assert_awaited_once_with(tool_name="recall_all", args={"user_id": "alice"})
    relevance.assert_awaited_once()


class FakeMappings:
    def all(self):
        return [{"claim_id": 2, "user_id": "alice", "status": "ACTIVE", "category": "hiking", "value": "enjoys hiking in forests"}]


class FakeResult:
    def mappings(self):
        return FakeMappings()


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, query, params):
        self.params = params
        self.sql = str(query)
        return FakeResult()


def test_recall_all_is_owner_scoped_and_active():
    session = FakeSession()
    result = asyncio.run(recall_all(lambda: session, "alice"))
    assert session.params == {"user_id": "alice"}
    assert "user_id = :user_id" in session.sql
    assert "status = 'ACTIVE'" in session.sql
    assert result["success"] is True
    assert result["data"][0]["category"] == "hiking"
