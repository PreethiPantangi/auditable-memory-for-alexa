import asyncio

from sqlalchemy import text

from database import engine


async def test_database():
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT version()"))

        print(result.scalar())


asyncio.run(test_database())
