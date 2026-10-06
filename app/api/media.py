import asyncio
import os
from pathlib import Path
from typing import Awaitable, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.media import Media, MediaType
from app.schemas.media import AvailabilityFilter, FeedResponse, MediaOut
from app.services.availability import (
    BROWSE_TIMEOUT, SourceUnavailable, check_records, file_info, remove_records, snapshot, source_error,
)
from app.services.availability_jobs import (
    cancel_check_job, get_check_job, list_check_jobs, start_check_job,
)
from app.services.disk_probe import probe
from app.services.import_jobs import (
    ImportConflict, cancel_import_job, get_import_job, list_import_jobs, start_import_job,
)
from app.schemas.import_job import ImportJobOut
from app.services.media import (
    ExportTag, FeedSort, batch_update, browse_folders, export_favorites, export_media_by_tags,
    get_feed, get_media,
    get_mime_type, get_random_media, parse_range, purge_deleted,
    toggle_damaged, toggle_deleted, toggle_favorite,
)

router = APIRouter(prefix="/api/media", tags=["media"])

CHUNK_SIZE = 64 * 1024  # 64KB
ResponseT = TypeVar("ResponseT")


async def bounded(operation: Awaitable[ResponseT]) -> ResponseT:
    try:
        async with asyncio.timeout(BROWSE_TIMEOUT):
            return await operation
    except SourceUnavailable as error:
        raise HTTPException(error.status, error.message) from error
    except TimeoutError as error:
        raise HTTPException(503, "读取媒体来源超时，请稍后重试") from error


async def file_size_on_disk(path: str, *, cached_image: bool = False) -> int:
    info = await file_info(path)
    if info["status"] != "available":
        if cached_image and info["status"] == "missing":
            raise SourceUnavailable(404, "缓存图片不存在，请使用备用封面或重新生成缓存")
        raise source_error(info)
    return info["size"]


@router.get("/thumbnail/{media_id}")
async def get_thumbnail(
    media_id: str,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media(db, media_id)
    if not media or not media.thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")
    size = await bounded(file_size_on_disk(media.thumbnail_path, cached_image=True))
    return _full_response(media.thumbnail_path, size, "image/jpeg")


@router.get("/preview/{media_id}")
async def get_preview(
    media_id: str,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media(db, media_id)
    if not media or not media.preview_path:
        raise HTTPException(404, "Preview not found")
    size = await bounded(file_size_on_disk(media.preview_path, cached_image=True))
    return _full_response(media.preview_path, size, "image/png")


@router.get("/feed", response_model=FeedResponse)
async def feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    media_type: MediaType | None = None,
    folder: str | None = None,
    is_favorited: bool | None = None,
    is_deleted: bool | None = None,
    is_damaged: bool | None = None,
    folder_exact: bool = False,
    folder_after: str | None = None,
    sort: FeedSort = "created_desc",
    availability: AvailabilityFilter = "available",
    db: AsyncSession = Depends(get_db),
):
    return await bounded(get_feed(
        db,
        page,
        page_size,
        media_type,
        folder,
        is_favorited,
        is_deleted,
        is_damaged,
        folder_exact,
        folder_after,
        sort,
        availability,
    ))


class RandomRequest(BaseModel):
    count: int = Field(50, ge=1, le=200)
    exclude_ids: list[str] = Field(default_factory=list)
    media_type: MediaType | None = None
    is_favorited: bool | None = None
    is_deleted: bool | None = None
    is_damaged: bool | None = None
    folder: str | None = None
    availability: AvailabilityFilter = "available"


@router.post("/random")
async def random_media(body: RandomRequest, db: AsyncSession = Depends(get_db)):
    exclude = body.exclude_ids or None
    return await bounded(get_random_media(
        db,
        body.count,
        exclude,
        body.media_type,
        body.is_favorited,
        body.is_deleted,
        body.is_damaged,
        body.folder,
        body.availability,
    ))


@router.get("/browse")
async def browse(
    root_dir: str | None = None,
    subdir: str | None = None,
    media_type: MediaType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    after_path: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if root_dir:
        root_dir = os.path.abspath(os.path.expanduser(root_dir))
        target = os.path.abspath(os.path.join(root_dir, subdir or ""))
        if os.path.commonpath([root_dir, target]) != root_dir:
            raise HTTPException(400, "子目录必须位于媒体根目录内")
    return await bounded(browse_folders(db, root_dir, subdir, media_type, page, page_size, after_path))


@router.get("/stream/{media_id}")
async def stream_media(
    media_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media(db, media_id)
    if not media:
        raise HTTPException(404, "Media not found")

    async def prepare():
        observations = {}
        checked = await check_records(db, [snapshot(media)], force=False, observations=observations)
        if not checked:
            raise HTTPException(404, "Media not found")
        info = observations.get(media_id)
        if not info or checked[0].file_path != file_path:
            raise SourceUnavailable(503, "媒体记录已变化，请重试")
        if checked[0].availability != "available" or info["status"] != "available":
            raise source_error({**info, "status": checked[0].availability})
        return info["size"]

    file_path = media.file_path
    file_size = await bounded(prepare())
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

    def iter_file():
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
    # Starlette runs synchronous iterators in its thread pool, keeping disk
    # reads off the ASGI event loop throughout the response.
    def iter_file():
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


@router.post("/{media_id}/damage")
async def mark_damaged(media_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await toggle_damaged(db, media_id)
    except ValueError:
        raise HTTPException(404, "Media not found")


class ExportRequest(BaseModel):
    target_dir: str
    tags: list[ExportTag] = Field(default_factory=lambda: ["favorited"])


class BatchRequest(BaseModel):
    ids: list[str]
    action: str  # favorite, unfavorite, delete, undelete, damage, undamage


class ImportRequest(BaseModel):
    request_id: UUID | None = None
    path: str
    preview: bool = False
    media_type: MediaType | None = None
    recursive: bool = True
    skip_hidden: bool = True
    backfill_existing: bool = True
    workers: int | None = Field(default=None, ge=1, le=16)


class ImportTargetInfo(BaseModel):
    path: str
    is_existing_library_path: bool
    existing_count: int


@router.post("/manage/purge")
async def purge(db: AsyncSession = Depends(get_db)):
    count = await purge_deleted(db)
    return {"deleted_count": count}


@router.post("/manage/export-favorites")
async def export_fav(body: ExportRequest, db: AsyncSession = Depends(get_db)):
    count = await export_favorites(db, body.target_dir)
    return {"exported_count": count}


@router.post("/manage/export")
async def export_media(body: ExportRequest, db: AsyncSession = Depends(get_db)):
    count = await export_media_by_tags(db, body.target_dir, body.tags)
    return {"exported_count": count}


@router.post("/manage/batch")
async def batch(body: BatchRequest, db: AsyncSession = Depends(get_db)):
    count = await batch_update(db, body.ids, body.action)
    return {"updated_count": count}


@router.get("/manage/directories")
async def list_directories(path: str | None = None):
    target = os.path.abspath(os.path.expanduser(path)) if path else str(Path.home())
    async def enumerate_target():
        result = await probe({"action": "directories", "path": target})
        if result["status"] != "available":
            raise source_error(result, directory=True)
        parent = os.path.dirname(target)
        return {"path": target, "parent": parent if parent != target else None,
                "directories": result["directories"]}
    return await bounded(enumerate_target())


class AvailabilityIds(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/manage/availability/probe", response_model=list[MediaOut])
async def recheck_media(body: AvailabilityIds, db: AsyncSession = Depends(get_db)):
    async def recheck():
        rows = (await db.scalars(select(Media).where(Media.id.in_(body.ids)))).all()
        return [MediaOut.model_validate(row) for row in await check_records(db, [snapshot(row) for row in rows])]
    return await bounded(recheck())


@router.post("/manage/availability/remove-records")
async def remove_media_records(body: AvailabilityIds, db: AsyncSession = Depends(get_db)):
    return {"removed_count": await bounded(remove_records(db, body.ids))}


@router.post("/manage/availability/check")
async def create_availability_check():
    return await start_check_job()


@router.get("/manage/availability/check")
async def availability_checks():
    return list_check_jobs()


@router.get("/manage/availability/check/{job_id}")
async def availability_check(job_id: str):
    job = get_check_job(job_id)
    if job is None:
        raise HTTPException(404, "检查任务不存在")
    return job


@router.post("/manage/availability/check/{job_id}/cancel")
async def stop_availability_check(job_id: str):
    job = await cancel_check_job(job_id)
    if job is None:
        raise HTTPException(404, "检查任务不存在")
    return job


@router.get("/manage/import-target", response_model=ImportTargetInfo)
async def import_target(path: str, db: AsyncSession = Depends(get_db)):
    if not path.strip():
        raise HTTPException(400, "Path is required")

    target_path = os.path.abspath(os.path.expanduser(path))
    target_prefix = target_path + os.sep
    result = await db.execute(
        select(func.count(Media.id)).where(
            or_(
                Media.root_dir == target_path,
                Media.folder == target_path,
                Media.folder.startswith(target_prefix),
            )
        )
    )
    existing_count = result.scalar_one()
    return ImportTargetInfo(
        path=target_path,
        is_existing_library_path=existing_count > 0,
        existing_count=existing_count,
    )


@router.post("/manage/import", response_model=ImportJobOut)
async def import_media(body: ImportRequest):
    try:
        return await start_import_job(body.model_dump(mode="json"))
    except ImportConflict as exc:
        raise HTTPException(409, {"message": "服务器已有导入任务", "job_id": exc.job_id})


@router.get("/manage/import", response_model=list[ImportJobOut])
async def import_media_jobs(request_id: UUID | None = None):
    return list_import_jobs(str(request_id) if request_id else None)


@router.get("/manage/import/{job_id}", response_model=ImportJobOut)
async def import_media_progress(job_id: str):
    job = get_import_job(job_id)
    if not job:
        raise HTTPException(404, "Import job not found")
    return job


@router.post("/manage/import/{job_id}/cancel", response_model=ImportJobOut)
async def cancel_media_import(job_id: str):
    job = await cancel_import_job(job_id)
    if not job:
        raise HTTPException(404, "Import job not found")
    return job
