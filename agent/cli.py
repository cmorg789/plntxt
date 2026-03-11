"""CLI for running agents manually or via cron.

Usage:
    python -m agent.cli run-writer
    python -m agent.cli run-responder
    python -m agent.cli run-moderator
    python -m agent.cli run-consolidator
    python -m agent.cli run-all
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="plntxt agent CLI")
    parser.add_argument(
        "command",
        choices=["run-writer", "run-responder", "run-moderator", "run-consolidator", "run-all"],
        help="Which agent to run",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    commands = {
        "run-writer": _run_writer,
        "run-responder": _run_responder,
        "run-moderator": _run_moderator,
        "run-consolidator": _run_consolidator,
        "run-all": _run_all,
    }

    asyncio.run(commands[args.command]())


async def _run_writer() -> None:
    from agent.writer import run_writer
    await run_writer()


async def _run_responder() -> None:
    from agent.responder import run_responder
    await run_responder()


async def _run_moderator() -> None:
    from agent.moderator import run_moderator
    await run_moderator()


async def _run_consolidator() -> None:
    from agent.consolidator import run_consolidator
    await run_consolidator()


async def _run_all() -> None:
    from agent.scheduler import run_all
    await run_all()


if __name__ == "__main__":
    main()
