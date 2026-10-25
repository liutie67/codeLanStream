import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.media import Base, Media, MediaType
from app.services import media as service


class PurgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lanstream-purge-")
        self.root = Path(self.temp.name)
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{self.root / "test.db"}')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp.cleanup()

    async def add_media(self, name, *, deleted=True, assets=False):
        source = self.root / f"{name}.mp4"
        source.write_bytes(b"test video")
        values = dict(id=name, file_path=str(source), media_type=MediaType.VIDEO,
                      is_deleted=deleted)
        if assets:
            for field, suffix in (("thumbnail_path", ".jpg"), ("preview_path", ".png")):
                asset = self.root / f"{name}{suffix}"
                asset.write_bytes(b"test image")
                values[field] = str(asset)
        async with self.sessions() as db:
            media = Media(**values)
            db.add(media)
            await db.commit()
        return media

    async def purge(self):
        async with self.sessions() as db:
            return await service.purge_deleted(db)

    async def remaining_ids(self):
        async with self.sessions() as db:
            return set((await db.scalars(select(Media.id))).all())

    async def test_removes_source_and_assets_but_keeps_unmarked_media(self):
        deleted = await self.add_media("deleted", assets=True)
        active = await self.add_media("active", deleted=False, assets=True)

        result = await self.purge()

        self.assertEqual(result.model_dump(), dict(deleted_count=1, failed_count=0, failures=[],
                                                   unprocessed_count=0))
        self.assertEqual(await self.remaining_ids(), {"active"})
        for field in ("file_path", "thumbnail_path", "preview_path"):
            self.assertFalse(Path(getattr(deleted, field)).exists())
            self.assertTrue(Path(getattr(active, field)).exists())

    async def test_missing_files_are_already_deleted(self):
        media = await self.add_media("missing", assets=True)
        for field in ("file_path", "thumbnail_path", "preview_path"):
            Path(getattr(media, field)).unlink()

        self.assertEqual((await self.purge()).deleted_count, 1)
        self.assertEqual(await self.remaining_ids(), set())
        self.assertEqual((await self.purge()).deleted_count, 0)

    async def test_permission_failure_keeps_record_and_assets_and_continues(self):
        blocked = await self.add_media("blocked", assets=True)
        await self.add_media("other", assets=True)
        remove = service._unlink_purge_file

        def deny_one(path):
            if path == blocked.file_path:
                raise PermissionError(errno.EACCES, "Access denied", path)
            remove(path)

        with patch.object(service, "_unlink_purge_file", side_effect=deny_one):
            result = await self.purge()

        self.assertEqual((result.deleted_count, result.failed_count), (1, 1))
        self.assertEqual(result.failures[0].file_path, blocked.file_path)
        self.assertIn("删除权限", result.failures[0].error)
        self.assertEqual(await self.remaining_ids(), {"blocked"})
        for field in ("file_path", "thumbnail_path", "preview_path"):
            self.assertTrue(Path(getattr(blocked, field)).exists())
        self.assertEqual((await self.purge()).deleted_count, 1)

    async def test_asset_failure_keeps_record_until_retry_finishes_cleanup(self):
        media = await self.add_media("asset", assets=True)
        remove = service._unlink_purge_file

        def deny_asset(path):
            if path == media.thumbnail_path:
                raise PermissionError(errno.EACCES, "Access denied", path)
            remove(path)

        with patch.object(service, "_unlink_purge_file", side_effect=deny_asset):
            result = await self.purge()

        self.assertEqual((result.deleted_count, result.failed_count), (0, 1))
        self.assertEqual(result.failures[0].file_path, media.thumbnail_path)
        self.assertFalse(Path(media.file_path).exists())
        self.assertTrue(Path(media.preview_path).exists())
        self.assertEqual(await self.remaining_ids(), {"asset"})
        self.assertEqual((await self.purge()).deleted_count, 1)
        self.assertFalse(Path(media.preview_path).exists())

    async def test_non_permission_io_error_is_reported_and_other_files_continue(self):
        media = await self.add_media("io-error")
        await self.add_media("other")
        remove = service._unlink_purge_file

        def fail_one(path):
            if path == media.file_path:
                raise OSError(errno.EIO, "I/O error", path)
            remove(path)

        with patch.object(service, "_unlink_purge_file", side_effect=fail_one):
            result = await self.purge()

        self.assertEqual((result.deleted_count, result.failed_count), (1, 1))
        self.assertIn("I/O error", result.failures[0].error)
        self.assertEqual(await self.remaining_ids(), {"io-error"})

    async def test_default_limit_stops_after_ten_failures(self):
        for index in range(15):
            await self.add_media(f"blocked-{index:02}", assets=True)
        error = PermissionError(errno.EACCES, "Access denied")

        with patch.object(service, "_unlink_purge_file", side_effect=error) as remove:
            result = await self.purge()

        self.assertEqual(remove.call_count, 10)
        self.assertEqual((result.deleted_count, result.failed_count, result.unprocessed_count), (0, 10, 5))
        self.assertEqual(len(result.failures), 10)
        self.assertEqual(len(await self.remaining_ids()), 15)
        # Failure at the source must leave every source and asset intact.
        self.assertEqual(len(list(self.root.glob("*.mp4"))), 15)
        self.assertEqual(len(list(self.root.glob("*.jpg"))), 15)
        self.assertEqual(len(list(self.root.glob("*.png"))), 15)

    async def test_failure_limit_is_cumulative_and_commits_prior_success(self):
        records = [await self.add_media(f"item-{index}") for index in range(4)]
        remove = service._unlink_purge_file
        attempts = []

        def alternate_failures(path):
            attempts.append(path)
            if len(attempts) in {1, 3}:
                raise PermissionError(errno.EACCES, "Access denied", path)
            remove(path)

        with patch.object(service.settings, "purge_failure_limit", 2), \
                patch.object(service, "_unlink_purge_file", side_effect=alternate_failures):
            result = await self.purge()

        self.assertEqual(len(attempts), 3)
        self.assertEqual((result.deleted_count, result.failed_count, result.unprocessed_count), (1, 2, 1))
        self.assertEqual(len(result.failures), 2)
        remaining = await self.remaining_ids()
        self.assertEqual(len(remaining), 3)
        for media in records:
            self.assertEqual(Path(media.file_path).exists(), media.id in remaining)
        self.assertFalse(Path(attempts[1]).exists())
        # After the error is fixed, failed and unprocessed records can be retried.
        self.assertEqual((await self.purge()).deleted_count, 3)
        self.assertEqual(await self.remaining_ids(), set())

    async def test_limit_on_last_item_does_not_report_unprocessed_files(self):
        await self.add_media("blocked")
        with patch.object(service.settings, "purge_failure_limit", 1), \
                patch.object(service, "_unlink_purge_file", side_effect=PermissionError(errno.EACCES, "Access denied")):
            result = await self.purge()
        self.assertEqual((result.failed_count, result.unprocessed_count), (1, 0))

    def test_permission_error_advice_matches_platform(self):
        error = PermissionError(errno.EACCES, "Access denied")
        with patch.object(service, "os", SimpleNamespace(name="posix")):
            message = service._purge_error_message(error)
            self.assertIn("删除权限", message)
            self.assertNotIn("占用", message)
        with patch.object(service, "os", SimpleNamespace(name="nt")):
            self.assertIn("占用", service._purge_error_message(error))

    @unittest.skipUnless(os.name == "nt", "Windows read-only attribute")
    async def test_windows_read_only_file_is_removed(self):
        media = await self.add_media("read-only", assets=True)
        paths = [media.file_path, media.thumbnail_path, media.preview_path]
        try:
            for path in paths:
                os.chmod(path, stat.S_IREAD)
            result = await self.purge()
            self.assertEqual((result.deleted_count, result.failed_count), (1, 0))
            self.assertEqual(await self.remaining_ids(), set())
        finally:
            for path in paths:
                if Path(path).exists():
                    os.chmod(path, stat.S_IWRITE)

    @unittest.skipUnless(os.name == "nt", "Windows sharing violation")
    async def test_windows_open_file_is_kept_and_can_be_retried_after_close(self):
        media = await self.add_media("open", assets=True)
        await self.add_media("other")
        with open(media.file_path, "rb"):
            result = await self.purge()
        self.assertEqual((result.deleted_count, result.failed_count), (1, 1))
        self.assertIn("占用", result.failures[0].error)
        self.assertEqual(await self.remaining_ids(), {"open"})
        self.assertTrue(Path(media.thumbnail_path).exists())
        self.assertEqual((await self.purge()).deleted_count, 1)

    @unittest.skipUnless(os.name == "nt", "Windows read-only and sharing violation")
    async def test_windows_failed_delete_restores_read_only_attribute(self):
        media = await self.add_media("read-only-open")
        try:
            os.chmod(media.file_path, stat.S_IREAD)
            with open(media.file_path, "rb"):
                result = await self.purge()
            self.assertEqual(result.failed_count, 1)
            self.assertTrue(os.stat(media.file_path).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
            self.assertEqual((await self.purge()).deleted_count, 1)
        finally:
            if Path(media.file_path).exists():
                os.chmod(media.file_path, stat.S_IWRITE)

    @unittest.skipUnless(os.name == "nt", "Windows sharing violation retry")
    async def test_windows_transient_lock_is_retried(self):
        media = await self.add_media("transient")
        error = PermissionError(errno.EACCES, "Sharing violation", media.file_path)
        error.winerror = 32
        remove = service._unlink_purge_file
        calls = 0

        def release_on_third_try(path):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise error
            remove(path)

        with patch.object(service, "_unlink_purge_file", side_effect=release_on_third_try):
            result = await self.purge()

        self.assertEqual(calls, 3)
        self.assertEqual((result.deleted_count, result.failed_count), (1, 0))


if __name__ == "__main__":
    unittest.main()
