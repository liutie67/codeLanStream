import asyncio
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from app.core.database import async_session
from app.services.media import scan_directory_stats

MAX_FINISHED_JOBS = 30

_jobs: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty_stats(preview_requested: bool = False) -> dict[str, int | str | bool]:
    return {
        "root_dir": "",
        "scanned_files": 0,
        "added_count": 0,
        "existing_count": 0,
        "skipped_count": 0,
        "thumbnail_count": 0,
        "preview_count": 0,
        "preview_requested": preview_requested,
    }


def _calculate_percent(stage: str, current: int, total: int, preview_requested: bool) -> int:
    if stage == "queued":
        return 0
    if stage == "preparing":
        return 2
    if stage in ("scanning", "thumbnail"):
        span = 60 if preview_requested else 90
        return min(95, 5 + round((current / total) * span)) if total else 5
    if stage == "preview":
        return min(97, 70 + round((current / total) * 25)) if total else 70
    if stage == "committing":
        return 98
    if stage == "completed":
        return 100
    if stage == "failed":
        return 100
    return 0


def _public_job(job_id: str) -> dict[str, Any] | None:
    job = _jobs.get(job_id)
    return deepcopy(job) if job else None


def _prune_finished_jobs() -> None:
    finished = [
        job
        for job in _jobs.values()
        if job["status"] in ("completed", "failed")
    ]
    if len(finished) <= MAX_FINISHED_JOBS:
        return

    finished.sort(key=lambda job: job["updated_at"])
    for job in finished[:len(finished) - MAX_FINISHED_JOBS]:
        _jobs.pop(job["id"], None)
        _tasks.pop(job["id"], None)


def start_import_job(options: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = _now()
    job = {
        "id": job_id,
        "status": "queued",
        "stage": "queued",
        "message": "等待开始",
        "percent": 0,
        "current": 0,
        "total": 0,
        "current_file": None,
        "stats": _empty_stats(bool(options.get("preview"))),
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    _jobs[job_id] = job
    _tasks[job_id] = asyncio.create_task(_run_import_job(job_id, options))
    _prune_finished_jobs()
    return deepcopy(job)


def get_import_job(job_id: str) -> dict[str, Any] | None:
    return _public_job(job_id)


async def _run_import_job(job_id: str, options: dict[str, Any]) -> None:
    job = _jobs[job_id]
    preview_requested = bool(options.get("preview"))

    def update_progress(payload: dict[str, Any]) -> None:
        stage = str(payload.get("stage") or job["stage"])
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        stats = payload.get("stats")

        job.update({
            "status": "running",
            "stage": stage,
            "message": payload.get("message") or job["message"],
            "current": current,
            "total": total,
            "current_file": payload.get("current_file"),
            "updated_at": _now(),
        })
        if isinstance(stats, dict):
            job["stats"] = deepcopy(stats)
        job["percent"] = _calculate_percent(stage, current, total, preview_requested)

    try:
        update_progress({"stage": "preparing", "message": "准备导入", "current": 0, "total": 0})
        async with async_session() as db:
            stats = await scan_directory_stats(
                options["path"],
                db,
                preview=preview_requested,
                workers=options.get("workers"),
                media_type_filter=options.get("media_type"),
                recursive=bool(options.get("recursive", True)),
                skip_hidden=bool(options.get("skip_hidden", True)),
                backfill_existing=bool(options.get("backfill_existing", True)),
                progress=update_progress,
            )

        job.update({
            "status": "completed",
            "stage": "completed",
            "message": "导入完成",
            "percent": 100,
            "current_file": None,
            "stats": deepcopy(stats),
            "updated_at": _now(),
        })
    except Exception as exc:
        job.update({
            "status": "failed",
            "stage": "failed",
            "message": "导入失败",
            "percent": 100,
            "error": str(exc),
            "current_file": None,
            "updated_at": _now(),
        })
