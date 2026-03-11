"""Anthropic client setup and config loading for agents."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from agent.tools import get_config

# Default models per agent role
DEFAULT_MODELS = {
    "writer": "claude-sonnet-4-6",
    "responder": "claude-sonnet-4-6",
    "moderator": "claude-haiku-4-5-20251001",
    "consolidator": "claude-haiku-4-5-20251001",
    "validation": "claude-haiku-4-5-20251001",
}

# Default schedule intervals in seconds
DEFAULT_SCHEDULE = {
    "writer": 86400,        # 24 hours
    "responder": 1800,      # 30 minutes
    "moderator": 1800,      # 30 minutes
    "consolidator": 604800,  # 7 days
}


def get_anthropic_client() -> AsyncAnthropic:
    """Create an AsyncAnthropic client. Uses ANTHROPIC_API_KEY env var automatically."""
    return AsyncAnthropic()


async def load_agent_config() -> dict:
    """Fetch agent configuration from the server, with sensible defaults."""
    try:
        config = await get_config()
    except Exception:
        config = {}

    personality_entry = config.get("agent_personality", {})
    models_entry = config.get("agent_models", {})
    schedule_entry = config.get("agent_schedule", {})

    return {
        "personality": personality_entry.get("value", {}),
        "models": {**DEFAULT_MODELS, **models_entry.get("value", {})},
        "schedule": {**DEFAULT_SCHEDULE, **schedule_entry.get("value", {})},
    }
