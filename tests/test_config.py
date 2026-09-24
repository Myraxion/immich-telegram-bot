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



def test_default_naming_and_timezone_settings(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    settings = Settings(_env_file=None)
    assert settings.tz == "UTC"
    assert settings.media_name_template == "{source}_{message_id}_{index}"
    assert settings.document_name_template == "{original_name}"
    assert settings.album_name_template == ""


def test_custom_naming_and_timezone_settings(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    monkeypatch.setenv("MEDIA_NAME_TEMPLATE", "{date:%Y%m%d}_{source}_{index}")
    monkeypatch.setenv("DOCUMENT_NAME_TEMPLATE", "{source}_{original_name}")
    monkeypatch.setenv("ALBUM_NAME_TEMPLATE", "{source}")

    settings = Settings(_env_file=None)
    assert settings.tz == "Asia/Shanghai"
    assert settings.media_name_template == "{date:%Y%m%d}_{source}_{index}"
    assert settings.document_name_template == "{source}_{original_name}"
    assert settings.album_name_template == "{source}"


def test_invalid_timezone_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("TZ", "Invalid/Timezone_Name")
    with pytest.raises(ValueError, match="Invalid timezone"):
        Settings(_env_file=None)

