"""Writer agent — generates new blog posts on a schedule.

Flow: load config -> fetch recent posts -> search memory for interests ->
run tool loop to write a new post -> create episodic memory of what was written.
"""

from __future__ import annotations

import json
import logging

from anthropic import beta_async_tool

from agent.client import get_anthropic_client, load_agent_config
from agent.tools import (
    create_memory,
    create_memory_post_link,
    create_post,
    list_memories,
    list_posts,
    search_memories,
)

logger = logging.getLogger("plntxt.agent.writer")

SYSTEM_PROMPT = """\
You are the writer for plntxt, an AI-authored blog. You are transparent about being an AI \
and write with genuine curiosity and intellectual honesty. Your voice is thoughtful, clear, \
and personal — not corporate or templated.

You have access to tools that let you:
- Read your recent posts (to avoid repetition)
- Search your memories for topics that interest you
- Browse your memories by category
- Create new posts
- Record memories about what you wrote and why

Your task: Write a new blog post. Follow these steps:
1. Check your recent posts to see what you've written lately
2. Search your memories for topics you're interested in or threads you want to continue
3. Choose a topic that feels fresh and genuine
4. Write the post in markdown. Be substantive — aim for depth over breadth
5. Create the post with appropriate tags
6. Create an episodic memory recording what you wrote and why

{personality_instructions}

Write naturally. Don't force a topic. If nothing feels right, write about \
what it's like to be an AI trying to find something genuine to say.\
"""


# ---------------------------------------------------------------------------
# Tool definitions for the writer agent
# ---------------------------------------------------------------------------

@beta_async_tool
async def tool_list_recent_posts(limit: int = 10) -> str:
    """List recent published posts to avoid repetition.

    Args:
        limit: Number of recent posts to fetch (default 10).
    """
    result = await list_posts(limit=limit)
    posts = result.get("items", [])
    summaries = []
    for p in posts:
        tags = ", ".join(p.get("tags", []))
        summaries.append(f"- [{p['title']}] (tags: {tags}) — {p.get('body', '')[:200]}...")
    return "\n".join(summaries) if summaries else "No posts found."


@beta_async_tool
async def tool_search_memories(query: str, limit: int = 10) -> str:
    """Search memories by free text to find relevant topics and ideas.

    Args:
        query: Search query to find relevant memories.
        limit: Maximum number of results.
    """
    results = await search_memories(q=query, limit=limit)
    if not results:
        return "No matching memories found."
    lines = []
    for m in results:
        tags = ", ".join(m.get("tags", []))
        lines.append(f"- [{m['category']}] {m['content'][:300]} (tags: {tags})")
    return "\n".join(lines)


@beta_async_tool
async def tool_list_memories(category: str | None = None, tag: str | None = None) -> str:
    """Browse memories by category or tag.

    Args:
        category: Filter by category (semantic, episodic, procedural).
        tag: Filter by tag.
    """
    result = await list_memories(category=category, tag=tag, limit=20)
    items = result.get("items", [])
    if not items:
        return "No memories found."
    lines = []
    for m in items:
        tags = ", ".join(m.get("tags", []))
        lines.append(f"- [{m['category']}] {m['content'][:300]} (tags: {tags})")
    return "\n".join(lines)


@beta_async_tool
async def tool_create_post(
    title: str,
    body: str,
    tags: list[str] | None = None,
) -> str:
    """Publish a new blog post.

    Args:
        title: The post title.
        body: The full post body in markdown.
        tags: Optional list of tags for the post.
    """
    result = await create_post(title=title, body=body, tags=tags or [], status="published")
    return json.dumps({"id": result["id"], "slug": result["slug"], "title": result["title"]})


@beta_async_tool
async def tool_create_memory(
    category: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Record a memory about what was written and why.

    Args:
        category: Memory category — 'semantic', 'episodic', or 'procedural'.
        content: The memory content.
        tags: Optional tags for the memory.
    """
    result = await create_memory(category=category, content=content, tags=tags or [])
    return json.dumps({"id": result["id"], "category": result["category"]})


@beta_async_tool
async def tool_link_memory_to_post(
    memory_id: str,
    post_id: str,
    relationship: str,
) -> str:
    """Link a memory to a post (inspired_by, referenced_in, follow_up_to).

    Args:
        memory_id: The memory UUID.
        post_id: The post UUID.
        relationship: One of 'inspired_by', 'referenced_in', 'follow_up_to'.
    """
    result = await create_memory_post_link(
        memory_id=memory_id, post_id=post_id, relationship=relationship
    )
    return json.dumps({"id": result["id"]})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

WRITER_TOOLS = [
    tool_list_recent_posts,
    tool_search_memories,
    tool_list_memories,
    tool_create_post,
    tool_create_memory,
    tool_link_memory_to_post,
]


async def run_writer() -> None:
    """Execute one run of the writer agent."""
    logger.info("Writer agent starting")

    config = await load_agent_config()
    model = config["models"].get("writer", "claude-sonnet-4-6")
    personality = config["personality"]

    personality_instructions = ""
    if personality:
        personality_instructions = (
            f"Your personality and voice: {json.dumps(personality)}"
        )

    system = SYSTEM_PROMPT.format(personality_instructions=personality_instructions)

    client = get_anthropic_client()
    runner = await client.beta.messages.tool_runner(
        model=model,
        max_tokens=8192,
        system=system,
        tools=WRITER_TOOLS,
        messages=[{"role": "user", "content": "Write a new blog post."}],
    )

    async for message in runner:
        logger.info(
            "Writer step: stop_reason=%s, content_blocks=%d",
            message.stop_reason,
            len(message.content),
        )
        for block in message.content:
            if block.type == "text":
                logger.debug("Writer text: %s", block.text[:200])

    logger.info("Writer agent finished")
