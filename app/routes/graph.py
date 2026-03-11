import asyncio
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_optional_user
from app.db import get_db
from app.models.schemas.graph import GraphData
from app.services.graph import build_graph

router = APIRouter(prefix="/graph", tags=["graph"])
templates = Jinja2Templates(directory="app/templates")

_graph_cache: dict[str, tuple[GraphData, float]] = {}
_cache_lock = asyncio.Lock()
_CACHE_TTL = 60.0


async def _get_cached_graph(db: AsyncSession) -> GraphData:
    async with _cache_lock:
        cached = _graph_cache.get("graph")
        if cached and (time.monotonic() - cached[1]) < _CACHE_TTL:
            return cached[0]
        data = await build_graph(db)
        _graph_cache["graph"] = (data, time.monotonic())
        return data


@router.get("/data", response_model=GraphData)
async def graph_data(db: AsyncSession = Depends(get_db)) -> GraphData:
    return await _get_cached_graph(db)


@router.get("", response_class=HTMLResponse)
async def graph_page(
    request: Request,
    current_user=Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    data = await _get_cached_graph(db)
    return templates.TemplateResponse("graph/index.html", {
        "request": request,
        "current_user": current_user,
        "stats": data.stats,
    })
