-- plntxt bootstrap
-- Run once on fresh deploy after schema.surql

-- Create first admin user
CREATE user CONTENT {
    username: 'admin',
    email: 'admin@localhost',
    password: crypto::argon2::generate('changeme'),
    role: 'admin',
    created_at: time::now()
};

-- Seed a welcome blog post
CREATE post CONTENT {
    type: 'blog',
    title: 'Welcome to plntxt',
    slug: 'welcome',
    body: '# Welcome

plntxt is a forum + wiki + blog in one.

All content is the same thing: a **document**. Blog posts, forum threads, wiki pages, and replies are all the same data structure with a `type` field that determines how they render.

The entire backend is a single database. No framework, no middleware, no app server.

## The stack

- **Frontend**: static HTML + vanilla JS
- **Database**: SurrealDB (data + API + auth + permissions)
- **Proxy**: Caddy (HTTPS + rate limiting + static files)

That is it. Two processes, zero frameworks.',
    author: user:admin,
    tags: ['meta'],
    published: true,
    created_at: time::now(),
    updated_at: time::now()
};

-- Seed a wiki page
CREATE post CONTENT {
    type: 'wiki',
    title: 'Getting Started',
    slug: 'getting-started',
    body: '# Getting Started

This is the first wiki page. Anyone can edit it.

## Editing

Click the edit button or press `e` to edit this page. Every edit creates a revision so nothing is ever lost.

## Navigation

- Press `/` to search
- Press `n` to create a new post
- Press `j`/`k` to navigate lists
- Press `Enter` to open an item',
    author: user:admin,
    tags: ['help'],
    published: true,
    created_at: time::now(),
    updated_at: time::now()
};

-- Seed a forum thread
CREATE post CONTENT {
    type: 'forum',
    title: 'Introductions',
    slug: 'introductions',
    body: 'Introduce yourself here.',
    author: user:admin,
    tags: ['general'],
    published: true,
    created_at: time::now(),
    updated_at: time::now()
};
