import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from bot import Base # Make sure 'bot.py' is your filename

async def create_db_tables():
    engine = create_async_engine(os.environ.get("DATABASE_URL"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables created successfully.")

asyncio.run(create_db_tables())