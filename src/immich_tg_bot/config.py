import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .i18n import SUPPORTED_LANGUAGES


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
    allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    album_name: str | None = None
    album_name_template: str = ""
    media_name_template: str = "{source}_{message_id}_{index}"
    document_name_template: str = "{original_name}"
    tz: str = "UTC"
    default_language: str = "en"

    max_archive_mb: int = 2000
    max_archive_files: int = 1000
    log_level: str = "INFO"

    data_dir: Path = Path("/data")
    tg_files_dir: Path = Path("/var/lib/telegram-bot-api")
    tg_api_base: str = "http://telegram-bot-api:8081"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _parse_user_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            try:
                decoded = json.loads(v)
            except json.JSONDecodeError:
                v = v.split(",")
            else:
                v = decoded if isinstance(decoded, list) else [decoded]
        if not isinstance(v, list):
            raise ValueError("allowed_user_ids must be a comma-separated list or JSON array")
        return [int(x) for x in v if str(x).strip()]

    @field_validator("immich_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("tz")
    @classmethod
    def _validate_tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Invalid timezone: {v}") from e
        return v

    @field_validator("default_language")
    @classmethod
    def _validate_default_language(cls, v: str) -> str:
        lang = v.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            supported_str = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(f"Invalid default_language: {v!r}. Must be one of: {supported_str}")
        return lang
