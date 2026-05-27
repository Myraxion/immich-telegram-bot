from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str
    telegram_api_id: int
    telegram_api_hash: str
    immich_url: str
    immich_api_key: str
    allowed_user_ids: list[int] = Field(default_factory=list)

    album_name: str | None = None
    max_archive_mb: int = 2000
    max_archive_files: int = 1000
    log_level: str = "INFO"

    data_dir: Path = Path("/data")
    tg_files_dir: Path = Path("/var/lib/telegram-bot-api")
    tg_api_base: str = "http://telegram-bot-api:8081"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _split_user_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("immich_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")
