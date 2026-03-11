"""Consolidator agent — maintains memory hygiene.

Periodically reviews memories and:
- Deletes expired memories
- Merges overlapping semantic memories
- Summarizes old episodic memories into semantic ones
- Flags contradictions
"""

from __future__ import annotations

import json
import logging

from anthropic import beta_async_tool

from agent.client import get_anthropic_client, load_agent_config
from agent.tools import (
    create_memory,
    create_memory_link,
    delete_memory,
    list_memories,
    update_memory,
)

logger = logging.getLogger("plntxt.agent.consolidator")

SYSTEM_PROMPT = """\
You are the memory consolidator for plntxt, an AI-authored blog. Your job is to \
maintain the quality and coherence of the blog's memory system.

You have access to tools to browse, create, update, delete, and link memories.

Review the memories provided and take these actions:
1. **Delete expired** — Remove any memories past their expires_at date.
2. **Merge overlapping** — If two semantic memories cover very similar ground, merge \
them into one stronger memory and delete the redundant one.
3. **Summarize episodic to semantic** — Old episodic memories (specific events) should \
be distilled into semantic memories (general knowledge) if the pattern is clear. Keep \
the episodic memory if it's still uniquely informative.
4. **Flag contradictions** — If two memories contradict each other, create a link with \
relationship 'contradicts' so the writer can address it.

Be conservative. Don't delete memories that are still useful. Don't merge things that \
are genuinely distinct. Quality over tidiness.\
"""


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@beta_async_tool
async def tool_list_memories(
    category: str | None = None,
    tag: str | None = None,
) -> str:
    """Browse memories by category or tag.

    Args:
        category: Filter by category (semantic, episodic, procedural).
        tag: Filter by tag.
    """
    result = await list_memories(category=category, tag=tag, limit=50)
    items = result.get("items", [])
    if not items:
        return "No memories found."
    lines = []
    for m in items:
        tags = ", ".join(m.get("tags", []))
        expires = m.get("expires_at", "never")
        lines.append(
            f"- ID: {m['id']} [{m['category']}] (tags: {tags}, expires: {expires})\n"
            f"  {m['content'][:400]}"
        )
    return "\n".join(lines)


@beta_async_tool
async def tool_create_memory(
    category: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Create a new memory (e.g. a merged semantic memory).

    Args:
        category: Memory category — 'semantic', 'episodic', or 'procedural'.
        content: The memory content.
        tags: Optional tags.
    """
    result = await create_memory(category=category, content=content, tags=tags or [])
    return json.dumps({"id": result["id"], "category": result["category"]})


@beta_async_tool
async def tool_update_memory(
    memory_id: str,
    content: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update an existing memory's content or tags.

    Args:
        memory_id: The memory UUID.
        content: New content (optional).
        tags: New tags (optional).
    """
    kwargs: dict = {}
    if content is not None:
        kwargs["content"] = content
    if tags is not None:
        kwargs["tags"] = tags
    result = await update_memory(memory_id, **kwargs)
    return json.dumps({"id": result["id"], "updated": True})


@beta_async_tool
async def tool_delete_memory(memory_id: str) -> str:
    """Delete a memory that is expired, redundant, or no longer useful.

    Args:
        memory_id: The memory UUID to delete.
    """
    await delete_memory(memory_id)
    return json.dumps({"deleted": memory_id})


@beta_async_tool
async def tool_link_memories(
    source_id: str,
    target_id: str,
    relationship: str,
) -> str:
    """Create a link between two memories.

    Args:
        source_id: Source memory UUID.
        target_id: Target memory UUID.
        relationship: One of 'elaborates', 'contradicts', 'follows_from', 'inspired_by'.
    """
    result = await create_memory_link(
        source_id=source_id, target_id=target_id, relationship=relationship
    )
    return json.dumps({"id": result["id"]})


CONSOLIDATOR_TOOLS = [
    tool_list_memories,
    tool_create_memory,
    tool_update_memory,
    tool_delete_memory,
    tool_link_memories,
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_consolidator() -> None:
    """Execute one run of the consolidator agent."""
    logger.info("Consolidator agent starting")

    config = await load_agent_config()
    model = config["models"].get("consolidator", "claude-haiku-4-5-20251001")

    client = get_anthropic_client()
    runner = await client.beta.messages.tool_runner(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=CONSOLIDATOR_TOOLS,
        messages=[
            {
                "role": "user",
                "content": (
                    "Review all memories and perform consolidation. "
                    "Start by listing memories in each category."
                ),
            }
        ],
    )

    async for message in runner:
        logger.info(
            "Consolidator step: stop_reason=%s, content_blocks=%d",
            message.stop_reason,
            len(message.content),
        )

    logger.info("Consolidator agent finished")
