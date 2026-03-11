from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.middleware import setup_middleware
from app.routes import auth, posts, comments, memory, moderation, media, admin, feed
from app.routes import frontend

app = FastAPI(title="plntxt", version="0.1.0")

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
app.include_router(media.router)

# Admin (HTML dashboard + JSON endpoints)
app.include_router(admin.router)

# Feed (RSS, sitemap)
app.include_router(feed.router)

# Frontend HTML routes (browser-facing)
app.include_router(frontend.router)

# Error handlers (404, 500 templates)
feed.setup_error_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
