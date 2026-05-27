import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from .archives import is_archive
from .config import Settings
from .immich import ImmichClient
from .pipeline import process_file
from .state import State

log = logging.getLogger(__name__)

_MEDIA_GROUP_DEBOUNCE = 1.5


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None or user.id not in self.allowed:
            log.info(
                "Ignoring message from non-whitelisted user id=%s username=%s",
                user.id if user else None,
                user.username if user else None,
            )
            return None
        return await handler(event, data)


def _file_id_for(message: Message) -> str | None:
    if message.document:
        return message.document.file_id
    if message.video:
        return message.video.file_id
    if message.animation:
        return message.animation.file_id
    if message.audio:
        return message.audio.file_id
    if message.voice:
        return message.voice.file_id
    if message.video_note:
        return message.video_note.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


def _is_archive_message(message: Message) -> bool:
    if message.document and message.document.file_name:
        return is_archive(message.document.file_name)
    return False


async def _resolve_local_path(
    bot: Bot, file_id: str, tg_files_dir: Path
) -> Path:
    """In local Bot API mode, file.file_path is an absolute server-side filesystem
    path. The volume is mounted into our container at the same path, so we read
    it directly."""
    tg_file = await bot.get_file(file_id)
    if tg_file.file_path is None:
        raise FileNotFoundError("Telegram returned no file_path")
    fp = Path(tg_file.file_path)
    if fp.is_absolute() and fp.exists():
        return fp
    # Fallback: try resolving relative to the shared mount.
    candidate = tg_files_dir / fp.name
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot locate downloaded file: {tg_file.file_path}")


async def run_bot(settings: Settings) -> None:
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.tg_api_base, is_local=True),
    )
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    state = State(settings.data_dir / "state.sqlite")
    await state.open()

    immich = ImmichClient(base_url=settings.immich_url, api_key=settings.immich_api_key)

    album_id: str | None = None
    if settings.album_name:
        try:
            album_id = await immich.get_or_create_album(settings.album_name)
            log.info("Using Immich album %r (id=%s)", settings.album_name, album_id)
        except Exception as e:
            log.warning(
                "Could not resolve album %r (%s) — uploads will go to library only",
                settings.album_name,
                e,
            )

    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware(set(settings.allowed_user_ids)))

    groups: dict[str, list[Message]] = {}
    group_tasks: dict[str, asyncio.Task[None]] = {}
    group_lock = asyncio.Lock()

    async def _process_one(message: Message) -> tuple[int, int, int, list[str]]:
        """Returns (uploaded, duplicates, errors, new_asset_ids)."""
        file_id = _file_id_for(message)
        if not file_id:
            return 0, 0, 0, []

        if await state.already_processed(message.chat.id, message.message_id):
            return 0, 1, 0, []

        try:
            local = await _resolve_local_path(bot, file_id, settings.tg_files_dir)
        except Exception as e:
            log.exception("Could not get file for message %s", message.message_id)
            with suppress(Exception):
                await message.reply(f"⚠️ Не удалось получить файл: {e}")
            return 0, 0, 1, []

        archive_flag = _is_archive_message(message)
        device_asset_prefix = f"telegram:{message.chat.id}:{message.message_id}"
        fallback_dt = (
            message.date.astimezone(timezone.utc)
            if message.date
            else datetime.now(timezone.utc)
        )

        results = await process_file(
            local_path=local,
            is_archive_flag=archive_flag,
            device_asset_prefix=device_asset_prefix,
            fallback_created_at=fallback_dt,
            immich=immich,
            state=state,
            max_archive_files=settings.max_archive_files,
        )
        await state.mark_processed(
            message.chat.id, message.message_id, 0, "done", None
        )

        uploaded = duplicates = errors = 0
        new_ids: list[str] = []
        for status, asset_id in results:
            if status == "created":
                uploaded += 1
                new_ids.append(asset_id)
            elif status in ("duplicate", "cached"):
                duplicates += 1
            else:
                errors += 1
        return uploaded, duplicates, errors, new_ids

    async def _process_messages(messages: list[Message]) -> None:
        uploaded = duplicates = errors = 0
        new_ids: list[str] = []
        for m in messages:
            u, d, e, ids = await _process_one(m)
            uploaded += u
            duplicates += d
            errors += e
            new_ids.extend(ids)

        if album_id and new_ids:
            try:
                await immich.add_to_album(album_id, new_ids)
            except Exception as e:
                log.warning("Failed to add %d asset(s) to album: %s", len(new_ids), e)

        head = messages[0]
        if errors and not uploaded and not duplicates:
            await head.reply(f"⚠️ Ошибок: {errors}")
        elif errors:
            await head.reply(
                f"⚠️ Загружено: {uploaded}, дубликатов: {duplicates}, ошибок: {errors}"
            )
        elif duplicates and not uploaded:
            await head.reply(f"♻️ Уже в Immich (дубликатов: {duplicates})")
        elif duplicates:
            await head.reply(f"✅ Загружено: {uploaded}, дубликатов: {duplicates}")
        elif uploaded:
            await head.reply(f"✅ Загружено: {uploaded}")
        else:
            await head.reply("ℹ️ В этом сообщении не нашлось медиа для загрузки.")

    async def _flush_group(mg_id: str) -> None:
        try:
            await asyncio.sleep(_MEDIA_GROUP_DEBOUNCE)
        except asyncio.CancelledError:
            return
        async with group_lock:
            messages = groups.pop(mg_id, [])
            group_tasks.pop(mg_id, None)
        if messages:
            messages.sort(key=lambda m: m.message_id)
            await _process_messages(messages)

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.reply(
            "👋 Привет! Пересылай мне фото, видео, файлы и архивы — "
            "и я залью их в твой Immich.\n\n"
            "Фото лучше отправлять <b>как файл / Document</b>, чтобы сохранить "
            "EXIF и оригинальное качество."
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.reply(
            "Что я умею:\n"
            "• photo / video / animation / voice / audio / video_note\n"
            "• document (фото, видео, любой файл)\n"
            "• архивы zip / rar / 7z / tar — распаковываю и заливаю медиа\n"
            "• media group (альбомы до 10 файлов) — обрабатываю вместе\n\n"
            "Дубликаты определяются по SHA1 — повторная отправка безопасна."
        )

    media_filter = (
        F.photo
        | F.video
        | F.document
        | F.animation
        | F.audio
        | F.voice
        | F.video_note
    )

    @dp.message(media_filter)
    async def on_media(message: Message) -> None:
        if message.media_group_id:
            async with group_lock:
                groups.setdefault(message.media_group_id, []).append(message)
                existing = group_tasks.get(message.media_group_id)
                if existing:
                    existing.cancel()
                group_tasks[message.media_group_id] = asyncio.create_task(
                    _flush_group(message.media_group_id)
                )
            return
        await _process_messages([message])

    log.info(
        "Bot starting (allowed users: %s, album: %s, immich: %s)",
        settings.allowed_user_ids,
        settings.album_name,
        settings.immich_url,
    )
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        # Drain any pending media-group flushes
        for task in list(group_tasks.values()):
            task.cancel()
        await immich.aclose()
        await state.close()
        await bot.session.close()
