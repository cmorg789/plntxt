"""Config loading for agents."""

from __future__ import annotations

from agent.tools import get_config

# Default models per agent role
DEFAULT_MODELS = {
    "writer": "claude-sonnet-4-6",
    "responder": "claude-sonnet-4-6",
    "moderator": "claude-haiku-4-5-20251001",
    "consolidator": "claude-haiku-4-5-20251001",
}

# Default cron schedules (UTC)
DEFAULT_SCHEDULE = {
    "writer": "0 8,14,20 * * *",       # 3x daily: 8am, 2pm, 8pm UTC
    "responder": "*/15 * * * *",        # every 15 minutes
    "moderator": "*/15 * * * *",        # every 15 minutes
    "consolidator": "0 3 * * 0",        # weekly: Sunday 3am UTC
}


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
