# Design decisions

This document explains the architectural choices, trade-offs and constraints behind **Auditable Memory for Alexa+**, built for the Amazon Developer Hackathon.

The project explores how an AI assistant can keep memory that users can inspect, correct and trace to its original evidence.

## Why PostgreSQL instead of relying on LLM memory alone?

The LLM interprets conversational language, extracts structured information and phrases responses. It is not the authoritative source of persistent memory state.

PostgreSQL provides transactions, row-level locking, constraints and indexes, so the application can enforce memory lifecycle rules independently of generated text. For example, a partial unique index allows at most one `ACTIVE` claim per `(user_id, category, memory_key)`, and a transaction keeps a correction consistent.

**Trade-off:** A database adds infrastructure, schema management and operational complexity. We accept that cost for traceability and enforceable integrity.

## Why preserve superseded memories?

Overwriting a preference destroys the evidence that it changed. When a memory is corrected, the previous claim becomes `SUPERSEDED`, a replacement is inserted, and the two are linked. Users can then see what was previously remembered and how it evolved.

**Trade-off:** Retaining previous claims creates privacy and retention responsibilities. In this prototype, `forget` removes a claim from active recall but does not permanently erase its stored content. Permanent deletion and a retention policy are future work.

## Why require confirmation for inferred memories?

Observed behavior is not always a stable preference. A user might change a recipe for a guest, experiment, or follow a temporary restriction. So the insights subsystem separates behavioral evidence from confirmed memory.

Repeated events may produce a candidate insight, but it must be explicitly confirmed before it creates an active `INFERRED_CONFIRMED` claim. A confirmed insight gets its **own memory key** and never overwrites an explicit claim.

**Trade-off:** Confirmation adds an interaction step, but avoids silently treating observed behavior as something the user said.

**Current status:** The inference feature is implemented but **experimental**. End-to-end validation is incomplete (see [testing.md](testing.md)), and the cooking-insights navigation entry is hidden in the public demo. *(Update this paragraph if you re-enable it.)*

## Why keep insight rules deterministic?

The system should be able to explain why an insight qualifies for confirmation using identifiable events and defined rules. "Deterministic" here means the same events, normalization rules and configuration always produce the same result. When new events arrive, the result can change, and that is intended.

The current `REPEATED_ADJUSTMENT` rule evaluates cooking events by dish, adjustment, outcome and date:

- At least three `BETTER` observations on **distinct UTC dates**.
- No matching contradictory `WORSE` observation.
- An evidence snapshot stored with the candidate.
- Revalidation against current history before confirmation.

The LLM can interpret a cooking statement and phrase an insight. Application code decides whether the evidence threshold is met.

**Trade-off:** Rules are easier to audit and test than a probabilistic recommender, but less flexible. The prototype has one insight type and known limitations around date handling and dish-name normalization.

## Why separate the MCP server from FastAPI?

FastAPI owns the browser-facing concerns: demo sessions, user authorization and conversation orchestration. The MCP server exposes memory, correction, event and insight operations through a standard tool interface over Streamable HTTP. This separates the conversational application from the memory service and gives other trusted MCP-compatible clients a possible integration path.

**Trade-off:** Two services add network, configuration, authentication and deployment complexity.

**Security limitation:** The prototype uses one shared bearer token, and the MCP server accepts `user_id` as a tool argument instead of verifying a user-scoped identity. A production integration would need stronger authorization at the MCP boundary.

## Why a web simulation of Alexa+?

No native Alexa+ integration pathway was available to this project, so the conversation is simulated in a React web interface connected to a real FastAPI backend, MCP server and PostgreSQL database. The hackathon's [official rules](https://amazonappdev2026.devpost.com/rules) list a simulated Alexa+ experience as an accepted alternative for the Alexa+ track, and this project also ships a working self-hosted MCP server over Streamable HTTP.

The simulation makes correction, provenance and history observable in a demo.

**Trade-off:** It demonstrates the external memory architecture. It does not prove native Alexa+ integration, account linking or compatibility with an official Alexa+ runtime. The simulation is labelled in the README and demo.

## Future work

- OAuth account linking and user-scoped MCP authorization
- Permanent erasure on forget with a defined retention policy
- Timezone-aware or explicitly declared cooking dates for insight evaluation
- Additional insight rules and configurable thresholds
- End-to-end tests of cooking insights, including confirmation, rejection and contradictory evidence
- Database-backed integration, concurrency and security regression tests
- Versioned database migrations
- Better event normalization and detection of conflicting preferences