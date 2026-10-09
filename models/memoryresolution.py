from typing import Literal

from pydantic import BaseModel


class MemoryResolution(BaseModel):
    status: Literal["MATCHED", "NO_MATCH", "AMBIGUOUS"]
    memory_key: str | None = None
    claim_id: int | None = None
    requires_clarification: bool = False
    clarification_reason: str | None = None
