import asyncio
import json

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .mcp_client import call_mcp_tool

from models.action import Action
from models.memoryresolution import MemoryResolution
from enums.intent import MemoryIntent
from enums.scope import ExplainScope

from prompts.inent_extraction import get_intent_extraction_prompt
from prompts.natural_response import NATURAL_RESPONSE_PROMPT
from prompts.resolve_memory import RESOLVE_MEMORY_PROMPT

load_dotenv()

client = OpenAI()
MODEL = "gpt-5.4-mini"

class Actions(BaseModel):
    actions: list[Action]

async def resolve_memory(user_message: str,claims: list[dict], intent: MemoryIntent) -> MemoryResolution:

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": RESOLVE_MEMORY_PROMPT
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"intent": intent.value,"message": user_message,"candidate_memories": claims},
                    default=str
                )
            }
        ],
        text_format=MemoryResolution
    )

    return response.output_parsed

async def execute_action(user_id: str, message: str, action: Action):
    match action.intent:

        case MemoryIntent.REMEMBER:
            return await call_mcp_tool(tool_name=MemoryIntent.REMEMBER.value, args={"user_id": user_id,"category": action.category.value,"value": action.value,"source_utterance": message})

        case MemoryIntent.RECALL:
            return await call_mcp_tool(tool_name=MemoryIntent.RECALL.value,args={"user_id": user_id,"category": action.category.value})

        case MemoryIntent.CORRECT_MEMORY:

            if not action.value or not action.value.strip():
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": "What would you like to change this preference to?"
                    }
                }
            
            recall_result = await call_mcp_tool(tool_name=MemoryIntent.RECALL.value,args={"user_id": user_id,"category": action.category.value})

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
                        )
                    }
                }

            resolution = await resolve_memory(user_message=message,claims=claims,intent=MemoryIntent.CORRECT_MEMORY)
            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        )
                    }
                }
            
            if resolution.status == "AMBIGUOUS":
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_MEMORY",
                        "message": (
                            "Multiple memories could match. Please specify which one to correct."
                        )
                    }
                }

            if resolution.status != "MATCHED":
                return {
                    "success": False,
                    "error": {
                        "code": "MEMORY_NOT_FOUND",
                        "message": (
                            "I couldn't identify which existing memory you want to correct."
                        )
                    }
                }

            valid_keys = {claim["memory_key"] for claim in claims}

            if resolution.memory_key not in valid_keys:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_MEMORY_KEY",
                        "message": "Memory resolution failed."
                    }
                }

            return await call_mcp_tool(tool_name=MemoryIntent.CORRECT_MEMORY.value,args={"user_id": user_id,"category": action.category.value,"memory_key": resolution.memory_key,"value": action.value,"source_utterance": message})

        case MemoryIntent.FORGET:
            recall_result = await call_mcp_tool(tool_name=MemoryIntent.RECALL.value,args={"user_id": user_id,"category": action.category.value})

            if not recall_result["success"]:
                return recall_result

            claims = recall_result["data"]

            if not claims:
                return {
                    "success": False,
                    "error": {
                        "code": "NO_ACTIVE_CLAIM",
                        "message": "No active memory found."
                    }
                }

            resolution = await resolve_memory(user_message=message,claims=claims, intent=MemoryIntent.FORGET)
            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        )
                    }
                }
            
            if resolution.status != "MATCHED":
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_MEMORY" if resolution.status == "AMBIGUOUS"
                                else "MEMORY_NOT_FOUND",
                        "message": "Could not identify which memory to forget."
                    }
                }

            if resolution.memory_key not in {claim["memory_key"] for claim in claims}:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_MEMORY_KEY",
                        "message": "Resolved memory was not found."
                    }
                }

            return await call_mcp_tool(tool_name=MemoryIntent.FORGET.value,args={"user_id": user_id,"category": action.category.value,"memory_key": resolution.memory_key})

        case MemoryIntent.MEMORY_HISTORY:
            return await call_mcp_tool(tool_name=MemoryIntent.MEMORY_HISTORY.value,args={"user_id": user_id,"category": action.category.value})

        case MemoryIntent.EXPLAIN:
            is_current = action.explain_scope == ExplainScope.CURRENT

            tool_name = (MemoryIntent.RECALL.value if is_current else MemoryIntent.MEMORY_HISTORY.value)

            result = await call_mcp_tool(tool_name=tool_name,args={"user_id": user_id,"category": action.category.value})

            if not result["success"]:
                return result

            claims = result["data"]

            if not claims:
                return {
                    "success": False,
                    "error": {
                        "code": "MEMORY_NOT_FOUND",
                        "message": "No matching memory exists."
                    }
                }

            resolution = await resolve_memory(user_message=message, claims=claims, intent=MemoryIntent.EXPLAIN)
            if resolution.requires_clarification:
                return {
                    "success": False,
                    "error": {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": (
                            resolution.clarification_reason
                            or "Please specify what you would like "
                            "to change your preference to."
                        )
                    }
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
                        "message": "Could not uniquely identify the memory."
                    }
                }

            if is_current:
                matching_claims = [
                    claim for claim in claims
                    if claim["memory_key"] == resolution.memory_key
                    and claim["status"] == "ACTIVE"
                ]
            else:
                matching_claims = [
                    claim for claim in claims
                    if claim["memory_key"] == resolution.memory_key
                    and claim["claim_id"] == resolution.claim_id
                ]

            if len(matching_claims) != 1:
                return {
                    "success": False,
                    "error": {
                        "code": "AMBIGUOUS_CLAIM_VERSION",
                        "message": "Could not uniquely identify the claim version."
                    }
                }

            return await call_mcp_tool(tool_name=MemoryIntent.EXPLAIN.value,args={"claim_id": matching_claims[0]["claim_id"],"user_id": user_id})

        case _:
            return {
                "success": False,
                "error": {
                    "code": "UNKNOWN_INTENT",
                    "message": f"Unknown intent: {action.intent}"
                }
            }

async def generate_natural_response(user_message: str, results: list[dict]) -> str:

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": NATURAL_RESPONSE_PROMPT
            },
            {
                "role": "user",
                "content": f"""
                    Original user message:
                    {user_message}

                    Structured results:
                    {json.dumps(results, indent=2, default=str)}
                """
            }
        ]
    )

    return response.output_text


async def handle_user_message(user_id: str, message: str):

    # 1. Extract memory actions from the user message.
    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": get_intent_extraction_prompt()
            },
            {
                "role": "user",
                "content": message
            }
        ],
        text_format=Actions
    )

    actions = response.output_parsed.actions
    results = []

    print("USER MESSAGE:", message)
    print("EXTRACTED ACTIONS:", actions)

    # 2. Handle messages without extracted memory actions.
    if not actions:
        print("NO ACTIONS EXTRACTED")
        print("NO MCP TOOLS EXECUTED")

        natural_response = await generate_natural_response(
            user_message=message,
            results=[]
        )

        print(f"AI: {natural_response}")

        return {
            "message": natural_response,
            "actions": []
        }

    # 3. Execute each extracted action.
    for action in actions:

        category = (
            action.category.value
            if action.category is not None
            else None
        )

        print(
            f"ACTION: {action.intent.value}, "
            f"CATEGORY: {category}"
        )

        # Validate category before executing MCP operations.
        if category is None:

            result = {
                "success": False,
                "error": {
                    "code": "CLARIFICATION_REQUIRED",
                    "message": (
                        "Which memory are you referring to? "
                        "Please mention the preference or fact "
                        "you want me to explain or modify."
                    )
                }
            }

            results.append({
                "intent": action.intent.value,
                "category": None,
                "result": result
            })

            print(
                "ACTION REQUIRES CLARIFICATION:",
                json.dumps(result, indent=2)
            )

            continue

        # Execute an action only when required information exists.
        try:
            result = await execute_action(
                user_id=user_id,
                message=message,
                action=action
            )

        except Exception as e:
            print(
                f"MCP EXECUTION ERROR: "
                f"{type(e).__name__}: {e}"
            )

            result = {
                "success": False,
                "error": {
                    "code": "TOOL_EXECUTION_FAILED",
                    "message": (
                        "The memory operation could not "
                        "be completed."
                    )
                }
            }

        print(
            "RAW MCP RESULT:",
            json.dumps(result, indent=2, default=str)
        )

        # Preserve the intent and category for the frontend.
        results.append({
            "intent": action.intent.value,
            "category": category,
            "result": result
        })

    # 4. Generate a natural-language response grounded in results.
    natural_response = await generate_natural_response(
        user_message=message,
        results=results
    )

    print(f"\nNATURAL RESPONSE: {natural_response}")

    # 5. Return the response and structured MCP action results.
    return {
        "message": natural_response,
        "actions": results
    }

