from pydantic import BaseModel

from enums.intent import MemoryIntent
from enums.category import MemoryCategory
from enums.scope import ExplainScope

class Action(BaseModel):
    intent: MemoryIntent
    category: MemoryCategory | None = None
    value: str | None = None
    memory_key: str | None = None
    explain_scope: ExplainScope | None = None