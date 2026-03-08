import os
from kimiko.config import get_settings
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

async def test_conn():
    settings = get_settings()
    env_url = os.environ.get("KIMIKO_DATABASE_URL")
    
    print(f"Pydantic Settings DB URL: {settings.database_url}")
    print(f"OS Environ DB URL: {env_url}")
    
    final_url = env_url or settings.database_url
    print(f"Final URL to connect: {final_url}")
    
    try:
        engine = create_async_engine(final_url)
        async with engine.connect() as conn:
            print("Connection successful!")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
