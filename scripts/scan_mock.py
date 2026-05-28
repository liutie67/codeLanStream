"""扫描指定目录的媒体文件并写入数据库。

用法: uv run python scripts/scan_mock.py [--preview] [目录路径]
"""

import argparse
import asyncio

from app.core.config import settings
from app.core.database import async_session, create_tables
from app.services.media import scan_directory


async def main():
    await create_tables()

    parser = argparse.ArgumentParser(description="扫描媒体文件")
    parser.add_argument("dirs", nargs="*", default=settings.media_scan_dirs, help="扫描目录")
    parser.add_argument("--preview", action="store_true", help="同时生成4x4网格预览图")
    args = parser.parse_args()

    async with async_session() as db:
        for d in args.dirs:
            print(f"扫描目录: {d}")
            if args.preview:
                print("  (含网格预览图生成)")
            count = await scan_directory(d, db, preview=args.preview)
            print(f"  新增 {count} 个媒体文件")


if __name__ == "__main__":
    asyncio.run(main())
