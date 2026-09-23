import asyncio
import tempfile
import threading
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.import_job import ImportJob
from app.models.media import Base, Media
from app.services import import_jobs as jobs
from app.services import media as scanner
from app.services.thumbnail import ThumbnailStrategy, generate_thumbnail


class ImportJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.media_dir = self.root / 'media'
        self.media_dir.mkdir()
        self.assets = self.root / 'assets'
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{self.root / "test.db"}')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.patches = [patch.object(jobs, 'async_session', self.sessions),
                        patch.object(jobs, 'IMPORT_ASSET_DIR', self.assets)]
        for p in self.patches:
            p.start()
        jobs._lock = asyncio.Lock()
        await jobs.initialize_import_jobs()
        self.gates: list[threading.Event] = []

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.set()
        await asyncio.wait_for(jobs.shutdown_import_jobs(), 5)
        for p in reversed(self.patches):
            p.stop()
        await self.engine.dispose()
        self.temp.cleanup()

    def files(self, count=3, extension='jpg'):
        for index in range(count):
            (self.media_dir / f'{index:02}.{extension}').write_bytes(b'test')

    async def start(self, **options):
        return await jobs.start_import_job(dict(path=str(self.media_dir), preview=False, **options))

    async def finished(self, job_id):
        async def wait():
            while jobs.get_import_job(job_id)['status'] in jobs.ACTIVE:
                await asyncio.sleep(.005)
            return jobs.get_import_job(job_id)
        return await asyncio.wait_for(wait(), 5)

    async def rows(self):
        async with self.sessions() as db:
            return list((await db.scalars(select(Media))).all())

    async def wait_event(self, event):
        async def wait():
            while not event.is_set():
                await asyncio.sleep(.005)
        await asyncio.wait_for(wait(), 5)

    def blocking_generator(self):
        entered = threading.Event()
        release = threading.Event()
        self.gates.append(release)
        calls = []

        def generate(path, media_id, *, output_dir=None):
            calls.append(media_id)
            entered.set()
            release.wait(5)
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f'{media_id}.png'
            output.write_bytes(b'image')
            return str(output)
        return generate, entered, release, calls

    async def test_single_task_and_idempotent_creation(self):
        request_id = str(uuid.uuid4())
        # Hold the worker so all requests compete while the slot is occupied.
        gate = asyncio.Event()
        async def hold(*args, **kwargs):
            await gate.wait()
        with patch.object(jobs, 'scan_directory_stats', hold):
            first, duplicate = await asyncio.gather(self.start(request_id=request_id), self.start(request_id=request_id))
            self.assertEqual(first['id'], duplicate['id'])
            with self.assertRaises(jobs.ImportConflict):
                await self.start(request_id=str(uuid.uuid4()))
            gate.set()
            await self.finished(first['id'])
            again = await self.start(request_id=request_id)
            self.assertEqual(again['id'], first['id'])

    async def test_queued_cancel_is_idempotent(self):
        self.files()
        job = await self.start()
        a, b = await asyncio.gather(jobs.cancel_import_job(job['id']), jobs.cancel_import_job(job['id']))
        self.assertEqual(a['status'], 'cancelling')
        self.assertEqual(b['status'], 'cancelling')
        done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'cancelled')
        self.assertEqual(len(await self.rows()), 0)
        self.assertIsNone(await jobs.cancel_import_job('missing'))

    async def test_thumbnail_cancel_drains_and_retains_current_file(self):
        self.files(extension='mp4')
        generate, entered, release, calls = self.blocking_generator()
        with patch.object(scanner, 'generate_thumbnail', generate):
            job = await self.start()
            await self.wait_event(entered)
            await jobs.cancel_import_job(job['id'])
            await asyncio.sleep(.03)
            self.assertEqual(jobs.get_import_job(job['id'])['status'], 'cancelling')
            self.assertEqual(jobs.get_import_job(job['id'])['stats']['added_count'], 0)
            release.set()
            done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'cancelled')
        self.assertEqual(len(calls), 1)
        self.assertEqual(done['stats']['added_count'], 1)
        self.assertEqual(done['stats']['thumbnail_count'], 1)
        row = (await self.rows())[0]
        self.assertTrue(Path(row.thumbnail_path).exists())
        self.assertLess(done['percent'], 100)

    async def test_preview_cancellation_stops_dispatch_and_drains_workers(self):
        self.files(5, 'mp4')
        generate, entered, release, calls = self.blocking_generator()
        with patch.object(scanner, 'generate_thumbnail', return_value=None), patch.object(scanner, 'generate_preview', generate):
            job = await jobs.start_import_job(dict(path=str(self.media_dir), preview=True, workers=2))
            await self.wait_event(entered)
            while len(calls) < 2:
                await asyncio.sleep(.005)
            await jobs.cancel_import_job(job['id'])
            self.assertEqual(jobs.get_import_job(job['id'])['stats']['added_count'], 5)
            release.set()
            done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'cancelled')
        self.assertEqual(len(calls), 2)
        self.assertEqual(done['stats']['preview_count'], 2)
        self.assertEqual(sum(bool(row.preview_path) for row in await self.rows()), 2)

    async def test_commit_failure_retains_earlier_records_and_cleans_assets(self):
        self.files(3, 'mp4')
        def generate(path, media_id, *, output_dir=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            target = output_dir / f'{media_id}.jpg'
            target.write_bytes(b'image')
            return str(target)
        persist = jobs._persist
        async def fail_second(job, db=None):
            if db is not None and job['status'] in jobs.ACTIVE and job['stats']['added_count'] == 2:
                raise RuntimeError('injected commit failure')
            return await persist(job, db)
        with patch.object(scanner, 'generate_thumbnail', generate), patch.object(jobs, '_persist', fail_second):
            job = await self.start()
            done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'failed')
        self.assertEqual(done['stats']['added_count'], 1)
        self.assertEqual(len(await self.rows()), 1)
        self.assertEqual(len(list(self.assets.rglob('*.jpg'))), 1)

    async def test_restart_marks_interrupted_preserves_stats_and_cleans_orphans(self):
        self.files(1)
        job = await self.start()
        done = await self.finished(job['id'])
        orphan = self.assets / job['id'] / 'orphan.jpg'
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'orphan')
        async with self.sessions() as db:
            record = await db.get(ImportJob, job['id'])
            payload = deepcopy(record.payload)
            payload.update(status='running', stage='preview')
            record.payload = payload
            record.active_slot = 'active'
            await db.commit()
        await jobs.initialize_import_jobs()
        restored = jobs.get_import_job(job['id'])
        self.assertEqual(restored['status'], 'interrupted')
        self.assertEqual(restored['stats'], done['stats'])
        self.assertFalse(orphan.exists())
        self.assertEqual(len(await self.rows()), 1)

    async def test_completed_cancel_and_incremental_rescan(self):
        self.files(2)
        job = await self.start()
        done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'completed')
        self.assertEqual((await jobs.cancel_import_job(job['id']))['status'], 'completed')
        async with self.sessions() as db:
            row = (await db.scalars(select(Media))).first()
            row.is_favorited = row.is_deleted = row.is_damaged = True
            media_id = row.id
            await db.commit()
        again = await self.start()
        result = await self.finished(again['id'])
        self.assertEqual(result['stats']['added_count'], 0)
        self.assertEqual(result['stats']['existing_count'], 2)
        row = next(r for r in await self.rows() if r.id == media_id)
        self.assertTrue(row.is_favorited and row.is_deleted and row.is_damaged)
        self.assertEqual(len(list(self.media_dir.iterdir())), 2)

    async def test_cancel_during_skipped_scan(self):
        self.files(300, 'txt')
        signal = asyncio.Event()
        def progress(payload):
            if payload['stage'] == 'scanning' and payload['current'] >= 5:
                signal.set()
        async with self.sessions() as db:
            stats = await scanner.scan_directory_stats(str(self.media_dir), db, cancel=signal, progress=progress)
        self.assertLess(stats['scanned_files'], 300)
        self.assertEqual(stats['added_count'], 0)

    async def test_cancel_during_preparation(self):
        self.files(300, 'txt')
        signal = asyncio.Event()
        def progress(payload):
            if payload['stage'] == 'preparing' and payload['current']:
                signal.set()
        async with self.sessions() as db:
            stats = await scanner.scan_directory_stats(str(self.media_dir), db, cancel=signal, progress=progress)
        self.assertEqual(stats['scanned_files'], 0)

    async def test_cancel_during_commit_keeps_committed_file(self):
        self.files(3)
        signal = asyncio.Event()
        async def checkpoint(db, stats):
            signal.set()
            await db.commit()
        async with self.sessions() as db:
            stats = await scanner.scan_directory_stats(str(self.media_dir), db, cancel=signal, checkpoint=checkpoint)
        self.assertEqual(stats['added_count'], 1)
        self.assertEqual(len(await self.rows()), 1)

    async def test_failed_generation_leaves_no_partial_image(self):
        class Partial(ThumbnailStrategy):
            def generate(self, source, output):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b'incomplete')
                return False
        result = generate_thumbnail('unused', 'id', strategy=Partial(), output_dir=self.assets)
        self.assertIsNone(result)
        self.assertEqual(list(self.assets.iterdir()), [])

    async def test_graceful_shutdown_preserves_current_file_and_marks_interrupted(self):
        self.files(2, 'mp4')
        generate, entered, release, _ = self.blocking_generator()
        with patch.object(scanner, 'generate_thumbnail', generate):
            job = await self.start()
            await self.wait_event(entered)
            shutdown = asyncio.create_task(jobs.shutdown_import_jobs())
            await asyncio.sleep(.01)
            self.assertFalse(shutdown.done())
            release.set()
            await asyncio.wait_for(shutdown, 5)
        done = jobs.get_import_job(job['id'])
        self.assertEqual(done['status'], 'interrupted')
        self.assertEqual(done['stats']['added_count'], 1)

    async def test_preview_failure_waits_for_other_workers_before_cleanup(self):
        self.files(3, 'mp4')
        release = threading.Event()
        entered = threading.Event()
        self.gates.append(release)
        calls = []
        def generate(path, media_id, *, output_dir=None):
            calls.append(media_id)
            if len(calls) == 1:
                entered.wait(5)
                raise RuntimeError('injected worker failure')
            entered.set()
            release.wait(5)
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f'{media_id}.png'
            output.write_bytes(b'image')
            return str(output)
        with patch.object(scanner, 'generate_thumbnail', return_value=None), patch.object(scanner, 'generate_preview', generate):
            job = await jobs.start_import_job(dict(path=str(self.media_dir), preview=True, workers=2))
            await self.wait_event(entered)
            await asyncio.sleep(.03)
            self.assertIn(jobs.get_import_job(job['id'])['status'], jobs.ACTIVE)
            release.set()
            done = await self.finished(job['id'])
        self.assertEqual(done['status'], 'failed')
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(self.assets.rglob('*.png'))), 0)
        self.assertEqual(done['stats']['added_count'], 3)

    async def test_history_pruning_keeps_thirty_terminal_records(self):
        template = await self.start()
        await self.finished(template['id'])
        async with self.sessions() as db:
            for index in range(35):
                record = deepcopy(jobs.get_import_job(template['id']))
                record['id'] = str(uuid.uuid4())
                record['updated_at'] = f'2026-09-06T10:00:{index:02}'
                db.add(ImportJob(id=record['id'], active_slot=None, payload=record))
            await db.commit()
        await jobs.initialize_import_jobs()
        self.assertEqual(len(jobs.list_import_jobs()), 30)
        async with self.sessions() as db:
            self.assertEqual(len((await db.scalars(select(ImportJob))).all()), 30)

    async def test_http_routes_validate_and_expose_cross_device_state(self):
        import json
        from app.main import app

        async def request(method, path, body=None, query=b''):
            sent = []
            payload = json.dumps(body).encode() if body is not None else b''
            async def receive():
                return {'type': 'http.request', 'body': payload, 'more_body': False}
            async def send(message):
                sent.append(message)
            await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                       'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                       'query_string': query, 'headers': [(b'content-type', b'application/json')],
                       'server': ('testserver', 80), 'client': ('testclient', 1000), 'root_path': ''}, receive, send)
            status = next(item['status'] for item in sent if item['type'] == 'http.response.start')
            content = b''.join(item.get('body', b'') for item in sent if item['type'] == 'http.response.body')
            return status, json.loads(content)

        base = '/api/media/manage/import'
        status, _ = await request('POST', base, {'path': str(self.media_dir), 'request_id': 'invalid'})
        self.assertEqual(status, 422)
        gate = asyncio.Event()
        async def hold(*args, **kwargs):
            await gate.wait()
        with patch.object(jobs, 'scan_directory_stats', hold):
            request_id = str(uuid.uuid4())
            status, first = await request('POST', base, {'path': str(self.media_dir), 'request_id': request_id})
            self.assertEqual(status, 200)
            status, conflict = await request('POST', base, {'path': str(self.media_dir)})
            self.assertEqual(status, 409)
            self.assertEqual(conflict['detail']['job_id'], first['id'])
            status, records = await request('GET', base, query=f'request_id={request_id}'.encode())
            self.assertEqual(records[0]['id'], first['id'])
            status, cancelled = await request('POST', base + '/' + first['id'] + '/cancel')
            self.assertEqual(cancelled['status'], 'cancelling')
            status, current = await request('GET', base + '/' + first['id'])
            self.assertEqual(current['status'], 'cancelling')
            status, _ = await request('POST', base + '/missing/cancel')
            self.assertEqual(status, 404)
            gate.set()
            await self.finished(first['id'])

    async def test_persistent_checkpoint_matches_saved_rows(self):
        self.files(3)
        job = await self.start()
        done = await self.finished(job['id'])
        async with self.sessions() as db:
            record = await db.get(ImportJob, job['id'])
            self.assertEqual(record.payload['stats'], done['stats'])
            self.assertIsNone(record.active_slot)
        self.assertEqual(done['stats']['added_count'], len(await self.rows()))


if __name__ == '__main__':
    unittest.main()
