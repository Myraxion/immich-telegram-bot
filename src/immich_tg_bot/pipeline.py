import asyncio
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from .archives import extract, is_archive, walk_media
from .immich import ImmichClient, sha1_file
from .state import State

log = logging.getLogger(__name__)

DEVICE_ID = "immich-telegram-bot"

# EXIF tag IDs
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


@dataclass(frozen=True)
class IngestItem:
    chat_id: int
    message_id: int
    local_path: Path
    file_name: str
    created_at: datetime


@dataclass
class IngestSummary:
    uploaded: int = 0
    duplicates: int = 0
    errors: int = 0
    new_asset_ids: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)


def _exif_datetime(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    for tag in (_EXIF_DATETIME_ORIGINAL, _EXIF_DATETIME):
        raw = exif.get(tag)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


class IngestionPipeline:
    def __init__(
        self,
        immich: ImmichClient,
        state: State,
        album_id: str | None = None,
        max_archive_files: int = 1000,
        device_id: str = DEVICE_ID,
    ) -> None:
        self._immich = immich
        self._state = state
        self._album_id = album_id
        self._max_archive_files = max_archive_files
        self._device_id = device_id

    async def ingest(self, items: Sequence[IngestItem]) -> IngestSummary:
        summary = IngestSummary()
        if not items:
            return summary

        for item in items:
            await self._ingest_item(item, summary)

        if self._album_id and summary.new_asset_ids:
            try:
                await self._immich.add_to_album(self._album_id, summary.new_asset_ids)
            except Exception as e:
                log.warning(
                    "Failed to add %d asset(s) to album %s: %s",
                    len(summary.new_asset_ids),
                    self._album_id,
                    e,
                )

        return summary

    async def _ingest_item(self, item: IngestItem, summary: IngestSummary) -> None:
        # 1. 消息级去重
        if await self._state.already_processed(item.chat_id, item.message_id):
            summary.duplicates += 1
            return

        # 2. 单文件 vs 归档展开
        item_errors: list[str] = []
        item_new_ids: list[str] = []

        prefix = f"telegram:{item.chat_id}:{item.message_id}"

        if is_archive(item.file_name):
            with tempfile.TemporaryDirectory(prefix="tg-archive-") as tmpdir:
                tmp = Path(tmpdir)
                try:
                    await extract(item.local_path, tmp)
                except Exception as e:
                    log.exception("Extraction failed for %s", item.local_path)
                    err = f"extract: {e}"
                    summary.errors += 1
                    summary.error_messages.append(err)
                    item_errors.append(err)
                    return

                media = walk_media(tmp, self._max_archive_files)
                if not media:
                    log.info("Archive %s contained no recognised media", item.local_path)
                    await self._state.mark_processed(item.chat_id, item.message_id, 0, "done", None)
                    return

                for i, m in enumerate(media):
                    await self._dispatch_upload(
                        file_path=m,
                        device_asset_id=f"{prefix}:{i}:{m.name}",
                        created_at=item.created_at,
                        summary=summary,
                        item_new_ids=item_new_ids,
                        item_errors=item_errors,
                    )
        else:
            await self._dispatch_upload(
                file_path=item.local_path,
                device_asset_id=prefix,
                created_at=item.created_at,
                summary=summary,
                item_new_ids=item_new_ids,
                item_errors=item_errors,
            )

        # 3. 严格成功标记：若无错误，标记消息已完成
        if not item_errors:
            await self._state.mark_processed(item.chat_id, item.message_id, 0, "done", None)

    async def _dispatch_upload(
        self,
        *,
        file_path: Path,
        device_asset_id: str,
        created_at: datetime,
        summary: IngestSummary,
        item_new_ids: list[str],
        item_errors: list[str],
    ) -> None:
        try:
            status, asset_id = await self._upload_one(
                file_path=file_path,
                device_asset_id=device_asset_id,
                fallback_created_at=created_at,
            )
            if status == "created":
                summary.uploaded += 1
                summary.new_asset_ids.append(asset_id)
                item_new_ids.append(asset_id)
            elif status in ("duplicate", "cached"):
                summary.duplicates += 1
        except Exception as e:
            log.exception("Upload failed for %s", file_path)
            err = str(e)
            summary.errors += 1
            summary.error_messages.append(err)
            item_errors.append(err)

    async def _upload_one(
        self,
        *,
        file_path: Path,
        device_asset_id: str,
        fallback_created_at: datetime,
    ) -> tuple[str, str]:
        checksum = await asyncio.to_thread(sha1_file, file_path)
        cached = await self._state.asset_for_sha1(checksum)
        if cached:
            return "cached", cached

        created_at = _exif_datetime(file_path) or fallback_created_at
        modified_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)

        result = await self._immich.upload_asset(
            file_path=file_path,
            device_asset_id=device_asset_id,
            device_id=self._device_id,
            file_created_at=created_at,
            file_modified_at=modified_at,
            checksum=checksum,
        )
        asset_id = result["id"]
        status = result.get("status", "created")
        await self._state.cache_sha1(checksum, asset_id)
        return status, asset_id
