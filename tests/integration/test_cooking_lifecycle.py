import asyncio
from datetime import UTC
from uuid import uuid4

import pytest

import events_service as events
import memory_service as memory
from insights import insight_queries as queries

pytestmark = pytest.mark.anyio


async def log(db, day=17, **changes):
    args = {
        "user_id": db.user,
        "domain": "cooking",
        "event_type": "meal_prepared",
        "subject": "lentil soup",
        "attributes": {"adjustment": "less salt"},
        "source_utterance": "Synthetic cooking observation",
        "request_id": str(uuid4()),
        "outcome": "BETTER",
        "occurred_at": f"2026-10-{day:02}T12:00:00Z",
    }

    args.update(changes)
    return await events.log_event(db.factory, db.logger, **args)


async def seed(db, **changes):
    results = [await log(db, day, **changes) for day in (17, 18, 19)]
    assert all(r["success"] for r in results)
    return {r["data"]["event"]["id"] for r in results}


async def pending(db):
    ids = await seed(db)
    result = await db.service.save_insight_candidates(db.user)
    assert result["created_count"] == 1
    return result["created"][0]["insight_id"], ids


async def claims(db):
    return await db.rows("SELECT * FROM claims WHERE user_id=:user", user=db.user)


async def test_t01_valid_candidate(cooking_db):
    db = cooking_db
    ids = await seed(db)
    derived = await queries.derive_insights(db.factory, db.logger, db.user)
    assert derived["success"] and derived["data"]["count"] == 1
    candidate = derived["data"]["insights"][0]
    assert (
        candidate["subject"] == "lentil soup" and candidate["adjustment"] == "less_salt"
    )
    assert set(candidate["evidence_event_ids"]) == ids
    saved = await db.service.save_insight_candidates(db.user)
    assert saved["created_count"] == 1
    listed = await queries.list_insights(db.factory, db.logger, db.user)
    assert listed["data"]["count"] == 1
    insight = listed["data"]["insights"][0]
    assert insight["status"] == "PENDING_CONFIRMATION"
    evidence = await queries.get_insight_evidence(
        db.factory, db.logger, db.user, insight["insight_id"]
    )
    assert {e["id"] for e in evidence["data"]["events"]} == ids
    assert (
        len(
            {
                e["occurred_at"].astimezone(UTC).date()
                for e in evidence["data"]["events"]
            }
        )
        == 3
    )
    assert await claims(db) == []
    assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0


@pytest.mark.parametrize("days", [(17, 18), (17, 17, 17)])
async def test_t02_t03_insufficient_dates(cooking_db, days):
    db = cooking_db
    for day in days:
        assert (await log(db, day))["success"]
    result = await queries.derive_insights(db.factory, db.logger, db.user)
    assert result["data"]["count"] == 0
    assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0
    assert (await queries.list_insights(db.factory, db.logger, db.user))["data"][
        "count"
    ] == 0
    assert await claims(db) == []
    rows = await db.rows("SELECT occurred_at FROM events")
    assert len({r["occurred_at"].astimezone(UTC).date() for r in rows}) == len(
        set(days)
    )


@pytest.mark.parametrize(
    "subject,adjustment,expected",
    [
        ("lentil soup", "less salt", 0),
        ("rice", "less salt", 1),
        ("lentil soup", "more salt", 1),
    ],
)
async def test_t04_contradictions(cooking_db, subject, adjustment, expected):
    db = cooking_db
    await seed(db)
    assert (
        await log(
            db,
            20,
            subject=subject,
            attributes={"adjustment": adjustment},
            outcome="WORSE",
        )
    )["success"]
    assert (await queries.derive_insights(db.factory, db.logger, db.user))["data"][
        "count"
    ] == expected
    assert (await db.service.save_insight_candidates(db.user))[
        "created_count"
    ] == expected
    assert await claims(db) == []


async def test_t05_t09_confirmation_provenance_and_explicit_preservation(cooking_db):
    db = cooking_db
    explicit = await memory.remember(
        db.factory,
        db.user,
        "food_preference",
        "I like salty soup",
        "Synthetic explicit preference",
    )
    before = await claims(db)
    insight_id, ids = await pending(db)
    result = await db.service.confirm_insight(db.user, insight_id)
    assert result["success"]
    claim_id = result["data"]["claim_id"]
    state = (await db.rows("SELECT * FROM insights WHERE id=:id", id=insight_id))[0]
    assert state["status"] == "CONFIRMED" and state["decided_at"] is not None
    rows = await claims(db)
    assert len(rows) == 2 and before[0] in rows
    inferred = next(r for r in rows if r["id"] == claim_id)
    assert (
        inferred["source_type"] == "INFERRED_CONFIRMED"
        and inferred["status"] == "ACTIVE"
    )
    assert inferred["user_id"] == db.user
    assert inferred["memory_key"] != explicit["data"]["memory_key"]
    recall = await memory.recall(
        db.factory, db.user, "food_preference", inferred["memory_key"]
    )
    assert [r["claim_id"] for r in recall["data"]] == [claim_id]
    evidence = await queries.get_insight_evidence(
        db.factory, db.logger, db.user, insight_id
    )
    assert evidence["data"]["status"] == "CONFIRMED"
    assert {e["id"] for e in evidence["data"]["events"]} == ids
    explanation = (await memory.explain(db.factory, db.logger, claim_id, db.user))[
        "data"
    ]
    assert (
        explanation["source_type"] == "INFERRED_CONFIRMED"
        and explanation["provenance_complete"] is True
    )
    assert explanation["insight"]["id"] == insight_id
    assert {e["event_id"] for e in explanation["evidence"]} == ids
    assert all(e["user_id"] == db.user for e in explanation["evidence"])
    retry = await db.service.confirm_insight(db.user, insight_id)
    assert (
        retry["data"]["already_confirmed"] is True
        and retry["data"]["claim_id"] == claim_id
    )
    assert len(await claims(db)) == 2


async def test_t06_rejection_suppresses_new_evidence(cooking_db):
    db = cooking_db
    insight_id, ids = await pending(db)
    assert (await db.service.reject_insight(db.user, insight_id))["success"]
    for extra in (False, True):
        if extra:
            await log(db, 20)
        assert (await queries.derive_insights(db.factory, db.logger, db.user))["data"][
            "count"
        ] == 1
        assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0
    state = await db.rows("SELECT * FROM insights")
    assert (
        len(state) == 1
        and state[0]["status"] == "REJECTED"
        and state[0]["decided_at"] is not None
    )
    assert (await db.service.confirm_insight(db.user, insight_id))["error"][
        "code"
    ] == "INSIGHT_ALREADY_REJECTED"
    assert (await db.service.reject_insight(db.user, insight_id))["data"][
        "already_rejected"
    ]
    evidence = await queries.get_insight_evidence(
        db.factory, db.logger, db.user, insight_id
    )
    assert {r["id"] for r in evidence["data"]["events"]} == ids
    assert await claims(db) == []


async def test_t07_invalidated_evidence_is_atomic(cooking_db):
    db = cooking_db
    insight_id, ids = await pending(db)
    before = await db.rows("SELECT * FROM insights")
    await log(db, 20, outcome="WORSE")
    result = await db.service.confirm_insight(db.user, insight_id)
    assert result["error"]["code"] == "INSIGHT_EVIDENCE_NO_LONGER_VALID"
    assert await db.rows("SELECT * FROM insights") == before
    assert await claims(db) == []
    assert {
        r["event_id"] for r in await db.rows("SELECT * FROM insight_evidence")
    } == ids


async def test_t08_event_idempotency(cooking_db):
    db = cooking_db
    request_id = str(uuid4())
    first = await log(db, request_id=request_id)
    retry = await log(db, request_id=request_id)
    assert first["data"]["created"] is True
    assert (
        retry["data"]["duplicate"] is True
        and retry["data"]["event"] == first["data"]["event"]
    )
    conflict = await log(db, request_id=request_id, outcome="WORSE")
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    rows = await db.rows("SELECT * FROM events")
    assert rows == [first["data"]["event"]]
    assert (await queries.derive_insights(db.factory, db.logger, db.user))["data"][
        "count"
    ] == 0


async def test_t10_service_user_scoping(cooking_db):
    db = cooking_db
    insight_id, _ = await pending(db)
    before = await db.rows("SELECT * FROM insights")
    assert (await events.list_events(db.factory, db.logger, db.other, "cooking"))[
        "data"
    ]["count"] == 0
    assert (await queries.list_insights(db.factory, db.logger, db.other))["data"][
        "count"
    ] == 0
    for operation in (db.service.confirm_insight, db.service.reject_insight):
        assert (await operation(db.other, insight_id))["error"][
            "code"
        ] == "INSIGHT_NOT_FOUND"
    assert (
        await queries.get_insight_evidence(db.factory, db.logger, db.other, insight_id)
    )["error"]["code"] == "INSIGHT_NOT_FOUND"
    assert await db.rows("SELECT * FROM insights") == before and await claims(db) == []
    await log(db, 17, user_id=db.other)
    await log(db, 18, user_id=db.other)
    assert (await queries.derive_insights(db.factory, db.logger, db.other))["data"][
        "count"
    ] == 0


async def test_e02_concurrent_confirmation(cooking_db):
    db = cooking_db
    insight_id, _ = await pending(db)
    results = await asyncio.gather(
        *(db.service.confirm_insight(db.user, insight_id) for _ in range(2))
    )
    assert all(r["success"] for r in results)
    assert len({r["data"]["claim_id"] for r in results}) == 1
    assert sorted(r["data"]["already_confirmed"] for r in results) == [False, True]
    assert len(await claims(db)) == 1


async def test_e07_rollback_after_claim_insert(cooking_db, monkeypatch):
    db = cooking_db
    insight_id, ids = await pending(db)
    before = await db.rows("SELECT * FROM insights")
    original = db.service._create_confirmed_claim

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("Synthetic failure before commit")

    monkeypatch.setattr(db.service, "_create_confirmed_claim", fail)
    with pytest.raises(RuntimeError, match="Synthetic failure"):
        await db.service.confirm_insight(db.user, insight_id)
    assert await claims(db) == []
    assert await db.rows("SELECT * FROM insights") == before
    assert {
        r["event_id"] for r in await db.rows("SELECT * FROM insight_evidence")
    } == ids


async def test_e04_dishes_do_not_combine(cooking_db):
    db = cooking_db
    for day, dish in zip((17, 18, 19), ("soup", "rice", "beans")):
        await log(db, day, subject=dish)
    assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0


async def test_e05_normalization(cooking_db):
    db = cooking_db
    for day, phrase in zip((17, 18, 19), ("less salt", "reduced salt", "less sodium")):
        assert (await log(db, day, attributes={"adjustment": phrase}))["success"]
    result = await queries.derive_insights(db.factory, db.logger, db.user)
    assert result["data"]["count"] == 1
    assert result["data"]["insights"][0]["adjustment"] == "less_salt"


async def test_e09_utc_midnight(cooking_db):
    db = cooking_db
    for stamp in (
        "2026-10-17T23:59:59Z",
        "2026-10-18T00:00:00Z",
        "2026-10-18T17:00:00-07:00",
    ):
        assert (await log(db, occurred_at=stamp))["success"]
    result = await db.service.save_insight_candidates(db.user)
    assert result["created_count"] == 1
    assert (
        await db.service.confirm_insight(db.user, result["created"][0]["insight_id"])
    )["success"]


@pytest.mark.parametrize(
    "changes",
    [
        {"subject": " "},
        {"subject": None},
        {"attributes": {"adjustment": ""}},
        {"attributes": {"adjustment": 123}},
        {"outcome": "INVALID"},
        {"request_id": "invalid"},
        {"request_id": None},
        {"occurred_at": "invalid"},
        {"occurred_at": "2026-10-17T12:00:00"},
    ],
)
async def test_e10_invalid_event(cooking_db, changes):
    db = cooking_db
    assert (await log(db, **changes))["error"]["code"] == "INVALID_EVENT"
    assert await db.rows("SELECT * FROM events") == []


async def test_e10_optional_fields_are_not_evidence(cooking_db):
    db = cooking_db
    await seed(db, attributes={}, outcome=None)
    assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0


async def test_new_positive_evidence_preserves_snapshot(cooking_db):
    db = cooking_db
    insight_id, ids = await pending(db)
    await log(db, 20)
    assert (await db.service.save_insight_candidates(db.user))["created_count"] == 0
    assert (await db.service.confirm_insight(db.user, insight_id))["success"]
    evidence = await queries.get_insight_evidence(
        db.factory, db.logger, db.user, insight_id
    )
    assert {row["id"] for row in evidence["data"]["events"]} == ids


async def test_e08_cross_user_events_do_not_combine(cooking_db):
    db = cooking_db
    await log(db, 17)
    await log(db, 18)
    await log(db, 19, user_id=db.other)
    for user in (db.user, db.other):
        assert (await queries.derive_insights(db.factory, db.logger, user))["data"][
            "count"
        ] == 0
        assert (await db.service.save_insight_candidates(user))["created_count"] == 0


async def test_core_memory_lifecycle_regression(cooking_db):
    db = cooking_db
    remembered = (
        await memory.remember(
            db.factory, db.user, "food_preference", "soup", "Synthetic explicit memory"
        )
    )["data"]
    key = remembered["memory_key"]
    corrected = await memory.correct_memory(
        db.factory, db.user, "food_preference", "rice", "Synthetic correction", key
    )
    assert corrected["success"]
    recall = await memory.recall(db.factory, db.user, "food_preference", key)
    assert len(recall["data"]) == 1 and recall["data"][0]["value"] == "rice"
    history = (
        await memory.memory_history(db.factory, db.user, "food_preference", key)
    )["data"]
    assert len(history) == 2
    old = next(r for r in history if r["claim_id"] == remembered["claim_id"])
    assert old["status"] == "SUPERSEDED"
    assert old["superseded_by_claim_id"] == corrected["data"]["claim_id"]
    explanation = await memory.explain(
        db.factory, db.logger, remembered["claim_id"], db.user
    )
    assert explanation["data"]["source_utterance"] == "Synthetic explicit memory"
    assert (
        await memory.explain(db.factory, db.logger, remembered["claim_id"], db.other)
    )["error"]["code"] == "CLAIM_NOT_FOUND"
    assert (await memory.forget(db.factory, db.user, "food_preference", key))["success"]
    assert (await memory.recall(db.factory, db.user, "food_preference", key))[
        "data"
    ] == []
