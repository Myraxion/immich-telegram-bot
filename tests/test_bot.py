from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from aiogram import Bot

from immich_tg_bot.bot import _resolve_local_path


class FakeBot:
    def __init__(self, token: str, file_path: str | None) -> None:
        self.token = token
        self.file_path = file_path

    async def get_file(self, file_id: str) -> SimpleNamespace:
        return SimpleNamespace(file_path=self.file_path)


@pytest.mark.asyncio
async def test_resolve_local_path_uses_per_bot_directory(tmp_path: Path) -> None:
    token = "123:token"
    expected = tmp_path / token / "photos" / "file_1.jpg"
    expected.parent.mkdir(parents=True)
    expected.touch()

    bot = cast(Bot, FakeBot(token, "photos/file_1.jpg"))
    actual = await _resolve_local_path(bot, "file-id", tmp_path)

    assert actual == expected
