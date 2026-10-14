
from pydantic import BaseModel, ConfigDict

from enums.category import MemoryCategory
from enums.intent import MemoryIntent
from enums.scope import ExplainScope


class EventAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adjustment: str | None


class Action(BaseModel):
    intent: MemoryIntent
    category: MemoryCategory | None = None
    value: str | None = None
    memory_key: str | None = None
    explain_scope: ExplainScope | None = None
    domain: str | None = None
    event_type: str | None = None
    subject: str | None = None
    attributes: EventAttributes | None
    outcome: str | None = None
    occurred_at: str | None = None
