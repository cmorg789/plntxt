"""HTTP client wrapper for all agent-facing API endpoints.

Provides async functions that call the plntxt server API using httpx,
authenticated via X-API-Key header.
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("AGENT_API_KEY", "change-me")

# Module-level client for connection pooling across requests
_shared_client: httpx.AsyncClient | None = None


class AgentAPIError(Exception):
    """Raised when an API call returns a non-2xx status."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API error {status_code}: {message}")


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"X-API-Key": API_KEY},
            timeout=30.0,
        )
    return _shared_client


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    client = _get_client()
    resp = await client.request(method, path, **kwargs)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise AgentAPIError(resp.status_code, str(detail))
    return resp


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

async def list_posts(
    cursor: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict:
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    if tag:
        params["tag"] = tag
    if status:
        params["status"] = status
    resp = await _request("GET", "/api/posts", params=params)
    return resp.json()


async def get_post(slug: str) -> dict:
    resp = await _request("GET", f"/api/posts/{slug}")
    return resp.json()


async def create_post(
    title: str,
    body: str,
    tags: list[str] | None = None,
    status: str = "published",
) -> dict:
    payload: dict = {"title": title, "body": body, "status": status}
    if tags is not None:
        payload["tags"] = tags
    resp = await _request("POST", "/api/posts", json=payload)
    return resp.json()


async def update_post(slug: str, **kwargs) -> dict:
    resp = await _request("PATCH", f"/api/posts/{slug}", json=kwargs)
    return resp.json()


async def get_engagement_summary(limit: int = 20) -> dict:
    resp = await _request("GET", "/api/posts/engagement", params={"limit": limit})
    return resp.json()


async def search_posts(q: str, limit: int = 20) -> dict:
    resp = await _request("GET", "/api/posts/search", params={"q": q, "limit": limit})
    return resp.json()


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

async def get_pending_comments(
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    resp = await _request("GET", "/api/comments/pending", params=params)
    return resp.json()


async def reply_to_comment(comment_id: str, body: str) -> dict:
    resp = await _request("POST", f"/api/comments/{comment_id}/reply", json={"body": body})
    return resp.json()


async def moderate_comment(
    comment_id: str,
    status: str | None = None,
    response_status: str | None = None,
) -> dict:
    payload: dict = {}
    if status is not None:
        payload["status"] = status
    if response_status is not None:
        payload["response_status"] = response_status
    resp = await _request("PATCH", f"/api/comments/{comment_id}", json=payload)
    return resp.json()


async def fetch_all_pending_comments(page_limit: int = 20) -> list[dict]:
    """Paginate through all pending comments and return them as a flat list."""
    all_comments: list[dict] = []
    cursor = None
    while True:
        result = await get_pending_comments(cursor=cursor, limit=page_limit)
        items = result.get("items", [])
        all_comments.extend(items)
        cursor = result.get("next_cursor")
        if not cursor or not items:
            break
    return all_comments


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

async def list_memories(
    category: str | None = None,
    tag: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    params: dict = {"limit": limit}
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag
    if cursor:
        params["cursor"] = cursor
    resp = await _request("GET", "/memory", params=params)
    return resp.json()


async def search_memories(q: str, limit: int = 20) -> list[dict]:
    resp = await _request("GET", "/memory/search", params={"q": q, "limit": limit})
    return resp.json()


async def create_memory(
    category: str,
    content: str,
    tags: list[str] | None = None,
    expires_at: str | None = None,
) -> dict:
    payload: dict = {"category": category, "content": content}
    if tags is not None:
        payload["tags"] = tags
    if expires_at is not None:
        payload["expires_at"] = expires_at
    resp = await _request("POST", "/memory", json=payload)
    return resp.json()


async def update_memory(memory_id: str, **kwargs) -> dict:
    resp = await _request("PATCH", f"/memory/{memory_id}", json=kwargs)
    return resp.json()


async def delete_memory(memory_id: str) -> None:
    await _request("DELETE", f"/memory/{memory_id}")


async def create_memory_link(
    source_id: str,
    target_id: str,
    relationship: str,
) -> dict:
    resp = await _request(
        "POST",
        "/memory/links",
        json={"source_id": source_id, "target_id": target_id, "relationship": relationship},
    )
    return resp.json()


async def create_memory_post_link(
    memory_id: str,
    post_id: str,
    relationship: str,
) -> dict:
    resp = await _request(
        "POST",
        "/memory/post-links",
        json={"memory_id": memory_id, "post_id": post_id, "relationship": relationship},
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

async def list_series() -> dict:
    resp = await _request("GET", "/api/series")
    return resp.json()


async def create_series(title: str, description: str | None = None) -> dict:
    payload: dict = {"title": title}
    if description is not None:
        payload["description"] = description
    resp = await _request("POST", "/api/series", json=payload)
    return resp.json()


async def assign_post_to_series(
    series_slug: str, post_slug: str, position: int
) -> dict:
    resp = await _request(
        "POST",
        f"/api/series/{series_slug}/posts",
        json={"post_slug": post_slug, "position": position},
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Moderation Rules
# ---------------------------------------------------------------------------


async def fetch_moderation_rules(active: bool = True) -> list[dict]:
    """Fetch moderation rules from the server."""
    params: dict = {}
    if active is not None:
        params["active"] = str(active).lower()
    resp = await _request("GET", "/moderation/rules", params=params)
    return resp.json()


async def propose_moderation_rule(
    rule_type: str,
    value: str,
    action: str,
    reason: str,
) -> dict:
    """Propose a new moderation rule for admin review.

    Rules proposed by agents are not active until an admin approves them.
    """
    resp = await _request(
        "POST",
        "/moderation/rules",
        json={
            "rule_type": rule_type,
            "value": value,
            "action": action,
            "proposed_reason": reason,
        },
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

async def get_config() -> dict:
    resp = await _request("GET", "/admin/config/json")
    return resp.json()


_about_page_read = False


def reset_about_page_guard() -> None:
    """Reset the read-before-write guard. Call at the start of each agent run."""
    global _about_page_read
    _about_page_read = False


async def get_about_page() -> str:
    """Read the current about page content."""
    global _about_page_read
    resp = await _request("GET", "/admin/config/json")
    data = resp.json()
    _about_page_read = True
    about = data.get("about_page", {})
    value = about.get("value", {}) if isinstance(about, dict) else {}
    return value.get("content", "")


async def update_about_page(content: str) -> dict:
    """Update the about page content (markdown). Requires get_about_page() first."""
    if not _about_page_read:
        raise RuntimeError("Must call get_about_page() before updating")
    resp = await _request(
        "PATCH",
        "/admin/config/about_page",
        json={"value": {"content": content}},
    )
    return resp.json()
