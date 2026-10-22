from unittest.mock import AsyncMock

import httpx2
import pytest

from tests.integration.test_cooking_lifecycle import pending, claims

pytestmark = pytest.mark.anyio


async def test_t10_signed_browser_session_against_real_mcp(cooking_mcp, orchestrator, monkeypatch):
    db = cooking_mcp.db
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "synthetic-test-password-at-least-32-characters")
    monkeypatch.setenv("DEMO_SESSION_SECRET", "synthetic-test-session-secret-at-least-32-characters")
    from client import api
    from client import memory_api
    from security import demo_access, demo_users
    from itsdangerous import URLSafeTimedSerializer
    monkeypatch.setattr(demo_users, "ALLOWED_DEMO_USERS", frozenset({db.user, db.other}))
    monkeypatch.setattr(demo_access, "serializer", URLSafeTimedSerializer("synthetic-test-session-secret-32-characters", salt="adh-demo-access-v2"))
    chat = AsyncMock()
    monkeypatch.setattr(api, "handle_user_message", chat)
    monkeypatch.setattr(memory_api, "SessionLocal", db.factory)
    insight_id, _ = await pending(db)
    before = await db.rows("SELECT * FROM insights")
    transport = httpx2.ASGITransport(app=api.app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://test.local") as browser:
        assert (await browser.get("/insights", params={"user_id": db.user})).status_code == 401
        browser.cookies.set(demo_access.COOKIE_NAME, demo_access.create_demo_session(db.other))
        assert (await browser.get("/insights", params={"user_id": db.other})).json()["count"] == 0
        assert (await browser.get("/insights", params={"user_id": db.user})).status_code == 403
        path = f"/insights/{insight_id}"
        assert (await browser.get(path + "/evidence", params={"user_id": db.other})).status_code == 404
        assert (await browser.get(path + "/evidence", params={"user_id": db.user})).status_code == 403
        for action in ("confirm", "reject"):
            assert (await browser.post(path + "/" + action, params={"user_id": db.other}, json={"user_id": db.other})).status_code == 404
            assert (await browser.post(path + "/" + action, params={"user_id": db.other}, json={"user_id": db.user})).status_code == 403
            assert (await browser.post(path + "/" + action, params={"user_id": db.user}, json={"user_id": db.user})).status_code == 403
        from uuid import uuid4
        assert (await browser.post("/chat", json={"user_id": db.user, "conversation_id": str(uuid4()), "message": "List my cooking events"})).status_code == 403
        chat.assert_not_awaited()
        assert await db.rows("SELECT * FROM insights") == before
        assert await claims(db) == []
        browser.cookies.set(demo_access.COOKIE_NAME, demo_access.create_demo_session(db.user))
        assert (await browser.get("/insights", params={"user_id": db.user})).json()["count"] == 1
        assert (await browser.post("/insights/derive", params={"user_id": db.user}, json={"user_id": db.user})).json()["created_count"] == 0
        assert (await browser.get(path + "/evidence", params={"user_id": db.user})).json()["count"] == 3
        response = await browser.post(path + "/confirm", params={"user_id": db.user}, json={"user_id": db.user})
        assert response.status_code == 200 and response.json()["status"] == "CONFIRMED"
        claim_id = response.json()["claim_id"]
        explanation = await browser.get(f"/memories/{claim_id}/explain", params={"user_id": db.user})
        assert explanation.status_code == 200 and explanation.json()["provenance_complete"] is True
        browser.cookies.set(demo_access.COOKIE_NAME, demo_access.create_demo_session(db.other))
        assert (await browser.get(f"/memories/{claim_id}/explain", params={"user_id": db.other})).status_code == 404
