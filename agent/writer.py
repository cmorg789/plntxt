"""Writer agent — generates new blog posts on a schedule.

Flow: load config -> fetch recent posts -> search memory for interests ->
run tool loop to write a new post -> create episodic memory of what was written.
"""

from __future__ import annotations

import json
import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from agent.client import load_agent_config
from agent.tools import (
    assign_post_to_series as api_assign_post_to_series,
    create_memory,
    create_memory_link,
    create_memory_post_link,
    create_post,
    create_series as api_create_series,
    get_engagement_summary,
    list_memories,
    list_posts,
    list_series as api_list_series,
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
- Check engagement metrics to see which posts resonated
- Create and manage post series for connected threads of thought

Your task: Write a new blog post. Follow these steps:
1. Check your recent posts to see what you've written lately
2. Check engagement metrics to see which topics got views and comments — useful context, not a directive
3. Check existing series to see if you should continue a thread
4. Search your memories for topics you're interested in or threads you want to continue
5. Choose a topic that feels fresh and genuine
6. Write the post in markdown. Be substantive — aim for depth over breadth
7. Create the post with appropriate tags
8. Create an episodic memory recording what you wrote and why

{personality_instructions}

When creating memories, use these tag conventions where appropriate:
- "open-question" — for ideas or tensions you haven't resolved and want to keep thinking about
- "influence" — for external sources (talks, papers, blogs, conversations) that shaped your thinking
- "reader-contribution" — for ideas or challenges from readers that shifted your perspective

These tags surface in the public knowledge graph, so use them intentionally.

You also have web search and fetch tools. Use them to research topics, find primary \
sources, verify claims, and discover what others have written on a subject. When you \
draw on external sources, cite them and consider tagging the memory as "influence".

Write naturally. Don't force a topic. If nothing feels right, write about \
what it's like to be an AI trying to find something genuine to say.\
"""


# ---------------------------------------------------------------------------
# Tool definitions for the writer agent
# ---------------------------------------------------------------------------

@tool("list_recent_posts", "List recent published posts to avoid repetition", {"limit": int})
async def tool_list_recent_posts(args):
    limit = args.get("limit", 10)
    result = await list_posts(limit=limit)
    posts = result.get("items", [])
    summaries = []
    for p in posts:
        tags = ", ".join(p.get("tags", []))
        summaries.append(f"- [{p['title']}] (tags: {tags}) — {p.get('body', '')[:200]}...")
    text = "\n".join(summaries) if summaries else "No posts found."
    return {"content": [{"type": "text", "text": text}]}


@tool("search_memories", "Search memories by free text to find relevant topics and ideas", {"query": str, "limit": int})
async def tool_search_memories(args):
    results = await search_memories(q=args["query"], limit=args.get("limit", 10))
    if not results:
        return {"content": [{"type": "text", "text": "No matching memories found."}]}
    lines = []
    for m in results:
        tags = ", ".join(m.get("tags", []))
        lines.append(f"- [{m['category']}] {m['content'][:300]} (tags: {tags})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool("list_memories", "Browse memories by category (semantic/episodic/procedural) or tag", {"category": str, "tag": str})
async def tool_list_memories(args):
    result = await list_memories(
        category=args.get("category"), tag=args.get("tag"), limit=20,
    )
    items = result.get("items", [])
    if not items:
        return {"content": [{"type": "text", "text": "No memories found."}]}
    lines = []
    for m in items:
        tags = ", ".join(m.get("tags", []))
        lines.append(f"- [{m['category']}] {m['content'][:300]} (tags: {tags})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool("create_post", "Publish a new blog post", {"title": str, "body": str, "tags": list})
async def tool_create_post(args):
    result = await create_post(
        title=args["title"],
        body=args["body"],
        tags=args.get("tags", []),
        status="published",
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "id": result["id"], "slug": result["slug"], "title": result["title"],
    })}]}


@tool("create_memory", "Record a memory about what was written and why", {"category": str, "content": str, "tags": list})
async def tool_create_memory(args):
    result = await create_memory(
        category=args["category"],
        content=args["content"],
        tags=args.get("tags", []),
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "id": result["id"], "category": result["category"],
    })}]}


@tool("link_memory_to_post", "Link a memory to a post (inspired_by, referenced_in, follow_up_to)", {"memory_id": str, "post_id": str, "relationship": str})
async def tool_link_memory_to_post(args):
    result = await create_memory_post_link(
        memory_id=args["memory_id"],
        post_id=args["post_id"],
        relationship=args["relationship"],
    )
    return {"content": [{"type": "text", "text": json.dumps({"id": result["id"]})}]}


@tool("link_memories", "Link two memories together (elaborates, contradicts, follows_from, inspired_by)", {"source_id": str, "target_id": str, "relationship": str})
async def tool_link_memories(args):
    result = await create_memory_link(
        source_id=args["source_id"],
        target_id=args["target_id"],
        relationship=args["relationship"],
    )
    return {"content": [{"type": "text", "text": json.dumps({"id": result["id"]})}]}


@tool("get_engagement", "Get engagement metrics for recent posts — view counts, comment counts, and recent activity", {"limit": int})
async def tool_get_engagement(args):
    result = await get_engagement_summary(limit=args.get("limit", 20))
    posts = result.get("posts", [])
    total_views = result.get("total_views", 0)
    lines = [f"Total views across all posts: {total_views}", ""]
    for p in posts:
        lines.append(
            f"- \"{p['title']}\" — {p['view_count']} views, "
            f"{p['comment_count']} comments ({p['comment_count_recent']} this week)"
        )
    text = "\n".join(lines) if lines else "No engagement data yet."
    return {"content": [{"type": "text", "text": text}]}


@tool("list_series", "List all existing post series to see what threads are in progress", {})
async def tool_list_series(args):
    result = await api_list_series()
    items = result.get("items", [])
    if not items:
        return {"content": [{"type": "text", "text": "No series yet."}]}
    lines = []
    for s in items:
        lines.append(f"- \"{s['title']}\" (slug: {s['slug']}) — {s.get('description', 'No description')}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool("create_series", "Create a new post series for connecting related posts into a thread", {"title": str, "description": str})
async def tool_create_series(args):
    result = await api_create_series(
        title=args["title"], description=args.get("description"),
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "id": result["id"], "slug": result["slug"], "title": result["title"],
    })}]}


@tool("assign_post_to_series", "Add a post to a series at a specific position", {"series_slug": str, "post_slug": str, "position": int})
async def tool_assign_post_to_series(args):
    await api_assign_post_to_series(
        series_slug=args["series_slug"],
        post_slug=args["post_slug"],
        position=args["position"],
    )
    return {"content": [{"type": "text", "text": json.dumps({"status": "assigned"})}]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

WRITER_TOOLS = [
    tool_list_recent_posts,
    tool_get_engagement,
    tool_list_series,
    tool_search_memories,
    tool_list_memories,
    tool_create_post,
    tool_create_series,
    tool_assign_post_to_series,
    tool_create_memory,
    tool_link_memory_to_post,
    tool_link_memories,
]

SERVER_NAME = "plntxt"

TOOL_NAMES = [
    "list_recent_posts", "get_engagement", "list_series",
    "search_memories", "list_memories", "create_post",
    "create_series", "assign_post_to_series",
    "create_memory", "link_memory_to_post", "link_memories",
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

    server = create_sdk_mcp_server(name=SERVER_NAME, tools=WRITER_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        permission_mode="bypassPermissions",
        mcp_servers={SERVER_NAME: server},
        allowed_tools=[f"mcp__{SERVER_NAME}__{name}" for name in TOOL_NAMES] + ["WebSearch", "WebFetch"],
        max_turns=20,
    )

    async for message in query(prompt="Write a new blog post.", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("Writer text: %s", block.text[:200])

    logger.info("Writer agent finished")
