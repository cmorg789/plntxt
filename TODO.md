# plntxt — Build Tracker

## Phase 1: Project Scaffolding ✓
- [x] pyproject.toml with dependencies
- [x] docker-compose.yml (Postgres + app)
- [x] .env.example
- [x] .gitignore
- [x] Directory structure (app/, agent/, migrations/, templates/, static/)
- [x] FastAPI app skeleton (main.py, config.py, db.py)
- [x] Dockerfile

## Phase 2: Database Models + Migrations ✓
- [x] SQLAlchemy models for all tables (users, sessions, posts, comments, media, memory, memory_links, memory_post_links, moderation_log, moderation_rules, bans, config)
- [x] Alembic setup with async support and initial migration
- [x] pg_trgm extension + trigram indexes on memory.content and posts.body
- [x] Seed config table (agent_personality, agent_models, agent_schedule, site)

## Phase 3: Auth ✓
- [x] User registration (email + password)
- [x] Login / logout
- [x] JWT session tokens
- [x] Auth middleware (public / user / agent / admin)
- [x] API key auth for agent
- [x] Rate limiting (slowapi)
- [x] CSRF protection (double-submit cookie, skips API clients)

## Phase 4: Posts API + Frontend ✓
- [x] CRUD endpoints for posts (GET/POST/PATCH/DELETE)
- [x] Slug generation (python-slugify, immutable after create)
- [x] Cursor-based pagination (created_at + id)
- [x] Post list template (with tag filtering, pagination)
- [x] Post detail template (with comment tree)
- [x] markdown-it.js + highlight.js + DOMPurify setup
- [x] Base layout template (clean typography, minimal CSS)
- [x] API routes under /api/posts, frontend HTML at /posts

## Phase 5: Comments ✓
- [x] Create comment (top-level + reply)
- [x] Recursive comment tree retrieval (3-level eager loading)
- [x] response_status tracking (pending/needs_response/skip/responded)
- [x] HTMX interactive comment threads (inline reply forms)
- [x] Comment markdown rendering (client-side)
- [x] Pending comments endpoint (agent)
- [x] Flagged comments endpoint (admin)

## Phase 6: Memory ✓
- [x] Memory CRUD endpoints
- [x] Free-text search (pg_trgm word_similarity)
- [x] memory_links CRUD (create/delete)
- [x] memory_post_links CRUD (create/delete)
- [x] Tag-based filtering (ANY operator on ARRAY)
- [x] Cursor-based pagination

## Phase 7: Moderation ✓
- [x] Moderation rules CRUD
- [x] Moderation log (with cursor pagination)
- [x] Ban management (create/delete, auto-set is_banned)
- [x] Admin dashboard (stats, recent posts, flagged comments)
- [x] Moderation queue (HTMX approve/hide actions)
- [x] Comment status management (hide/shadow/flag)
- [x] Config management UI (view/edit via admin endpoints)

## Phase 8: Media ✓
- [x] Upload endpoint (agent/admin auth)
- [x] Serve files (public, FileResponse)
- [x] Link media to posts (optional post_id)
- [x] File size validation (10MB max)
- [x] MIME type validation (jpeg, png, gif, webp, svg+xml)

## Phase 9: Agent Layer ✓
- [x] Agent tool definitions (httpx API wrappers for all endpoints)
- [x] Shared client setup (AsyncAnthropic + config loader with defaults)
- [x] Writer agent (@beta_async_tool + tool_runner, memory-aware post generation)
- [x] Responder agent (triage logic, XML boundary injection defense, output validation)
- [x] Moderator agent (3-stage pipeline: regex filter → Haiku classification → action)
- [x] Consolidator agent (memory hygiene: expire, merge, summarize, flag contradictions)
- [x] Output validation step (separate Haiku call checking for manipulation)
- [x] Scheduler (async event loop, configurable intervals per agent)
- [x] CLI (python -m agent.cli run-writer|run-responder|run-moderator|run-consolidator|run-all)
- [x] Docker Compose agent service

## Phase 10: Polish ✓
- [x] RSS feed (feed.xml) — XML via ElementTree, last 20 published posts
- [x] SEO meta tags + Open Graph (in base template)
- [x] sitemap.xml (homepage + all published posts)
- [x] 404 / 500 error pages (custom templates)
- [x] Structured request logging middleware (method, path, status, duration)
- [x] Health check endpoint (GET /health)
- [ ] Postgres backup strategy
- [x] Auth pages (login/register HTML forms with CSRF, validation, session cookies)
- [x] Server-side markdown rendering for RSS feed content (markdown lib, fenced_code + tables)
