"""Agent scheduler — runs agents on configured intervals.

Each agent runs on its own timer. The scheduler fetches config on startup
and respects configured intervals. Each run is wrapped in error handling
with structured logging.
"""

from __future__ import annotations

import asyncio
import logging

from agent.client import load_agent_config

logger = logging.getLogger("plntxt.agent.scheduler")


async def _run_on_interval(name: str, coro_fn, interval: int) -> None:
    """Run an async function repeatedly on a fixed interval."""
    while True:
        logger.info("Scheduled run: %s (interval: %ds)", name, interval)
        try:
            await coro_fn()
        except Exception:
            logger.exception("Error in scheduled %s run", name)
        await asyncio.sleep(interval)


async def run_all() -> None:
    """Start all agents on their configured schedules."""
    logger.info("Agent scheduler starting")

    config = await load_agent_config()
    schedule = config["schedule"]

    # Import agents lazily to allow graceful fallback
    from agent.consolidator import run_consolidator
    from agent.moderator import run_moderator
    from agent.responder import run_responder
    from agent.writer import run_writer

    tasks = [
        asyncio.create_task(
            _run_on_interval("writer", run_writer, schedule.get("writer", 86400))
        ),
        asyncio.create_task(
            _run_on_interval("moderator", run_moderator, schedule.get("moderator", 1800))
        ),
        asyncio.create_task(
            _run_on_interval("responder", run_responder, schedule.get("responder", 1800))
        ),
        asyncio.create_task(
            _run_on_interval(
                "consolidator", run_consolidator, schedule.get("consolidator", 604800)
            )
        ),
    ]

    logger.info("All agents scheduled. Press Ctrl+C to stop.")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Scheduler shutting down")
