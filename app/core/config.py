from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "LanStream"
    debug: bool = True
    database_url: str = "sqlite+aiosqlite:///./data/lanstream.db"
    media_scan_dirs: list[str] = ["./test_media"]
    supported_video_exts: set[str] = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".m4v"}
    supported_image_exts: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    feed_page_size: int = 20

    @property
    def supported_exts(self) -> set[str]:
        return self.supported_video_exts | self.supported_image_exts

    model_config = {"env_prefix": "LANSTREAM_"}


settings = Settings()

Path("./data").mkdir(exist_ok=True)
