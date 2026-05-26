#!/usr/bin/env python3
"""Run the worker pool for processing jobs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import Settings
from app.workers.normalization import NormalizationWorker
from app.workers.media import MediaDownloadWorker


async def run_workers():
    """Run all workers."""
    settings = Settings()

    print("Starting worker pool...")

    normalizer = NormalizationWorker(settings)
    await normalizer.initialize()

    media_worker = MediaDownloadWorker(settings)
    await media_worker.initialize()

    print("Workers initialized. Press Ctrl+C to stop.")

    try:
        while True:
            processed_norm = await normalizer.process_pending()
            processed_media = await media_worker.process_pending()

            if processed_norm > 0 or processed_media > 0:
                print(f"Processed: {processed_norm} normalize, {processed_media} media")

            await asyncio.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping workers...")


if __name__ == "__main__":
    asyncio.run(run_workers())