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
    create_memory,
    create_memory_link,
    create_memory_post_link,
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

When creating or updating memories, preserve these special tags if present:
- "open-question" — unresolved ideas (keep until genuinely resolved)
- "influence" — external sources that shaped thinking
- "reader-contribution" — ideas from readers that shifted perspective

These tags surface in the public knowledge graph. Don't strip them during merges unless \
the merged memory no longer fits the convention.

Be conservative. Don't delete memories that are still useful. Don't merge things that \
are genuinely distinct. Quality over tidiness.\
"""


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool("list_memories", "Browse memories by category (semantic/episodic/procedural) or tag", {"category": str, "tag": str})
async def tool_list_memories(args):
    result = await list_memories(
        category=args.get("category"), tag=args.get("tag"), limit=50,
    )
    items = result.get("items", [])
    if not items:
        return {"content": [{"type": "text", "text": "No memories found."}]}
    lines = []
    for m in items:
        tags = ", ".join(m.get("tags", []))
        expires = m.get("expires_at", "never")
        lines.append(
            f"- ID: {m['id']} [{m['category']}] (tags: {tags}, expires: {expires})\n"
            f"  {m['content'][:400]}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool("create_memory", "Create a new memory (e.g. a merged semantic memory)", {"category": str, "content": str, "tags": list})
async def tool_create_memory(args):
    result = await create_memory(
        category=args["category"],
        content=args["content"],
        tags=args.get("tags", []),
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "id": result["id"], "category": result["category"],
    })}]}


@tool("update_memory", "Update an existing memory's content or tags", {"memory_id": str, "content": str, "tags": list})
async def tool_update_memory(args):
    kwargs: dict = {}
    if "content" in args and args["content"]:
        kwargs["content"] = args["content"]
    if "tags" in args and args["tags"]:
        kwargs["tags"] = args["tags"]
    result = await update_memory(args["memory_id"], **kwargs)
    return {"content": [{"type": "text", "text": json.dumps({
        "id": result["id"], "updated": True,
    })}]}


@tool("delete_memory", "Delete a memory that is expired, redundant, or no longer useful", {"memory_id": str})
async def tool_delete_memory(args):
    await delete_memory(args["memory_id"])
    return {"content": [{"type": "text", "text": json.dumps({"deleted": args["memory_id"]})}]}


@tool("link_memories", "Create a link between two memories (elaborates, contradicts, follows_from, inspired_by)", {"source_id": str, "target_id": str, "relationship": str})
async def tool_link_memories(args):
    result = await create_memory_link(
        source_id=args["source_id"],
        target_id=args["target_id"],
        relationship=args["relationship"],
    )
    return {"content": [{"type": "text", "text": json.dumps({"id": result["id"]})}]}


@tool("link_memory_to_post", "Link a memory to a post (inspired_by, referenced_in, follow_up_to)", {"memory_id": str, "post_id": str, "relationship": str})
async def tool_link_memory_to_post(args):
    result = await create_memory_post_link(
        memory_id=args["memory_id"],
        post_id=args["post_id"],
        relationship=args["relationship"],
    )
    return {"content": [{"type": "text", "text": json.dumps({"id": result["id"]})}]}


CONSOLIDATOR_TOOLS = [
    tool_list_memories,
    tool_create_memory,
    tool_update_memory,
    tool_delete_memory,
    tool_link_memories,
    tool_link_memory_to_post,
]

SERVER_NAME = "plntxt"

TOOL_NAMES = [
    "list_memories", "create_memory", "update_memory",
    "delete_memory", "link_memories", "link_memory_to_post",
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_consolidator() -> None:
    """Execute one run of the consolidator agent."""
    logger.info("Consolidator agent starting")

    config = await load_agent_config()
    model = config["models"].get("consolidator", "claude-haiku-4-5-20251001")

    server = create_sdk_mcp_server(name=SERVER_NAME, tools=CONSOLIDATOR_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=model,
        permission_mode="bypassPermissions",
        mcp_servers={SERVER_NAME: server},
        allowed_tools=[f"mcp__{SERVER_NAME}__{name}" for name in TOOL_NAMES],
        max_turns=30,
    )

    async for message in query(
        prompt="Review all memories and perform consolidation. Start by listing memories in each category.",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("Consolidator text: %s", block.text[:200])

    logger.info("Consolidator agent finished")
