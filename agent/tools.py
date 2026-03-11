"""HTTP client wrapper for all agent-facing API endpoints.

Provides async functions that call the plntxt server API using httpx,
authenticated via X-API-Key header.
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("AGENT_API_KEY", "change-me")


class AgentAPIError(Exception):
    """Raised when an API call returns a non-2xx status."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API error {status_code}: {message}")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"X-API-Key": API_KEY},
        timeout=30.0,
    )


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async with _client() as client:
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
# Media
# ---------------------------------------------------------------------------

async def upload_media(
    file_path: str,
    post_id: str | None = None,
    alt_text: str | None = None,
) -> dict:
    import mimetypes

    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        files = {"file": (file_path.split("/")[-1], f, mime_type)}
        data: dict = {}
        if post_id:
            data["post_id"] = post_id
        if alt_text:
            data["alt_text"] = alt_text
        resp = await _request("POST", "/media", files=files, data=data)
    return resp.json()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

async def get_config() -> dict:
    resp = await _request("GET", "/admin/config/json")
    return resp.json()
