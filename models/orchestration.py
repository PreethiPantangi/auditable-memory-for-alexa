from typing import Literal

from pydantic import BaseModel, Field

from models.action import Action


class ContextResolution(BaseModel):
    status: Literal[
        "FOLLOW_UP",
        "NEW_REQUEST",
        "UNCLEAR",
    ]


class Actions(BaseModel):
    actions: list[Action]


class RecallRelevanceResult(BaseModel):
    status: Literal["MATCHED", "AMBIGUOUS", "NOT_FOUND"]

    selected_claim_ids: list[int]

    clarification_question: str | None


class MemoryRelevanceDecision(BaseModel):
    status: Literal["MATCHED", "AMBIGUOUS", "NOT_FOUND"]

    claims: list[dict]

    clarification_question: str | None


class MemoryConflict(BaseModel):
    claim_ids: list[int]

    subject: str

    attribute: str

    conflicting_values: list[str]


class ConflictAnalysis(BaseModel):
    conflicts: list[MemoryConflict] = Field(default_factory=list)


class ClarificationResolution(BaseModel):
    status: Literal[
        "SELECTED",
        "STILL_AMBIGUOUS",
        "NEW_REQUEST",
    ]

    memory_key: str | None


class CorrectionTargetResolution(BaseModel):
    status: Literal["MATCHED", "AMBIGUOUS", "NOT_FOUND"]

    memory_key: str | None


class PendingCorrectionResolution(BaseModel):
    status: Literal[
        "REPLACE",
        "FORGET",
        "CANCEL",
        "NEW_REQUEST",
        "UNCLEAR",
    ]

    replacement_value: str | None


# Preserve the original public identity for imports and pickle references.
ContextResolution.__module__ = "client.orchestrator"
Actions.__module__ = "client.orchestrator"
RecallRelevanceResult.__module__ = "client.orchestrator"
MemoryRelevanceDecision.__module__ = "client.orchestrator"
MemoryConflict.__module__ = "client.orchestrator"
ConflictAnalysis.__module__ = "client.orchestrator"
ClarificationResolution.__module__ = "client.orchestrator"
CorrectionTargetResolution.__module__ = "client.orchestrator"
PendingCorrectionResolution.__module__ = "client.orchestrator"


class ContextOperationResolution(BaseModel):
    status: Literal["MATCHED", "NEW_REQUEST", "UNCLEAR"]
    operation: Literal["CORRECT_MEMORY", "FORGET", "EXPLAIN", "NONE"]
    replacement_value: str | None


class ConversationDecision(BaseModel):
    target: Literal[
        "PREVIOUS_MEMORY",
        "NEW_REQUEST",
        "AMBIGUOUS",
    ]

    operation: Literal[
        "RECALL",
        "CORRECT_MEMORY",
        "FORGET",
        "EXPLAIN",
        "NONE",
    ]

    replacement_value: str | None
    clarification_question: str | None
