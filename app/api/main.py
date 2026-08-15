from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.config import get_settings
from app.api.routers.chunks import chunks_router, source_chunks_router
from app.api.routers.search import router as search_router
from app.api.routers.sources import router as sources_router
from app.web.auth import NotAuthenticated
from app.web.router import login_router
from app.web.router import router as web_router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
settings = get_settings()

app = FastAPI(title="Comparative Civil Law — Corpus Storage Service")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="ccl_session",
    max_age=14 * 24 * 60 * 60,
    same_site="lax",
)

app.include_router(sources_router)
app.include_router(source_chunks_router)
app.include_router(chunks_router)
app.include_router(search_router)
app.include_router(login_router)
app.include_router(web_router)

app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.exception_handler(NotAuthenticated)
async def _redirect_to_login(request: Request, exc: NotAuthenticated) -> RedirectResponse:
    next_url = quote(request.url.path, safe="/")
    if request.url.query:
        next_url += "%3F" + quote(request.url.query, safe="")
    return RedirectResponse(url=f"/ui/login?next={next_url}", status_code=303)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
