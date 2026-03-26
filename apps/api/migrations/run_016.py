import asyncio
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.database import db


async def run_migration():
    with open(Path(__file__).parent / "016_unify_memory_architecture.sql", "r") as f:
        sql = f.read()

    await db.connect()
    try:
        await db.execute(sql)
        print("Migration 016 completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(run_migration())
