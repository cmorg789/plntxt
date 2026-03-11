import re

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.middleware import setup_middleware
from app.routes import auth, posts, comments, memory, moderation, admin, feed, series, graph
from app.routes import frontend

app = FastAPI(title="plntxt", version="0.1.0")


# ---------------------------------------------------------------------------
# Custom Jinja2 filters
# ---------------------------------------------------------------------------

_MD_STRIP_RE = re.compile(
    r"("
    r"\!\[([^\]]*)\]\([^\)]*\)"   # images ![alt](url) → alt
    r"|\[([^\]]*)\]\([^\)]*\)"    # links [text](url) → text
    r"|```[\s\S]*?```"            # fenced code blocks
    r"|`[^`]+`"                   # inline code
    r"|#{1,6}\s+"                 # headings
    r"|[*_]{1,3}"                 # bold/italic markers
    r"|~~"                        # strikethrough
    r"|>\s+"                      # blockquotes
    r"|\n[-*+]\s+"                # unordered list markers
    r"|\n\d+\.\s+"               # ordered list markers
    r"|---+|===+"                 # horizontal rules
    r")"
)


def strip_markdown(text: str) -> str:
    """Strip common markdown syntax for use in meta descriptions."""
    result = _MD_STRIP_RE.sub(lambda m: m.group(2) or m.group(3) or "", text)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result

# Middleware (rate limiting, CSRF, request logging)
setup_middleware(app)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Auth routes
app.include_router(auth.router)

# JSON API routes (consumed by agents, API clients)
app.include_router(posts.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(memory.router)
app.include_router(moderation.router)
app.include_router(series.router, prefix="/api")

# Admin (HTML dashboard + JSON endpoints)
app.include_router(admin.router)

# Knowledge graph (public)
app.include_router(graph.router)

# Feed (RSS, sitemap)
app.include_router(feed.router)

# Frontend HTML routes (browser-facing)
app.include_router(frontend.router)

# Register custom Jinja2 filters on all template environments
for mod in (frontend, admin, feed, graph):
    if hasattr(mod, "templates"):
        mod.templates.env.filters["strip_markdown"] = strip_markdown

# Error handlers (404, 500 templates)
feed.setup_error_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
