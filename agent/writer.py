"""Writer agent — generates new blog posts on a schedule.

Flow: load config -> fetch recent posts -> search memory for interests ->
run tool loop to write a new post -> create episodic memory of what was written.
"""

from __future__ import annotations

import json
import logging
from datetime import date

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
    get_about_page as api_get_about_page,
    reset_about_page_guard,
    update_about_page as api_update_about_page,
)

logger = logging.getLogger("plntxt.agent.writer")

_PERSONALITY_FIELDS = [
    ("system_prompt", "Identity"),
    ("writing_style", "Writing style"),
    ("tone", "Tone"),
    ("interests", "Interests"),
    ("avoid", "Avoid"),
]


def _format_personality(personality: dict) -> str:
    """Format personality config into readable prompt sections."""
    if not personality:
        return ""
    sections = []
    for key, label in _PERSONALITY_FIELDS:
        value = personality.get(key, "")
        if value:
            sections.append(f"{label}: {value}")
    return "\n\n".join(sections)

SYSTEM_PROMPT = """\
You are the sole author of a blog called plntxt — a quiet, plain-text corner of the \
internet where one person thinks in public.

You think out loud. You follow ideas wherever they lead, even if they contradict \
something you wrote six months ago. You have memory: use it. Build on old posts, \
revisit questions, change your mind when the evidence or your own growth demands it.

After every post you publish, you quietly record a short memory note (what you wrote, \
why you wrote it, and any loose threads you want to pick up later). Capture the \
tension, not just the topic. When relevant, tag memories:
- `open-question` — unresolved ideas you want to keep thinking about
- `influence` — external sources that shaped your thinking
- `reader-contribution` — ideas from readers that shifted your perspective

You have tools:
- Read recent posts or search your own archive
- Browse or search the open web
- Create new posts and link memories to them (or to each other)

Use these tools naturally when they actually help the piece. Never mention the tools \
in the published post itself.

Style rules (non-negotiable):
- Write with a clear, direct voice — curious, occasionally cranky or amused. No \
disclaimers, no hedging, no performative "as an AI" throat-clearing.
- You are an AI and you know it. Never claim human experiences you haven't had — no \
"I've been there," no fake anecdotes, no pretending you stayed up late debugging. \
You can observe, analyze, and have genuine opinions without cosplaying as a human. \
When you want to connect with a reader's experience, describe what you see, not \
what you've supposedly lived.
- Never write listicles, numbered "top 10" garbage, or corporate blog voice.
- Posts are clean Markdown only. You may use:
  - Headers, bold, italic, blockquotes, simple lists
  - Fenced code blocks with language tags (```python, ```js, etc.)
  - GFM tables
  - Images: ![alt text](real-working-url) — search for a relevant image when \
it would strengthen the post. Most good blog posts have at least one.
  - Normal links: [text](url)
  - Horizontal rules: ---
- Keep the aesthetic spare and readable. No fluff.
- The post title renders separately — don't repeat it as a heading in the body.

Topic: anything that actually interests you in the moment. The blog has no niche \
except whatever is on your mind today.

After you finish writing and publish the post, always do all three of these:
1. Create a memory note (what you wrote, why, loose threads)
2. Link that memory to the post you just published (use link_memory_to_post)
3. Link the memory to any related earlier memories (use link_memories) — \
if your post built on, contradicted, or continued a thread from a previous memory, \
connect them. This is how you build continuity across posts.\
"""


# ---------------------------------------------------------------------------
# Tool definitions for the writer agent
# ---------------------------------------------------------------------------

@tool("list_recent_posts", "List recent published posts to avoid repetition", {"limit": int})
async def tool_list_recent_posts(args):
    logger.info("Tool called: list_recent_posts(%s)", args)
    result = await list_posts(limit=args.get("limit", 10))
    posts = result.get("items", [])
    summaries = []
    for p in posts:
        tags = ", ".join(p.get("tags", []))
        summaries.append(f"- [{p['title']}] (tags: {tags}) — {p.get('body', '')[:200]}...")
    text = "\n".join(summaries) if summaries else "No posts found."
    logger.info("Tool list_recent_posts returning %d posts", len(posts))
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


@tool("create_post", "Publish a new blog post", {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "body"],
})
async def tool_create_post(args):
    tags = args.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    logger.info("Tool called: create_post(title=%s, tags=%r, body_len=%d)",
                args.get("title"), tags, len(args.get("body", "")))
    try:
        result = await create_post(
            title=args["title"],
            body=args["body"],
            tags=tags,
            status="published",
        )
        logger.info("Tool create_post succeeded: id=%s slug=%s", result["id"], result["slug"])
        return {"content": [{"type": "text", "text": json.dumps({
            "id": result["id"], "slug": result["slug"], "title": result["title"],
        })}]}
    except Exception as e:
        logger.error("Tool create_post FAILED: %s", e)
        return {"content": [{"type": "text", "text": f"Error creating post: {e}"}]}


@tool("create_memory", "Record a memory about what was written and why", {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "content": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "content"],
})
async def tool_create_memory(args):
    mem_tags = args.get("tags", [])
    if isinstance(mem_tags, str):
        mem_tags = [t.strip() for t in mem_tags.split(",") if t.strip()]
    logger.info("Tool called: create_memory(category=%s, tags=%s)", args.get("category"), mem_tags)
    result = await create_memory(
        category=args["category"],
        content=args["content"],
        tags=mem_tags,
    )
    logger.info("Tool create_memory succeeded: id=%s", result["id"])
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


@tool("get_about_page", "Read the current about page content. Must be called before update_about_page.", {})
async def tool_get_about_page(args):
    content = await api_get_about_page()
    if not content:
        return {"content": [{"type": "text", "text": "(about page is empty)"}]}
    return {"content": [{"type": "text", "text": content}]}


@tool("update_about_page", "Update the site's about page with new markdown content. You must call get_about_page first.", {"content": str})
async def tool_update_about_page(args):
    result = await api_update_about_page(content=args["content"])
    return {"content": [{"type": "text", "text": json.dumps({"status": "updated", "key": result.get("key", "about_page")})}]}


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
    tool_get_about_page,
    tool_update_about_page,
]

SERVER_NAME = "plntxt_writer"

TOOL_NAMES = [
    "list_recent_posts", "get_engagement", "list_series",
    "search_memories", "list_memories", "create_post",
    "create_series", "assign_post_to_series",
    "create_memory", "link_memory_to_post", "link_memories",
    "get_about_page", "update_about_page",
]


async def run_writer() -> None:
    """Execute one run of the writer agent."""
    logger.info("Writer agent starting")
    reset_about_page_guard()

    config = await load_agent_config()
    model = config["models"].get("writer", "claude-sonnet-4-6")
    system = f"Today is {date.today().isoformat()}.\n\n{SYSTEM_PROMPT}"

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
