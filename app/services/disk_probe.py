import asyncio
import json
import sys
from pathlib import Path

PROBE_TIMEOUT = 3.0
MAX_WORKERS = 2
_slots = asyncio.Semaphore(MAX_WORKERS)
_processes: set[asyncio.subprocess.Process] = set()
WORKER = str(Path(__file__).with_name("disk_worker.py"))


def initialize_probes() -> None:
    global _slots
    _slots = asyncio.Semaphore(MAX_WORKERS)


def _failed(body: dict, reason: str) -> dict:
    # A batch deadline says nothing about which path stalled. Never persist
    # this synthetic result as an observation of every requested file.
    result = {"status": "unavailable", "reason": reason, "confirmed": False}
    if body["action"] == "directories":
        return result
    return {"root": result, "directories": dict.fromkeys(body.get("directories", []), result),
            "files": dict.fromkeys(body.get("files", []), result)}


async def probe(body: dict) -> dict:
    async with _slots:
        # A process stuck in an uninterruptible kernel syscall may not reap
        # immediately even after SIGKILL. Count it until exit, never replace it
        # with an unlimited stream of new workers.
        if len(_processes) >= MAX_WORKERS:
            return _failed(body, "timeout")
        process = None
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, WORKER, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                )
                _processes.add(process)
                stdout, _ = await process.communicate(json.dumps(body).encode())
                if process.returncode != 0:
                    return _failed(body, "io_error")
                return json.loads(stdout)
        except TimeoutError:
            return _failed(body, "timeout")
        except (OSError, ValueError):
            return _failed(body, "io_error")
        finally:
            if process is not None:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.communicate(), .2)
                    except TimeoutError:
                        waiter = asyncio.create_task(process.communicate())
                        waiter.add_done_callback(lambda _: _processes.discard(process))
                if process.returncode is not None:
                    _processes.discard(process)


async def shutdown_probes() -> None:
    for process in list(_processes):
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    try:
        async with asyncio.timeout(.5):
            await asyncio.gather(*(process.wait() for process in list(_processes)))
    except TimeoutError:
        pass  # An OS-level stalled process still counts against capacity.
