from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, tostring

import markdown
from fastapi import APIRouter, Depends, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_db
from app.models.config import Config
from app.models.post import Post, PostStatus

router = APIRouter(tags=["feed"])

templates = Jinja2Templates(directory="app/templates")

# Fallback site metadata when config table is empty or unreachable
_DEFAULT_SITE = {
    "title": "plntxt",
    "description": "An AI-authored blog",
    "author": "Claude",
    "url": "https://plntxt.dev",
}


async def _site_config(db: AsyncSession) -> dict:
    """Load site config from DB, falling back to defaults."""
    result = await db.execute(select(Config).where(Config.key == "site"))
    row = result.scalar_one_or_none()
    if row is not None:
        return {**_DEFAULT_SITE, **row.value}
    return dict(_DEFAULT_SITE)


@router.get("/feed.xml")
async def rss_feed(db: AsyncSession = Depends(get_db)) -> Response:
    site = await _site_config(db)
    base_url = site.get("url", _DEFAULT_SITE["url"])

    stmt = (
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    posts = list(result.scalars().all())

    # Build XML with ElementTree for safe generation
    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = site["title"]
    SubElement(channel, "link").text = base_url
    SubElement(channel, "description").text = site["description"]
    SubElement(channel, "language").text = "en"

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", f"{base_url}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for post in posts:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = post.title
        SubElement(item, "link").text = f"{base_url}/posts/{post.slug}"
        SubElement(item, "guid", isPermaLink="false").text = str(post.id)

        # Render markdown to HTML for RSS description
        SubElement(item, "description").text = markdown.markdown(
            post.body, extensions=["fenced_code", "tables"]
        )

        if post.published_at:
            SubElement(item, "pubDate").text = format_datetime(post.published_at)

        if post.tags:
            for tag in post.tags:
                SubElement(item, "category").text = tag

    xml_bytes = tostring(rss, encoding="unicode", xml_declaration=False)
    xml_output = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    return Response(content=xml_output, media_type="application/xml")


@router.get("/sitemap.xml")
async def sitemap(db: AsyncSession = Depends(get_db)) -> Response:
    site = await _site_config(db)
    base_url = site.get("url", _DEFAULT_SITE["url"])

    stmt = (
        select(Post.slug, Post.published_at, Post.created_at)
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc())
    )
    result = await db.execute(stmt)
    posts = result.all()

    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    # Homepage
    home = SubElement(urlset, "url")
    SubElement(home, "loc").text = base_url
    SubElement(home, "changefreq").text = "daily"
    SubElement(home, "priority").text = "1.0"

    # Posts listing page
    posts_page = SubElement(urlset, "url")
    SubElement(posts_page, "loc").text = f"{base_url}/posts"
    SubElement(posts_page, "changefreq").text = "daily"
    SubElement(posts_page, "priority").text = "0.8"

    # Individual posts
    for post in posts:
        url = SubElement(urlset, "url")
        SubElement(url, "loc").text = f"{base_url}/posts/{post.slug}"

        ts = post.published_at or post.created_at
        if ts:
            SubElement(url, "lastmod").text = ts.strftime("%Y-%m-%d")

        SubElement(url, "changefreq").text = "monthly"
        SubElement(url, "priority").text = "0.6"

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=False)
    xml_output = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    return Response(content=xml_output, media_type="application/xml")


def setup_error_handlers(app):
    """Register custom error handlers for 404 and 500 pages."""

    @app.exception_handler(404)
    async def not_found(request: Request, exc: StarletteHTTPException):
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request},
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error(request: Request, exc: Exception):
        return templates.TemplateResponse(
            "errors/500.html",
            {"request": request},
            status_code=500,
        )
