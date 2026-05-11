import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.media import MediaType
from app.schemas.media import FeedResponse
from app.services.media import (
    batch_update, browse_folders, export_favorites, get_feed, get_media,
    get_mime_type, get_random_media, parse_range, purge_deleted,
    toggle_deleted, toggle_favorite,
)

router = APIRouter(prefix="/api/media", tags=["media"])

CHUNK_SIZE = 64 * 1024  # 64KB


@router.get("/thumbnail/{media_id}")
async def get_thumbnail(
    media_id: str,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media(db, media_id)
    if not media or not media.thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")
    if not os.path.exists(media.thumbnail_path):
        raise HTTPException(404, "Thumbnail file missing")
    return _full_response(media.thumbnail_path, os.path.getsize(media.thumbnail_path), "image/jpeg")


@router.get("/feed", response_model=FeedResponse)
async def feed(
    page: int = 1,
    page_size: int = 20,
    media_type: MediaType | None = None,
    folder: str | None = None,
    is_favorited: bool | None = None,
    is_deleted: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_feed(db, page, page_size, media_type, folder, is_favorited, is_deleted)


@router.get("/random")
async def random_media(
    count: int = 50,
    exclude_ids: str = "",
    media_type: MediaType | None = None,
    db: AsyncSession = Depends(get_db),
):
    ids = [x.strip() for x in exclude_ids.split(",") if x.strip()] or None
    return await get_random_media(db, count, ids, media_type)


@router.get("/browse")
async def browse(
    root_dir: str | None = None,
    subdir: str | None = None,
    media_type: MediaType | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await browse_folders(db, root_dir, subdir, media_type)


@router.get("/stream/{media_id}")
async def stream_media(
    media_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media(db, media_id)
    if not media:
        raise HTTPException(404, "Media not found")

    file_path = media.file_path
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found on disk")

    file_size = os.path.getsize(file_path)
    mime_type = get_mime_type(file_path)
    range_header = request.headers.get("range")

    if not range_header:
        return _full_response(file_path, file_size, mime_type)

    try:
        start, end = parse_range(range_header, file_size)
    except ValueError:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    content_length = end - start + 1

    async def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type=mime_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
        },
    )


def _full_response(file_path: str, file_size: int, mime_type: str) -> StreamingResponse:
    async def iter_file():
        with open(file_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=mime_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
    )


# --- 收藏 / 删除 / 管理 ---

@router.post("/{media_id}/favorite")
async def favorite(media_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await toggle_favorite(db, media_id)
    except ValueError:
        raise HTTPException(404, "Media not found")


@router.post("/{media_id}/delete")
async def mark_deleted(media_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await toggle_deleted(db, media_id)
    except ValueError:
        raise HTTPException(404, "Media not found")


class ExportRequest(BaseModel):
    target_dir: str


class BatchRequest(BaseModel):
    ids: list[str]
    action: str  # favorite, unfavorite, delete, undelete


@router.post("/manage/purge")
async def purge(db: AsyncSession = Depends(get_db)):
    count = await purge_deleted(db)
    return {"deleted_count": count}


@router.post("/manage/export-favorites")
async def export_fav(body: ExportRequest, db: AsyncSession = Depends(get_db)):
    count = await export_favorites(db, body.target_dir)
    return {"exported_count": count}


@router.post("/manage/batch")
async def batch(body: BatchRequest, db: AsyncSession = Depends(get_db)):
    count = await batch_update(db, body.ids, body.action)
    return {"updated_count": count}
