import asyncio

from client.conversation_state import get_pending_clarification


async def main():
    pending = await get_pending_clarification(
        conversation_id="ac416ff9-4daf-4b3a-98ee-b714e13dd593",
        user_id="adh_correction_test",
    )

    print(pending)


asyncio.run(main())
