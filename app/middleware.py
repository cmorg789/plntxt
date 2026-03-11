import logging
import secrets
import time

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("plntxt.middleware")

# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


def setup_rate_limiting(app: FastAPI) -> None:
    """Attach the slowapi limiter to the application."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# IP Extraction
# ---------------------------------------------------------------------------


def get_client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For may contain a comma-separated list; first is the client.
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# CSRF Protection Middleware
# ---------------------------------------------------------------------------

_STATE_CHANGING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Simple double-submit-cookie CSRF protection for browser forms.

    Skips validation for API clients that authenticate via X-API-Key or
    Authorization: Bearer headers — those endpoints don't rely on cookies.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Always ensure a CSRF cookie is present so templates can read it.
        csrf_cookie = request.cookies.get("csrf_token")
        if not csrf_cookie:
            csrf_cookie = secrets.token_urlsafe(32)

        # Only validate on state-changing methods from cookie-authenticated
        # (i.e. browser) requests.
        if request.method in _STATE_CHANGING_METHODS:
            if not self._is_api_client(request):
                submitted = await self._get_submitted_token(request)
                if not submitted or not secrets.compare_digest(submitted, csrf_cookie):
                    return Response("CSRF token missing or invalid", status_code=403)

        response = await call_next(request)

        # Set / refresh the CSRF cookie on every response.
        response.set_cookie(
            key="csrf_token",
            value=csrf_cookie,
            httponly=False,
            samesite="strict",
            secure=False,  # flip to True behind HTTPS in production
            path="/",
        )
        return response

    @staticmethod
    def _is_api_client(request: Request) -> bool:
        if request.headers.get("x-api-key"):
            return True
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return True
        return False

    @staticmethod
    async def _get_submitted_token(request: Request) -> str | None:
        # Prefer the header (HTMX / JS callers).
        token = request.headers.get("x-csrf-token")
        if token:
            return token

        # Fall back to parsing the raw body for form submissions so we don't
        # consume the stream that FastAPI's Form() needs to read later.
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            from urllib.parse import parse_qs

            body = await request.body()
            parsed = parse_qs(body.decode("utf-8", errors="replace"))
            values = parsed.get("_csrf_token", [])
            return values[0] if values else None

        return None


# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------

_SKIP_LOG_PREFIXES = ("/health", "/static")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path.startswith(_SKIP_LOG_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "method=%s path=%s status=%d duration_ms=%.1f",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        return response


# ---------------------------------------------------------------------------
# Site Config Middleware
# ---------------------------------------------------------------------------

_site_config_cache: dict | None = None
_site_config_defaults = {
    "title": "plntxt",
    "description": "An AI-authored blog",
    "author": "Claude",
}


class SiteConfigMiddleware(BaseHTTPMiddleware):
    """Load site config from DB and attach to request.state for templates.

    Caches the config in memory and refreshes when /admin/config is POSTed.
    Only runs for HTML-facing requests (skips /api, /static, /health).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        global _site_config_cache

        path = request.url.path
        if not path.startswith(("/api/", "/static/", "/health", "/media/", "/memory", "/moderation")):
            if _site_config_cache is None:
                _site_config_cache = await self._load_config()
            request.state.site_config = _site_config_cache
        else:
            request.state.site_config = _site_config_defaults

        response = await call_next(request)

        # Invalidate cache when config is edited
        if path.startswith("/admin/config") and request.method == "POST":
            _site_config_cache = None

        return response

    @staticmethod
    async def _load_config() -> dict:
        from sqlalchemy import select

        from app.db import async_session
        from app.models.config import Config

        try:
            async with async_session() as session:
                result = await session.execute(select(Config).where(Config.key == "site"))
                row = result.scalar_one_or_none()
                if row is not None:
                    return {**_site_config_defaults, **row.value}
        except Exception:
            pass
        return dict(_site_config_defaults)


# ---------------------------------------------------------------------------
# Aggregate Setup
# ---------------------------------------------------------------------------


def setup_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI application.

    Middleware is added in reverse order of desired execution:
    outermost (first to run) should be added last.
    """
    # Rate limiting (attaches to app.state + exception handler, not middleware).
    setup_rate_limiting(app)

    # Site config — innermost, loads site config for template rendering.
    app.add_middleware(SiteConfigMiddleware)

    # CSRF — runs after logging so failed CSRF attempts are still logged.
    app.add_middleware(CSRFMiddleware)

    # Request logging — outermost, added last so it executes first.
    app.add_middleware(RequestLoggingMiddleware)
