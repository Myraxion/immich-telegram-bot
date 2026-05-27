import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from .archives import extract, walk_media
from .immich import ImmichClient, sha1_file
from .state import State

log = logging.getLogger(__name__)

DEVICE_ID = "immich-telegram-bot"

# EXIF tag IDs
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


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


async def upload_one(
    *,
    file_path: Path,
    device_asset_id: str,
    fallback_created_at: datetime,
    immich: ImmichClient,
    state: State,
) -> tuple[str, str]:
    """Upload a single file. Returns (status, asset_id).

    Status values: 'created' | 'duplicate' | 'cached'.
    """
    checksum = await asyncio.to_thread(sha1_file, file_path)
    cached = await state.asset_for_sha1(checksum)
    if cached:
        return "cached", cached

    created_at = _exif_datetime(file_path) or fallback_created_at
    modified_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)

    result = await immich.upload_asset(
        file_path=file_path,
        device_asset_id=device_asset_id,
        device_id=DEVICE_ID,
        file_created_at=created_at,
        file_modified_at=modified_at,
        checksum=checksum,
    )
    asset_id = result["id"]
    status = result.get("status", "created")
    await state.cache_sha1(checksum, asset_id)
    return status, asset_id


async def process_file(
    *,
    local_path: Path,
    is_archive_flag: bool,
    device_asset_prefix: str,
    fallback_created_at: datetime,
    immich: ImmichClient,
    state: State,
    max_archive_files: int,
) -> list[tuple[str, str]]:
    """Process one file or one archive. Returns list of (status, asset_id)."""
    results: list[tuple[str, str]] = []
    if is_archive_flag:
        with tempfile.TemporaryDirectory(prefix="tg-archive-") as tmpdir:
            tmp = Path(tmpdir)
            try:
                await extract(local_path, tmp)
            except Exception as e:
                log.exception("Extraction failed for %s", local_path)
                results.append(("error", f"extract: {e}"))
                return results

            media = walk_media(tmp, max_archive_files)
            if not media:
                log.info("Archive %s contained no recognised media", local_path)
                return results

            for i, m in enumerate(media):
                try:
                    r = await upload_one(
                        file_path=m,
                        device_asset_id=f"{device_asset_prefix}:{i}:{m.name}",
                        fallback_created_at=fallback_created_at,
                        immich=immich,
                        state=state,
                    )
                    results.append(r)
                except Exception as e:
                    log.exception("Upload failed for %s", m)
                    results.append(("error", str(e)))
    else:
        try:
            r = await upload_one(
                file_path=local_path,
                device_asset_id=device_asset_prefix,
                fallback_created_at=fallback_created_at,
                immich=immich,
                state=state,
            )
            results.append(r)
        except Exception as e:
            log.exception("Upload failed for %s", local_path)
            results.append(("error", str(e)))
    return results
