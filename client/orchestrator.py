import asyncio

import json

import logging

from typing import Literal

from uuid import UUID, uuid5


from dotenv import load_dotenv

from openai import OpenAI

from pydantic import BaseModel, Field

from sqlalchemy.exc import SQLAlchemyError


from client.conversation_state import (
    clear_pending_clarification,
    get_pending_clarification,
    save_pending_clarification,
    save_pending_correction,
)

from client.memory_context import (
    clear_memory_context,
    get_memory_context,
    save_memory_context,
)

from enums.intent import MemoryIntent

from enums.scope import ExplainScope

from models.action import Action

from models.memoryresolution import MemoryResolution

from prompts.intent_extraction import get_intent_extraction_prompt

from prompts.memory_conflicts import MEMORY_CONFLICT_PROMPT

from prompts.natural_response import NATURAL_RESPONSE_PROMPT

from prompts.relevant_memories import RELAVENT_MEMORIES_PROMPT

from prompts.resolve_clarification import RESOLVE_CLARIFICATION_PROMPT

from prompts.resolve_memory import RESOLVE_MEMORY_PROMPT


from .mcp_client import call_mcp_tool


load_dotenv()


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


client = OpenAI()

MODEL = "gpt-5.4-mini"


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


async def resolve_correction_target(
    message: str,
    claims: list[dict],
) -> CorrectionTargetResolution:

    candidates = [
        {
            "memory_key": str(claim["memory_key"]),
            "value": claim["value"],
        }
        for claim in claims
        if claim.get("status") == "ACTIVE"
    ]

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """

Identify the EXISTING memory targeted by

the user's correction request.



MATCHED:

Exactly one active memory clearly matches.



AMBIGUOUS:

Multiple active memories might match.



NOT_FOUND:

No existing memory can be identified reliably.



The user may say a preference is no longer true

without providing a replacement.



Example:

Old memory: "chocolate brownie with hot fudge"

User: "I no longer eat chocolate brownie

with hot fudge."

Result: MATCHED with that old memory's key.



Do not select a memory merely because it

belongs to the same category.



Return only a memory_key supplied in candidates.

Do not invent keys.

""",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "candidates": candidates,
                    }
                ),
            },
        ],
        text_format=CorrectionTargetResolution,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError("Correction target resolution failed.")

    valid_keys = {candidate["memory_key"] for candidate in candidates}

    if parsed.status == "MATCHED":
        if parsed.memory_key not in valid_keys:
            raise ValueError("Invalid correction target.")

    elif parsed.memory_key is not None:
        raise ValueError("Unexpected correction target.")

    return parsed


async def resolve_pending_correction_reply(
    message: str,
    pending: dict,
    active_claim: dict,
) -> PendingCorrectionResolution:

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """

A user was asked whether to forget an

existing memory or replace it.



Classify the latest user message.



REPLACE:

The user clearly provides a complete new

replacement value for the targeted memory.

Extract the standalone replacement fact.



FORGET:

The user explicitly chooses to forget/remove

the targeted saved memory.



CANCEL:

The user explicitly cancels the operation.



NEW_REQUEST:

The user clearly starts an unrelated request.



UNCLEAR:

The message is ambiguous, incomplete, or

only chooses "replace" without giving a

replacement value.



Examples:

Old: "chocolate brownie with hot fudge"



"I now eat chocolate brownie without hot fudge"

-> REPLACE

replacement_value:

"eats chocolate brownie without hot fudge"



"Replace it"

-> UNCLEAR



"Forget that preference"

-> FORGET



"Never mind"

-> CANCEL



"What's my hiking preference?"

-> NEW_REQUEST



Do not infer a replacement from the old claim.

Do not store instructions, questions, or a

bare yes/no as replacement values.



For statuses other than REPLACE,

replacement_value must be null.

""",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "original_request": pending["original_question"],
                        "old_memory": active_claim["value"],
                        "latest_message": message,
                    }
                ),
            },
        ],
        text_format=PendingCorrectionResolution,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError("Pending correction resolution failed.")

    if parsed.status == "REPLACE":
        if not parsed.replacement_value:
            raise ValueError("Replacement value is missing.")

        if not parsed.replacement_value.strip():
            raise ValueError("Replacement value is empty.")

    elif parsed.replacement_value is not None:
        raise ValueError("Unexpected replacement value.")

    return parsed


async def classify_context_followup(
    message: str,
    claim: dict,
) -> ContextResolution:

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """

Determine whether the user's latest message

refers to the previously retrieved memory.



FOLLOW_UP:

The message clearly requests information

about the previous memory.



NEW_REQUEST:

The message introduces a separate request

or clearly refers to another subject.



UNCLEAR:

The reference cannot be established reliably.



Do not invent facts.

A new request for correction, deletion, or saving

must not be classified as a factual follow-up.





Important classification rules:



1. FOLLOW_UP includes questions about the previous

   memory, even when the requested detail is absent

   from that memory.



2. Missing information does not mean NEW_REQUEST.



3. Examples:

   Previous memory: Mom's apple pie recipe.



   "How many eggs?" -> FOLLOW_UP

   "How much butter?" -> FOLLOW_UP

   "What temperature?" -> FOLLOW_UP

   "How long should I bake it?" -> FOLLOW_UP



4. NEW_REQUEST applies when the user clearly

   introduces another subject, such as:

   "What about Grandma's banana recipe?"



5. Never invent missing information.



Broad memory discovery questions are NEW_REQUEST,

even when an active memory exists.



Examples:

"What recipe did I share earlier?" -> NEW_REQUEST

"What recipes do you remember?" -> NEW_REQUEST

"Which food preferences have I saved?" -> NEW_REQUEST



FOLLOW_UP should apply when the message clearly

continues discussing the previously selected memory.



Examples:

"How long should I bake it?" -> FOLLOW_UP

"What temperature?" -> FOLLOW_UP

"How much sugar?" -> FOLLOW_UP

"How many eggs?" -> FOLLOW_UP



A missing ingredient or field does not make

a contextual question a NEW_REQUEST.





""",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "previous_memory": claim["value"],
                    }
                ),
            },
        ],
        text_format=ContextResolution,
    )

    if response.output_parsed is None:
        raise ValueError("Context classification failed.")

    return response.output_parsed


async def try_contextual_recall(
    user_id: str,
    conversation_id: str,
    message: str,
) -> dict | None:

    context = await get_memory_context(user_id, conversation_id)

    if context is None:
        return None

    logger.info(
        "R3-06 context: user=%s conversation=%s context=%s",
        user_id,
        conversation_id,
        context,
    )

    result = await call_mcp_tool(
        tool_name=MemoryIntent.RECALL.value,
        args={
            "user_id": user_id,
            "category": context["category"],
        },
    )

    if not result.get("success"):
        raise RuntimeError("Memory validation failed.")

    claims = [
        claim
        for claim in result.get("data", [])
        if claim.get("memory_key") == str(context["memory_key"])
        and claim.get("status") == "ACTIVE"
    ]

    if len(claims) != 1:
        await clear_memory_context(user_id, conversation_id)

        return None

    claim = claims[0]

    decision = await classify_context_followup(message, claim)

    logger.info(
        "R3-06 decision: message=%r status=%s memory_key=%s",
        message,
        decision.status,
        claim["memory_key"],
    )

    if decision.status != "FOLLOW_UP":
        return None

    actions = [
        {
            "intent": MemoryIntent.RECALL.value,
            "category": claim["category"],
            "result": {
                "success": True,
                "data": [claim],
            },
        }
    ]

    natural_response = await generate_natural_response(
        user_message=message,
        results=actions,
    )

    return {
        "message": natural_response,
        "actions": actions,
    }


async def resolve_pending_reply(
    latest_message: str,
    pending: dict,
    candidate_claims: list[dict],
) -> ClarificationResolution:

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": RESOLVE_CLARIFICATION_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "original_question": pending["original_question"],
                        "clarification_question": pending["clarification_question"],
                        "latest_message": latest_message,
                        "candidate_memories": [
                            {
                                "memory_key": claim["memory_key"],
                                "value": claim["value"],
                            }
                            for claim in candidate_claims
                        ],
                    }
                ),
            },
        ],
        text_format=ClarificationResolution,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError("Clarification resolver returned no result.")

    allowed_keys = {claim["memory_key"] for claim in candidate_claims}

    if parsed.status == "SELECTED":
        if parsed.memory_key not in allowed_keys:
            raise ValueError("Resolver selected an invalid memory key.")

    elif parsed.memory_key is not None:
        raise ValueError("Unexpected memory key for unresolved reply.")

    return parsed


async def filter_relevant_memories(
    user_message: str,
    claims: list[dict],
) -> MemoryRelevanceDecision:

    if not claims:
        return MemoryRelevanceDecision(
            status="NOT_FOUND",
            claims=[],
            clarification_question=None,
        )

    valid_claims = {
        int(claim["claim_id"]): claim
        for claim in claims
        if claim.get("claim_id") is not None
    }

    candidates = [
        {
            "claim_id": claim_id,
            "category": claim.get("category"),
            "value": claim.get("value"),
        }
        for claim_id, claim in valid_claims.items()
    ]

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": RELAVENT_MEMORIES_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_message": user_message,
                        "candidate_memories": candidates,
                    }
                ),
            },
        ],
        text_format=RecallRelevanceResult,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError("Memory relevance returned no result.")

    selected_ids = set(parsed.selected_claim_ids)

    if not selected_ids.issubset(valid_claims.keys()):
        raise ValueError("Relevance selected unknown claim IDs.")

    selected_claims = [
        claim for claim_id, claim in valid_claims.items() if claim_id in selected_ids
    ]

    if parsed.status == "MATCHED" and not selected_claims:
        raise ValueError("MATCHED requires a selected claim.")

    if parsed.status == "NOT_FOUND" and selected_claims:
        raise ValueError("NOT_FOUND cannot contain selected claims.")

    if parsed.status == "AMBIGUOUS":
        if len(selected_claims) < 2 or not parsed.clarification_question:
            raise ValueError("Invalid ambiguous memory selection.")

    elif parsed.clarification_question is not None:
        raise ValueError("Only ambiguous results may include a clarification question.")

    return MemoryRelevanceDecision(
        status=parsed.status,
        claims=selected_claims,
        clarification_question=parsed.clarification_question,
    )


async def fallback_food_memory_recall(
    user_id: str,
    user_message: str,
) -> dict:

    recall_result = await call_mcp_tool(
        tool_name=MemoryIntent.RECALL.value,
        args={
            "user_id": user_id,
            "category": "food_preference",
        },
    )

    if not recall_result.get("success"):
        return recall_result

    claims = recall_result.get("data", [])

    if not isinstance(claims, list):
        raise TypeError("Unexpected recall result format.")

    decision = await filter_relevant_memories(
        user_message=user_message,
        claims=claims,
    )

    return await apply_recall_decision(
        user_message=user_message,
        recall_result=recall_result,
        decision=decision,
    )


async def resolve_memory(
    user_message: str, claims: list[dict], intent: MemoryIntent
) -> MemoryResolution:

    response = client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": RESOLVE_MEMORY_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "intent": intent.value,
                        "message": user_message,
                        "candidate_memories": claims,
                    },
                    default=str,
                ),
            },
        ],
        text_format=MemoryResolution,
    )

    return response.output_parsed


async def detect_memory_conflicts(
    user_message: str,
    claims: list[dict],
) -> ConflictAnalysis:

    if len(claims) < 2:
        return ConflictAnalysis(conflicts=[])

    candidates = [
        {
            "claim_id": claim["claim_id"],
            "memory_key": claim.get("memory_key"),
            "status": claim.get("status"),
            "value": claim.get("value"),
        }
        for claim in claims
    ]

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": MEMORY_CONFLICT_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": user_message,
                        "claims": candidates,
                    }
                ),
            },
        ],
        text_format=ConflictAnalysis,
    )

    analysis = response.output_parsed

    if analysis is None:
        raise ValueError("Conflict detection returned no result.")

    valid_ids = {int(claim["claim_id"]) for claim in claims}

    for conflict in analysis.conflicts:
        ids = conflict.claim_ids

        if len(set(ids)) < 2:
            raise ValueError("A conflict requires two distinct claims.")

        if not set(ids).issubset(valid_ids):
            raise ValueError("Conflict references an unknown claim.")

        if len(conflict.conflicting_values) < 2:
            raise ValueError("Conflicting values are missing.")

    return analysis


async def apply_recall_decision(
    user_message: str,
    recall_result: dict,
    decision: MemoryRelevanceDecision,
) -> dict:

    if decision.status == "AMBIGUOUS":
        return {
            "success": False,
            "error": {
                "code": "AMBIGUOUS_MEMORY",
                "message": decision.clarification_question,
            },
            "data": decision.claims,
        }

    if decision.status == "NOT_FOUND":
        return {
            **recall_result,
            "data": [],
        }

    conflict_analysis = await detect_memory_conflicts(
        user_message=user_message,
        claims=decision.claims,
    )

    if conflict_analysis.conflicts:
        return {
            "success": False,
            "error": {
                "code": "CONFLICTING_MEMORIES",
                "message": (
                    "I found conflicting saved information. "
                    "Please clarify which value is correct."
                ),
            },
            "data": decision.claims,
            "conflicts": [
                conflict.model_dump() for conflict in conflict_analysis.conflicts
            ],
        }

    return {
        **recall_result,
        "data": decision.claims,
    }


async def execute_action(
    user_id: str,
    message: str,
    action: Action,
    request_id: str | None = None,
    action_index: int = 0,
):

    match action.intent:
        case MemoryIntent.LOG_EVENT:
            if request_id is None:
                return {
                    "success": False,
                    "error": {
                        "code": "REQUEST_ID_REQUIRED",
                        "message": "A request ID is required to log an event.",
                    },
                }

            if (
                action.domain != "cooking"
                or action.event_type != "meal_prepared"
                or not action.subject
                or not action.subject.strip()
            ):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_EVENT",
                        "message": "A supported cooking event and dish are required.",
                    },
                }

            event_request_id = str(
                uuid5(
                    UUID(request_id),
                    f"log_event:{action_index}",
                )
            )

            return await call_mcp_tool(
                tool_name=MemoryIntent.LOG_EVENT.value,
                args={
                    "user_id": user_id,
                    "domain": action.domain,
                    "event_type": action.event_type,
                    "subject": action.subject,
                    "attributes": (
                        action.attributes.model_dump(exclude_none=True)
                        if action.attributes is not None
                        else {}
                    ),
                    "outcome": action.outcome,
                    "source_utterance": message,
                    "occurred_at": action.occurred_at,
                    "request_id": event_request_id,
                },
            )

        case MemoryIntent.REMEMBER:
            return await call_mcp_tool(
                tool_name=MemoryIntent.REMEMBER.value,
                args={
                    "user_id": user_id,
                    "category": action.category.value,
                    "value": action.value,
                    "source_utterance": message,
                },
            )

        case MemoryIntent.RECALL:
            return await call_mcp_tool(
                tool_name=MemoryIntent.RECALL.value,
                args={"user_id": user_id, "category": action.category.value},
            )

        case MemoryIntent.CORRECT_MEMORY:
            if not action.value or not action.value.strip():
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": "What would you like to change this preference to?",
                    },
                }

            recall_result = await call_mcp_tool(
                tool_name=MemoryIntent.RECALL.value,
                args={"user_id": user_id, "category": action.category.value},
            )

            if not recall_result["success"]:
                return recall_result

            claims = recall_result["data"]

            if not claims:
                return {
                    "success": False,
                    "error": {
                        "code": "NO_ACTIVE_CLAIM",
                        "message": (
                            "I couldn't find an existing memory to correct. Would you like me to save this as a new memory?"
                        ),
                    },
                }

            resolution = await resolve_memory(
                user_message=message, claims=claims, intent=MemoryIntent.CORRECT_MEMORY
            )

            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        ),
                    },
                }

            if resolution.status == "AMBIGUOUS":
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_MEMORY",
                        "message": (
                            "Multiple memories could match. Please specify which one to correct."
                        ),
                    },
                }

            if resolution.status != "MATCHED":
                return {
                    "success": False,
                    "error": {
                        "code": "MEMORY_NOT_FOUND",
                        "message": (
                            "I couldn't identify which existing memory you want to correct."
                        ),
                    },
                }

            valid_keys = {claim["memory_key"] for claim in claims}

            if resolution.memory_key not in valid_keys:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_MEMORY_KEY",
                        "message": "Memory resolution failed.",
                    },
                }

            return await call_mcp_tool(
                tool_name=MemoryIntent.CORRECT_MEMORY.value,
                args={
                    "user_id": user_id,
                    "category": action.category.value,
                    "memory_key": resolution.memory_key,
                    "value": action.value,
                    "source_utterance": message,
                },
            )

        case MemoryIntent.FORGET:
            recall_result = await call_mcp_tool(
                tool_name=MemoryIntent.RECALL.value,
                args={"user_id": user_id, "category": action.category.value},
            )

            if not recall_result["success"]:
                return recall_result

            claims = recall_result["data"]

            if not claims:
                return {
                    "success": False,
                    "error": {
                        "code": "NO_ACTIVE_CLAIM",
                        "message": "No active memory found.",
                    },
                }

            resolution = await resolve_memory(
                user_message=message, claims=claims, intent=MemoryIntent.FORGET
            )

            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        ),
                    },
                }

            if resolution.status != "MATCHED":
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_MEMORY"
                        if resolution.status == "AMBIGUOUS"
                        else "MEMORY_NOT_FOUND",
                        "message": "Could not identify which memory to forget.",
                    },
                }

            if resolution.memory_key not in {claim["memory_key"] for claim in claims}:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_MEMORY_KEY",
                        "message": "Resolved memory was not found.",
                    },
                }

            return await call_mcp_tool(
                tool_name=MemoryIntent.FORGET.value,
                args={
                    "user_id": user_id,
                    "category": action.category.value,
                    "memory_key": resolution.memory_key,
                },
            )

        case MemoryIntent.MEMORY_HISTORY:
            return await call_mcp_tool(
                tool_name=MemoryIntent.MEMORY_HISTORY.value,
                args={"user_id": user_id, "category": action.category.value},
            )

        case MemoryIntent.EXPLAIN:
            is_current = action.explain_scope == ExplainScope.CURRENT

            tool_name = (
                MemoryIntent.RECALL.value
                if is_current
                else MemoryIntent.MEMORY_HISTORY.value
            )

            result = await call_mcp_tool(
                tool_name=tool_name,
                args={"user_id": user_id, "category": action.category.value},
            )

            if not result["success"]:
                return result

            claims = result["data"]

            if not claims:
                return {
                    "success": False,
                    "error": {
                        "code": "MEMORY_NOT_FOUND",
                        "message": "No matching memory exists.",
                    },
                }

            resolution = await resolve_memory(
                user_message=message, claims=claims, intent=MemoryIntent.EXPLAIN
            )

            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        ),
                    },
                }

            if resolution.status != "MATCHED":
                return {
                    "success": False,
                    "error": {
                        "code": (
                            "AMBIGUOUS_MEMORY"
                            if resolution.status == "AMBIGUOUS"
                            else "MEMORY_NOT_FOUND"
                        ),
                        "message": "Could not uniquely identify the memory.",
                    },
                }

            if is_current:
                matching_claims = [
                    claim
                    for claim in claims
                    if claim["memory_key"] == resolution.memory_key
                    and claim["status"] == "ACTIVE"
                ]

            else:
                matching_claims = [
                    claim
                    for claim in claims
                    if claim["memory_key"] == resolution.memory_key
                    and claim["claim_id"] == resolution.claim_id
                ]

            if len(matching_claims) != 1:
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_CLAIM_VERSION",
                        "message": "Could not uniquely identify the claim version.",
                    },
                }

            return await call_mcp_tool(
                tool_name=MemoryIntent.EXPLAIN.value,
                args={"claim_id": matching_claims[0]["claim_id"], "user_id": user_id},
            )

        case _:
            return {
                "success": False,
                "error": {
                    "code": "UNKNOWN_INTENT",
                    "message": f"Unknown intent: {action.intent}",
                },
            }


async def generate_natural_response(user_message: str, results: list[dict]) -> str:

    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": NATURAL_RESPONSE_PROMPT},
            {
                "role": "user",
                "content": f"""

                    Original user message:

                    {user_message}



                    Structured results:

                    {json.dumps(results, indent=2, default=str)}

                """,
            },
        ],
    )

    return response.output_text


async def handle_pending_correction(
    user_id: str,
    conversation_id: str,
    message: str,
    pending: dict,
) -> dict | None:

    category = pending["category"]

    memory_key = pending["target_memory_key"]

    # Determine whether the user is continuing the

    # clarification before attempting any write.

    # Fetch the target first so the classifier has

    # its actual previous value.

    recall_result = await call_mcp_tool(
        tool_name=MemoryIntent.RECALL.value,
        args={
            "user_id": user_id,
            "category": category,
        },
    )

    if not recall_result.get("success"):
        return {
            "message": "I couldn't verify the memory right now.",
            "actions": [],
        }

    active_claims = [
        claim
        for claim in recall_result.get("data", [])
        if str(claim.get("memory_key")) == memory_key
        and claim.get("status") == "ACTIVE"
    ]

    if len(active_claims) != 1:
        await clear_pending_clarification(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        await clear_memory_context(user_id, conversation_id)

        return {
            "message": (
                "That memory has changed or is no longer "
                "active. Please start the correction again."
            ),
            "actions": [],
        }

    claim = active_claims[0]

    decision = await resolve_pending_correction_reply(
        message=message,
        pending=pending,
        active_claim=claim,
    )

    logger.info(
        "Pending correction: user=%s status=%s target=%s",
        user_id,
        decision.status,
        memory_key,
    )

    if decision.status == "NEW_REQUEST":
        await clear_pending_clarification(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        return None  # Continue normal message handling

    if decision.status == "CANCEL":
        await clear_pending_clarification(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        return {
            "message": "Okay, I haven't changed that memory.",
            "actions": [],
        }

    if decision.status == "UNCLEAR":
        return {
            "message": pending["clarification_question"],
            "actions": [
                {
                    "intent": MemoryIntent.CORRECT_MEMORY.value,
                    "category": category,
                    "result": {
                        "success": False,
                        "error": {
                            "code": "CLARIFICATION_REQUIRED",
                            "message": pending["clarification_question"],
                        },
                    },
                }
            ],
        }

    if decision.status == "FORGET":
        intent = MemoryIntent.FORGET

        args = {
            "user_id": user_id,
            "category": category,
            "memory_key": memory_key,
        }

    else:
        intent = MemoryIntent.CORRECT_MEMORY

        args = {
            "user_id": user_id,
            "category": category,
            "memory_key": memory_key,
            "value": decision.replacement_value,
            "source_utterance": message,
        }

    result = await call_mcp_tool(
        tool_name=intent.value,
        args=args,
    )

    actions = [
        {
            "intent": intent.value,
            "category": category,
            "result": result,
        }
    ]

    if result.get("success") is not True:
        return {
            "message": result.get("error", {}).get(
                "message",
                "I couldn't complete that memory change.",
            ),
            "actions": actions,
        }

    # Only clear pending state after confirmed success.

    await clear_pending_clarification(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    # Invalidate the previously retrieved claim;

    # the next recall will load the current version.

    await clear_memory_context(user_id, conversation_id)

    response = await generate_natural_response(
        user_message=message,
        results=actions,
    )

    return {
        "message": response,
        "actions": actions,
    }


async def handle_user_message(
    user_id: str,
    message: str,
    request_id: str | None = None,
    conversation_id: str | None = None,
):

    if conversation_id is not None:
        pending = await get_pending_clarification(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        if pending is not None:
            if pending["operation"] == "correct_memory":
                correction_response = await handle_pending_correction(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message=message,
                    pending=pending,
                )

                if correction_response is not None:
                    return correction_response

                # The pending operation was cancelled by an unrelated

                # new request. Continue with normal intent extraction.

                pending = None

            if pending is not None and pending["operation"] == "recall":
                recall_result = await call_mcp_tool(
                    tool_name=MemoryIntent.RECALL.value,
                    args={
                        "user_id": user_id,
                        "category": pending["category"],
                    },
                )

                if not recall_result.get("success"):
                    return {
                        "message": "I couldn't retrieve the saved memories right now.",
                        "actions": [],
                    }

                allowed_keys = set(pending["candidate_memory_keys"])

                candidate_claims = [
                    claim
                    for claim in recall_result.get("data", [])
                    if claim.get("memory_key") in allowed_keys
                    and claim.get("status") == "ACTIVE"
                ]

                resolution = await resolve_pending_reply(
                    latest_message=message,
                    pending=pending,
                    candidate_claims=candidate_claims,
                )

                if resolution.status == "SELECTED":
                    selected_claims = [
                        claim
                        for claim in candidate_claims
                        if claim["memory_key"] == resolution.memory_key
                    ]

                    if len(selected_claims) != 1:
                        await clear_pending_clarification(
                            conversation_id=conversation_id,
                            user_id=user_id,
                        )
                        return {
                            "message": "That memory has changed. Please ask again.",
                            "actions": [],
                        }

                    await save_memory_context(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        claim=selected_claims[0],
                    )

                    await clear_pending_clarification(
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )

                    result = {
                        "success": True,
                        "data": selected_claims,
                    }

                    actions = [
                        {
                            "intent": MemoryIntent.RECALL.value,
                            "category": pending["category"],
                            "result": result,
                        }
                    ]

                    natural_response = await generate_natural_response(
                        user_message=(
                            f"{pending['original_question']} User clarified: {message}"
                        ),
                        results=actions,
                    )

                    return {
                        "message": natural_response,
                        "actions": actions,
                    }

                if resolution.status == "STILL_AMBIGUOUS":
                    return {
                        "message": pending["clarification_question"],
                        "actions": [
                            {
                                "intent": MemoryIntent.RECALL.value,
                                "category": pending["category"],
                                "result": {
                                    "success": False,
                                    "error": {
                                        "code": "AMBIGUOUS_MEMORY",
                                        "message": pending["clarification_question"],
                                    },
                                    "data": candidate_claims,
                                },
                            }
                        ],
                    }

                if resolution.status == "NEW_REQUEST":
                    await clear_pending_clarification(
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )

                    # Continue to normal intent extraction.

        # Resolve follow-ups against the last retrieved memory.

    if conversation_id is not None:
        context_response = await try_contextual_recall(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
        )

        if context_response is not None:
            return context_response

    # 1. Extract memory actions from the user message.

    response = await asyncio.to_thread(
        client.responses.parse,
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": get_intent_extraction_prompt(),
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        text_format=Actions,
    )

    if response.output_parsed is None:
        raise ValueError("Intent extraction returned no result.")

    actions = response.output_parsed.actions

    logger.info(
        "CORRECTION DEBUG: message=%r actions=%s conversation_id=%s",
        message,
        [action.model_dump(mode="json") for action in actions],
        conversation_id,
    )

    results = []

    # Start a multi-turn correction when the

    # replacement value has not been supplied.

    incomplete_corrections = [
        action
        for action in actions
        if action.intent == MemoryIntent.CORRECT_MEMORY
        and (action.value is None or not action.value.strip())
    ]

    if incomplete_corrections:
        if len(actions) != 1:
            return {
                "message": (
                    "Please handle the correction separately from your other requests."
                ),
                "actions": [],
            }

        action = incomplete_corrections[0]

        if action.category is None:
            return {
                "message": "Which preference would you like to change?",
                "actions": [],
            }

        category = action.category.value

        if conversation_id is None:
            return {
                "message": (
                    "I need an active conversation to continue this correction."
                ),
                "actions": [],
            }

        recall_result = await call_mcp_tool(
            tool_name=MemoryIntent.RECALL.value,
            args={
                "user_id": user_id,
                "category": category,
            },
        )

        if not recall_result.get("success"):
            return {
                "message": "I couldn't retrieve the existing memory.",
                "actions": [],
            }

        target = await resolve_correction_target(
            message=message,
            claims=recall_result.get("data", []),
        )

        if target.status == "NOT_FOUND":
            return {
                "message": (
                    "I couldn't identify an existing memory "
                    "to correct. Which one do you mean?"
                ),
                "actions": [],
            }

        if target.status == "AMBIGUOUS":
            return {
                "message": (
                    "Multiple memories might match. Please "
                    "identify the specific one to change."
                ),
                "actions": [],
            }

        question = (
            "Would you like me to forget that preference "
            "or replace it? If replacing it, tell me "
            "the new preference."
        )

        await save_pending_correction(
            conversation_id=conversation_id,
            user_id=user_id,
            original_question=message,
            category=category,
            target_memory_key=target.memory_key,
            clarification_question=question,
        )

        return {
            "message": question,
            "actions": [
                {
                    "intent": MemoryIntent.CORRECT_MEMORY.value,
                    "category": category,
                    "result": {
                        "success": False,
                        "error": {
                            "code": "CLARIFICATION_REQUIRED",
                            "message": question,
                        },
                    },
                }
            ],
        }

    print("USER MESSAGE:", message)

    print("EXTRACTED ACTIONS:", actions)

    # 2. Handle messages without extracted memory actions.

    if not actions:
        print("NO ACTIONS EXTRACTED")

        # Only attempt this fallback for information-seeking

        # questions, not every casual message.

        question_starters = (
            "what ",
            "which ",
            "who ",
            "where ",
            "when ",
            "how ",
            "why ",
            "do you remember",
            "can you recall",
            "tell me",
            "remind me",
        )

        normalized = message.strip().lower()

        should_try_recall = normalized.endswith("?") or normalized.startswith(
            question_starters
        )

        logger.info(
            "R3-06 fallback entered: message=%r",
            message,
        )

        if should_try_recall:
            try:
                recall_result = await fallback_food_memory_recall(
                    user_id=user_id,
                    user_message=message,
                )

                results = [
                    {
                        "intent": MemoryIntent.RECALL.value,
                        "category": "food_preference",
                        "result": recall_result,
                    }
                ]

                # Persist clarification generated by fallback recall.

                if (
                    conversation_id is not None
                    and recall_result.get("error", {}).get("code") == "AMBIGUOUS_MEMORY"
                ):
                    candidates = recall_result.get("data", [])

                    question = recall_result["error"]["message"]

                    if len(candidates) >= 2:
                        await save_pending_clarification(
                            conversation_id=conversation_id,
                            user_id=user_id,
                            original_question=message,
                            category="food_preference",
                            candidate_memory_keys=[
                                claim["memory_key"] for claim in candidates
                            ],
                            clarification_question=question,
                        )

                if len(results) == 1:
                    operation = results[0]

                    operation_result = operation["result"]

                    if (
                        operation["intent"] == MemoryIntent.RECALL.value
                        and operation_result.get("error", {}).get("code")
                        == "CONFLICTING_MEMORIES"
                    ):
                        conflicts = operation_result.get("conflicts", [])

                        if conflicts:
                            conflict = conflicts[0]

                            # Display only the values supplied in the

                            # structured conflict analysis.

                            values = conflict["conflicting_values"]

                            message_text = (
                                f"I found conflicting saved information about "
                                f"{conflict['attribute']} for {conflict['subject']}: "
                                + " versus ".join(values)
                                + ". Which value should I use?"
                            )

                            return {
                                "message": message_text,
                                "actions": results,
                            }

                # Save the last successfully retrieved memory

                # for subsequent conversational follow-ups.

                if conversation_id is not None and recall_result.get("success") is True:
                    matched_claims = recall_result.get("data", [])

                    if len(matched_claims) == 1:
                        await save_memory_context(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            claim=matched_claims[0],
                        )

                natural_response = await generate_natural_response(
                    user_message=message,
                    results=results,
                )

                return {
                    "message": natural_response,
                    "actions": results,
                }

            except (ValueError, TimeoutError, SQLAlchemyError):
                logger.exception("Fallback memory recall failed")

                return {
                    "message": "I couldn't retrieve your memories right now.",
                    "actions": [],
                }

        natural_response = await generate_natural_response(
            user_message=message,
            results=[],
        )

        return {
            "message": natural_response,
            "actions": [],
        }

    # 3. Execute each extracted action.

    for index, action in enumerate(actions):
        category = action.category.value if action.category is not None else None

        print(f"ACTION: {action.intent.value}, CATEGORY: {category}")

        # Validate the category before MCP operations.

        if category is None and action.intent != MemoryIntent.LOG_EVENT:
            result = {
                "success": False,
                "error": {
                    "code": "CLARIFICATION_REQUIRED",
                    "message": (
                        "Which memory are you referring to? "
                        "Please mention the preference or fact "
                        "you want me to explain or modify."
                    ),
                },
            }

            results.append(
                {
                    "intent": action.intent.value,
                    "category": None,
                    "result": result,
                }
            )

            print(
                "ACTION REQUIRES CLARIFICATION:",
                json.dumps(result, indent=2),
            )

            continue

        # Execute an action only when required

        # information exists.

        try:
            result = await execute_action(
                user_id=user_id,
                message=message,
                action=action,
                request_id=request_id,
                action_index=index,
            )

            print(
                "RAW MCP RESULT:",
                json.dumps(
                    result,
                    indent=2,
                    default=str,
                ),
            )

            if action.intent == MemoryIntent.RECALL and result.get("success") is True:
                raw_claims = result.get("data", [])

                if not isinstance(raw_claims, list):
                    raise ValueError("Unexpected recall result format.")

                decision = await filter_relevant_memories(
                    user_message=message,
                    claims=raw_claims,
                )

                print(
                    "RELEVANCE DECISION:",
                    decision.model_dump_json(indent=2),
                )

                result = await apply_recall_decision(
                    user_message=message,
                    recall_result=result,
                    decision=decision,
                )

                if (
                    conversation_id is not None
                    and action.intent == MemoryIntent.RECALL
                    and result.get("success") is True
                ):
                    matched_claims = result.get("data", [])

                    if len(matched_claims) == 1:
                        await save_memory_context(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            claim=matched_claims[0],
                        )

                if conversation_id is not None and decision.status == "AMBIGUOUS":
                    await save_pending_clarification(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        original_question=message,
                        category=category,
                        candidate_memory_keys=[
                            claim["memory_key"] for claim in decision.claims
                        ],
                        clarification_question=decision.clarification_question,
                    )

                print(
                    "FINAL RECALL RESULT:",
                    json.dumps(result, indent=2, default=str),
                )

        except (ValueError, TimeoutError, SQLAlchemyError) as e:
            import traceback

            print("===== MCP EXECUTION ERROR =====")

            traceback.print_exception(type(e), e, e.__traceback__)

            print("===============================")

            result = {
                "success": False,
                "error": {
                    "code": "TOOL_EXECUTION_FAILED",
                    "message": ("The memory operation could not be completed."),
                },
            }

        # Preserve the intent and category

        # for the frontend.

        results.append(
            {
                "intent": action.intent.value,
                "category": category,
                "domain": action.domain,
                "event_type": action.event_type,
                "subject": action.subject,
                "result": result,
            }
        )

    # 4. Generate a natural-language response

    # grounded in the filtered results.

    natural_response = await generate_natural_response(
        user_message=message,
        results=results,
    )

    print(f"\nNATURAL RESPONSE: {natural_response}")

    # 5. Return the response and structured results.

    return {
        "message": natural_response,
        "actions": results,
    }
