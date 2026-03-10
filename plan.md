# plntxt

**forum + wiki + blog in one**

---

## concept

All content is the same thing: a document. Blog posts, forum threads, wiki pages, and replies are all rows with a `type` field. The database is the entire backend. No framework, no middleware, no app server. One binary, one HTML file.

---

## architecture

```
Static HTML + vanilla JS (no build step, no framework)
                        ↓ HTTP (CRUD) + WebSocket (presence only)
              SurrealDB 3.0 (data + API + auth + permissions + file storage)
```

Two things to run. One serves static files and proxies to the database (Caddy). The other is SurrealDB. That's the whole stack. Frontend can be split into multiple files if complexity warrants it — no single-file dogma.

---

## database: SurrealDB 3.0

- **Why**: native HTTP + WebSocket API, built-in auth, row-level permissions, SQL-like queries with document/graph flexibility, file storage via DEFINE BUCKET, single Rust binary, runs anywhere.
- **License**: BSL 1.1 — free for all use except offering it as a commercial DBaaS. Converts to Apache 2.0 four years after each release.
- **Auth**: built-in record-based auth with SIGNUP/SIGNIN logic defined in SurrealQL. Argon2 password hashing. Two access methods: default (24h session) and remember-me (30d session). JWT stored in localStorage. No external auth service.
- **Permissions**: table-level and row-level via PERMISSIONS clauses. Users can only read/write what they're allowed to.
- **Files**: experimental DEFINE BUCKET feature (3.0). Images stored via file pointers. Permissions on file operations. Backend can be memory, disk, or (soon) S3.

---

## data model

Everything is a post. The `type` field determines rendering.

```
post (table)
├── id             — SurrealDB record ID
├── type           — "blog" | "forum" | "wiki"
├── parent         — record link to parent post (for replies/threads)
├── title          — post title
├── slug           — URL-friendly identifier (unique per type)
├── body           — content (plain text / markdown)
├── author         — record link to user
├── tags           — array of strings
├── published      — boolean
├── created_at     — datetime
└── updated_at     — datetime

revision (table, for wiki)
├── id             — record ID
├── post           — record link to post
├── body           — content snapshot
├── author         — record link to user
└── created_at     — datetime

user (table)
├── id             — record ID
├── username       — unique string
├── email          — unique string
├── password       — argon2 hashed
├── role           — "user" | "admin"
└── created_at     — datetime

tag (table)
├── id             — record ID
├── name           — unique string
└── type           — "category" | "forum" | "label"
```

### content type behavior

- **blog**: single author, chronological listing, replies as comments, only author can edit
- **forum**: multi-author threads, replies are first-class posts with `parent` link, anyone can reply
- **wiki**: single living document, anyone can edit, each edit creates a revision, full history viewable, optimistic locking (check `updated_at` on save — reject if stale, show diff)

---

## frontend

Vanilla JS. No framework, no build step, no npm. Start with a single HTML file, split into multiple files as needed.

### aesthetic

Terminal UI — the C+D hybrid:

- Monospace font (Courier New)
- Dark background (#0e0e16), Catppuccin-ish palette
- Box-drawing characters (┌─┐│└─┘) for panel borders
- Paneled home layout: blog + forum side by side, wiki spanning full width below
- Editorial breathing room inside panels
- Colored accents: purple (blog), blue (forum), green (wiki), aqua (authors), red (logo accent)
- Keyboard shortcuts via JS
- Status bar at bottom with keybinds and connection info
- Content rendered via markdown-it (single `<script>` tag, no build step, `html: false` for built-in XSS safety) into styled `<div>` blocks with monospace font preserved
- Subtle scanline overlay

### views

1. **home** — paneled overview of all three sections
2. **blog** — chronological post list with excerpts
3. **forum** — thread list with reply counts, active indicators
4. **wiki** — page index with revision counts
5. **thread/post** — full post with nested replies
6. **wiki page** — rendered content with revision bar, edit link
7. **new post** — form with type selector, title, tags, body
8. **edit** — pre-filled form for editing existing content

### interactions

- All reads/writes via HTTP to SurrealDB's REST API (debuggable, cacheable, rate-limitable)
- WebSocket used only for "users online" presence (lightweight heartbeat, no query subscriptions)
- Forms submit via JS over HTTP
- Page transitions without full reload (JS view switching)
- Keyboard shortcuts: `n` new, `/` search, `j`/`k` navigate, `⏎` open
- Pagination: offset/limit with page numbers (SurrealDB `LIMIT`/`START` syntax)

---

## images

SurrealDB 3.0 DEFINE BUCKET (experimental). Images stored on disk via file pointers. Permissions controlled through SurrealQL. No separate upload service.

```sql
DEFINE BUCKET uploads BACKEND "file:/data/uploads";

-- in a post
f"uploads:/images/{post_id}_{filename}".put(<bytes>);
```

Primarily a text platform — images are supported but not the focus.

---

## search

SurrealDB's built-in full-text search. No external search service (no Elasticsearch, no Meilisearch). Just indexes on existing tables.

### setup

```sql
-- Define text analyzer with stemming
DEFINE ANALYZER plntxt_search
  TOKENIZERS blank, class, punct
  FILTERS lowercase, snowball(english);

-- Full-text indexes on post fields
DEFINE INDEX post_title ON post
  FIELDS title FULLTEXT ANALYZER plntxt_search BM25;

DEFINE INDEX post_body ON post
  FIELDS body FULLTEXT ANALYZER plntxt_search BM25 HIGHLIGHTS;
```

### querying

```sql
-- Search with relevance scoring and highlighted snippets
SELECT
  title,
  type,
  search::score(1) + search::score(2) AS relevance,
  search::highlight('<b>', '</b>', 2) AS snippet
FROM post
WHERE title @1@ $query
   OR body  @2@ $query
ORDER BY relevance DESC
LIMIT 20;
```

### features

- **BM25 ranking** — relevance-scored results out of the box
- **Snowball stemming** — "running" matches "run", "databases" matches "database"
- **Highlighting** — matched terms highlighted in result snippets
- **Autocomplete** — possible via edgengram filter on a separate index for search-as-you-type
- **Hybrid search** — can combine full-text with vector similarity via reciprocal rank fusion if semantic search is ever desired

### UI

- `/` keyboard shortcut opens search
- Results rendered inline in the TUI aesthetic
- Searches across all content types (blog, forum, wiki) simultaneously
- Type badges on results so you know what you're looking at

---

## rate limiting

SurrealDB has no built-in rate limiting. Handle at the reverse proxy layer (Caddy).

### Caddyfile example

```caddyfile
your-domain.com {
    root * /srv/public
    file_server

    # rate limit auth endpoints
    @auth path /signup /signin
    rate_limit @auth {remote.ip} 5r/m

    # rate limit API/WebSocket
    @api path /rpc/*
    rate_limit @api {remote.ip} 30r/s

    reverse_proxy /signup db:8000
    reverse_proxy /signin db:8000
    reverse_proxy /rpc/* db:8000
}
```

Note: rate limiting requires the `caddy-ratelimit` plugin.

---

## bootstrap

`init.surql` — run once on fresh deploy to create the first admin user and apply schema.

```sql
-- apply schema
-- (schema.surql is imported separately or concatenated before this)

-- create first admin user
CREATE user CONTENT {
    username: 'admin',
    email: 'admin@localhost',
    password: crypto::argon2::generate('changeme'),
    role: 'admin',
    created_at: time::now()
};
```

```bash
# run bootstrap
surreal import --conn http://localhost:8000 --user root --pass changeme --ns plntxt --db plntxt init.surql
```

---

## deployment

### docker-compose (recommended)

```yaml
services:
  db:
    image: surrealdb/surrealdb:latest
    command: start --user root --pass changeme --allow-experimental files file:/data/db.surql
    expose:
      - "8000"
    volumes:
      - ./data:/data

  web:
    image: caddy:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./public:/srv/public:ro
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data

volumes:
  caddy_data:
```

SurrealDB is only exposed internally to Caddy — not to the public internet. Caddy handles HTTPS automatically.

### manual

```bash
# start surrealdb
surreal start --user root --pass changeme --allow-experimental files file:data/db.surql

# serve via caddy (or any static file server for dev)
caddy run --config Caddyfile
```

---

## deliverables

1. **schema.surql** — full SurrealDB schema (tables, fields, permissions, auth, bucket, indexes)
2. **init.surql** — bootstrap script (first admin user, seed data)
3. **public/index.html** — frontend entry point (HTML + CSS + JS, can split into multiple files)
4. **docker-compose.yml** — one-command setup
5. **Caddyfile** — reverse proxy config with rate limiting and automatic HTTPS
6. **README.md** — setup instructions, architecture explanation, the philosophy

---

## decisions

- **File storage**: keep DEFINE BUCKET despite experimental status — images aren't the focus
- **Wiki conflicts**: optimistic locking via `updated_at` check on save
- **Transport**: HTTP for all CRUD, WebSocket only for "users online" presence
- **Security**: trust SurrealDB permissions fully, no middleware layer
- **Markdown**: rendered via markdown-it (`html: false` default safe mode, no build step, loaded as single static JS file)
- **Auth sessions**: two access methods — 24h default, 30d "remember me" checkbox
- **Pagination**: offset/limit with page numbers
- **Reverse proxy**: Caddy (single binary, automatic HTTPS, simpler config than nginx)
- **Port exposure**: SurrealDB internal-only in docker-compose, Caddy as single entry point
- **Signup**: no email verification for v1, rate limiting handles spam

---

## philosophy

- the database is the application
- text is the primary medium
- no build steps, no dependency trees, no node_modules
- two processes, zero frameworks
- if you can't explain the whole stack in 60 seconds, it's too complex
