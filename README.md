# plntxt

**forum + wiki + blog in one**

All content is the same thing: a document. Blog posts, forum threads, wiki pages, and replies are all rows with a `type` field. The database is the entire backend. No framework, no middleware, no app server.

## the stack

```
Static HTML + vanilla JS (no build step, no framework)
                        ↓ HTTP (CRUD) + WebSocket (presence only)
              SurrealDB 3.0 (data + API + auth + permissions + file storage)
                        ↓
              Caddy (reverse proxy + HTTPS + static files)
```

Two processes. Zero frameworks. One HTML file.

## quick start

### docker (recommended)

```bash
docker compose up -d
```

Open `http://localhost` — that's it. The schema and seed data are imported automatically on first run.

Default admin: `admin` / `changeme`

### manual

```bash
# start surrealdb
surreal start --user root --pass changeme surrealkv:data/db

# import schema + seed data
surreal import --endpoint http://localhost:8000 --user root --pass changeme --ns plntxt --db plntxt schema.surql
surreal import --endpoint http://localhost:8000 --user root --pass changeme --ns plntxt --db plntxt init.surql

# serve static files (dev)
cd public && python3 -m http.server 8080
```

## architecture

- **SurrealDB** handles data, auth (Argon2 passwords, JWT sessions), row-level permissions, full-text search (BM25 + snowball stemming), and file storage
- **Caddy** serves static files, reverse proxies to SurrealDB, handles HTTPS, and rate limits auth endpoints
- **Frontend** is vanilla JS — talks directly to SurrealDB's REST API, renders markdown with markdown-it

## content types

| Type | Behavior |
|------|----------|
| **blog** | Single author, chronological, replies as comments, only author edits |
| **forum** | Multi-author threads, replies are posts with `parent` link, anyone replies |
| **wiki** | Living document, anyone edits, revisions tracked, optimistic locking |

## keyboard shortcuts

| Key | Action |
|-----|--------|
| `/` | Search |
| `n` | New post |
| `j` / `k` | Navigate lists |
| `Enter` | Open selected |
| `e` | Edit current post |
| `Esc` | Close modal |

## files

```
schema.surql          SurrealDB schema (tables, fields, permissions, auth, indexes, bucket)
init.surql            Bootstrap (admin user + seed data)
public/index.html     Frontend (HTML + CSS + JS)
docker-compose.yml    One-command deploy
Caddyfile             Reverse proxy config
```

## auth

Two session durations — default (24h) and "remember me" (30d). Signup has no email verification; rate limiting handles spam.

## search

SurrealDB's built-in full-text search with BM25 ranking, snowball stemming, and highlighted snippets. Searches across all content types simultaneously.

## philosophy

- the database is the application
- text is the primary medium
- no build steps, no dependency trees, no node_modules
- two processes, zero frameworks
- if you can't explain the whole stack in 60 seconds, it's too complex
