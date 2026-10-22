# Cooking inference validation report

Executed **2026-10-21**, America/Los_Angeles. Starting Git commit: `7806ce513836a130773c7622986cd67986f92dec`. Results include the uncommitted tests and validation fix described here.

Recommendation: **BACKEND VALIDATED — KEEP UI HIDDEN**. Mandatory cooking backend gates pass on real PostgreSQL, including MCP HTTP and signed API session authorization. The regression suite is now green after the follow-up below; interactive browser/live-model workflow remains unverified. Cooking Insights was not enabled or modified.

## Regression-repair follow-up — October 21, 2026

The complete suite now passes: **487 passed in 21.94s, zero failures, errors or skips**. No module was excluded. All 34 cooking inference tests ran with real disposable PostgreSQL where required. The sections below this follow-up retain the original validation results as historical evidence.

Reviewed current production contracts before editing. Updated contextual tests to use `try_conversational_context` and `ConversationDecision`, with intent extraction before context routing, fail-closed referential mutations, verified claim ownership, independent-request context clearing, and post-correction re-read/retention. Retained the old scenarios and expanded coverage for foreign claims, independent request types and invalid classifier decisions. Updated message orchestration mocks/call order to the current entry point and category-aware ALL-scope fallback. No removed function was reintroduced.

Reviewed snapshot edits are limited to nullable `recall_scope` (`CATEGORY` / `ALL`) and the registered `recall_all(user_id)` tool after `recall`. Existing schema/tool assertions remain intact. Added `recall_all` to the shared authorization test arguments. No snapshots were regenerated wholesale.

Also replaced `tests/test_conversation_state.py`'s import-time manual database read/print with seven assertion-based, isolated tests. They verify user/expiry scoping, missing rows, candidate-key/target normalization and invalid pending state. Collection no longer performs that application-data query.

Commands:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_contextual_operations.py tests/test_message_orchestration.py tests/test_orchestration_models.py tests/test_server_operations.py -q --tb=short
# 259 passed in 5.79s

$env:INFERENCE_TEST_ADMIN_URL='postgresql://inference_test@127.0.0.1:55439/postgres'
$env:DATABASE_URL='postgresql+asyncpg://inference_test@127.0.0.1:55439/postgres'
.venv/Scripts/python.exe -m pytest tests -q --tb=short
# 487 passed in 21.94s

.venv/Scripts/python.exe -m pytest tests/integration tests/test_cooking_orchestration.py -q --tb=short
# 34 passed in 17.82s (standalone rerun after the full suite)
```

The disposable cluster was restarted; scenario databases still use the existing generated-database fixtures and actual schema. DATABASE_URL points to the local maintenance database only for safe import-time engine configuration; integration services use their fixture-created databases. Cleanup verified zero generated databases remained and stopped the disposable cluster. `git diff --check` passed. No production code, inference rules, authentication behavior or frontend sidebar changed during this repair. Files changed for the follow-up: the four requested test/fixture areas, `tests/test_conversation_state.py`, and factual testing/design documentation. Remaining regression failures: **none**. Hosted browser/live-model checks and a fresh dependency installation remain unverified; the frontend build was not rerun for these test-only changes.

## Environment and safety

Windows, Python 3.12, project `.venv`, PostgreSQL 18.6. Initialized a fresh `.test-postgres` cluster on `127.0.0.1:55439`, separate from the existing PostgreSQL service on port 5432. Every scenario creates its own random database, applies `scripts/scripts.sql`, uses unique synthetic users and fixed October 2026 observation dates, disposes connections and drops only that new database. No development/demo database was used. The maintenance URL is explicit and local; no application DATABASE_URL fallback is permitted. The local cluster directory is ignored by Git.

Installed versions used: pytest 9.1.1, anyio 4.15.1, MCP 2.3.0, SQLAlchemy 2.1.3, asyncpg 0.31.0, psycopg 3.3.6, FastAPI 0.143.0, OpenAI 3.26.0. Several differ from requirements.txt; a clean installation of its exact pins was not tested. pytest-asyncio is absent, so tests reuse installed AnyIO infrastructure. Docker's daemon was unavailable; local PostgreSQL tools were available. PostgreSQL startup required sandbox escalation after its restricted-token startup failed.

## Discovery and discrepancies

Inspected server.py, client/api.py, client/orchestrator.py, memory/event services, insight queries/persistence/evidence validation, validators, SQL schema, tests/fixtures, dependency files and design/testing documents. Database operations use SQL text and async SQLAlchemy sessions, not ORM entity models. The actual dev requirements filename is `requirementsdev.txt`, not the documented `requirements-dev.txt`.

The implemented rule/lifecycle match the intended design: three distinct UTC dates; any matching WORSE blocks; candidate evidence is a snapshot; confirmation/rejection lock the insight row and transact changes; inferred claims have separate memory keys. Persistence's unique rule/user/dish/adjustment index suppresses duplicates and previously rejected patterns. Pure derivation still returns eligible patterns after rejection; suppression happens at persistence. Confirmation retry succeeds with `already_confirmed` and the original claim ID.

Discrepancies and limits identified before test implementation:

- Snapshot confirmation validation calls raw `.date()` while derivation explicitly converts to UTC. The actual asyncpg path returned UTC and passed boundary tests; non-UTC values from other adapters remain a latent discrepancy. Existing unit tests preserve raw-date behavior; this was not silently changed.
- EventInput accepted timestamps without a timezone, while pure derivation ignores naive datetime values. A real database test demonstrated acceptance; the trust-boundary validation defect was fixed below.
- Missing adjustment/outcome are supported optional observation fields, not invalid requests. They do not qualify as evidence. Supplied blank/invalid values are rejected.
- No browser event-list route exists. Service event ownership and the authenticated chat impersonation guard are tested; no event API was invented.
- MCP trusts client-supplied allowed user_id under a shared service bearer token. Browser/API sessions enforce ownership; MCP is not independently user-authorized.
- These MCP tools declare no output schemas. Actual responses use JSON text with no structured content. The test checks supported text envelopes, equality if structured content is supplied, and the production client's actual fallback.

## Commands and final counts

Cluster setup/shutdown commands are in [testing.md](testing.md).

```powershell
python -m pytest tests -q
# System Python: No module named pytest

.venv/Scripts/python.exe -m pytest tests -q
# Before and after change: 1 collection error, removed contextual helper

$env:INFERENCE_TEST_ADMIN_URL='postgresql://inference_test@127.0.0.1:55439/postgres'
.venv/Scripts/python.exe -m pytest tests/integration tests/test_cooking_orchestration.py -q --tb=short
# 34 passed in 18.70s

.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_contextual_operations.py --tb=short
# 2 failed, 368 passed, 61 errors in 26.90s

cd frontend
npm.cmd run build
# Formatting, ESLint, TypeScript and Vite passed
```

PowerShell initially rejected npm.ps1 under execution policy; the installed npm.cmd entry point succeeded. Intermediate targeted runs included 25 initial PostgreSQL passes and 30 lifecycle/validator passes after the fix. Counts above describe final distinct cases, not the sum of repeated executions.

| Test | Status | Evidence | Notes |
|---|---|---|---|
| T01 | PASS | `test_t01_valid_candidate` | 3 stored events, one pending insight, canonical values, exact evidence IDs, 3 UTC dates, no premature claim |
| T02 | PASS | `test_t02_t03_insufficient_dates[days0]` | 2 dates; no candidate, persisted insight or claim |
| T03 | PASS | `test_t02_t03_insufficient_dates[days1]`, `test_e09_utc_midnight` | Same-day repeats count once; UTC midnight/offset observations span 3 UTC dates |
| T04 | PASS | 3 `test_t04_contradictions` cases | Matching WORSE blocks; unrelated dish/adjustment does not; no premature claim |
| T05 | PASS | `test_t05_t09_confirmation_provenance_and_explicit_preservation` | CONFIRMED timestamp, ACTIVE inferred source/user, separate key, explicit row unchanged, supported recall |
| T06 | PASS | `test_t06_rejection_suppresses_new_evidence` | REJECTED timestamp, no claim, no duplicate/reproposal even after more positive evidence |
| T07 | PASS | `test_t07_invalidated_evidence_is_atomic` | Exact INSIGHT_EVIDENCE_NO_LONGER_VALID; insight unchanged, no claim, snapshot retained |
| T08 | PASS | `test_t08_event_idempotency` | Exact retry original row; conflict typed error; event unchanged and no multiplied evidence |
| T09 | PASS | Combined T05/T09 and `test_mcp_http_lifecycle` | Persisted IDs agree across evidence/explain; source/user checked; inspectable after confirmation |
| T10 | PASS | `test_t10_service_user_scoping`, `test_t10_signed_browser_session_against_real_mcp` | B cannot impersonate A, read evidence, confirm or reject; 401/403/404; state unchanged; real downstream MCP |

Additional executed coverage:

| Cases | Result and evidence |
|---|---|
| E01 repeated derivation/persistence | PASS: T01/T06 and snapshot test return zero additional inserts |
| E02 concurrent confirmation | PASS: two separate sessions succeed with same claim ID, one ACTIVE claim, one already_confirmed result |
| E03 retry | PASS: original claim ID, already_confirmed true, no additional claim |
| E04 dishes | PASS: distributed positives do not combine |
| E05 normalization | PASS: less salt/reduced salt/less sodium normalize to less_salt; unrelated adjustment also tested in T04 |
| E06 explicit preservation | PASS: complete explicit database row remains unchanged |
| E07 rollback | PASS: injected exception after real claim INSERT before commit leaves no claim, unchanged pending insight and evidence |
| E08 cross-user evidence | PASS: 2 A events plus 1 B event qualify for neither user |
| E09 dates | PASS: UTC midnight and offset timestamp qualify on 3 UTC dates; confirmation succeeds |
| E10 invalid inputs | PASS: 9 invalid payload cases reject before persistence; missing optional adjustment/outcome creates no candidate |
| Positive event after snapshot | PASS: fourth positive permits confirmation but preserves original 3 evidence IDs |
| Core memory regression | PASS: real remember/recall/correct/history/explain/forget; supersession link and foreign explanation denial |
| MCP transport | PASS: real initialize/tools-list, log/derive/save/list/evidence/confirm/reject/explain, JSON fallback, missing bearer rejection |
| Browser/API | PASS: signed ownership, actual list/derive/evidence/confirm and inferred explanation; foreign access denied |
| Orchestration | PASS, mocked extraction only: 3 utterances enter handle_user_message; supplied parsed actions invoke exactly log_event with correct user/outcome and stable UUID5 request ID, no fabricated date; validator canonicalization checked |

The orchestration tests prove routing of mocked OpenAI responses, not live extraction accuracy. Dish normalization only lowercases/collapses whitespace; alternative spellings and underscores remain separate. No live model/API key is required by the suite.

## Failures investigated

1. **Fixed timestamp-validation bug:** `test_e10_invalid_event[changes8]` failed with `KeyError: 'error'` because naive `2026-10-17T12:00:00` succeeded and was persisted. Added an occurred_at field validator requiring timezone information when supplied. Omission still uses server UTC; aware timestamps, inference thresholds and UTC-date rules are unchanged. Reran the failed group, all new cases and regression suite.
2. **Corrected new MCP test setup:** first transport attempt raised `ValueError: not enough values to unpack (expected 3, got 2)`. Inspected installed SDK and used its actual two-value signature. An initial structured-content requirement was corrected after inspection showed tools have no output schemas; the supported JSON text and production fallback now pass against the real server.
3. **Unresolved pre-existing collection error:** `tests/test_contextual_operations.py` imports removed `looks_like_contextual_operation`. Full prescribed command cannot collect; no pass is claimed for that module.
4. **Unresolved pre-existing setup errors:** 61 cases in `tests/test_message_orchestration.py` patch removed `try_contextual_recall`, raising AttributeError before assertions execute.
5. **Unresolved pre-existing snapshot failures:** `test_response_model_schema_and_public_identity[Actions]` baseline lacks `recall_scope`; `test_registered_tool_contracts_and_order` expects remember where recall_all is now registered. Both were reproduced before the fix. Baselines were not blindly regenerated.

## Deliverables and release gate

Added **34 cases**: **31 real PostgreSQL**, including MCP/API tests; **3 deterministic mocked-extraction routing**. Final new group: **34 executed, 34 passed, 0 failed, 0 skipped/blocked**.

Diagnostic repository run: **431 cases = 368 passed + 2 failed + 61 setup errors**, zero skips, excluding the single uncollectable contextual module. Thus 63 existing cases remain unsuccessful and a separate module remains blocked at collection. The full regression gate is not green.

Modified files: `.gitignore`; `validators/event_validator.py`; `tests/integration/__init__.py`, `conftest.py`, `test_cooking_lifecycle.py`, `test_insight_authorization.py`, `test_mcp_cooking.py`; `tests/test_cooking_orchestration.py`; `docs/testing.md`; `docs/design-decisions.md`; this report.

No thresholds, contradiction semantics, rejection policy, authentication implementation, unrelated memory behavior or frontend functionality changed. Documentation now corrects the former all-unit-only claim and requirements filename. README's experimental/hidden status remains accurate. Cleanup verified zero remaining generated test databases and stopped the disposable cluster; its ignored files remain available for reruns. `git diff --check` passed.

Remaining risks: live extraction and interactive/hosted browser workflow unverified; broken contextual tests/stale baselines prevent a clean repository regression gate; shared-token MCP is unsuitable for untrusted per-user access; snapshot raw-date handling is adapter-dependent. Confirmation racing a simultaneously arriving contradictory event was not stress-tested; the tested concurrency case is two confirmations. Exact dependency pins were not reinstalled. Login UI, conversation-context behavior, load, native Alexa+ and production were not tested here.

**Do not expose Cooking Insights yet.** Backend validation is substantial, but READY TO DEMO requires complete public-flow validation and regression repair.
