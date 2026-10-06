"""Independent, persistent single-server availability checks."""
import asyncio
import logging
import uuid
from copy import deepcopy
from datetime import datetime

from sqlalchemy import delete, select

from app.core.database import async_session
from app.models.availability_job import AvailabilityJob
from app.models.media import Media
from app.services.availability import BATCH_SIZE, CheckCancelled, check_records, snapshot

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "running", "cancelling"}
_jobs: dict[str, dict] = {}
_tasks: dict[str, asyncio.Task] = {}
_signals: dict[str, asyncio.Event] = {}
_lock = asyncio.Lock()
_stopping = False


def now() -> str:
    return datetime.now().isoformat(timespec="microseconds")


async def persist(job: dict) -> None:
    async with async_session() as db:
        record = await db.get(AvailabilityJob, job["id"])
        if record is None:
            record = AvailabilityJob(id=job["id"])
            db.add(record)
        record.payload = deepcopy(job)
        record.active_slot = "active" if job["status"] in ACTIVE else None
        await db.commit()


async def initialize_check_jobs() -> None:
    global _lock, _stopping
    _lock = asyncio.Lock()
    _stopping = False
    _jobs.clear()
    _tasks.clear()
    _signals.clear()
    async with async_session() as db:
        for record in (await db.scalars(select(AvailabilityJob))).all():
            job = deepcopy(record.payload)
            if job["status"] in ACTIVE:
                job.update(status="interrupted", message="服务重启，检查已中断；已保存的检查结果保留", updated_at=now())
                record.payload = job
                record.active_slot = None
            _jobs[job["id"]] = job
        await db.commit()


def list_check_jobs() -> list[dict]:
    return deepcopy(sorted(_jobs.values(), key=lambda job: job["created_at"], reverse=True))


def get_check_job(job_id: str) -> dict | None:
    return deepcopy(_jobs.get(job_id))


async def start_check_job() -> dict:
    async with _lock:
        if _stopping:
            raise RuntimeError("服务正在关闭")
        active = next((job for job in _jobs.values() if job["status"] in ACTIVE), None)
        if active:
            return deepcopy(active)  # Repeated clicks attach to the existing check.
        async with async_session() as db:
            # Snapshot membership: concurrent imports join the next check.
            ids = list((await db.scalars(select(Media.id).order_by(Media.id))).all())
        job_id = str(uuid.uuid4())
        job = dict(id=job_id, status="queued", message="等待检查", processed=0, total=len(ids),
                   available=0, missing=0, unavailable=0, percent=0, error=None,
                   created_at=now(), updated_at=now())
        await persist(job)
        _jobs[job_id] = job
        _signals[job_id] = asyncio.Event()
        _tasks[job_id] = asyncio.create_task(run_job(job_id, ids))
        # Bounded history, independent of import tasks.
        finished = [j for j in list_check_jobs() if j["status"] not in ACTIVE]
        for old in finished[30:]:
            async with async_session() as db:
                await db.execute(delete(AvailabilityJob).where(AvailabilityJob.id == old["id"]))
                await db.commit()
            _jobs.pop(old["id"], None)
        return deepcopy(job)


async def cancel_check_job(job_id: str) -> dict | None:
    async with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job["status"] in ACTIVE:
            _signals[job_id].set()
            job.update(status="cancelling", message="正在停止检查", updated_at=now())
            await persist(job)
        return deepcopy(job)


async def run_job(job_id: str, ids: list[str]) -> None:
    job = _jobs[job_id]
    try:
        async with _lock:
            if not _signals[job_id].is_set():
                job.update(status="running", message="正在检查原文件", updated_at=now())
                await persist(job)
        for offset in range(0, len(ids), BATCH_SIZE):
            if _signals[job_id].is_set():
                break
            batch = ids[offset:offset + BATCH_SIZE]
            async with async_session() as db:
                rows = (await db.scalars(select(Media).where(Media.id.in_(batch)))).all()
                try:
                    checked = await check_records(db, [snapshot(row) for row in rows], cancel=_signals[job_id])
                except CheckCancelled:
                    break
            async with _lock:
                job["processed"] += len(batch)
                for row in checked:
                    job[row.availability] += 1
                job.update(percent=round(100 * job["processed"] / job["total"]) if job["total"] else 100,
                           updated_at=now())
                await persist(job)
        async with _lock:
            status = "interrupted" if _stopping else "cancelled" if _signals[job_id].is_set() else "completed"
            finished = {**job, "status": status,
                        "message": {"completed": "检查完成", "cancelled": "检查已取消，已保存结果保留",
                                    "interrupted": "服务关闭，检查已中断；已保存结果保留"}[status], "updated_at": now()}
            if status == "completed":
                finished["percent"] = 100
            # Publish a terminal state only after its durable checkpoint.
            # Pollers may stop immediately once they observe completion.
            await persist(finished)
            job.update(finished)
    except Exception as error:
        logger.exception("Availability check %s failed", job_id)
        async with _lock:
            failed = {**job, "status": "failed", "message": "检查失败，已保存结果保留",
                      "error": str(error), "updated_at": now()}
            await persist(failed)
            job.update(failed)
    finally:
        _tasks.pop(job_id, None)
        _signals.pop(job_id, None)


async def shutdown_check_jobs() -> None:
    global _stopping
    _stopping = True
    for signal in list(_signals.values()):
        signal.set()
    await asyncio.gather(*list(_tasks.values()), return_exceptions=True)
