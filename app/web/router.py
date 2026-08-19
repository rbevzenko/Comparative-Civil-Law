import json
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.database import get_db
from app.api.models.chunk import Chunk
from app.api.models.footnote import Footnote
from app.api.models.source import Source
from app.api.schemas.chunk import ChunkBulkCreate
from app.api.security import verify_chunk_signature
from app.api.services.chunks import create_chunks as create_chunks_records
from app.api.services.sources import ALLOWED_SOURCE_TYPES, InvalidSourceUpload, parse_authors
from app.api.services.sources import create_source as create_source_record
from app.api.services.sources import update_source as update_source_record
from app.api.storage import generate_presigned_url
from app.web.auth import SESSION_KEY, check_password, require_session

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Login/logout must stay reachable without a session; everything else in
# this module requires one.
login_router = APIRouter(prefix="/ui", tags=["web"])
router = APIRouter(prefix="/ui", tags=["web"], dependencies=[Depends(require_session)])

# The public citation page (universal_ref target). Deliberately outside
# /ui: it must be openable by anyone who follows a link from a citation,
# with no session and no API token — access is instead gated per-chunk by
# the ?sig= query param (see app.api.security.verify_chunk_signature), and
# the page itself shows only the one fragment plus a short snippet of its
# immediate neighbors — never a way to browse the rest of the source.
public_router = APIRouter(tags=["public"])


def _pop_flash(request: Request) -> str | None:
    return request.session.pop("flash", None)


def _set_flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def _optional_int(raw: str | None, field: str) -> int | None:
    """Числовое поле формы: пустое — это NULL, а не ошибка.

    Пустой <input type="number"> приходит как "", и объявить параметр
    `int | None` мало: FastAPI отвечает на "" своей 422 в JSON, мимо формы,
    и человек видит голый машинный ответ вместо подсвеченного поля.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise InvalidSourceUpload(f"{field}: нужно целое число, а не «{raw}»") from None


def _source_form_values(source: Source) -> dict:
    """Source row → the shape the upload/edit form template expects."""
    return {
        "title": source.title,
        "jurisdiction": source.jurisdiction,
        "source_type": source.source_type,
        "authors": "; ".join(source.authors or []),
        "edition": source.edition,
        "year": source.year,
        "publisher": source.publisher,
        "language": source.language,
        "pdf_pages_total": source.pdf_pages_total,
    }


# --- auth ---------------------------------------------------------------


@login_router.get("/login")
async def ui_login_form(request: Request, next: str = "/ui"):
    if request.session.get(SESSION_KEY):
        return RedirectResponse(url=next or "/ui")
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})


@login_router.post("/login")
async def ui_login_submit(
    request: Request,
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/ui",
):
    if not check_password(password):
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": "Неверный пароль"}, status_code=401
        )
    request.session[SESSION_KEY] = True
    return RedirectResponse(url=next or "/ui", status_code=status.HTTP_303_SEE_OTHER)


@login_router.post("/logout")
async def ui_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/ui/login", status_code=status.HTTP_303_SEE_OTHER)


# --- dashboard ------------------------------------------------------------


@router.get("/")
async def ui_dashboard(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    n_sources = (await db.execute(select(func.count()).select_from(Source))).scalar_one()
    n_chunks = (await db.execute(select(func.count()).select_from(Chunk))).scalar_one()
    n_footnotes = (await db.execute(select(func.count()).select_from(Footnote))).scalar_one()

    breakdown_stmt = (
        select(Source.jurisdiction, func.count(func.distinct(Source.id)), func.count(Chunk.id))
        .select_from(Source)
        .outerjoin(Chunk, Chunk.source_id == Source.id)
        .group_by(Source.jurisdiction)
        .order_by(Source.jurisdiction)
    )
    breakdown = [
        {"jurisdiction": j, "n_sources": ns, "n_chunks": nc}
        for j, ns, nc in (await db.execute(breakdown_stmt)).all()
    ]

    recent_stmt = select(Source).order_by(Source.created_at.desc()).limit(8)
    recent_sources = (await db.execute(recent_stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "n_sources": n_sources,
            "n_chunks": n_chunks,
            "n_footnotes": n_footnotes,
            "n_jurisdictions": len(breakdown),
            "breakdown": breakdown,
            "recent_sources": recent_sources,
            "flash": _pop_flash(request),
        },
    )


# --- browsing ---------------------------------------------------------------


@router.get("/sources")
async def ui_sources(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    jurisdiction: str | None = None,
):
    stmt = select(Source).order_by(Source.jurisdiction, Source.title)
    if jurisdiction:
        stmt = stmt.where(Source.jurisdiction == jurisdiction)
    sources = (await db.execute(stmt)).scalars().all()

    all_jurisdictions_rows = (await db.execute(select(Source.jurisdiction).distinct())).scalars().all()
    jurisdictions = sorted(set(all_jurisdictions_rows))

    return templates.TemplateResponse(
        request,
        "sources_list.html",
        {
            "active": "sources",
            "sources": sources,
            "jurisdictions": jurisdictions,
            "selected_jurisdiction": jurisdiction,
            "flash": _pop_flash(request),
        },
    )


@router.get("/sources/{source_id}")
async def ui_source_detail(source_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    source = await db.get(Source, source_id)
    if source is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "источник"}, status_code=404)

    chunks_stmt = (
        select(Chunk).where(Chunk.source_id == source_id).order_by(Chunk.page_start.nulls_last(), Chunk.created_at)
    )
    chunks = (await db.execute(chunks_stmt)).scalars().all()
    pdf_url = generate_presigned_url(source.pdf_object_key)

    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {"active": "sources", "source": source, "chunks": chunks, "pdf_url": pdf_url, "flash": _pop_flash(request)},
    )


@router.get("/sources/{source_id}/edit")
async def ui_source_edit_form(source_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    source = await db.get(Source, source_id)
    if source is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "источник"}, status_code=404)
    return templates.TemplateResponse(
        request,
        "source_edit.html",
        {
            "active": "sources",
            "source": source,
            "error": None,
            "form": _source_form_values(source),
            "source_types": sorted(ALLOWED_SOURCE_TYPES),
        },
    )


@router.post("/sources/{source_id}/edit")
async def ui_source_edit_submit(
    source_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    title: Annotated[str, Form()],
    jurisdiction: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    authors: Annotated[str, Form()] = "",
    edition: Annotated[str | None, Form()] = None,
    year: Annotated[str | None, Form()] = None,
    publisher: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    pdf_pages_total: Annotated[str | None, Form()] = None,
):
    source = await db.get(Source, source_id)
    if source is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "источник"}, status_code=404)

    submitted = {
        "title": title,
        "jurisdiction": jurisdiction,
        "source_type": source_type,
        "authors": authors,
        "edition": edition,
        "year": year,
        "publisher": publisher,
        "language": language,
        "pdf_pages_total": pdf_pages_total,
    }
    # The form always posts the whole card, so an emptied optional field is a
    # deliberate erasure, not "leave as is" — an empty text input arrives as
    # "" and has to become NULL, or the card keeps a blank string forever.
    try:
        changes = {
            "title": title,
            "jurisdiction": jurisdiction,
            "source_type": source_type,
            "authors": parse_authors(authors),
            "edition": edition or None,
            "year": _optional_int(year, "Год"),
            "publisher": publisher or None,
            "language": language or None,
            "pdf_pages_total": _optional_int(pdf_pages_total, "Страниц в PDF"),
        }
        await update_source_record(db, source, changes)
    except InvalidSourceUpload as exc:
        return templates.TemplateResponse(
            request,
            "source_edit.html",
            {
                "active": "sources",
                "source": source,
                "error": str(exc),
                "form": submitted,
                "source_types": sorted(ALLOWED_SOURCE_TYPES),
            },
            status_code=422,
        )

    _set_flash(request, "Карточка источника обновлена.")
    return RedirectResponse(url=f"/ui/sources/{source_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chunks/{chunk_id}")
async def ui_chunk_detail(chunk_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = (
        select(Chunk)
        .where(Chunk.id == chunk_id)
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    chunk = (await db.execute(stmt)).scalar_one_or_none()
    if chunk is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "чанк"}, status_code=404)

    pdf_url = generate_presigned_url(chunk.source.pdf_object_key) if chunk.source else None

    return templates.TemplateResponse(
        request, "chunk_detail.html", {"active": "sources", "chunk": chunk, "pdf_url": pdf_url}
    )


# --- uploads ---------------------------------------------------------------


@router.get("/upload/source")
async def ui_upload_source_form(request: Request):
    return templates.TemplateResponse(
        request,
        "upload_source.html",
        {"active": "upload_source", "error": None, "form": {}, "source_types": sorted(ALLOWED_SOURCE_TYPES)},
    )


@router.post("/upload/source")
async def ui_upload_source_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    title: Annotated[str, Form()],
    jurisdiction: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    pdf: Annotated[UploadFile, File()],
    authors: Annotated[str, Form()] = "",
    edition: Annotated[str | None, Form()] = None,
    year: Annotated[str | None, Form()] = None,
    publisher: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    pdf_pages_total: Annotated[str | None, Form()] = None,
):
    submitted = {
        "title": title,
        "jurisdiction": jurisdiction,
        "source_type": source_type,
        "authors": authors,
        "edition": edition,
        "year": year,
        "publisher": publisher,
        "language": language,
        "pdf_pages_total": pdf_pages_total,
    }
    try:
        source = await create_source_record(
            db,
            title=title,
            jurisdiction=jurisdiction,
            source_type=source_type,
            authors_raw=authors,
            edition=edition or None,
            year=_optional_int(year, "Год"),
            publisher=publisher or None,
            language=language or None,
            pdf_pages_total=_optional_int(pdf_pages_total, "Страниц в PDF"),
            pdf_filename=pdf.filename,
            pdf_content_type=pdf.content_type,
            pdf_file=pdf.file,
        )
    except InvalidSourceUpload as exc:
        return templates.TemplateResponse(
            request,
            "upload_source.html",
            {
                "active": "upload_source",
                "error": str(exc),
                "form": submitted,
                "source_types": sorted(ALLOWED_SOURCE_TYPES),
            },
            status_code=422,
        )

    _set_flash(request, f"Источник «{source.title}» добавлен.")
    return RedirectResponse(url=f"/ui/sources/{source.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/upload/chunks")
async def ui_upload_chunks_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    source_id: uuid.UUID | None = None,
):
    sources = (await db.execute(select(Source).order_by(Source.jurisdiction, Source.title))).scalars().all()
    return templates.TemplateResponse(
        request,
        "upload_chunks.html",
        {"active": "upload_chunks", "sources": sources, "selected_source_id": source_id, "error": None},
    )


@router.post("/upload/chunks")
async def ui_upload_chunks_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    source_id: Annotated[uuid.UUID, Form()],
    chunks_file: Annotated[UploadFile, File()],
):
    sources = (await db.execute(select(Source).order_by(Source.jurisdiction, Source.title))).scalars().all()

    source = await db.get(Source, source_id)
    if source is None:
        return templates.TemplateResponse(
            request,
            "upload_chunks.html",
            {
                "active": "upload_chunks",
                "sources": sources,
                "selected_source_id": source_id,
                "error": "Источник не найден.",
            },
            status_code=404,
        )

    raw = await chunks_file.read()
    try:
        data = json.loads(raw)
        payload = ChunkBulkCreate.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        return templates.TemplateResponse(
            request,
            "upload_chunks.html",
            {
                "active": "upload_chunks",
                "sources": sources,
                "selected_source_id": source_id,
                "error": f"Файл не прошёл проверку: {exc}",
            },
            status_code=422,
        )

    created = await create_chunks_records(db, source_id, payload.chunks)
    _set_flash(request, f"Загружено чанков: {len(created)} для источника «{source.title}».")
    return RedirectResponse(url=f"/ui/sources/{source_id}", status_code=status.HTTP_303_SEE_OTHER)


# --- public citation page (universal_ref target) ---------------------------

_NOT_FOUND_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Ссылка недействительна</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body><div class="page"><main>
<h1>Ссылка недействительна</h1>
<p class="page-lede">Такой фрагмент не найден, либо ссылка повреждена или устарела.</p>
</main></div></body></html>"""


def _snippet(text: str, limit: int = 220) -> str:
    """Short, non-navigable teaser of a neighboring chunk's text — enough to
    place the requested fragment in context, not enough to read the source
    by hopping between /source/ links (there's nothing to click here)."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rsplit(" ", 1)[0] + "…"


@public_router.get("/source/{chunk_id}", include_in_schema=False)
async def source_public_detail(
    chunk_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    sig: str | None = None,
):
    """universal_ref target: renders one fragment (+ a short snippet of its
    immediate neighbors for context) with its bibliographic reference.

    No session, no API token — access is a per-chunk signature in ?sig=
    (see app.api.security), and the page never exposes anything the
    signature doesn't already name: no table of contents, no PDF, no
    next/prev page links, no browsing to the rest of the source.
    """
    if not verify_chunk_signature(chunk_id, sig):
        return Response(_NOT_FOUND_HTML, status_code=404, media_type="text/html", headers={"X-Robots-Tag": "noindex, nofollow"})

    stmt = (
        select(Chunk)
        .where(Chunk.id == chunk_id)
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    chunk = (await db.execute(stmt)).scalar_one_or_none()
    if chunk is None:
        return Response(_NOT_FOUND_HTML, status_code=404, media_type="text/html", headers={"X-Robots-Tag": "noindex, nofollow"})

    # Nearest neighbors within the same source, by the same ordering used
    # everywhere else chunks are listed (page_start, then created_at as a
    # tiebreaker). Row-wise tuple comparison instead of two separate
    # inequalities so the tiebreaker actually breaks ties correctly.
    order_key = func.coalesce(Chunk.page_start, -1)
    current_key = (chunk.page_start if chunk.page_start is not None else -1, chunk.created_at)

    prev_stmt = (
        select(Chunk)
        .where(Chunk.source_id == chunk.source_id, Chunk.id != chunk.id)
        .where(tuple_(order_key, Chunk.created_at) < current_key)
        .order_by(order_key.desc(), Chunk.created_at.desc())
        .limit(1)
    )
    next_stmt = (
        select(Chunk)
        .where(Chunk.source_id == chunk.source_id, Chunk.id != chunk.id)
        .where(tuple_(order_key, Chunk.created_at) > current_key)
        .order_by(order_key.asc(), Chunk.created_at.asc())
        .limit(1)
    )
    prev_chunk = (await db.execute(prev_stmt)).scalar_one_or_none()
    next_chunk = (await db.execute(next_stmt)).scalar_one_or_none()

    response = templates.TemplateResponse(
        request,
        "source_public.html",
        {
            "chunk": chunk,
            "prev_citation": prev_chunk.citation if prev_chunk else None,
            "prev_snippet": _snippet(prev_chunk.text) if prev_chunk else None,
            "next_citation": next_chunk.citation if next_chunk else None,
            "next_snippet": _snippet(next_chunk.text) if next_chunk else None,
        },
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
