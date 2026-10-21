# Auditable Memory for Alexa+

**Memory that shows its work.** A self-hosted MCP server that gives an Alexa+-style assistant a memory you can inspect, correct and trace.

Built for the **Amazon Developer Hackathon, Alexa+ track.**

> **Integration status:** The Alexa+-style conversation is a **web simulation**. The MCP server, memory engine and PostgreSQL database are real. This project does not integrate with or modify Alexa+'s internal memory. Alexa+ already has its own memory (Remember This). This is a complementary, independently built memory service.

## TL;DR

Assistants can remember preferences, but you usually can't see *where a memory came from, how it changed, or why the assistant believes it.* This project adds three guarantees:

1. **Provenance.** Every memory keeps your original words, a timestamp and a source type (`EXPLICIT` or `INFERRED_CONFIRMED`).
2. **Corrections with lineage.** Changing a preference marks the old claim `SUPERSEDED` and links it to the new one in one transaction. Nothing is silently overwritten.
3. **Evidence-backed insights.** A repeated pattern in your cooking history becomes a *candidate* insight that cites the exact events behind it. It only becomes a memory if you confirm it.

**Design rule:** the LLM interprets language and phrases replies. Deterministic code and database constraints decide what is active, what counts as evidence, and what can change state.

- **Live demo:** [auditable-memory-interface.onrender.com](https://auditable-memory-interface.onrender.com/) (first load may take about a minute while the free-tier host wakes up)
- **Demo video (under 3 min):** `<ADD YOUTUBE/VIMEO URL>`
- **Login:** username and password are in the Devpost *Testing Instructions*.
- **Run it yourself:** [Quick start](#quick-start-local)

## Contents

[How it works](#how-it-works) · [Architecture](#architecture) · [Quick start](#quick-start-local) · [Environment variables](#environment-variables) · [Verify the MCP server](#verify-the-mcp-server) · [MCP tools](#mcp-tools) · [Memory and insight model](#memory-and-insight-model) · [Tests](#tests) · [Trust boundary](#trust-boundary) · [Limitations](#limitations) · [More docs](#more-docs)

## How it works

```
You:        Remember that I prefer aisle seats on flights.
Assistant:  I'll remember that you prefer aisle seats on flights.

You:        Actually, change that to window seats.
Assistant:  Updated. Your preference is now window seats on flights.

            claim 1  aisle seats    SUPERSEDED  --superseded_by-->  claim 2
            claim 2  window seats   ACTIVE

You:        Why do you remember that?
Assistant:  (returns the stored source statement, its date and the correction history,
            read from the database rather than invented by the model)
```

For cooking, you log events ("made lentil soup with less salt, it was better") on different days. After three consistent observations the system proposes: *"You seem to prefer less salt when preparing lentil soup."* You see the three supporting events and choose **Confirm** or **Reject**.

## Architecture

```
React + TypeScript (conversation UI, memory ledger, history timeline)
        |   HTTPS + signed session cookie
        v
FastAPI (client/api.py): session validation, user authorization, conversation routing
        |                         |
        v                         v
LLM orchestrator (OpenAI)    MCP client (bearer token)
                                  |   Streamable HTTP
                                  v
                    MCP server (server.py, /mcp)
                                  |
                                  v
        Memory / corrections / events / insights services
                                  |
                                  v
                    PostgreSQL (claims, events, insights, insight_evidence)
```

| Responsibility | LLM | Application code and database |
|---|---|---|
| Interpret the request and extract arguments | yes | |
| Phrase replies and explanations from returned evidence | yes | |
| Decide which claim is active | | yes |
| Enforce state transitions and uniqueness | | yes |
| Atomic corrections | | yes |
| Event idempotency | | yes |
| Insight thresholds and contradiction rules | | yes |

## Quick start (local)

**Prerequisites:** Python 3.12, Node.js 20+, PostgreSQL 14+ with `psql`, an OpenAI API key.

> Use a dedicated, **empty, disposable** database. Never point schema or reset SQL at data you care about.

```bash
# 1. Backend dependencies
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Frontend dependencies
cd frontend && npm install && cd ..

# 3. Configuration (Windows: use `copy` instead of `cp`)
cp .env.example .env
cp frontend/.env.example frontend/.env.local
#   Edit both files. Generate each secret separately with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. Create the schema (psql uses the plain postgresql:// scheme)
psql "postgresql://USER:PASSWORD@HOST:5432/DBNAME" -f scripts/scripts.sql
```

Run each process in its own terminal from the project root with the virtualenv active:

```bash
python server.py                       # MCP server  -> http://localhost:8000/mcp
uvicorn client.api:app --port 8001     # FastAPI     -> http://localhost:8001
cd frontend && npm run dev             # Frontend    -> http://localhost:5173
```

Check the API with `curl http://localhost:8001/health` (expect `{"status":"ok"}`), then open http://localhost:5173 and sign in with a name from `ALLOWED_DEMO_USERS` and your `DEMO_ACCESS_PASSWORD`.

`scripts/scripts.sql` is a **fresh-database installer**, not a migration tool. It uses conditional statements and contains no `DROP`. Existing databases need separately reviewed `ALTER` statements.

## Environment variables

Backend (`.env`):

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | Async SQLAlchemy URL: `postgresql+asyncpg://user:pass@host:5432/db` |
| `MCP_SERVICE_TOKEN` | yes | Shared bearer token between FastAPI and the MCP server (min 32 chars) |
| `MCP_URL` | yes | MCP endpoint, e.g. `http://localhost:8000/mcp` |
| `PORT` | no | MCP server port (default `8000`) |
| `OPENAI_API_KEY` | yes | Intent extraction and reply phrasing |
| `MODEL` | yes | OpenAI model name used by the orchestrator |
| `ALLOWED_DEMO_USERS` | yes | Comma-separated user IDs allowed to sign in |
| `DEMO_ACCESS_PASSWORD` | yes | Shared demo password (min 32 chars) |
| `DEMO_SESSION_SECRET` | yes | Session cookie signing secret (min 32 chars) |

Frontend (`frontend/.env.local`): `VITE_API_BASE_URL=http://localhost:8001`

The app refuses to start if a required secret is missing or shorter than 32 characters. `VITE_` variables are bundled into browser code, so never put a token, key or database credential in one.

## Verify the MCP server

The MCP server speaks **Streamable HTTP**, negotiates protocol **2025-11-25**, and requires a bearer token. With the server running:

```bash
TOKEN=your-MCP_SERVICE_TOKEN
HDRS=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")

# No token -> 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/mcp "${HDRS[@]}" -d '{}'

# Initialize -> protocolVersion "2025-11-25"
curl -s -X POST http://localhost:8000/mcp "${HDRS[@]}" -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}'

# Discover tools -> 16 tools
curl -s -X POST http://localhost:8000/mcp "${HDRS[@]}" -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

The server is configured as stateless with JSON responses, so each request stands alone. You can also connect the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to `http://localhost:8000/mcp` with an `Authorization: Bearer ...` header.

## MCP tools

| Group | Tool | Purpose |
|---|---|---|
| Memory | `remember` | Store an explicit claim with its source utterance |
| | `recall` / `recall_all` | Active claims for a category, or all of them |
| | `explain` | A claim's provenance; for confirmed insights, also the supporting events |
| | `correct_memory` | Supersede the active claim for a `memory_key` and insert its replacement, atomically |
| | `forget` | Remove a claim from active recall (see [Limitations](#limitations)) |
| | `memory_history` | Every version of a memory, including superseded and forgotten |
| Events | `log_event` | Store a cooking event; idempotent per `(user_id, request_id)` |
| | `list_events` | List a user's events |
| Insights | `derive_insights` | Evaluate the rule without saving anything |
| | `save_insight_candidates` | Persist new candidates with their evidence |
| | `list_insights` / `get_insight_evidence` | Insights and the events behind them |
| | `confirm_insight` / `reject_insight` | The user's decision |
| System | `server_status` | Health check including a database round trip |

## Memory and insight model

**Claims.** Statuses are `ACTIVE`, `SUPERSEDED`, `FORGOTTEN`. A partial unique index allows at most one `ACTIVE` claim per `(user_id, category, memory_key)`. A correction locks the active row (`SELECT ... FOR UPDATE`), marks it `SUPERSEDED`, inserts the replacement under the same `memory_key`, and links `superseded_by_claim_id`, all in one transaction.

**Events.** A unique index on `(user_id, request_id)` plus a payload hash gives idempotency: a retry returns the original event, and the same ID with a changed payload returns `IDEMPOTENCY_CONFLICT`. Adjustment phrases are canonicalized (for example "reduced salt" becomes `less_salt`).

**Insights.** One rule, `REPEATED_ADJUSTMENT`:

- Considers cooking `meal_prepared` events with outcome `BETTER` or `WORSE`, grouped by dish and adjustment.
- Needs **at least three `BETTER` events on three distinct dates** (dates are counted in UTC).
- **Any matching `WORSE` event blocks the candidate.**
- The candidate saves a snapshot of its evidence events. Confirming re-checks the current history and fails with `INSIGHT_EVIDENCE_NO_LONGER_VALID` if it no longer supports the insight.
- **Confirm** creates a new `INFERRED_CONFIRMED` claim with its own memory key. It never overwrites an explicit memory. **Reject** is permanent for that dish and adjustment: it is not proposed again, even if new events arrive.
- A database CHECK constraint requires a confirmed insight to have a claim and a decision time.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q                  # backend
cd frontend && npm run build               # format check, lint, typecheck, production build
```

The backend suite is unit-level and mocks the database and OpenAI. Passing it does **not** establish end-to-end coverage. Manual scenarios and the insight test plan are in [docs/testing.md](docs/testing.md), kept separate from automated results.

## Trust boundary

This is a prototype. The boundaries are stated deliberately.

- **Browser to FastAPI.** Demo login with a shared password issues a signed, HTTP-only session cookie. Memory and insight routes require the session user to match the requested user (HTTP 403 otherwise). `/chat` records which user owns each `conversation_id` and rejects another user replaying it. Pending conversational state is keyed by `(conversation_id, user_id)`.
- **FastAPI to MCP server.** A **single static bearer token** authenticates the caller. MCP tools take `user_id` as a **client-supplied argument** that the MCP server does not independently verify. Anyone holding the token can operate on any allowed demo user's memories. Keep the token server-side and do not expose the MCP endpoint to untrusted clients.
- **Production design (not built).** OAuth account linking, so the MCP server derives the user from a verified token claim, plus per-resource authorization, token rotation and rate limiting.
- **Not implemented:** CSRF tokens (the cookie is `SameSite=None; Secure`, so protection relies on the CORS allowlist and JSON bodies), rate limiting on login or chat, token rotation.
- **Data handling.** Messages are sent to OpenAI for interpretation. Do not enter sensitive personal information in the public demo.

## Limitations

- **Simulated Alexa+.** No access to private Alexa+ add-on tooling, so a web UI stands in. No claim of native integration.
- **Forget is not erasure.** `forget` removes a claim from active recall, but its stored value and source utterance remain and appear in history. Source utterances also remain in event records. A production system needs a deletion and retention policy.
- **Narrow domain.** Food preferences and cooking events, one insight rule. No recommendation engine.
- **Insight rule edges.** Distinct dates use UTC, so evenings in US time zones can fall on the next UTC date. One `WORSE` event blocks a pattern permanently. Dish names are matched after lowercasing and whitespace cleanup only. Details in [docs/testing.md](docs/testing.md).
- **Sample data.** The cooking history in the demo is labelled sample data, not real long-term activity.
- **Not a safety system.** Memories can be wrong or stale. Do not rely on this for allergies or medical decisions.
- **Simple identity.** A fixed allowlist with a shared demo password. No household or voice identification.
- **Schema script** is an installer, not a migration framework.

## More docs

- [docs/friction.md](docs/friction.md): developer friction log and product feedback
- [docs/testing.md](docs/testing.md): manual verification and the insight test plan
- [docs/design-decisions.md](docs/design-decisions.md): why PostgreSQL, why preserve history, why confirm inferences, why deterministic rules

## Hackathon details

**Track:** Alexa+ (self-hosted MCP server, Streamable HTTP, protocol 2025-11-25, MCP Python SDK 2.x).
**Stack:** Python 3.12, FastAPI, SQLAlchemy (async) with asyncpg, PostgreSQL, OpenAI API, React, TypeScript, Vite, Tailwind CSS. Hosted on Render.
**Dependencies** keep their own licenses; see `requirements.txt` and `frontend/package.json`.

## License

MIT. See [LICENSE](LICENSE).