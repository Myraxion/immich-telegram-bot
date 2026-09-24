import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from .config import Settings
from .immich import ImmichClient
from .pipeline import IngestionPipeline, IngestItem
from .state import State

log = logging.getLogger(__name__)

_MEDIA_GROUP_DEBOUNCE = 1.5


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
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


async def _resolve_local_path(bot: Bot, file_id: str, tg_files_dir: Path) -> Path:
    """Locate a file exposed by the local Bot API through the shared volume."""
    tg_file = await bot.get_file(file_id)
    if tg_file.file_path is None:
        raise FileNotFoundError("Telegram returned no file_path")
    fp = Path(tg_file.file_path)
    if fp.is_absolute() and fp.exists():
        return fp
    # Relative paths are rooted at the local Bot API's per-bot work directory.
    candidate = tg_files_dir / bot.token / fp
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot locate downloaded file: {tg_file.file_path}")


async def _extract_ingest_item(bot: Bot, message: Message, tg_files_dir: Path) -> IngestItem | None:
    file_id = _file_id_for(message)
    if not file_id:
        return None
    local = await _resolve_local_path(bot, file_id, tg_files_dir)
    file_name = (message.document and message.document.file_name) or local.name
    fallback_dt = message.date.astimezone(UTC) if message.date else datetime.now(UTC)
    return IngestItem(
        chat_id=message.chat.id,
        message_id=message.message_id,
        local_path=local,
        file_name=file_name,
        created_at=fallback_dt,
    )


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

    pipeline = IngestionPipeline(
        immich=immich,
        state=state,
        album_id=album_id,
        max_archive_files=settings.max_archive_files,
    )

    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware(set(settings.allowed_user_ids)))

    groups: dict[str, list[Message]] = {}
    group_tasks: dict[str, asyncio.Task[None]] = {}
    group_lock = asyncio.Lock()

    async def _process_messages(messages: list[Message]) -> None:
        items: list[IngestItem] = []
        resolve_errors = 0
        for m in messages:
            try:
                item = await _extract_ingest_item(bot, m, settings.tg_files_dir)
                if item:
                    items.append(item)
            except Exception as e:
                log.exception("Could not get file for message %s", m.message_id)
                with suppress(Exception):
                    await m.reply(f"⚠️ Не удалось получить файл: {e}")
                resolve_errors += 1

        summary = await pipeline.ingest(items)
        uploaded = summary.uploaded
        duplicates = summary.duplicates
        errors = summary.errors + resolve_errors

        head = messages[0]
        if errors and not uploaded and not duplicates:
            await head.reply(f"⚠️ Ошибок: {errors}")
        elif errors:
            await head.reply(f"⚠️ Загружено: {uploaded}, дубликатов: {duplicates}, ошибок: {errors}")
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

    media_filter = F.photo | F.video | F.document | F.animation | F.audio | F.voice | F.video_note

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
