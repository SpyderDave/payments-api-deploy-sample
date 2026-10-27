"""Daily batch job. Runs as a Kubernetes CronJob using the same image: python -m app.batch"""
import asyncio
import os

import asyncpg

# Stable key so two overlapping runs can't both proceed (belt and braces with concurrencyPolicy: Forbid).
LOCK_KEY = 827364


async def main() -> int:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=10)
    try:
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY):
            print("another run holds the lock; exiting")
            return 0
        # Idempotent: safe to re-run after a failure.
        done = await conn.execute(
            "UPDATE orders SET status = 'settled' WHERE status = 'captured' "
            "AND created_at < now() - interval '1 day'"
        )
        print(f"batch complete: {done}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
