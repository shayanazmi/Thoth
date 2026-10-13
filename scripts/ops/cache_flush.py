#!/usr/bin/env python3
"""
Thoth Redis Cache Operations Tool.

Provides safe cache clearing, pattern-based invalidation, and inspection
for Redis cache and rate limit counters.

Usage:
    python scripts/ops/cache_flush.py [--pattern "thoth:*"] [--all] [--dry-run] [-y]
"""

import os
import sys
import asyncio
import argparse
import logging

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("ThothCacheOps")

async def flush_cache(pattern: str = "thoth:*", flush_all: bool = False, dry_run: bool = False, confirm: bool = False):
    settings = get_settings()
    redis_url = settings.REDIS_URL

    if not redis_url:
        logger.info("REDIS_URL not configured. Checking in-memory cache status...")
        from backend.core.cache import cache_manager
        if dry_run:
            logger.info(f"[DRY RUN] In-memory cache contains {len(cache_manager._memory_store)} entries.")
        else:
            count = len(cache_manager._memory_store)
            cache_manager._memory_store.clear()
            logger.info(f"Cleared {count} entries from in-memory cache.")
        return

    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        logger.info(f"Connected to Redis at {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")
    except ImportError:
        logger.info("'redis' package not installed in environment. Inspecting in-memory cache...")
        from backend.core.cache import cache_manager
        if dry_run:
            logger.info(f"[DRY RUN] In-memory cache contains {len(cache_manager._memory_fallback)} entries.")
        else:
            count = len(cache_manager._memory_fallback)
            cache_manager._memory_fallback.clear()
            cache_manager._memory_expiry.clear()
            logger.info(f"Cleared {count} entries from in-memory cache.")
        return
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        return

    try:
        if flush_all:
            if not confirm and not dry_run:
                ans = input("WARNING: This will flush ALL keys in the current Redis database. Proceed? [y/N]: ")
                if ans.lower() not in ["y", "yes"]:
                    logger.info("Aborted.")
                    await client.close()
                    return

            if dry_run:
                total_keys = await client.dbsize()
                logger.info(f"[DRY RUN] Would execute FLUSHDB. Current database size: {total_keys} keys.")
            else:
                await client.flushdb()
                logger.info("Successfully executed FLUSHDB. All keys flushed.")
        else:
            keys = []
            async for k in client.scan_iter(match=pattern):
                keys.append(k)

            logger.info(f"Found {len(keys)} keys matching pattern '{pattern}'.")
            if dry_run:
                for k in keys[:10]:
                    logger.info(f"  [Sample key]: {k}")
                if len(keys) > 10:
                    logger.info(f"  ... and {len(keys) - 10} more.")
                logger.info("[DRY RUN] No keys deleted.")
            else:
                if keys:
                    deleted = await client.delete(*keys)
                    logger.info(f"Successfully deleted {deleted} keys.")
                else:
                    logger.info("No matching keys to delete.")

    finally:
        await client.close()

def main():
    parser = argparse.ArgumentParser(description="Flush Redis cache keys for Thoth")
    parser.add_argument("--pattern", default="thoth:*", help="Key pattern to match (default: 'thoth:*')")
    parser.add_argument("--all", action="store_true", help="Flush the entire Redis database (FLUSHDB)")
    parser.add_argument("--dry-run", action="store_true", help="Preview keys without deleting")
    parser.add_argument("-y", "--yes", action="store_true", help="Bypass interactive confirmation")
    args = parser.parse_args()

    print("=" * 70)
    print("THOTH CACHE FLUSH TOOL")
    print("=" * 70)

    asyncio.run(flush_cache(
        pattern=args.pattern,
        flush_all=args.all,
        dry_run=args.dry_run,
        confirm=args.yes
    ))
    print("=" * 70)

if __name__ == "__main__":
    main()
