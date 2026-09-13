"""Persistent, single-server import jobs with cooperative cancellation.

The lock serializes state transitions with media checkpoints. Worker threads never
access SQLAlchemy sessions or mutate public job state.
"""
import asyncio
import logging
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.import_job import ImportJob
from app.models.media import Media
from app.services.media import scan_directory_stats
from app.services.thumbnail import IMPORT_ASSET_DIR

logger = logging.getLogger(__name__)
MAX_FINISHED_JOBS = 30
ACTIVE = {"queued", "running", "cancelling"}
_jobs: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task] = {}
_signals: dict[str, asyncio.Event] = {}
_lock = asyncio.Lock()
_shutting_down = False


class ImportConflict(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id


def _now() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _percent(stage: str, current: int, total: int, preview: bool) -> int:
    if stage == "preparing":
        return 2
    if stage in ("scanning", "thumbnail"):
        return min(95, 5 + round(current / total * (60 if preview else 90))) if total else 5
    if stage == "preview":
        return min(97, 70 + round(current / total * 25)) if total else 70
    if stage == "committing":
        return 98
    return 0


async def _persist(job: dict[str, Any], db: AsyncSession | None = None) -> None:
    if db is None:
        async with async_session() as session:
            await _persist(job, session)
            await session.commit()
        return
    await db.execute(update(ImportJob).where(ImportJob.id == job["id"]).values(
        payload=deepcopy(job), active_slot="active" if job["status"] in ACTIVE else None,
    ))


async def cleanup_import_assets(job_id: str | None = None) -> None:
    """Only remove task-owned files that no committed media record references."""
    async with async_session() as db:
        rows = (await db.execute(select(Media.thumbnail_path, Media.preview_path))).all()
    referenced = {str(Path(p).resolve()) for row in rows for p in row if p}
    root = IMPORT_ASSET_DIR / job_id if job_id else IMPORT_ASSET_DIR

    def clean() -> None:
        if not root.exists():
            return
        for file in root.rglob("*"):
            if file.is_file() and str(file.resolve()) not in referenced:
                file.unlink(missing_ok=True)
        for directory in sorted(root.rglob("*"), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    await asyncio.to_thread(clean)


async def initialize_import_jobs() -> None:
    global _shutting_down
    _shutting_down = False
    async with _lock:
        _jobs.clear()
        _signals.clear()
        _tasks.clear()
        async with async_session() as db:
            records = (await db.scalars(select(ImportJob))).all()
            for record in records:
                job = deepcopy(record.payload)
                if job["status"] in ACTIVE:
                    job.update(status="interrupted", stage="interrupted", current_file=None,
                               message="服务已重启，导入已中断；已保存结果保留，可重新导入补齐", updated_at=_now())
                    record.payload = job
                    record.active_slot = None
                _jobs[job["id"]] = job
            await db.commit()
        await cleanup_import_assets()
        await _prune()


async def _prune() -> None:
    finished = sorted((j for j in _jobs.values() if j["status"] not in ACTIVE),
                      key=lambda j: j["updated_at"], reverse=True)
    async with async_session() as db:
        for job in finished[MAX_FINISHED_JOBS:]:
            record = await db.get(ImportJob, job["id"])
            if record:
                await db.delete(record)
            _jobs.pop(job["id"], None)
        await db.commit()


async def start_import_job(options: dict[str, Any]) -> dict[str, Any]:
    options = deepcopy(options)
    request_id = options.pop("request_id", None)
    async with _lock:
        if request_id:
            for job in _jobs.values():
                if job.get("request_id") == request_id:
                    return deepcopy(job)
        for job in _jobs.values():
            if job["status"] in ACTIVE:
                raise ImportConflict(job["id"])
        job_id = str(uuid.uuid4())
        now = _now()
        job = dict(id=job_id, request_id=request_id, options=options, status="queued", stage="queued",
                   message="等待开始", percent=0, current=0, total=0, current_file=None, error=None,
                   created_at=now, updated_at=now,
                   stats=dict(root_dir=str(Path(options["path"]).expanduser().resolve()), scanned_files=0,
                              added_count=0, existing_count=0, skipped_count=0, thumbnail_count=0,
                              preview_count=0, preview_requested=bool(options.get("preview"))))
        async with async_session() as db:
            db.add(ImportJob(id=job_id, request_id=request_id, active_slot="active", payload=deepcopy(job)))
            await db.commit()
        _jobs[job_id] = job
        _signals[job_id] = asyncio.Event()
        _tasks[job_id] = asyncio.create_task(_run_import_job(job_id, options))
        return deepcopy(job)


def get_import_job(job_id: str) -> dict[str, Any] | None:
    job = _jobs.get(job_id)
    return deepcopy(job) if job else None


def list_import_jobs(request_id: str | None = None) -> list[dict[str, Any]]:
    return deepcopy(sorted((j for j in _jobs.values() if request_id is None or j.get("request_id") == request_id),
                           key=lambda j: j["created_at"], reverse=True))


async def cancel_import_job(job_id: str) -> dict[str, Any] | None:
    async with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job["status"] in {"queued", "running"}:
            candidate = deepcopy(job)
            candidate.update(status="cancelling", stage="cancelling", updated_at=_now(),
                             message="正在安全终止，等待当前处理完成并保存结果")
            # Signal before awaiting I/O, so a worker cannot dispatch more work
            # while the cancellation request is being persisted.
            _signals[job_id].set()
            await _persist(candidate)
            job.update(candidate)
        return deepcopy(job)


async def _run_import_job(job_id: str, options: dict[str, Any]) -> None:
    job = _jobs[job_id]
    signal = _signals[job_id]

    def progress(payload: dict[str, Any]) -> None:
        job.update(current=payload.get("current", job["current"]), total=payload.get("total", job["total"]),
                   current_file=payload.get("current_file"), updated_at=_now())
        if job["status"] != "cancelling":
            stage = payload.get("stage", job["stage"])
            job.update(status="running", stage=stage, message=payload.get("message", job["message"]))
            job["percent"] = max(job["percent"], _percent(stage, job["current"], job["total"], bool(options.get("preview"))))
        # Saved counters are updated exclusively after an atomic DB checkpoint.
        if "stats" in payload:
            for key in ("scanned_files", "skipped_count"):
                job["stats"][key] = payload["stats"][key]

    async def checkpoint(db: AsyncSession, stats: dict[str, Any]) -> None:
        async with _lock:
            candidate = deepcopy(job)
            candidate.update(stats=deepcopy(stats), updated_at=_now())
            await _persist(candidate, db)
            await db.commit()
            job.update(candidate)

    error = None
    try:
        async with async_session() as db:
            await scan_directory_stats(
                options["path"], db=db, preview=bool(options.get("preview")),
                workers=options.get("workers"), media_type_filter=options.get("media_type"),
                recursive=options.get("recursive", True), skip_hidden=options.get("skip_hidden", True),
                backfill_existing=options.get("backfill_existing", True), cancel=signal, progress=progress,
                                       checkpoint=checkpoint, asset_dir=IMPORT_ASSET_DIR / job_id)
    except Exception as exc:
        logger.exception("Import %s failed", job_id)
        error = str(exc)
    try:
        await cleanup_import_assets(job_id)
    except Exception as exc:
        logger.exception("Import %s asset cleanup failed", job_id)
        error = error or f"清理生成文件失败: {exc}"
    # Serialize the final commit boundary against cancellation. Release the lock
    # between persistence retries so a temporary database failure cannot prevent
    # accepting a later stop request.
    while True:
        async with _lock:
            status = ("failed" if error else "interrupted" if _shutting_down
                      else "cancelled" if signal.is_set() else "completed")
            candidate = deepcopy(job)
            candidate.update(status=status, stage=status, error=error, current_file=None, updated_at=_now(),
                             message={"failed": "导入失败，已保存结果保留", "cancelled": "已安全终止，已保存结果保留",
                                      "interrupted": "服务停止，导入已中断；已保存结果保留，可重新导入补齐",
                                      "completed": "导入完成"}[status])
            if status == "completed":
                candidate["percent"] = 100
            try:
                await _persist(candidate)
            except Exception:
                logger.exception("Unable to persist import terminal state; retrying")
            else:
                job.update(candidate)
                _signals.pop(job_id, None)
                _tasks.pop(job_id, None)
                await _prune()
                return
        await asyncio.sleep(1)


async def shutdown_import_jobs() -> None:
    global _shutting_down
    _shutting_down = True
    for signal in list(_signals.values()):
        signal.set()
    if _tasks:
        await asyncio.gather(*list(_tasks.values()), return_exceptions=True)
