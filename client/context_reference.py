"""Non-LLM validation and routing guardrails for conversational references."""

import re

# Only run the contextual operation classifier for commands containing an
# anaphoric reference; ordinary category-specific actions retain their path.
_OPERATION = re.compile(
    r"\b(?:change|changed|correct|update|replace|switch|make|forget|delete|remove|"
    r"why|source|origin|where|remember)\b",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"\b(?:it|that|this|those|them|the previous one|the last one)\b", re.IGNORECASE
)


def verify_active_context_claim(
    context: dict,
    claims: list[dict],
    user_id: str | None = None,
) -> dict | None:
    """Require exactly one matching active version of the selected memory."""
    matched = [
        claim
        for claim in claims
        if str(claim.get("memory_key")) == str(context.get("memory_key"))
        and claim.get("category") == context.get("category")
        and claim.get("status") == "ACTIVE"
        and (user_id is None or claim.get("user_id") == user_id)
    ]
    return matched[0] if len(matched) == 1 else None


_MUTATION = re.compile(
    r"\b(?:change|changed|correct|update|replace|switch|make|forget|delete|remove)\b",
    re.IGNORECASE,
)


def is_referential_mutation(message: str) -> bool:
    """A rejected referential write must never fall back to a guessed target."""
    return bool(_MUTATION.search(message) and _REFERENCE.search(message))
