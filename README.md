# Auditable Memory for Alexa+

Auditable Memory is a self-hosted MCP-based memory layer designed for Alexa+ style assistants.

The project focuses on a simple problem: assistants can remember user preferences, but users often cannot see **where a memory came from, how it changed, or why the assistant is using it**.

This project adds three core capabilities:

- **Provenance** — every stored memory keeps the original user statement, timestamp, and source.
- **Corrections that stick** — when a user changes a preference, the old memory is marked as superseded instead of silently overwritten.
- **Evidence-backed learning** — patterns learned from repeated user behavior are linked back to the events that produced them and can be confirmed or rejected.

The MVP focuses on food preferences and cooking history because these are easy to demonstrate across multiple sessions.

Example:

```text
User: Remember that I'm vegetarian.

Later...

User: Why did you suggest vegetarian pasta?

Assistant:
Because you told me on September 14:
"I'm vegetarian."
```

If the user later says:

```text
Actually, I eat fish now.
```

the system keeps the history:

```text
Vegetarian   → SUPERSEDED
Pescatarian  → ACTIVE
```

The goal is not just to give an assistant memory.

The goal is to build **memory that can explain itself**.

## Running the client

Run the client as a module from the project root (the directory containing
`models`, `enums`, and `client`):

```powershell
python -m client.orchestrator
```

To run the MCP client demo:

```powershell
python -m client.test_client
```

Running `python client/orchestrator.py` directly does not put the project root
on Python's import path, so imports such as `from models.action import Action`
cannot resolve. Install the dependencies from `requirements.txt` and configure
`OPENAI_API_KEY` and `MCP_URL` in your environment or `.env` before running.

## High-Level Architecture

```text
Web Conversation UI
        ↓
MCP Client
        ↓
Streamable HTTP
        ↓
MCP Server
        ↓
Memory Engine
        ↓
Persistent Storage
```

The MCP server exposes tools for remembering, recalling, explaining, correcting, forgetting, and learning from repeated events.

For the hackathon, the Alexa+ interaction is represented through a web-based simulation while the MCP server and memory behavior are fully functional.
