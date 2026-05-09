"""视频封面生成服务。

当前实现：ffmpeg 提取第一帧。
后续可扩展其他策略（等间距拼接、AI关键帧等）。
"""

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path("./data/thumbnails")


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


# 后续可扩展：
# class GridStrategy(ThumbnailStrategy):
#     """等间距取9/16帧拼接成封面。"""
#     def generate(self, video_path, output_path): ...

# class AIKeyFrameStrategy(ThumbnailStrategy):
#     """AI 抓取关键帧作为封面。"""
#     def generate(self, video_path, output_path): ...


DEFAULT_STRATEGY = FirstFrameStrategy()


def generate_thumbnail(
    video_path: str,
    media_id: str,
    strategy: ThumbnailStrategy | None = None,
) -> str | None:
    """为视频生成封面，返回封面路径或 None。"""
    strat = strategy or DEFAULT_STRATEGY
    output_path = THUMBNAIL_DIR / f"{media_id}.webp"
    if output_path.exists():
        return str(output_path)
    if strat.generate(video_path, output_path):
        return str(output_path)
    return None
