"""Source availability shared by browse, delivery and explicit checks.

Probe snapshots outside transactions; compare path and check timestamp on write.
Filesystem workers only return observations and never touch application state.
"""
import asyncio
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import Media
from app.services.disk_probe import probe

DIRECTORY_TTL = 5.0
BROWSE_TIMEOUT = 8.0
BATCH_SIZE = 128
CACHE_LIMIT = 4096
_cache: OrderedDict[tuple[str, str, str], tuple[float, dict, datetime]] = OrderedDict()
_pending: dict[tuple[str, str, tuple[str, ...], object | None], asyncio.Task] = {}


class SourceUnavailable(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class CheckCancelled(Exception):
    pass


def initialize_availability() -> None:
    _cache.clear()
    _pending.clear()


async def shutdown_availability() -> None:
    tasks = list(_pending.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _pending.clear()


def source_error(result: dict, *, directory: bool = False) -> SourceUnavailable:
    if result.get("reason") == "permission":
        return SourceUnavailable(403, "没有权限读取此目录或文件")
    if result["status"] == "missing":
        return SourceUnavailable(404, "目录已不存在" if directory else "原文件已不存在")
    return SourceUnavailable(503, "媒体来源暂不可访问，请连接硬盘或检查网络后重试")


def snapshot(media: Media) -> dict[str, Any]:
    return {"id": media.id, "file_path": media.file_path, "root_dir": media.root_dir,
            "folder": media.folder, "availability_checked_at": media.availability_checked_at}


async def check_records(
    db: AsyncSession, records: list[dict], *, cancel: asyncio.Event | None = None,
    force: bool = True, tolerate_uncertain: bool = False, observations: dict | None = None,
) -> list[Media]:
    if not records:
        return []
    # Close the read transaction before any slow filesystem work.
    await db.commit()
    groups: dict[str, list[dict]] = {}
    for record in records:
        root = record["root_dir"] or record["folder"] or str(Path(record["file_path"]).parent)
        groups.setdefault(root, []).append(record)

    async def check(root: str, group: list[dict]):
        result = await probe_paths(root, [r["file_path"] for r in group], "files", force=force)
        return group, result

    checks = asyncio.gather(*(check(root, group) for root, group in groups.items()))
    stopped = asyncio.create_task(cancel.wait()) if cancel is not None else None
    try:
        if stopped is not None:
            await asyncio.wait([checks, stopped], return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                checks.cancel()
                await asyncio.gather(checks, return_exceptions=True)
                raise CheckCancelled()
        results = await checks
    finally:
        if stopped is not None:
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)
        if not checks.done():
            checks.cancel()
            await asyncio.gather(checks, return_exceptions=True)
    uncertain = set()
    for group, result in results:
        for record in group:
            info = result["files"][record["file_path"]]
            if info.get("confirmed") is False:
                uncertain.add(record["id"])
                continue
            if observations is not None:
                observations[record["id"]] = info
            observed = info["observed_at"]
            # Cache hits must not acquire a write lock or move the check time.
            previous = record["availability_checked_at"]
            if previous is not None and previous >= observed:
                continue
            await db.execute(update(Media).where(
                Media.id == record["id"], Media.file_path == record["file_path"],
                Media.availability_checked_at == record["availability_checked_at"],
            ).values(availability=info["status"], availability_checked_at=observed, updated_at=Media.updated_at)
                .execution_options(synchronize_session=False))
    await db.commit()
    if uncertain and not tolerate_uncertain:
        raise SourceUnavailable(503, "探测超时或失败，未确认的记录保留原状态，请重试")
    rows = (await db.scalars(select(Media).where(Media.id.in_([r["id"] for r in records]))
                            .where(Media.id.notin_(uncertain))
                            .execution_options(populate_existing=True))).all()
    return list(rows)


def _prune_cache(now: float) -> None:
    for key, (stamp, _, _) in list(_cache.items()):
        if now - stamp >= DIRECTORY_TTL:
            del _cache[key]
    while len(_cache) > CACHE_LIMIT:
        _cache.popitem(last=False)


def _cache_result(root: str, kind: str, path: str, info: dict, observed: datetime) -> dict:
    info = {**info, "observed_at": observed}
    if info.get("confirmed") is not False:
        key = (root, kind, path)
        existing = _cache.get(key)
        if existing is None or existing[2] <= observed:
            _cache[key] = (asyncio.get_running_loop().time(), info, observed)
            _cache.move_to_end(key)
            while len(_cache) > CACHE_LIMIT:
                _cache.popitem(last=False)
    return info


async def probe_paths(root: str, paths: list[str], kind: str, *, force: bool = False) -> dict:
    """Share bounded per-path metadata between browsing and media delivery."""
    paths = sorted(set(paths))
    now = asyncio.get_running_loop().time()
    _prune_cache(now)
    found = {}
    if not force:
        for path in paths:
            key = (root, kind, path)
            if key in _cache:
                found[path] = _cache[key][1]
                _cache.move_to_end(key)
    missing = [path for path in paths if path not in found]
    root_cached = _cache.get((root, "root", root))
    if not missing and root_cached:
        _cache.move_to_end((root, "root", root))
        if root_cached[1]["status"] != "available":
            found = dict.fromkeys(paths, root_cached[1])
        return {"root": root_cached[1], kind: found}
    # A manual retry must not join a probe that started before the retry.
    key = (root, kind, tuple(missing), object() if force else None)

    async def run():
        observed = datetime.now()
        result = await probe({"action": "probe", "root": root or None, kind: missing})
        root_info = _cache_result(root, "root", root, result["root"], observed)
        values = {path: _cache_result(root, kind, path, info, observed)
                  for path, info in result.get(kind, {}).items()}
        return {"root": root_info, kind: values}

    task = _pending.get(key)
    if task is None:
        task = asyncio.create_task(run())
        _pending[key] = task
        task.add_done_callback(lambda finished: _pending.pop(key, None) if _pending.get(key) is finished else None)
    # File checks own their probe lifetime so cancellation kills the child.
    # Directory discovery is single-flight and can outlive an aborted client.
    result = await asyncio.shield(task) if kind == "directories" else await task
    found.update(result[kind])
    if result["root"]["status"] != "available":
        # A fresh root failure takes precedence over old positive file metadata.
        found = dict.fromkeys(paths, result["root"])
    return {"root": result["root"], kind: found}


async def probe_directories(root: str, folders: list[str], *, force: bool = False) -> tuple[dict, datetime]:
    result = await probe_paths(root, folders, "directories", force=force)
    return result, result["root"]["observed_at"]


async def file_info(path: str, *, root: str = "") -> dict:
    result = await probe_paths(root, [path], "files")
    return result["files"][path]


def scope_filters(root: str | None = None, folder: str | None = None) -> list:
    filters = []
    if root:
        filters.append(Media.root_dir == root)
    if folder:
        filters.append(or_(Media.folder == folder, Media.folder.startswith(folder.rstrip(os.sep) + os.sep, autoescape=True)))
    return filters


async def refresh_directories(db: AsyncSession, *, root: str | None = None, folder: str | None = None) -> dict[str, dict]:
    filters = scope_filters(root, folder)
    pairs = (await db.execute(select(Media.root_dir, Media.folder).where(*filters).distinct())).all()
    groups: dict[str, list[str]] = {}
    for source, directory in pairs:
        if source:
            groups.setdefault(source, [])
        if directory:
            groups.setdefault(source or directory, []).append(directory)
    await db.commit()
    results = await asyncio.gather(*(probe_directories(source, directories) for source, directories in groups.items()))
    roots = {}
    accessible = []
    for (source, directories), (result, observed) in zip(groups.items(), results):
        roots[source] = result["root"]
        for directory in directories:
            info = result["directories"][directory]
            state = info["status"]
            observed = info["observed_at"]
            if info.get("confirmed") is False:
                continue  # A batch timeout is not evidence about its members.
            if state == "available":
                accessible.append(directory)
                continue
            # Only write changes. Repeated cached observations cannot overwrite
            # a more recent explicit check or resurrect a deleted record.
            await db.execute(update(Media).where(
                *filters, Media.folder == directory, Media.availability != state,
                or_(Media.root_dir == source, Media.root_dir.is_(None)),
                or_(Media.availability_checked_at.is_(None), Media.availability_checked_at <= observed),
            ).values(availability=state, availability_checked_at=observed, updated_at=Media.updated_at)
                .execution_options(synchronize_session=False))
    await db.commit()
    # Hidden rows participate in recovery. Rotate by oldest check so a large
    # restored directory eventually recovers without a permanent exclusion.
    if accessible:
        stale = datetime.now() - timedelta(seconds=DIRECTORY_TTL)
        recovery = (await db.scalars(select(Media).where(
            *filters, Media.folder.in_(accessible), Media.availability != "available",
            or_(Media.availability_checked_at.is_(None), Media.availability_checked_at < stale),
        ).order_by(Media.availability_checked_at.asc(), Media.id.asc()).limit(BATCH_SIZE))).all()
        await check_records(db, [snapshot(row) for row in recovery], tolerate_uncertain=True)
    return roots


async def require_directory(root: str, target: str) -> None:
    # A selected path is probed afresh: removed directories never remain an
    # empty, apparently valid destination because of a cached folder tree.
    result, _ = await probe_directories(root, [target], force=True)
    state = result["directories"][target]
    if state["status"] != "available":
        raise source_error(state, directory=True)


async def validated_rows(db: AsyncSession, query, *, offset: int, limit: int) -> list[Media]:
    uncertain = set()
    while True:
        rows = (await db.scalars(query.where(Media.id.notin_(uncertain)).offset(offset).limit(limit))).all()
        if not rows:
            if uncertain:
                raise SourceUnavailable(503, "部分媒体探测超时，请稍后重试")
            return []
        checked = await check_records(db, [snapshot(row) for row in rows], force=False, tolerate_uncertain=True)
        by_id = {row.id: row for row in checked}
        uncertain.update(row.id for row in rows if row.id not in by_id)
        if all(row.id in by_id and by_id[row.id].availability == "available" for row in rows):
            return [by_id[row.id] for row in rows]
        # Re-query at the same offset after removing invalid candidates. This
        # refills the page instead of mistaking filtered rows for exhaustion.


async def remove_records(db: AsyncSession, ids: list[str]) -> int:
    rows = (await db.scalars(select(Media).where(Media.id.in_(ids)))).all()
    checked = await check_records(db, [snapshot(row) for row in rows])
    if any(row.availability == "available" for row in checked):
        raise SourceUnavailable(409, "部分文件已恢复可用，请复查后仅选择失效记录移除")
    from sqlalchemy import delete
    count = 0
    for row in checked:
        result = await db.execute(delete(Media).where(
            Media.id == row.id, Media.file_path == row.file_path,
            Media.availability == row.availability, Media.availability_checked_at == row.availability_checked_at,
        ).execution_options(synchronize_session=False))
        count += result.rowcount
    await db.commit()
    return count
