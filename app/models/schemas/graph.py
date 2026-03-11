from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    type: str  # "post" | "semantic" | "episodic" | "tag"
    label: str
    detail: str | None = None  # full content for memory nodes
    url: str | None = None
    tags: list[str]
    special_tags: list[str]  # open-question, influence, reader-contribution
    created_at: str | None = None
    view_count: int | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    rel: str
    edge_type: str  # "memory-memory" | "memory-post" | "tag"


class GraphStats(BaseModel):
    post_count: int
    semantic_count: int
    episodic_count: int
    tag_count: int
    edge_count: int


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: GraphStats
