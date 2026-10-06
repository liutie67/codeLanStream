import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import database
from app.models.availability_job import AvailabilityJob
from app.models.media import Base, Media, MediaType
from app.services import availability as availability
from app.services import availability_jobs as jobs
from app.services import disk_probe as disk
from app.services.media import browse_folders, get_feed, get_random_media, scan_directory_stats


class AvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{self.root / "test.db"}')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.patches = [patch.object(jobs, 'async_session', self.sessions),
                        patch.object(availability, 'DIRECTORY_TTL', 0)]
        for item in self.patches:
            item.start()
        disk.initialize_probes()
        availability.initialize_availability()
        await jobs.initialize_check_jobs()

    async def asyncTearDown(self):
        await jobs.shutdown_check_jobs()
        await availability.shutdown_availability()
        await disk.shutdown_probes()
        for item in reversed(self.patches):
            item.stop()
        await self.engine.dispose()
        self.temp.cleanup()

    async def add(self, name, *, exists=True, folder=None, source=None, **flags):
        directory = folder or self.source
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        if exists:
            path.write_bytes(b'media')
        async with self.sessions() as db:
            row = Media(file_path=str(path), folder=str(directory), root_dir=str(source or self.source),
                        media_type=MediaType.IMAGE, **flags)
            db.add(row)
            await db.commit()
            return row.id

    async def row(self, media_id):
        async with self.sessions() as db:
            return await db.get(Media, media_id)

    async def finish(self, job_id):
        async def wait():
            while jobs.get_check_job(job_id)['status'] in jobs.ACTIVE:
                await asyncio.sleep(.01)
            return jobs.get_check_job(job_id)
        return await asyncio.wait_for(wait(), 10)

    async def test_removed_subdirectory_hides_media_preserves_classification(self):
        folder = self.source / 'removed'
        media_id = await self.add('photo.jpg', folder=folder, is_favorited=True, is_deleted=True, is_damaged=True)
        folder.rename(self.root / 'moved')
        async with self.sessions() as db:
            feed = await get_feed(db)
            random = await get_random_media(db)
            tree = await browse_folders(db, str(self.source))
            with self.assertRaises(availability.SourceUnavailable) as error:
                await browse_folders(db, str(self.source), 'removed')
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(feed.items, [])
        self.assertEqual(random['items'], [])
        self.assertEqual(tree['folders'], [])
        row = await self.row(media_id)
        self.assertEqual(row.availability, 'missing')
        self.assertTrue(row.is_favorited and row.is_deleted and row.is_damaged)
        self.assertTrue((self.root / 'moved/photo.jpg').exists())

    async def test_missing_candidates_refill_pages_and_random_batches(self):
        for index in range(7):
            await self.add(f'{index}.jpg', exists=index >= 2)
        async with self.sessions() as db:
            first = await get_feed(db, page_size=2, sort='file_path_asc')
            second = await get_feed(db, page=2, page_size=2, sort='file_path_asc')
            last = await get_feed(db, page=3, page_size=2, sort='file_path_asc')
            random = await get_random_media(db, count=4)
        self.assertEqual([Path(item.file_path).name for item in first.items], ['2.jpg', '3.jpg'])
        self.assertTrue(first.has_next)
        self.assertEqual([Path(item.file_path).name for item in second.items], ['4.jpg', '5.jpg'])
        self.assertEqual([Path(item.file_path).name for item in last.items], ['6.jpg'])
        self.assertFalse(last.has_next)
        self.assertEqual(len(random['items']), 4)
        self.assertTrue(all(Path(item.file_path).exists() for item in random['items']))
        self.assertEqual(random['total'], 5)

    async def test_all_missing_random_ends_without_losing_records(self):
        for index in range(5):
            await self.add(f'{index}.jpg', exists=False)
        async with self.sessions() as db:
            result = await get_random_media(db, count=2)
            retained = await get_feed(db, availability='missing')
        self.assertEqual(result, {'items': [], 'total': 0})
        self.assertEqual(retained.total, 5)

    async def test_disconnected_root_is_unavailable_and_restores_same_id(self):
        media_id = await self.add('photo.jpg', is_favorited=True)
        self.source.rename(self.root / 'offline')
        async with self.sessions() as db:
            result = await browse_folders(db)
            with self.assertRaises(availability.SourceUnavailable) as error:
                await browse_folders(db, str(self.source))
        self.assertEqual(result['roots'][0]['availability'], 'unavailable')
        self.assertEqual(error.exception.status, 503)
        self.assertEqual((await self.row(media_id)).availability, 'unavailable')
        (self.root / 'offline').rename(self.source)
        async with self.sessions() as db:
            restored = await get_feed(db)
        self.assertEqual([item.id for item in restored.items], [media_id])
        self.assertTrue(restored.items[0].is_favorited)

    async def test_restore_single_missing_file_and_incremental_import_preserves_tags(self):
        media_id = await self.add('photo.jpg', exists=False, is_favorited=True, is_damaged=True)
        async with self.sessions() as db:
            self.assertEqual((await get_feed(db)).items, [])
        (self.source / 'photo.jpg').write_bytes(b'restored')
        async with self.sessions() as db:
            result = await get_feed(db)
            stats = await scan_directory_stats(str(self.source), db)
        self.assertEqual(result.items[0].id, media_id)
        self.assertEqual(stats['existing_count'], 1)
        row = await self.row(media_id)
        self.assertTrue(row.is_favorited and row.is_damaged)
        self.assertEqual(row.availability, 'available')

    async def test_missing_thumbnail_does_not_mark_source_missing(self):
        from app.api.media import get_thumbnail
        media_id = await self.add('photo.jpg')
        async with self.sessions() as db:
            row = await db.get(Media, media_id)
            row.thumbnail_path = str(self.root / 'nonexistent.jpg')
            await db.commit()
            with self.assertRaises(HTTPException) as error:
                await get_thumbnail(media_id, db)
        self.assertEqual(error.exception.status_code, 404)
        self.assertIn('缓存图片', error.exception.detail)
        self.assertNotIn('原文件', error.exception.detail)
        self.assertEqual((await self.row(media_id)).availability, 'available')

    async def test_late_probe_cannot_overwrite_newer_check_or_classification(self):
        media_id = await self.add('photo.jpg')
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(body):
            entered.set()
            await release.wait()
            return {'root': {'status': 'available'}, 'files': {path: {'status': 'missing'} for path in body['files']}}
        async with self.sessions() as db:
            record = availability.snapshot(await db.get(Media, media_id))
            with patch.object(availability, 'probe', delayed):
                task = asyncio.create_task(availability.check_records(db, [record]))
                await entered.wait()
                async with self.sessions() as newer:
                    await newer.execute(update(Media).where(Media.id == media_id).values(
                        availability='available', availability_checked_at=datetime.now(), is_favorited=True))
                    await newer.commit()
                release.set()
                await task
        row = await self.row(media_id)
        self.assertEqual(row.availability, 'available')
        self.assertTrue(row.is_favorited)

    async def test_deleted_record_is_not_resurrected_by_probe(self):
        media_id = await self.add('photo.jpg')
        async with self.sessions() as db:
            record = availability.snapshot(await db.get(Media, media_id))
            await db.delete(await db.get(Media, media_id))
            await db.commit()
            result = await availability.check_records(db, [record])
        self.assertEqual(result, [])
        self.assertIsNone(await self.row(media_id))

    async def test_index_removal_never_deletes_original_or_cached_images(self):
        media_id = await self.add('photo.jpg', is_favorited=True)
        cached = self.root / 'cover.jpg'
        cached.write_bytes(b'cached')
        async def offline(body):
            return {'root': {'status': 'unavailable'}, 'files': {path: {'status': 'unavailable'} for path in body['files']}}
        async with self.sessions() as db:
            row = await db.get(Media, media_id)
            row.thumbnail_path = str(cached)
            await db.commit()
            with patch.object(availability, 'probe', offline):
                count = await availability.remove_records(db, [media_id])
        self.assertEqual(count, 1)
        self.assertIsNone(await self.row(media_id))
        self.assertTrue((self.source / 'photo.jpg').exists())
        self.assertTrue(cached.exists())

    async def test_removal_rejects_restored_selection_atomically(self):
        missing = await self.add('missing.jpg', exists=False)
        valid = await self.add('valid.jpg')
        async with self.sessions() as db:
            with self.assertRaises(availability.SourceUnavailable) as error:
                await availability.remove_records(db, [missing, valid])
        self.assertEqual(error.exception.status, 409)
        self.assertIsNotNone(await self.row(missing))
        self.assertIsNotNone(await self.row(valid))

    async def test_full_check_and_duplicate_start_are_independent_of_imports(self):
        for index in range(5):
            await self.add(f'{index}.jpg', exists=index != 0)
        first = await jobs.start_check_job()
        duplicate = await jobs.start_check_job()
        self.assertEqual(first['id'], duplicate['id'])
        result = await self.finish(first['id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual((result['processed'], result['available'], result['missing']), (5, 4, 1))
        async with self.sessions() as db:
            persisted = await db.get(AvailabilityJob, first['id'])
            self.assertEqual(persisted.payload, result)
            self.assertIsNone(persisted.active_slot)

    async def test_completed_check_is_published_only_after_checkpoint_is_saved(self):
        await self.add('photo.jpg')
        entered, release = asyncio.Event(), asyncio.Event()
        original = jobs.persist
        async def delayed(job):
            if job['status'] == 'completed':
                entered.set()
                await release.wait()
            await original(job)
        with patch.object(jobs, 'persist', delayed):
            job = await jobs.start_check_job()
            try:
                await asyncio.wait_for(entered.wait(), 2)
                self.assertEqual(jobs.get_check_job(job['id'])['status'], 'running')
                async with self.sessions() as db:
                    self.assertEqual((await db.get(AvailabilityJob, job['id'])).payload['status'], 'running')
            finally:
                release.set()
                result = await self.finish(job['id'])
        async with self.sessions() as db:
            self.assertEqual((await db.get(AvailabilityJob, job['id'])).payload, result)

    async def test_cancel_keeps_finished_batch_and_no_more_dispatch(self):
        for index in range(5):
            await self.add(f'{index}.jpg')
        entered, release = asyncio.Event(), asyncio.Event()
        original = jobs.check_records
        async def held(db, records, **options):
            checked = await original(db, records, **options)
            entered.set()
            await release.wait()
            return checked
        with patch.object(jobs, 'BATCH_SIZE', 2), patch.object(jobs, 'check_records', held):
            job = await jobs.start_check_job()
            await entered.wait()
            await jobs.cancel_check_job(job['id'])
            release.set()
            result = await self.finish(job['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['processed'], 2)
        self.assertEqual((await jobs.cancel_check_job(job['id']))['status'], 'cancelled')

    async def test_cancel_interrupts_active_probe_without_waiting_for_slow_source(self):
        await self.add('photo.jpg')
        worker = self.root / 'stalled.py'
        worker.write_text('import time\ntime.sleep(30)\n')
        with patch.object(disk, 'WORKER', str(worker)):
            job = await jobs.start_check_job()
            async def started():
                while not disk._processes:
                    await asyncio.sleep(.005)
            await asyncio.wait_for(started(), 1)
            await jobs.cancel_check_job(job['id'])
            result = await asyncio.wait_for(self.finish(job['id']), 1)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['processed'], 0)
        self.assertEqual(len(disk._processes), 0)

    async def test_restart_marks_check_interrupted_without_erasing_progress(self):
        payload = dict(id='interrupted', status='running', message='', processed=7, total=20,
                       available=5, missing=2, unavailable=0, percent=35, error=None,
                       created_at=jobs.now(), updated_at=jobs.now())
        async with self.sessions() as db:
            db.add(AvailabilityJob(id='interrupted', active_slot='active', payload=payload))
            await db.commit()
        await jobs.initialize_check_jobs()
        result = jobs.get_check_job('interrupted')
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['processed'], 7)

    async def test_directory_cache_coalesces_requests_and_expires(self):
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', wraps=availability.probe) as tracked:
            await asyncio.gather(*(availability.probe_directories(str(self.source), [str(self.source)]) for _ in range(4)))
            await availability.probe_directories(str(self.source), [str(self.source)])
            self.assertEqual(tracked.call_count, 1)
            await availability.probe_directories(str(self.source), [str(self.source)], force=True)
            self.assertEqual(tracked.call_count, 2)

    async def test_worker_timeout_reaps_process_and_event_loop_remains_responsive(self):
        worker = self.root / 'stalled.py'
        worker.write_text('import time\ntime.sleep(30)\n')
        with patch.object(disk, 'WORKER', str(worker)), patch.object(disk, 'PROBE_TIMEOUT', .08):
            task = asyncio.create_task(disk.probe({'action': 'probe', 'root': str(self.source), 'files': ['file']}))
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            result = await asyncio.wait_for(task, 1)
        self.assertEqual(result['files']['file'], {'status': 'unavailable', 'reason': 'timeout', 'confirmed': False})
        self.assertEqual(len(disk._processes), 0)
        self.assertEqual(availability.source_error(result['root']).status, 503)

    async def test_batch_timeout_does_not_flip_records_or_allow_index_removal(self):
        ids = [await self.add(f'{index}.jpg', is_favorited=True) for index in range(3)]
        worker = self.root / 'stalled.py'
        worker.write_text('import time\ntime.sleep(30)\n')
        with patch.object(disk, 'WORKER', str(worker)), patch.object(disk, 'PROBE_TIMEOUT', .05):
            async with self.sessions() as db:
                rows = (await db.scalars(select(Media))).all()
                with self.assertRaises(availability.SourceUnavailable) as error:
                    await availability.check_records(db, [availability.snapshot(row) for row in rows])
                self.assertEqual(error.exception.status, 503)
                await availability.refresh_directories(db)
                with self.assertRaises(availability.SourceUnavailable):
                    await availability.remove_records(db, ids)
        for media_id in ids:
            row = await self.row(media_id)
            self.assertEqual(row.availability, 'available')
            self.assertIsNone(row.availability_checked_at)
            self.assertTrue(row.is_favorited)

    async def test_timed_out_root_keeps_database_state_and_other_roots_browseable(self):
        valid = await self.add('valid.jpg')
        slow_root = self.root / 'slow'
        slow_id = await self.add('slow.jpg', folder=slow_root, source=slow_root)
        original = availability.probe
        async def slow(body):
            if body.get('root') == str(slow_root):
                return disk._failed(body, 'timeout')
            return await original(body)
        with patch.object(availability, 'probe', slow):
            async with self.sessions() as db:
                result = await get_random_media(db, count=10)
                roots = await browse_folders(db)
        self.assertEqual([item.id for item in result['items']], [valid])
        self.assertEqual((await self.row(slow_id)).availability, 'available')
        self.assertEqual(next(root for root in roots['roots'] if root['path'] == str(slow_root))['availability'], 'unavailable')

    async def test_unconfirmed_check_job_reports_failure_without_mass_state_changes(self):
        media_id = await self.add('photo.jpg')
        async def timeout(body):
            return disk._failed(body, 'timeout')
        with patch.object(availability, 'probe', timeout):
            job = await jobs.start_check_job()
            result = await self.finish(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('保留原状态', result['error'])
        self.assertEqual((await self.row(media_id)).availability, 'available')

    async def test_stream_range_requests_share_feed_metadata_without_probes_or_writes(self):
        from app.api.media import stream_media
        from starlette.requests import Request
        media_id = await self.add('photo.jpg')
        request = Request({'type': 'http', 'headers': [(b'range', b'bytes=0-1')]})
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', wraps=availability.probe) as tracked:
            async with self.sessions() as db:
                await get_feed(db)
                first_checked = (await db.get(Media, media_id)).availability_checked_at
                tracked.reset_mock()
                with patch.object(db, 'execute', wraps=db.execute) as statements:
                    for _ in range(4):
                        response = await stream_media(media_id, request, db)
                        self.assertEqual(response.status_code, 206)
                        self.assertEqual(response.headers['content-range'], 'bytes 0-1/5')
                    self.assertFalse(any(str(call.args[0]).startswith('UPDATE') for call in statements.call_args_list))
                self.assertEqual(tracked.call_count, 0)
                self.assertEqual((await db.get(Media, media_id)).availability_checked_at, first_checked)

    async def test_cold_stream_uses_one_probe_and_manual_recheck_bypasses_cache(self):
        from app.api.media import stream_media
        from starlette.requests import Request
        media_id = await self.add('photo.jpg')
        request = Request({'type': 'http', 'headers': []})
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', wraps=availability.probe) as tracked:
            async with self.sessions() as db:
                response = await stream_media(media_id, request, db)
                self.assertEqual(response.headers['content-length'], '5')
                self.assertEqual(tracked.call_count, 1)
                (self.source / 'photo.jpg').unlink()
                row = await db.get(Media, media_id)
                checked = await availability.check_records(db, [availability.snapshot(row)])
                self.assertEqual(checked[0].availability, 'missing')
                self.assertEqual(tracked.call_count, 2)

    async def test_large_folder_checks_only_page_and_refills_missing_candidates(self):
        async with self.sessions() as db:
            for index in range(160):
                path = self.source / f'{index:03}.jpg'
                if index >= 2:
                    path.write_bytes(b'media')
                db.add(Media(file_path=str(path), folder=str(self.source), root_dir=str(self.source), media_type=MediaType.IMAGE))
            await db.commit()
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', wraps=availability.probe) as tracked:
            async with self.sessions() as db:
                first = await browse_folders(db, str(self.source), page_size=20)
                file_probes = [path for call in tracked.call_args_list for path in call.args[0].get('files', [])]
                self.assertLessEqual(len(file_probes), 23)
                self.assertEqual([Path(item.file_path).name for item in first['items']], [f'{i:03}.jpg' for i in range(2, 22)])
                self.assertTrue(first['has_next'])
                self.assertEqual(first['total'], 158)
                second = await browse_folders(db, str(self.source), page=2, page_size=20)
                self.assertEqual(Path(second['items'][0].file_path).name, '022.jpg')

    async def test_folder_cursor_does_not_skip_items_if_previous_page_loses_media(self):
        ids = [await self.add(f'{index}.jpg') for index in range(6)]
        async with self.sessions() as db:
            first = await browse_folders(db, str(self.source), page_size=2)
            cursor = first['items'][-1].file_path
            (self.source / '0.jpg').unlink()
            row = await db.get(Media, ids[0])
            await availability.check_records(db, [availability.snapshot(row)])
            second = await browse_folders(db, str(self.source), page=2, page_size=2, after_path=cursor)
        self.assertEqual([Path(item.file_path).name for item in second['items']], ['2.jpg', '3.jpg'])
        self.assertEqual(second['total'], 5)
        self.assertTrue(second['has_next'])

    async def test_manual_recheck_does_not_join_old_probe_or_cache_its_late_result(self):
        media_id = await self.add('photo.jpg')
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def delayed(body):
            nonlocal calls
            calls += 1
            old = calls == 1
            if old:
                entered.set()
                await release.wait()
            return {'root': {'status': 'available'}, 'files': {
                path: {'status': 'missing' if old else 'available', 'size': 5} for path in body['files']}}
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', delayed):
            async with self.sessions() as db:
                row = await db.get(Media, media_id)
                previous = asyncio.create_task(availability.check_records(db, [availability.snapshot(row)], force=False))
                await entered.wait()
                try:
                    async with self.sessions() as newer:
                        row = await newer.get(Media, media_id)
                        checked = await asyncio.wait_for(availability.check_records(newer, [availability.snapshot(row)]), 1)
                        self.assertEqual(checked[0].availability, 'available')
                finally:
                    release.set()
                    await previous
            cached = await availability.file_info(str(self.source / 'photo.jpg'), root=str(self.source))
        self.assertEqual(calls, 2)
        self.assertEqual(cached['status'], 'available')
        self.assertEqual((await self.row(media_id)).availability, 'available')

    async def test_first_page_total_includes_unchecked_legacy_records(self):
        for index in range(8):
            await self.add(f'{index}.jpg')
        async with self.sessions() as db:
            feed = await get_feed(db, page_size=2)
            random = await get_random_media(db, count=1)
        self.assertEqual(feed.total, 8)
        self.assertEqual(random['total'], 8)
        self.assertTrue(feed.has_next)

    async def test_per_path_cache_is_bounded_expires_and_reuses_overlapping_scopes(self):
        folders = [str(self.source / f'{i}') for i in range(7)]
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'CACHE_LIMIT', 4):
            await availability.probe_directories(str(self.source), folders)
            self.assertLessEqual(len(availability._cache), 4)
        availability.initialize_availability()
        with patch.object(availability, 'DIRECTORY_TTL', 5), patch.object(availability, 'probe', wraps=availability.probe) as tracked:
            await availability.probe_directories(str(self.source), folders[:3])
            await availability.probe_directories(str(self.source), folders[:2])
            self.assertEqual(tracked.call_count, 1)
        with patch.object(availability, 'DIRECTORY_TTL', 0):
            await availability.probe_directories(str(self.source), [])
            self.assertLessEqual(len(availability._cache), 1)

    async def test_worker_concurrency_is_bounded(self):
        worker = self.root / 'slow.py'
        worker.write_text('import json, sys, time\njson.load(sys.stdin)\ntime.sleep(.08)\nprint("{}")\n')
        maximum = 0
        async def sample(tasks):
            nonlocal maximum
            while any(not task.done() for task in tasks):
                maximum = max(maximum, len(disk._processes))
                await asyncio.sleep(.005)
        with patch.object(disk, 'WORKER', str(worker)):
            tasks = [asyncio.create_task(disk.probe({'action': 'probe'})) for _ in range(6)]
            await asyncio.gather(*tasks, sample(tasks))
        self.assertEqual(maximum, 2)
        self.assertEqual(len(disk._processes), 0)

    async def test_permission_errors_are_unavailable_and_directory_returns_403(self):
        from app.services.disk_worker import inspect
        with patch('os.stat', side_effect=PermissionError):
            result = inspect(str(self.source), True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(availability.source_error(result, directory=True).status, 403)

    async def test_unavailable_source_does_not_hide_other_roots(self):
        valid = await self.add('valid.jpg')
        other = self.root / 'other'
        hidden = await self.add('hidden.jpg', source=other, folder=other)
        other.rename(self.root / 'disconnected')
        async with self.sessions() as db:
            result = await get_random_media(db, count=10)
        self.assertEqual([item.id for item in result['items']], [valid])
        self.assertEqual((await self.row(hidden)).availability, 'unavailable')

    async def test_browse_deadline_returns_503_and_cancels_operation(self):
        from app.api.media import bounded
        completed = False
        async def stalled():
            nonlocal completed
            await asyncio.sleep(10)
            completed = True
        with patch('app.api.media.BROWSE_TIMEOUT', .03):
            with self.assertRaises(HTTPException) as error:
                await bounded(stalled())
        self.assertEqual(error.exception.status_code, 503)
        self.assertFalse(completed)

    async def test_migration_is_idempotent_and_preserves_old_record(self):
        legacy = create_async_engine(f'sqlite+aiosqlite:///{self.root / "legacy.db"}')
        try:
            async with legacy.begin() as conn:
                await conn.execute(text('''CREATE TABLE media (
                    id VARCHAR(36) PRIMARY KEY, file_path VARCHAR(1024) NOT NULL,
                    media_type VARCHAR(5) NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0,
                    duration FLOAT, width INTEGER, height INTEGER, folder VARCHAR(1024),
                    thumbnail_path VARCHAR(1024), is_favorited BOOLEAN NOT NULL DEFAULT 0,
                    is_deleted BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
                await conn.execute(text("INSERT INTO media (id, file_path, media_type, is_favorited, is_deleted) VALUES ('old', '/legacy/file.jpg', 'IMAGE', 1, 1)"))
            with patch.object(database, 'engine', legacy):
                await database.create_tables()
                await database.create_tables()
            async with legacy.connect() as conn:
                row = (await conn.execute(text('SELECT id, is_favorited, is_deleted, availability, availability_checked_at FROM media'))).one()
                self.assertEqual(tuple(row), ('old', 1, 1, 'available', None))
        finally:
            await legacy.dispose()

    async def test_http_routes_validate_filters_and_expose_checks(self):
        from app.main import app
        from app.core.database import get_db
        async def test_db():
            async with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db] = test_db
        async def request(method, path, body=None, query=''):
            sent = []
            async def receive():
                return {'type': 'http.request', 'body': json.dumps(body).encode() if body is not None else b'', 'more_body': False}
            async def send(message):
                sent.append(message)
            await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method,
                       'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': query.encode(),
                       'headers': [(b'content-type', b'application/json')], 'server': ('test', 80),
                       'client': ('test', 1), 'root_path': ''}, receive, send)
            status = next(item['status'] for item in sent if item['type'] == 'http.response.start')
            return status, json.loads(b''.join(item.get('body', b'') for item in sent if item['type'] == 'http.response.body'))
        try:
            media_id = await self.add('gone.jpg', exists=False, is_favorited=True)
            self.assertEqual((await request('GET', '/api/media/feed', query='availability=invalid'))[0], 422)
            status, result = await request('POST', '/api/media/manage/availability/probe', {'ids': [media_id]})
            self.assertEqual(status, 200)
            self.assertEqual(result[0]['availability'], 'missing')
            self.assertTrue(result[0]['is_favorited'])
            status, result = await request('GET', '/api/media/feed', query='availability=missing')
            self.assertEqual((status, result['total']), (200, 1))
            status, job = await request('POST', '/api/media/manage/availability/check')
            self.assertEqual(status, 200)
            await self.finish(job['id'])
            self.assertEqual((await request('GET', '/api/media/manage/availability/check/' + job['id']))[1]['status'], 'completed')
            status, _ = await request('GET', '/api/media/browse', query=f'root_dir={self.source}&subdir=../')
            self.assertEqual(status, 400)
            status, result = await request('POST', '/api/media/manage/availability/remove-records', {'ids': [media_id]})
            self.assertEqual((status, result['removed_count']), (200, 1))
        finally:
            app.dependency_overrides.pop(get_db, None)
