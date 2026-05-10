"""扫描指定目录的媒体文件并写入数据库。

用法: uv run python scripts/scan_mock.py [目录路径]
"""

import asyncio
import sys

from app.core.config import settings
from app.core.database import async_session, create_tables
from app.services.media import scan_directory


async def main():
    await create_tables()

    dirs = sys.argv[1:] if len(sys.argv) > 1 else settings.media_scan_dirs

    async with async_session() as db:
        for d in dirs:
            print(f"扫描目录: {d}")
            count = await scan_directory(d, db)
            print(f"  新增 {count} 个媒体文件")


if __name__ == "__main__":
    asyncio.run(main())
