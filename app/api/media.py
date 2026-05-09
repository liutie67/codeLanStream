import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.media import MediaType
from app.schemas.media import FeedResponse
from app.services.media import get_feed, get_media, get_mime_type, parse_range

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
    db: AsyncSession = Depends(get_db),
):
    return await get_feed(db, page, page_size, media_type, folder)


@router.get("/random")
async def random_media(
    count: int = 10,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    from app.schemas.media import MediaOut

    result = await db.execute(
        text("SELECT * FROM media ORDER BY RANDOM() LIMIT :limit"),
        {"limit": count},
    )
    rows = result.mappings().all()
    return [MediaOut.model_validate(row) for row in rows]


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
