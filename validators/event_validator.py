from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from validators.event_normalizer import normalize_adjustment


class EventInput(BaseModel):
    user_id: str = Field(min_length=1)
    domain: str
    event_type: str
    subject: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    outcome: str | None = None
    source_utterance: str = Field(min_length=1)
    occurred_at: datetime | None = None
    request_id: UUID

    @field_validator("user_id", "subject", "source_utterance")
    @classmethod
    def validate_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_cooking_event(self):
        if self.domain != "cooking":
            raise ValueError("Unsupported event domain")

        if self.event_type != "meal_prepared":
            raise ValueError("Unsupported cooking event type")

        if self.outcome not in {None, "BETTER", "WORSE", "SAME", "UNKNOWN"}:
            raise ValueError("Invalid cooking outcome")

        adjustment = self.attributes.get("adjustment")

        if adjustment is not None:
            if not isinstance(adjustment, str) or not adjustment.strip():
                raise ValueError("Invalid cooking adjustment")

            self.attributes["adjustment"] = normalize_adjustment(adjustment)

        return self
