# Developer friction log and product feedback

**Project:** Auditable Memory for Alexa+, Amazon Developer Hackathon, Alexa+ track
**Build period:** October 6–21, 2026
**Stack:** MCP Python SDK (Streamable HTTP), FastAPI, OpenAI API, PostgreSQL with SQLAlchemy, React and TypeScript, Render

This log keeps the issues that cost real time or that point to a documentation or tooling gap. Entries describe what happened, not defects in Alexa+ itself.

## Summary

Making an MCP tool callable was the easy part. The hard part was making a browser conversation, LLM orchestration, a hosted MCP endpoint and a stateful database behave consistently across authentication, deployment, ambiguous language and retries. Four lessons mattered most:

- A tool call succeeding in Postman did not show that the hosted, authenticated, browser-to-backend-to-MCP flow worked.
- Failures at one boundary surfaced as misleading symptoms at another.
- An LLM schema and a database transaction solve different classes of correctness problem; an auditable system needs both.
- "Change that" is a write operation, not a read, and conversation routing has to treat it that way.

## Tools used

| Tool | Used for |
|---|---|
| MCP Python SDK, Streamable HTTP | The memory service and its 16 tools |
| OpenAI API (structured outputs) | Intent extraction, event extraction, reply phrasing |
| FastAPI | Browser-facing API, sessions, authorization |
| PostgreSQL, SQLAlchemy async, asyncpg | Claims, events, insights, constraints |
| Render | Hosting for the frontend, API and MCP server |
| React, TypeScript, Vite | Web simulation of the Alexa+-style conversation |

## Friction entries

Severity: **Blocker** stopped progress, **High** cost hours or hid a real failure, **Medium** caused a detour, **Low** minor.

### F1. No public Alexa+ add-on tooling for the intended prototype
**Severity:** High · **Date:** Oct 6 · **Area:** Scope and integration pathway
**Task:** Connect a self-hosted MCP memory service to Alexa+.
**Expected:** A clear path to test an MCP service against Alexa+.
**Actual:** No add-on toolkit, CLI or official simulator was available to this project. An earlier wearable concept was also dropped because of device access and demo risk.
**Workaround:** Built a real MCP server and a clearly labelled web simulation of the Alexa+-style conversation. No claim of native integration is made.
**Suggestion:** Documentation that separates *MCP-capable service*, *supported Alexa+ integration pathway* and *official testing or simulator availability* would remove early architectural uncertainty.

### F2. A passing tool call did not prove the Streamable HTTP lifecycle
**Severity:** Medium · **Date:** Oct 6 · **Area:** MCP testing
**Task:** Test the first MCP tool from Postman.
**Expected:** One request shows the server works.
**Actual:** A misspelled `jsonrpc` field cost time, and a direct `tools/call` succeeded without demonstrating initialization or discovery.
**Workaround:** Tested initialize, `tools/list`, a valid call, an invalid tool and invalid arguments separately, then used a real MCP client.
**Suggestion:** A small copy-pasteable test sequence (headers, initialization, `tools/list`, `tools/call`, structured result) in the hosting docs.

### F3. Hosted MCP returned HTTP 421 "Invalid Host header"
**Severity:** High · **Date:** Oct 9 · **Area:** Transport security and hosting
**Task:** Call the Render-hosted `/mcp` endpoint.
**Expected:** A valid bearer token is enough.
**Actual:** `421 Invalid Host header` even with a valid token.
**Workaround:** Added the Render hostname to the SDK's `TransportSecuritySettings` allowed hosts, keeping DNS-rebinding protection on. Requests then returned 200 and 202.
**Suggestion:** A prominent deployment recipe for managed hostnames that shows how to configure the allowlist without disabling protection, and a clearer distinction in diagnostics between a host rejection (421) and an authorization rejection (401).

### F4. A backend HTTP 200 hid an upstream MCP 401
**Severity:** High · **Date:** Oct 9 · **Area:** FastAPI to MCP error propagation
**Task:** Send a chat message through the hosted stack.
**Expected:** A failed tool call looks like a failure.
**Actual:** The browser received a successful FastAPI response while the downstream MCP call had failed with 401. The error was embedded in a payload.
**Workaround:** Verified the token and URL at both services and surfaced upstream authorization failures separately from tool results.
**Suggestion:** Guidance for multi-hop MCP deployments on propagating errors distinctly at each boundary.

### F5. MCP tool results were not always plain text
**Severity:** Medium · **Date:** Oct 9 · **Area:** MCP client
**Task:** Read a tool result in the orchestrator.
**Expected:** A text block in the result.
**Actual:** The client reported "no text response" although the call succeeded.
**Workaround:** Prefer `structuredContent` and fall back to text only when needed.
**Suggestion:** An example client showing the supported result shapes.

### F6. Strict OpenAI structured outputs rejected a flexible dictionary
**Severity:** Medium · **Date:** Oct 12 · **Area:** OpenAI API
**Task:** Extract cooking events whose attributes vary.
**Expected:** A permissive `dict[str, Any]` schema is accepted.
**Actual:** HTTP 400 because the schema did not meet strict-mode requirements (`additionalProperties: false`).
**Workaround:** A typed attributes model with an explicit schema and no extra fields.
**Suggestion:** Examples of flexible-but-finite attributes in strict mode, and a way to validate a schema before runtime.

### F7. Login succeeded but the session cookie was not sent
**Severity:** High · **Date:** Oct 9 · **Area:** Cross-origin browser auth
**Task:** Log in from the hosted frontend to the hosted API.
**Expected:** Login returns 200 and later requests are authenticated.
**Actual:** Login returned 200, then session and memory requests returned 401.
**Workaround:** Credentialed requests with matching cookie flags (`Secure`, `SameSite=None`), HTTPS and a credentialed CORS allowlist.
**Note:** This setup removes the browser's default CSRF protection; dedicated CSRF tokens are not implemented. This is disclosed in the README.

### F8. "Change that to window" performed a read, not a write
**Severity:** High · **Date:** Oct 13–16 · **Area:** Conversation routing
**Task:** Correct a preference with a pronoun reference.
**Expected:** The correction tool is called and state changes.
**Actual:** The phrase was classified as a generic follow-up, so the orchestrator ran `recall` and returned. Logs showed auth and the database read working but no update.
**Workaround:** Route contextual mutations (correct, forget) and provenance requests ahead of the read-only follow-up path, re-fetch the intended active claim, reject ambiguous targets, and assert in tests which MCP tool was actually called.
**Lesson:** Language classification passing is not enough; check which tool ran and whether state changed.

### F9. A correction was stored as a new memory
**Severity:** High · **Date:** Oct 12 · **Area:** Intent classification
**Task:** Change "likes spicy food" to "prefers mild food."
**Expected:** The existing claim is superseded.
**Actual:** "I prefer mild food" was treated as a new fact, creating a second active claim under a different memory key.
**Workaround:** Distinguish new facts from corrections, resolve the target claim, and call the correction tool.
**Lesson:** A database invariant cannot repair a semantic mistake that creates a different memory key.

### F10. Service authentication did not protect individual users
**Severity:** High · **Date:** Oct 9–19 · **Area:** Trust boundary
**Task:** Keep one user's memories private behind an MCP tool server.
**Actual:** Browser routes enforce session ownership, but the MCP endpoint authenticates one shared token and accepts `user_id` as a tool argument. A direct, token-authorized call could act on any allowed demo user.
**Current approach:** Token kept server-side, ownership enforced at the API boundary, limitation disclosed.
**Suggestion:** Documented patterns for user-scoped authorization behind an MCP tool server, so a service token is not mistaken for permission over every user's data.

### F11. Normalization passed unit tests but needed end-to-end checking
**Severity:** Medium · **Date:** Oct 12–14 · **Area:** Event data quality
**Task:** Turn "less salt" and "reduced salt" into one canonical adjustment before counting evidence.
**Actual:** Idempotency worked (retry returns the original event; changed payload returns a conflict), but equivalent phrasings were not consistently canonicalized when tested through real traffic.
**Workaround:** Normalize adjustments at validation and test the orchestrator-to-database path with a vocabulary of equivalent phrases. Matching contradictory outcomes were also made to block an insight.
**Lesson:** Deduplication and semantic normalization are different problems.

### F12. Deployment failed on one missing environment variable
**Severity:** Medium · **Date:** Oct 9 · **Area:** Hosting
**Task:** First Render deploy.
**Actual:** `Expected string or URL object, got None`, followed by a port-scan timeout that was only a secondary symptom.
**Workaround:** Set `DATABASE_URL` with the async driver scheme (`postgresql+asyncpg://`), bind to `0.0.0.0` and the assigned `PORT`.
**Lesson:** Read the first application exception in the logs before chasing the health-check symptom.

## What worked well

- The MCP Python SDK's Streamable HTTP server was straightforward to stand up and expose a tool surface with.
- Stateless JSON responses suited a hosted deployment.
- The bearer-token plus allowed-hosts model made the security boundary explicit.
- PostgreSQL constraints (partial unique index, row locks, CHECK) gave guarantees the LLM could not.

## Onboarding

Most onboarding time went to hosting (F3, F12) and authentication (F4, F7) rather than to MCP itself. A single end-to-end hosted sample would have shortened that.

## Would build with these tools again?

Yes. The protocol and SDK were a good fit for exposing a memory service as tools. The feedback below is about documentation and integration clarity, not about the approach.

## Feature requests

| Request | Why it matters | Priority |
|---|---|---|
| A minimal hosted MCP Streamable HTTP sample (initialization, host allowlist, reverse proxy, bearer auth, `tools/list`, structured results) | Removes the largest early time sink | Important |
| Documented user-scoped authorization patterns for MCP tool servers | Prevents a shared service token from becoming access to every user | Critical |
| Clear developer guidance on native Alexa+ integration vs independent MCP tooling vs web simulation | Lets teams scope correctly on day one | Important |
| Strict structured-output examples for flexible-but-finite attributes | Saves debugging time with strict schemas | Nice-to-have |

## Known limitations carried forward

- Native Alexa+ integration and real account linking were not built.
- The MCP service token is shared and not user-scoped.
- CSRF tokens, rate limiting and token rotation are not implemented.
- `forget` removes a claim from active recall but does not erase stored values or source utterances.
- Automated tests are unit-level; deployed, cross-user and concurrency behavior was checked manually.
- Insights use one rule and labelled sample history.