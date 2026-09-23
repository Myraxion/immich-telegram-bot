import pytest

from immich_tg_bot.config import Settings


@pytest.fixture
def required_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("IMMICH_URL", "https://immich.example/api")
    monkeypatch.setenv("IMMICH_API_KEY", "key")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1643423542,6111406923", [1643423542, 6111406923]),
        ("[123,456]", [123, 456]),
    ],
)
def test_allowed_user_ids_accepts_csv_and_json(
    monkeypatch: pytest.MonkeyPatch,
    required_settings_env: None,
    value: str,
    expected: list[int],
) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", value)

    settings = Settings(_env_file=None)

    assert settings.allowed_user_ids == expected
