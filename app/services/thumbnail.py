"""视频封面生成服务。

当前实现：ffmpeg 提取第一帧。
后续可扩展其他策略（等间距拼接、AI关键帧等）。
"""

import logging
import subprocess
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path("./data/thumbnails")
PREVIEW_DIR = Path("./data/previews")
IMPORT_ASSET_DIR = Path("./data/import-assets")


class ThumbnailStrategy(ABC):
    @abstractmethod
    def generate(self, video_path: str, output_path: Path) -> bool:
        ...


class FirstFrameStrategy(ThumbnailStrategy):
    """提取视频第一帧作为封面。"""

    def generate(self, video_path: str, output_path: Path) -> bool:
        if not Path(video_path).exists():
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", "0",
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                str(output_path),
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=30,
            )
            if result.returncode == 0 and output_path.exists():
                return True
            logger.warning("ffmpeg failed for %s: %s", video_path, result.stderr.decode()[:200])
            return False
        except FileNotFoundError:
            logger.warning("ffmpeg not found, skip thumbnail generation")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg timeout for %s", video_path)
            return False


class GridPreviewStrategy(ThumbnailStrategy):
    """使用 video_preview 包生成 4x4 网格预览图。"""

    def generate(self, video_path: str, output_path: Path) -> bool:
        if not Path(video_path).exists():
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from video_preview import generate_video_preview
            generate_video_preview(
                video_path=video_path,
                output_path=str(output_path),
                rows=4,
                cols=4,
                preview_width=1980,
            )
            return output_path.exists()
        except Exception as e:
            logger.warning("Grid preview failed for %s: %s", video_path, str(e)[:200])
            return False


DEFAULT_STRATEGY = FirstFrameStrategy()
GRID_STRATEGY = GridPreviewStrategy()


def generate_thumbnail(
    video_path: str,
    media_id: str,
    strategy: ThumbnailStrategy | None = None,
    *,
    output_dir: Path | None = None,
) -> str | None:
    """为视频生成封面，返回封面路径或 None。"""
    strat = strategy or DEFAULT_STRATEGY
    output_path = (output_dir or THUMBNAIL_DIR) / f"{media_id}.jpg"
    if output_path.exists():
        return str(output_path)
    return _generate_atomic(strat, video_path, output_path)


def generate_preview(
    video_path: str,
    media_id: str,
    *,
    output_dir: Path | None = None,
) -> str | None:
    """为视频生成 4x4 网格预览图，返回路径或 None。"""
    output_path = (output_dir or PREVIEW_DIR) / f"{media_id}.png"
    if output_path.exists():
        return str(output_path)
    return _generate_atomic(GRID_STRATEGY, video_path, output_path)


def _generate_atomic(strategy: ThumbnailStrategy, video_path: str, output_path: Path) -> str | None:
    temporary = output_path.with_name(f".{output_path.stem}-{uuid.uuid4().hex}.tmp{output_path.suffix}")
    try:
        if strategy.generate(video_path, temporary) and temporary.exists():
            # Each import owns its output directory; never replace a prior artifact.
            if not output_path.exists():
                temporary.replace(output_path)
            return str(output_path)
        return None
    finally:
        temporary.unlink(missing_ok=True)
