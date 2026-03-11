from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas.graph import GraphData, GraphEdge, GraphNode, GraphStats

SPECIAL_TAGS = {"open-question", "influence", "reader-contribution"}
MAX_MEMORIES = 200
MAX_POSTS = 100


async def build_graph(db: AsyncSession) -> GraphData:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    memory_ids: list[str] = []
    post_ids: list[str] = []
    tag_counts: dict[str, int] = defaultdict(int)
    tag_node_map: dict[str, list[str]] = defaultdict(list)

    semantic_count = 0
    episodic_count = 0

    # Query 1: Public, non-expired memories (excluding procedural)
    mem_result = await db.execute(
        text("""
            SELECT id::text, category::text, content, tags, created_at::text
            FROM memory
            WHERE public = true
              AND category != 'PROCEDURAL'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT :limit
        """),
        {"limit": MAX_MEMORIES},
    )
    for row in mem_result.mappings():
        mid = row["id"]
        memory_ids.append(mid)
        cat = row["category"].lower()
        tags = row["tags"] or []
        content = row["content"] or ""
        special = [t for t in tags if t in SPECIAL_TAGS]

        label = content[:80] + "..." if len(content) > 80 else content

        nodes.append(GraphNode(
            id=mid,
            type=cat,
            label=label,
            detail=content if len(content) > 80 else None,
            tags=tags,
            special_tags=special,
            created_at=row["created_at"],
        ))

        if cat == "semantic":
            semantic_count += 1
        else:
            episodic_count += 1

        for t in tags:
            if t not in SPECIAL_TAGS:
                tag_counts[t] += 1
                tag_node_map[t].append(mid)

    # Query 2: Published posts
    post_result = await db.execute(
        text("""
            SELECT id::text, title, slug, tags, published_at::text, view_count
            FROM posts
            WHERE status = 'PUBLISHED'
            ORDER BY published_at DESC
            LIMIT :limit
        """),
        {"limit": MAX_POSTS},
    )
    for row in post_result.mappings():
        pid = row["id"]
        post_ids.append(pid)
        tags = row["tags"] or []
        title = row["title"] or ""

        label = title[:80] + "..." if len(title) > 80 else title

        nodes.append(GraphNode(
            id=pid,
            type="post",
            label=label,
            url=f"/posts/{row['slug']}",
            tags=tags,
            special_tags=[],
            created_at=row["published_at"],
            view_count=row["view_count"],
        ))

        for t in tags:
            tag_counts[t] += 1
            tag_node_map[t].append(pid)

    # Query 3: Edges (memory-memory + memory-post)
    if memory_ids or post_ids:
        edge_result = await db.execute(
            text("""
                SELECT id::text, source_id::text AS source, target_id::text AS target,
                       relationship::text AS rel, 'memory-memory' AS edge_type
                FROM memory_links
                WHERE source_id = ANY(:mem_ids) AND target_id = ANY(:mem_ids)
                UNION ALL
                SELECT id::text, memory_id::text AS source, post_id::text AS target,
                       relationship::text AS rel, 'memory-post' AS edge_type
                FROM memory_post_links
                WHERE memory_id = ANY(:mem_ids) AND post_id = ANY(:post_ids)
            """),
            {"mem_ids": memory_ids or ["00000000-0000-0000-0000-000000000000"],
             "post_ids": post_ids or ["00000000-0000-0000-0000-000000000000"]},
        )
        for row in edge_result.mappings():
            edges.append(GraphEdge(
                id=row["id"],
                source=row["source"],
                target=row["target"],
                rel=row["rel"],
                edge_type=row["edge_type"],
            ))

    # Synthesize tag cluster nodes for tags appearing on 2+ nodes
    tag_count_total = 0
    for tag, count in tag_counts.items():
        if count >= 2:
            tag_id = f"tag:{tag}"
            nodes.append(GraphNode(
                id=tag_id,
                type="tag",
                label=tag,
                tags=[],
                special_tags=[],
            ))
            tag_count_total += 1
            for node_id in tag_node_map[tag]:
                edges.append(GraphEdge(
                    id=f"tag-edge:{tag}:{node_id}",
                    source=node_id,
                    target=tag_id,
                    rel="tagged",
                    edge_type="tag",
                ))

    stats = GraphStats(
        post_count=len(post_ids),
        semantic_count=semantic_count,
        episodic_count=episodic_count,
        tag_count=tag_count_total,
        edge_count=len(edges),
    )

    return GraphData(nodes=nodes, edges=edges, stats=stats)
