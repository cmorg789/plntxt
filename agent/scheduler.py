"""Agent scheduler — runs agents on cron schedules.

Each agent runs on its own cron expression. The scheduler fetches config
on startup, calculates the next fire time for each agent, and sleeps
until then. Each run is wrapped in error handling with structured logging.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter

from agent.client import load_agent_config

logger = logging.getLogger("plntxt.agent.scheduler")


async def _run_on_cron(name: str, coro_fn, cron_expr: str) -> None:
    """Run an async function on a cron schedule."""
    cron = croniter(cron_expr, datetime.now(timezone.utc))
    while True:
        next_run = cron.get_next(datetime).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        wait_seconds = max(0, (next_run - now).total_seconds())
        logger.info(
            "Scheduled %s: next run at %s (in %.0fs)",
            name,
            next_run.isoformat(),
            wait_seconds,
        )
        await asyncio.sleep(wait_seconds)
        logger.info("Running: %s", name)
        try:
            await coro_fn()
        except Exception:
            logger.exception("Error in scheduled %s run", name)


async def run_all() -> None:
    """Start all agents on their configured cron schedules."""
    logger.info("Agent scheduler starting")

    config = await load_agent_config()
    schedule = config["schedule"]

    from agent.consolidator import run_consolidator
    from agent.moderator import run_moderator
    from agent.responder import run_responder
    from agent.writer import run_writer

    tasks = [
        asyncio.create_task(
            _run_on_cron("writer", run_writer, schedule["writer"])
        ),
        asyncio.create_task(
            _run_on_cron("moderator", run_moderator, schedule["moderator"])
        ),
        asyncio.create_task(
            _run_on_cron("responder", run_responder, schedule["responder"])
        ),
        asyncio.create_task(
            _run_on_cron("consolidator", run_consolidator, schedule["consolidator"])
        ),
    ]

    logger.info("All agents scheduled. Press Ctrl+C to stop.")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Scheduler shutting down")
