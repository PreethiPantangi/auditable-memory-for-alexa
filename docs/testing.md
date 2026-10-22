# Testing

Automated results and manual checks are kept separate. A scenario listed under *Manual* is not a claim that an automated end-to-end test covers it.

## Automated

```bash
pip install -r requirementsdev.txt
python -m pytest tests -q
cd frontend && npm run build
```

The October 21, 2026 run added 34 passing cases: 31 use real PostgreSQL (including MCP HTTP and signed browser/API session authorization), and 3 mock OpenAI extraction to exercise routing. See [inference-test-report.md](inference-test-report.md). Recommendation: **BACKEND VALIDATED — KEEP UI HIDDEN**.

After repairing obsolete regression tests on October 21, the complete suite passes: **487 passed, zero failures/errors/skips**, including the previously uncollectable module and all 34 cooking tests. The initial validation's collection/setup/snapshot failures are resolved; see the report's regression-repair follow-up. The frontend formatting/lint/typecheck/build passed during the initial validation; it was not rerun for the test-only repair.

### Disposable PostgreSQL configuration

Use a separate local disposable cluster, never the demo/development database. On Windows with PostgreSQL binaries on PATH, initialize a fresh directory:

```powershell
initdb -D .test-postgres -U inference_test -A trust --no-locale --encoding=UTF8
pg_ctl -D .test-postgres -l .test-postgres/server.log -o '-h 127.0.0.1 -p 55439' -w start
$env:INFERENCE_TEST_ADMIN_URL='postgresql://inference_test@127.0.0.1:55439/postgres'
.venv/Scripts/python.exe -m pytest tests/integration tests/test_cooking_orchestration.py -q
pg_ctl -D .test-postgres -m fast -w stop
```

Trust authentication is for this disposable loopback cluster only. The admin role needs CREATE DATABASE permission. Each scenario creates an `inference_test_<random UUID>` database, applies the actual `scripts/scripts.sql`, uses unique synthetic identities and fixed timezone-aware dates, disposes connections and drops only that new database. No application DATABASE_URL fallback is allowed. Missing opt-in configuration produces BLOCKED pytest skips, never mock substitutes. The MCP fixture launches a real separate server with the test database and a generated bearer token on a dynamic port. API tests use signed synthetic session cookies and real downstream MCP calls.

## Manual scenarios

**Memory lifecycle.** Remember a preference, recall it, correct it, confirm the replacement is active and the old version appears as superseded in history, ask for the explanation, forget it, confirm active recall no longer returns it.

**User isolation.** Sign in as user A and store a memory. Sign in as user B. Confirm B cannot list, explain or view A's memory through browser routes, and that replaying A's `conversation_id` as B returns HTTP 403 with no downstream action.

**Event idempotency.** Log an event with a request ID. Repeat it unchanged and confirm the original event is returned. Repeat the ID with a changed payload and confirm `IDEMPOTENCY_CONFLICT`.

**Hosted flow.** On the deployed app, from a fresh browser: log in, remember, correct, forget, reload the page, open a history deep link, log out.

## Insight test plan

The insight rule is `REPEATED_ADJUSTMENT` (see the README). T01–T10 and relevant edge cases now pass against disposable PostgreSQL; see the execution report for assertion-level evidence. The older checklist below is retained as a scenario reference, not an assertion that live chat or interactive UI testing was completed.

### Checked offline (derivation function only)

| Scenario | Result |
|---|---|
| 3 `BETTER` events on 3 distinct UTC dates, same dish and adjustment | Candidate with those 3 event IDs |
| 3 `BETTER` events on the same day | No candidate |
| `SAME` or `UNKNOWN` outcomes mixed in | Ignored; still needs 3 `BETTER` |
| One `WORSE` for the same dish and adjustment, even from long ago, plus 3 newer `BETTER` | No candidate (blocked permanently) |
| 4 `BETTER` events on 4 dates | Candidate with 4 events |
| Timestamp without timezone | Event ignored |
| 3 events on 3 distinct **Pacific** days (6 PM, then two mornings) | **No candidate**, because dates are counted in UTC |
| Subjects `lentil soup`, `lentil_soup`, `Lentil  Soup` | Only the lowercase/whitespace variants group together; the underscore variant does not |

### Scenario reference (executed coverage is in the report)

| # | Scenario | Expected |
|---|---|---|
| I1 | Log 3 `BETTER` events on 3 distinct days, call `save_insight_candidates` | One pending insight, 3 rows in `insight_evidence` |
| I2 | Call `save_insight_candidates` again | `created_count` is 0; still 3 evidence rows, not 6 |
| I3 | Log "reduced salt", "less sodium", "less salt" via chat | All stored as `less_salt` |
| I4 | Log "Lentil Soup" and "lentil soup" | Grouped as one dish |
| I5 | A `WORSE` event for a *different* dish | Does not block this candidate |
| I6 | A `WORSE` event logged after the candidate was saved, then `confirm_insight` | `INSIGHT_EVIDENCE_NO_LONGER_VALID`, no claim created |
| I7 | A 4th `BETTER` event logged after the candidate was saved, then confirm | Succeeds; evidence shown is the 3-event snapshot |
| I8 | `confirm_insight` | Insight `CONFIRMED`; new claim with source `INFERRED_CONFIRMED`; appears in the ledger |
| I9 | `explain` on that claim | Returns the insight, each supporting event with its utterance and date, `provenance_complete: true` |
| I10 | `confirm_insight` twice | Second call returns `already_confirmed`; exactly one claim exists |
| I11 | Two concurrent `confirm_insight` calls | Exactly one claim (row lock) |
| I12 | `reject_insight`, then `confirm_insight` | `INSIGHT_ALREADY_REJECTED`; no claim |
| I13 | After a rejection, run `save_insight_candidates`, then log more `BETTER` events and run it again | Not re-proposed either time (permanent) |
| I14 | User B calls `list_insights`, `get_insight_evidence`, `confirm_insight` on user A's insight | Not visible; `INSIGHT_NOT_FOUND` |
| I15 | Forget the confirmed claim through chat | Claim excluded from recall; insight stays `CONFIRMED`; pattern is not re-proposed. Check the UI shows this sensibly |
| I16 | Open the evidence panel for the demo insight | Three distinct events, distinct dates, consistent outcomes, no duplicates or contradictions |

Run I3 and I4 through the real chat path, not just the validator, because a unit test of the normalizer does not prove the orchestrator-to-database path.

### Known behaviors to decide on before the demo

1. **UTC dates.** UTC dates are the intended rule, not local cooking days. The real asyncpg path passed UTC-midnight and offset tests. Snapshot validation takes raw `.date()` and relies on the adapter returning UTC; non-UTC values from another adapter remain a limitation. A supplied event timestamp must now include a timezone; omitted timestamps use server UTC time.
2. **A single `WORSE` blocks permanently,** even a very old one, even after many newer `BETTER` events. This is conservative and consistent with the contradiction rule, but state it, and keep contradictory fixtures out of the demo user.
3. **Reject is permanent** for that dish and adjustment, because the unique index prevents re-creation even with new evidence. State this wherever you describe rejection.
4. **Dish names** are only lowercased and whitespace-collapsed. Differently spelled names split the evidence.
5. **Confirmed claims are separate.** A confirmed "prefers less salt" insight can coexist with an explicit claim that says the opposite. The prototype does not detect that conflict.

### Demo data requirements

- Three or more events for one dish, on **distinct dates**, at midday, all outcome `BETTER`, all the same adjustment.
- No contradictory `WORSE` event for that dish and adjustment.
- Label the history as sample data.
- Use a separate user for negative and rejection tests so the demo user stays clean.
