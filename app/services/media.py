import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from sqlalchemy import delete as sql_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.media import Media, MediaType
from app.schemas.media import FeedResponse, MediaOut
from app.services.thumbnail import generate_thumbnail, generate_preview

ProgressCallback = Callable[[dict[str, Any]], None]
ExportTag = Literal["favorited", "deleted", "damaged"]
FeedSort = Literal["created_desc", "file_path_asc", "size_desc"]


def _classify_media(ext: str) -> MediaType | None:
    ext = ext.lower()
    if ext in settings.supported_video_exts:
        return MediaType.VIDEO
    if ext in settings.supported_image_exts:
        return MediaType.IMAGE
    return None


async def scan_directory(
    dir_path: str,
    db: AsyncSession,
    preview: bool = False,
    workers: int | None = None,
    media_type_filter: MediaType | None = None,
    recursive: bool = True,
    skip_hidden: bool = True,
    backfill_existing: bool = True,
) -> int:
    stats = await scan_directory_stats(
        dir_path,
        db,
        preview=preview,
        workers=workers,
        media_type_filter=media_type_filter,
        recursive=recursive,
        skip_hidden=skip_hidden,
        backfill_existing=backfill_existing,
    )
    return stats["added_count"] + stats["preview_count"]


async def scan_directory_stats(
    dir_path: str,
    db: AsyncSession,
    preview: bool = False,
    workers: int | None = None,
    media_type_filter: MediaType | None = None,
    recursive: bool = True,
    skip_hidden: bool = True,
    backfill_existing: bool = True,
    progress: ProgressCallback | None = None,
    cancel: asyncio.Event | None = None,
    checkpoint: Callable[[AsyncSession, dict[str, Any]], Awaitable[None]] | None = None,
    asset_dir: Path | None = None,
) -> dict[str, Any]:
    path = Path(dir_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {dir_path}")

    stats = dict(root_dir=str(path), scanned_files=0, added_count=0, existing_count=0,
                 skipped_count=0, thumbnail_count=0, preview_count=0, preview_requested=preview)
    saved_stats = stats.copy()
    pending_previews: list[tuple[str, str]] = []
    in_flight: set[asyncio.Task] = set()

    def stopped() -> bool:
        return cancel is not None and cancel.is_set()

    def notify(stage: str, message: str, current: int, total: int, current_file: str | None = None) -> None:
        if progress:
            progress(dict(stage=stage, message=message, current=current, total=total,
                          current_file=current_file, stats=stats.copy()))

    async def save() -> None:
        nonlocal saved_stats
        try:
            if checkpoint:
                await checkpoint(db, stats.copy())
            else:
                await db.commit()
            saved_stats = stats.copy()
        except BaseException:
            await db.rollback()
            stats.update(saved_stats)
            raise

    # Pull directory entries in small batches off the event loop. Even a large
    # directory or a NAS enumeration must not block progress/cancel HTTP requests.
    iterator = iter(path.rglob("*") if recursive else path.iterdir())

    def next_batch() -> tuple[list[Path], bool]:
        batch = []
        for _ in range(128):
            if stopped():
                return batch, True
            entry = next(iterator, None)
            if entry is None:
                return batch, True
            if entry.is_file():
                batch.append(entry)
        return batch, False

    files: list[Path] = []
    notify("preparing", "统计目录文件", 0, 0)
    while not stopped():
        batch, done = await asyncio.to_thread(next_batch)
        files.extend(batch)
        notify("preparing", "统计目录文件", len(files), 0)
        if done:
            break
    total_files = len(files)
    try:
        for index, file in enumerate(files, start=1):
            await asyncio.sleep(0)
            if stopped():
                break
            stats["scanned_files"] += 1
            notify("scanning", "扫描媒体文件", index, total_files, str(file))
            media_type = _classify_media(file.suffix)
            if ((skip_hidden and any(part.startswith('.') for part in file.relative_to(path).parts))
                or file.name in ('Thumbs.db', 'desktop.ini', 'Desktop.ini')
                or media_type is None or (media_type_filter and media_type != media_type_filter)):
                stats["skipped_count"] += 1
                continue

            resolved = str(file.resolve())
            media = (await db.execute(select(Media).where(Media.file_path == resolved))).scalar_one_or_none()
            if stopped():
                break
            existing = media is not None
            if media is None:
                # Allocate the ID before generation, without holding a SQLite write lock.
                stat = await asyncio.to_thread(file.stat)
                media = Media(id=str(uuid.uuid4()), file_path=resolved, media_type=media_type,
                              size_bytes=stat.st_size, folder=str(file.parent), root_dir=str(path))
            if media_type == MediaType.VIDEO and (not existing or backfill_existing):
                if not media.thumbnail_path:
                    notify("thumbnail", "处理视频首帧", index, total_files, resolved)
                    media.thumbnail_path = await asyncio.to_thread(
                        generate_thumbnail, resolved, media.id, output_dir=asset_dir)
                    if media.thumbnail_path:
                        stats["thumbnail_count"] += 1
                if preview and not media.preview_path:
                    pending_previews.append((resolved, media.id))
            if existing:
                stats["existing_count"] += 1
            else:
                db.add(media)
                stats["added_count"] += 1
            await save()

        if pending_previews and not stopped():
            limit = workers or min(os.cpu_count() or 4, 4)
            queue = iter(pending_previews)
            completed = 0
            notify("preview", "生成视频预览图", 0, len(pending_previews))

            async def run_preview(video_path: str, media_id: str) -> tuple[str, str | None]:
                # Check again when this coroutine actually starts, before a thread is dispatched.
                if stopped():
                    return media_id, None
                result = await asyncio.to_thread(generate_preview, video_path, media_id, output_dir=asset_dir)
                return media_id, result

            def fill() -> None:
                while not stopped() and len(in_flight) < limit:
                    item = next(queue, None)
                    if item is None:
                        break
                    in_flight.add(asyncio.create_task(run_preview(*item)))

            fill()
            while in_flight:
                done, _ = await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)
                # Keep all tasks tracked until their results have been handled, so
                # a failed commit still drains every worker before file cleanup.
                for task in done:
                    media_id, preview_path = task.result()
                    if preview_path:
                        media = await db.get(Media, media_id)
                        if media is not None:
                            media.preview_path = preview_path
                            stats["preview_count"] += 1
                    completed += 1
                    await save()
                    in_flight.remove(task)
                    notify("preview", "生成视频预览图", completed, len(pending_previews))
                fill()

        notify("committing", "保存处理结果", stats["scanned_files"], total_files)
        await save()
        return stats
    except BaseException:
        await db.rollback()
        # Cancelling an asyncio wrapper does not stop its underlying thread.
        # Drain workers before callers delete unreferenced generated files.
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
        raise


async def get_feed(
    db: AsyncSession,
    page: int = 1,
    page_size: int = settings.feed_page_size,
    media_type: MediaType | None = None,
    folder: str | None = None,
    is_favorited: bool | None = None,
    is_deleted: bool | None = None,
    is_damaged: bool | None = None,
    folder_exact: bool = False,
    folder_after: str | None = None,
    sort: FeedSort = "created_desc",
) -> FeedResponse:
    query = select(Media)
    count_query = select(func.count(Media.id))

    if media_type:
        query = query.where(Media.media_type == media_type)
        count_query = count_query.where(Media.media_type == media_type)
    if folder:
        folder_filter = Media.folder == folder if folder_exact else Media.folder.contains(folder)
        query = query.where(folder_filter)
        count_query = count_query.where(folder_filter)
    if folder_after:
        query = query.where(Media.folder.isnot(None), Media.folder > folder_after)
        count_query = count_query.where(Media.folder.isnot(None), Media.folder > folder_after)
    if is_favorited is not None:
        query = query.where(Media.is_favorited == is_favorited)
        count_query = count_query.where(Media.is_favorited == is_favorited)
    if is_deleted is not None:
        query = query.where(Media.is_deleted == is_deleted)
        count_query = count_query.where(Media.is_deleted == is_deleted)
    if is_damaged is not None:
        query = query.where(Media.is_damaged == is_damaged)
        count_query = count_query.where(Media.is_damaged == is_damaged)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size

    if sort == "file_path_asc":
        query = query.order_by(Media.folder.asc(), Media.file_path.asc())
    elif sort == "size_desc":
        query = query.order_by(Media.size_bytes.desc(), Media.file_path.asc())
    else:
        query = query.order_by(Media.created_at.desc())
    query = query.offset(offset).limit(page_size + 1)
    rows = (await db.execute(query)).scalars().all()

    has_next = len(rows) > page_size
    items = [MediaOut.model_validate(m) for m in rows[:page_size]]

    return FeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


async def get_random_media(
    db: AsyncSession,
    count: int = 50,
    exclude_ids: list[str] | None = None,
    media_type: MediaType | None = None,
    is_favorited: bool | None = None,
    is_deleted: bool | None = None,
    is_damaged: bool | None = None,
    folder: str | None = None,
) -> dict:
    query = select(Media)
    count_query = select(func.count(Media.id))

    if media_type:
        query = query.where(Media.media_type == media_type)
        count_query = count_query.where(Media.media_type == media_type)

    if folder is not None:
        query = query.where(Media.folder == folder)
        count_query = count_query.where(Media.folder == folder)

    if exclude_ids:
        query = query.where(Media.id.notin_(exclude_ids))

    if is_favorited is not None:
        query = query.where(Media.is_favorited == is_favorited)
        count_query = count_query.where(Media.is_favorited == is_favorited)
    if is_deleted is not None:
        query = query.where(Media.is_deleted == is_deleted)
        count_query = count_query.where(Media.is_deleted == is_deleted)
    if is_damaged is not None:
        query = query.where(Media.is_damaged == is_damaged)
        count_query = count_query.where(Media.is_damaged == is_damaged)

    query = query.order_by(func.random()).limit(count)

    result = await db.execute(query)
    items = [MediaOut.model_validate(m) for m in result.scalars().all()]

    total = (await db.execute(count_query)).scalar_one()

    return {"items": items, "total": total}


async def browse_folders(
    db: AsyncSession,
    root_dir: str | None = None,
    subdir: str | None = None,
    media_type: MediaType | None = None,
) -> dict:
    if root_dir is None:
        result = await db.execute(
            select(Media.root_dir, func.count(Media.id))
            .where(Media.root_dir.isnot(None))
            .group_by(Media.root_dir)
        )
        roots = [
            {"path": r, "name": Path(r).name, "count": c}
            for r, c in result.all()
        ]
        return {"roots": roots, "folders": [], "items": []}

    target_dir = str(Path(root_dir) / subdir) if subdir else root_dir

    # Media directly in this directory, sorted by filename
    query = select(Media).where(Media.folder == target_dir)
    if media_type:
        query = query.where(Media.media_type == media_type)
    query = query.order_by(Media.file_path)
    direct_result = await db.execute(query)
    items = [MediaOut.model_validate(m) for m in direct_result.scalars().all()]

    # Find immediate subdirectories
    sep = os.sep
    prefix = target_dir + sep
    sub_result = await db.execute(
        select(Media.folder)
        .where(Media.root_dir == root_dir, Media.folder.startswith(prefix))
        .distinct()
    )
    subdirs = sorted({
        folder[len(prefix):].split(sep)[0]
        for (folder,) in sub_result.all()
    })

    return {"roots": [], "folders": subdirs, "items": items}


async def get_media(db: AsyncSession, media_id: str) -> Media | None:
    result = await db.execute(select(Media).where(Media.id == media_id))
    return result.scalar_one_or_none()


def parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse Range header, return (start, end) bytes inclusive."""
    unit, ranges = range_header.split("=")
    if unit.strip() != "bytes":
        raise ValueError("Only bytes range is supported")

    part = ranges.split(",")[0].strip()
    start_str, end_str = part.split("-")

    if start_str == "" and end_str == "":
        raise ValueError("Invalid range")

    if start_str == "":
        start = file_size - int(end_str)
        end = file_size - 1
    elif end_str == "":
        start = int(start_str)
        end = file_size - 1
    else:
        start = int(start_str)
        end = min(int(end_str), file_size - 1)

    if start > end or start >= file_size:
        raise ValueError("Range not satisfiable")

    return start, end


def get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_map.get(ext, "application/octet-stream")


async def toggle_favorite(db: AsyncSession, media_id: str) -> MediaOut:
    media = await get_media(db, media_id)
    if not media:
        raise ValueError("Media not found")
    media.is_favorited = not media.is_favorited
    await db.commit()
    await db.refresh(media)
    return MediaOut.model_validate(media)


async def toggle_deleted(db: AsyncSession, media_id: str) -> MediaOut:
    media = await get_media(db, media_id)
    if not media:
        raise ValueError("Media not found")
    media.is_deleted = not media.is_deleted
    await db.commit()
    await db.refresh(media)
    return MediaOut.model_validate(media)


async def toggle_damaged(db: AsyncSession, media_id: str) -> MediaOut:
    media = await get_media(db, media_id)
    if not media:
        raise ValueError("Media not found")
    media.is_damaged = not media.is_damaged
    await db.commit()
    await db.refresh(media)
    return MediaOut.model_validate(media)


async def purge_deleted(db: AsyncSession) -> int:
    result = await db.execute(select(Media).where(Media.is_deleted == True))
    items = result.scalars().all()
    count = 0
    for media in items:
        if media.file_path and os.path.exists(media.file_path):
            os.remove(media.file_path)
        if media.thumbnail_path and os.path.exists(media.thumbnail_path):
            os.remove(media.thumbnail_path)
        if media.preview_path and os.path.exists(media.preview_path):
            os.remove(media.preview_path)
        await db.delete(media)
        count += 1
    await db.commit()
    return count


async def export_favorites(db: AsyncSession, target_dir: str) -> int:
    return await export_media_by_tags(db, target_dir, ["favorited"])


async def export_media_by_tags(db: AsyncSession, target_dir: str, tags: list[ExportTag]) -> int:
    filters = []
    if "favorited" in tags:
        filters.append(Media.is_favorited == True)
    if "deleted" in tags:
        filters.append(Media.is_deleted == True)
    if "damaged" in tags:
        filters.append(Media.is_damaged == True)
    if not filters:
        return 0

    result = await db.execute(select(Media).where(or_(*filters)))
    items = result.scalars().all()
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    count = 0
    for media in items:
        if media.file_path and os.path.exists(media.file_path):
            dest = Path(target_dir) / Path(media.file_path).name
            shutil.copy2(media.file_path, dest)
            count += 1
    return count


async def batch_update(db: AsyncSession, ids: list[str], action: str) -> int:
    count = 0
    for mid in ids:
        media = await get_media(db, mid)
        if not media:
            continue
        if action == "favorite":
            media.is_favorited = True
        elif action == "unfavorite":
            media.is_favorited = False
        elif action == "delete":
            media.is_deleted = True
        elif action == "undelete":
            media.is_deleted = False
        elif action == "damage":
            media.is_damaged = True
        elif action == "undamage":
            media.is_damaged = False
        else:
            continue
        count += 1
    await db.commit()
    return count
