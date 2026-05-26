"""Scripts for utility operations."""

#!/usr/bin/env python3
"""Initialize the database with sample data for testing."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import Settings
from app.storage.database import init_database


async def main():
    """Initialize database."""
    settings = Settings()
    settings.storage.ensure_dirs()

    print("Initializing database...")
    db = await init_database(settings)
    print(f"Database created at: {settings.storage.data_dir / 'life_data_lake.db'}")

    print("\nTables created:")
    print("  - chats")
    print("  - topics")
    print("  - raw_events")
    print("  - normalized_messages")
    print("  - media")
    print("  - links_knowledge_base")
    print("  - daily_summaries")
    print("  - weekly_summaries")
    print("  - search_index (FTS5)")
    print("  - processing_jobs")
    print("  - embeddings")

    print("\nDatabase initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())