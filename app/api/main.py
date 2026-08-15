from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routers.chunks import chunks_router, source_chunks_router
from app.api.routers.search import router as search_router
from app.api.routers.sources import router as sources_router
from app.web.router import router as web_router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Comparative Civil Law — Corpus Storage Service")

app.include_router(sources_router)
app.include_router(source_chunks_router)
app.include_router(chunks_router)
app.include_router(search_router)
app.include_router(web_router)

app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
