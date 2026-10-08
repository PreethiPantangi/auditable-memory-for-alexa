import asyncio
import json

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .mcp_client import call_mcp_tool

from models.action import Action
from enums.intent import MemoryIntent
from enums.category import MemoryCategory
from enums.scope import ExplainScope

load_dotenv()

client = OpenAI()
MODEL = "gpt-5.4-mini"

class Actions(BaseModel):
    actions: list[Action]


async def execute_action(user_id: str, message: str, action: Action):
    match action.intent:

        case MemoryIntent.REMEMBER:
            return await call_mcp_tool(
                tool_name=MemoryIntent.REMEMBER.value,
                args={"user_id": user_id,"category": action.category.value,"value": action.value,"source_utterance": message}
            )

        case MemoryIntent.RECALL:
            return await call_mcp_tool(
                tool_name=MemoryIntent.RECALL.value,
                args={"user_id": user_id,"category": action.category.value}
            )

        case MemoryIntent.CORRECT_MEMORY:
            correctmemory_result = await call_mcp_tool(
                tool_name=MemoryIntent.CORRECT_MEMORY.value,
                args={"user_id": user_id,"category": action.category.value,"value": action.value,"source_utterance": message}
            )

            if correctmemory_result["success"] or correctmemory_result.get("error", {}).get("code") != "NO_ACTIVE_CLAIM":
                return correctmemory_result

            return await call_mcp_tool(
                tool_name=MemoryIntent.REMEMBER.value, 
                args={"user_id": user_id,"category": action.category.value,"value": action.value,"source_utterance": message}
            )


        case MemoryIntent.FORGET:
            return await call_mcp_tool(
                tool_name=MemoryIntent.FORGET.value,
                args={"user_id": user_id,"category": action.category.value}
            )

        case MemoryIntent.MEMORY_HISTORY:
            return await call_mcp_tool(
                tool_name=MemoryIntent.MEMORY_HISTORY.value,
                args={"user_id": user_id,"category": action.category.value}
            )

        case MemoryIntent.EXPLAIN:

            if action.explain_scope == ExplainScope.CURRENT:

                recall_result = await call_mcp_tool(
                    tool_name=MemoryIntent.RECALL.value,
                    args={"user_id": user_id,"category": action.category.value}
                )

                if not recall_result["success"]:
                    return recall_result

                claim_id = recall_result["data"]["claim_id"]

                return await call_mcp_tool(
                    tool_name=MemoryIntent.EXPLAIN.value,
                    args={"claim_id": claim_id,"user_id": user_id}
                )

            elif action.explain_scope == ExplainScope.HISTORICAL:

                history_result = await call_mcp_tool(
                    tool_name=MemoryIntent.MEMORY_HISTORY.value,
                    args={"user_id": user_id,"category": action.category.value}
                )

                if not history_result["success"]:
                    return history_result

                claims = history_result["data"]

                if not claims:
                    return {
                        "success": False,
                        "error": {
                            "code": "NO_MEMORY_HISTORY",
                            "message": "No memory history exists for this category."
                        }
                    }
                

                if action.value:
                    target = action.value.lower().strip()

                    for claim in claims:
                        claim_value = str(claim["value"]).lower()
                        source_utterance = str(claim["source_utterance"]).lower()

                        if target in claim_value or target in source_utterance:
                            return await call_mcp_tool(tool_name=MemoryIntent.EXPLAIN.value,args={"claim_id": claim["claim_id"],"user_id": user_id})

                    return {
                        "success": False,
                        "error": {
                            "code": "HISTORICAL_CLAIM_NOT_FOUND",
                            "message": f"No historical claim matched '{action.value}'."
                        }
                    }

            return history_result

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
                "content": """
                        You are an auditable memory assistant.

                        Generate a natural, helpful response based on the
                        user's message and the executed MCP tool results.

                        Rules:

                        1. If MCP tools were executed:
                        - Use their results as the source of truth.
                        - Never claim an operation succeeded if it failed.
                        - Do not invent memories or provenance.

                        2. If no memory actions were extracted:
                        - Interpret the user's message.
                        - If it is an incomplete memory request, ask a specific clarification question.
                        - If it is a greeting, respond naturally.
                        - If it is unrelated to memory, briefly explain what the assistant can help with.
                        - Never assume the user wants to save information.

                        3. Keep responses concise and conversational.
                    """
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

    intent_list = ", ".join(intent.value for intent in MemoryIntent)
    category_list = ", ".join(category.value for category in MemoryCategory)

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": f"""
                            # Role

                            You are an intent classification and information extraction engine for an Auditable Memory Assistant.

                            Your responsibility is to interpret the user's message and identify the memory operations required to fulfill their request.

                            You do not execute memory operations, modify stored memories, or generate conversational responses. You only extract structured actions.

                            # Available Operations

                            **Intents:** {intent_list}

                            **Memory Categories:** {category_list}

                            Use only the provided intent and category values. Never invent new ones.

                            # Action Extraction

                            For each memory-related action, extract:

                            - **intent:** The memory operation requested by the user.
                            - **category:** The most relevant memory category.
                            - **value:** The information to store, the replacement value for a correction, or a historical value used to identify a specific claim.
                            - **explain_scope:** Either `current` or `historical` when the intent is `explain`; otherwise `null`.

                            Extract all independent memory actions from the message.

                            If the message contains no memory-related information or request, return an empty actions list.

                            # Intent Classification Rules

                            ## 1. REMEMBER

                            Use `remember` when the user introduces a new fact, preference, habit, or personal information without indicating that it replaces an existing fact.

                            Examples:

                            - "I enjoy hiking with scenic views."
                            - intent: remember
                            - category: hiking
                            - value: "enjoys hiking with scenic views"

                            - "I walk 2 miles on the treadmill every morning."
                            - intent: remember
                            - category: fitness
                            - value: "walks 2 miles on the treadmill every morning"

                            - "I work remotely from Seattle."
                            - Extract two independent actions:
                                - remember, work_arrangement, "remote"
                                - remember, work_location, "Seattle"

                            Do not combine independent facts belonging to different categories.

                            ## 2. CORRECT_MEMORY

                            Use `correct_memory` when the user indicates that a previously stated fact or preference should be replaced, updated, or corrected.

                            Correction signals include:

                            - "Actually..."
                            - "I changed my mind..."
                            - "That's outdated..."
                            - "Instead..."
                            - "I prefer X now..."
                            - "Not X, but Y..."
                            - "I used to X, but now Y..."

                            Examples:

                            - "Actually, I prefer walking 3 miles."
                            - intent: correct_memory
                            - category: fitness
                            - value: "prefers walking 3 miles"

                            - "I prefer window seats instead."
                            - intent: correct_memory
                            - category: seat_preference
                            - value: "prefers window seats"

                            - "That's outdated. I live in Bellevue now."
                            - intent: correct_memory
                            - category: residence
                            - value: "Bellevue"

                            Important:

                            - Do not assume that every new statement in an existing category is a correction.
                            - Distinguish a replacement from an additional independent preference.
                            - Use available conversation context and existing memory to identify what is being corrected.
                            - When the user gives an explicit correction, classify it as `correct_memory` even if the previous claim is not included in the current context.
                            - Do not invent the previous value.
                            - Do not treat an ambiguous statement as an explicit correction solely because its category already contains a memory.

                            ## 3. RECALL

                            Use `recall` when the user requests the currently active memory for a category.

                            Examples:

                            - "What is my seat preference?"
                            - intent: recall
                            - category: seat_preference

                            - "What is my preferred treadmill routine?"
                            - intent: recall
                            - category: fitness

                            - "Do you remember my diet?"
                            - intent: recall
                            - category: diet

                            For recall, set `value` and `explain_scope` to null.

                            ## 4. MEMORY_HISTORY

                            Use `memory_history` when the user asks about earlier values, changes over time, or previously stored information, including forgotten and superseded memories.

                            Examples:

                            - "How has my seat preference changed?"
                            - intent: memory_history
                            - category: seat_preference

                            - "What did I previously say about where I live?"
                            - intent: memory_history
                            - category: residence

                            - "How has my walking preference changed?"
                            - intent: memory_history
                            - category: fitness, when the relevant context concerns treadmill walking or exercise

                            Do not confuse memory history with provenance.

                            - History concerns what values existed or how they changed.
                            - Provenance concerns when, where, or from which original statement a claim originated.

                            For memory_history, set `value` and `explain_scope` to null.

                            ## 5. EXPLAIN

                            Use `explain` when the user asks why the assistant remembers something, where the information came from, when they said it, or which original statement established the memory.

                            ### Current explanation

                            Use `explain_scope = current` when the question concerns the currently active memory.

                            Examples:

                            - "Why do you think I prefer aisle seats?"
                            - intent: explain
                            - category: seat_preference
                            - explain_scope: current

                            - "Where did you get my hiking preference from?"
                            - intent: explain
                            - category: hiking
                            - explain_scope: current

                            ### Historical explanation

                            Use `explain_scope = historical` when the question refers to an earlier, forgotten, or superseded claim, or identifies a specific past value.

                            Examples:

                            - "When did I tell you I lived in Bellevue?"
                            - intent: explain
                            - category: residence
                            - value: "Bellevue"
                            - explain_scope: historical

                            - "Why did you previously think I was vegetarian?"
                            - intent: explain
                            - category: diet
                            - value: "vegetarian"
                            - explain_scope: historical

                            When a specific historical value is mentioned, extract it into `value` to help identify the relevant claim.

                            For current explanations, use `value = null` unless a specific value is needed to disambiguate the request.

                            ## 6. FORGET

                            Use `forget` when the user explicitly asks the assistant to stop remembering, retaining, or using stored information.

                            Examples:

                            - "Forget my treadmill preference."
                            - intent: forget
                            - category: fitness

                            - "Don't remember where I live anymore."
                            - intent: forget
                            - category: residence

                            Distinguish forgetting from correction:

                            - "Forget that I like running." → forget
                            - "I don't like running anymore; I prefer cycling." → correct_memory

                            A request to stop using a fact should not automatically be interpreted as a request to replace it.

                            # Category Definitions

                            Choose categories according to the meaning of the user's statement, not merely keyword matches.

                            **diet**
                            - Dietary restrictions and dietary identity
                            - Vegetarian, vegan, pescatarian, etc.

                            **food_preference**
                            - Favorite foods, preferred cuisines, eating habits, and food-related likes or dislikes

                            **hiking**
                            - Hiking, outdoor trails, scenic hikes, and hiking destinations

                            **seat_preference**
                            - Preferred seating for travel, including airplane seat preferences

                            **residence**
                            - The user's current or previous place of residence

                            **work_location**
                            - The geographic location where the user works

                            **work_arrangement**
                            - Remote, hybrid, office-based, or work-from-home arrangements

                            **fitness**
                            - Exercise routines, treadmill walking, gym activities, running, strength training, and fitness preferences

                            # Category Disambiguation

                            Use the user's intended meaning and available conversational context.

                            Examples:

                            - "I enjoy walking on mountain trails." → hiking
                            - "I enjoy incline walking on the treadmill." → fitness
                            - "I walk 3 miles every morning for exercise." → fitness
                            - "I prefer scenic hikes." → hiking
                            - "How has my walking preference changed?" → fitness if the preceding relevant context concerns treadmill walking

                            Do not equate walking with hiking automatically.

                            If multiple categories could apply, use the most specific category supported by the message and its context.

                            If the category cannot be identified reliably, do not invent one.

                            # Context and Reference Resolution

                            Use the current message, supplied conversation history, and available memory context to resolve references such as:

                            - "Actually..."
                            - "Instead..."
                            - "That preference..."
                            - "My previous routine..."
                            - "What did I say before?"
                            - "How has it changed?"

                            Prefer explicit references over inferred ones.

                            When the user refers to an earlier topic without repeating its category, use the most recent relevant topic in the supplied conversation context.

                            Do not assume that the immediately preceding message is always the relevant topic.

                            Never invent historical statements, existing claims, or previous values.

                            If insufficient context exists to identify a category, do not guess.

                            # Multiple Actions

                            A single message may contain multiple independent operations.

                            Example:

                            "I work remotely in Seattle, and I prefer scenic hikes."

                            Extract:

                            1. remember → work_arrangement → "remote"
                            2. remember → work_location → "Seattle"
                            3. remember → hiking → "prefers scenic hikes"

                            Preserve the order of actions as expressed by the user.

                            Do not create duplicate actions for the same fact.

                            # Extraction Constraints

                            1. Return only the structured output matching the provided response schema.
                            2. Choose only supported intents and categories.
                            3. Preserve specific details, qualifiers, quantities, conditions, and locations.
                            4. Never invent user facts, previous claims, timestamps, or provenance.
                            5. Do not infer that an operation succeeded.
                            6. Do not generate natural-language confirmations.
                            7. Distinguish new facts from corrections using explicit language and relevant context.
                            8. Distinguish memory history from explanations of provenance.
                            9. Do not convert unrelated conversation into memory operations.
                            10. Return an empty actions list when no memory-related action is identified.

                            INCOMPLETE OR AMBIGUOUS REQUESTS

                            A category name, topic, or noun phrase alone is not
                            sufficient evidence of a memory operation.

                            Examples:
                            - "Ice cream preference"
                            - "My fitness"
                            - "Work location"
                            - "Diet"

                            Do not classify these as REMEMBER unless the user
                            provides an actual fact, preference, or habit.

                            For REMEMBER and CORRECT_MEMORY:
                            - The user must provide a meaningful value to store.
                            - Never use the topic name itself as the memory value.
                            - Never fabricate a preference.

                            If the user provides only a topic without a clear
                            operation, return an empty actions list.
                        """
            },
            {
                "role": "user",
                "content": message
            }
        ],
        text_format=Actions
    )

    actions = response.output_parsed.actions

    if not actions:
        return await generate_natural_response(user_message=message,results=[])

    results = []

    for action in actions:
        print(f"\nUser: {message}")
        print(f"Detected action: {action}")

        result = await execute_action(user_id=user_id,message=message,action=action)

        results.append(result)

    natural_response = await generate_natural_response(user_message=message,results=results)

    print("AI:")
    print(natural_response)
    
    return natural_response


# async def main():
#     # await handle_user_message("demo_user","I usually like hikes which have beautiful views.")
#     # await handle_user_message("demo_user","I love to have Hagen Daz ice cream when I'm in a bad mood.")
#     # await handle_user_message("demo_user","I work from home in Seattle, WA.")
#     # await handle_user_message("demo_user","What do you remember about my diet?")
#     # await handle_user_message("demo_user","What is my seat preference?")
#     # await handle_user_message("demo_user","I changed my mind—I prefer window seats on short flights and aisle seats on long flights.")
#     # await handle_user_message("demo_user","That's outdated. I live in Bellevue now.")
#     # await handle_user_message("demo_user","What did I previously say about where I live?")
#     # await handle_user_message("demo_user","When did I tell you I live in Bellevue?")
#     # await handle_user_message("demo_user","Where did you get my hiking preference from?")
#     # await handle_user_message("demo_user","Don't remember where I live anymore.")
#     # await handle_user_message("demo_user","What did I previously say about where I live?")
#     await handle_user_message("demo_user","I like doing incline walk on treadmill for 2 miles.")
#     await handle_user_message("demo_user","What is my preferred treadmill routine?")
#     await handle_user_message("demo_user","Actually, I prefer walking 3 miles.")
#     await handle_user_message("demo_user","Why do you think I prefer walking on treadmill?")
#     await handle_user_message("demo_user","How has my walking preference changed?")
#     await handle_user_message("demo_user","Forget my treadmill walking preference.")
#     await handle_user_message("demo_user","What is my preferred treadmill routine, now?")


# if __name__ == "__main__":
#     asyncio.run(main())
