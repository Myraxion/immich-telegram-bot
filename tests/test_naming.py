from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from immich_tg_bot.naming import (
    MessageMetadata,
    disambiguate_filenames,
    extract_metadata,
    render_stem,
    resolve_album_name,
    resolve_filename,
    sanitize_stem,
)


def test_sanitize_stem_replaces_illegal_characters_and_trims() -> None:
    raw = '  /bad:name*with?illegal"chars<and>pipes|and\nnewlines  '
    assert sanitize_stem(raw) == "bad_name_with_illegal_chars_and_pipes_and_newlines"


def test_sanitize_stem_collapses_multiple_underscores() -> None:
    raw = "hello____world__test"
    assert sanitize_stem(raw) == "hello_world_test"


def test_render_stem_smart_variables_channel_forward() -> None:
    tz = ZoneInfo("Asia/Shanghai")
    fwd_dt = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)  # 20:00 in Shanghai
    meta = MessageMetadata(
        source="MyChannel",
        source_id="-1001234567890",
        source_username="my_channel",
        message_id="108",
        date=fwd_dt.astimezone(tz),
        sender="Alice",
        index=1,
        msg_date=datetime(2026, 9, 24, 13, 0, 0, tzinfo=tz),
        forward_date=fwd_dt.astimezone(tz),
        media_type="photo",
        file_unique_id="AQAD1234",
    )

    template = "{source}_{message_id}_{index}"
    assert render_stem(template, meta) == "MyChannel_108_1"

    date_template = "{date:%Y%m%d_%H%M%S}_{username}_{media_type}"
    assert render_stem(date_template, meta) == "20260924_200000_my_channel_photo"


def test_render_stem_explicit_msg_date_ignores_forward_date() -> None:
    tz = ZoneInfo("UTC")
    meta = MessageMetadata(
        source="Channel",
        source_id="123",
        source_username="ch",
        message_id="999",
        date=datetime(2021, 1, 1, 0, 0, 0, tzinfo=tz),  # old forward date
        sender="Bob",
        index=1,
        msg_date=datetime(2026, 9, 24, 15, 30, 0, tzinfo=tz),  # current send date
    )
    template = "{msg_date:%Y%m%d}_{source}_{index}"
    assert render_stem(template, meta) == "20260924_Channel_1"


def test_render_stem_safe_handling_of_missing_and_none_variables() -> None:
    meta = MessageMetadata(
        source="DM_User",
        source_id="456",
        source_username="",
        message_id="12",
        date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
        sender="DM_User",
        index=1,
        msg_date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
        forward_date=None,  # Not a forward
        exif_date=None,
    )
    # forward_date with format specifier should safely evaluate to empty string, not crash
    template = "{forward_date:%Y%m%d}_{source}_{unknown_var}_{index}"
    assert render_stem(template, meta) == "DM_User_1"


def test_render_stem_falls_back_on_malformed_syntax_or_type_error() -> None:
    meta = MessageMetadata(
        source="MySource",
        source_id="1",
        source_username="src",
        message_id="55",
        date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
        sender="Sender",
        index=1,
        msg_date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
    )
    # Invalid specifier for string
    broken_template = "{source:%Y%m%d}_{message_id}"
    default_template = "{source}_{message_id}_{index}"
    assert render_stem(broken_template, meta, default_template=default_template) == "MySource_55_1"


def test_resolve_filename_appends_extension() -> None:
    meta = MessageMetadata(
        source="Channel",
        source_id="1",
        source_username="ch",
        message_id="42",
        date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
        sender="Sender",
        index=1,
        msg_date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
    )
    res = resolve_filename("{source}_{message_id}_{index}", meta, ".jpg", "{source}_{index}")
    assert res == "Channel_42_1.jpg"


def test_resolve_album_name_returns_rendered_or_fallback() -> None:
    meta = MessageMetadata(
        source="Awesome_Wallpapers",
        source_id="1",
        source_username="awesome",
        message_id="42",
        date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
        sender="Sender",
        index=1,
        msg_date=datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC),
    )
    assert resolve_album_name("{source}", meta, fallback_album="Default") == "Awesome_Wallpapers"
    assert resolve_album_name("", meta, fallback_album="Default") == "Default"
    assert resolve_album_name("{unknown_var}", meta, fallback_album="Default") == "Default"


def test_disambiguate_filenames_handles_duplicates() -> None:
    items = ["photo.jpg", "photo.jpg", "other.png", "photo.jpg"]
    disambiguated = disambiguate_filenames(items)
    assert disambiguated == ["photo_1.jpg", "photo_2.jpg", "other.png", "photo_3.jpg"]


def test_disambiguate_filenames_prevents_secondary_collisions() -> None:
    items = ["photo.jpg", "photo.jpg", "photo_1.jpg"]
    disambiguated = disambiguate_filenames(items)
    assert len(set(disambiguated)) == 3
    assert "photo_1.jpg" in disambiguated



def test_extract_metadata_from_aiogram_channel_forward() -> None:
    tz = ZoneInfo("Asia/Shanghai")
    message = MagicMock()
    message.chat.id = 1001
    message.chat.title = "DirectChat"
    message.message_id = 999
    message.date = datetime(2026, 9, 24, 10, 0, 0, tzinfo=UTC)
    message.from_user.full_name = "Forwarder"
    message.from_user.id = 555
    message.from_user.username = "forwarder_user"
    message.caption = "Beautiful view!\nLine 2"
    message.media_group_id = "group_123"

    # Forward origin: Channel
    origin = MagicMock()
    origin.type = "channel"
    origin.date = datetime(2026, 9, 24, 8, 0, 0, tzinfo=UTC)
    origin.chat.title = "Nature Channel"
    origin.chat.id = -1009999999
    origin.chat.username = "nature_ch"
    origin.message_id = 77
    origin.author_signature = "Photographer"
    message.forward_origin = origin

    meta = extract_metadata(
        message,
        target_tz=tz,
        index=2,
        file_unique_id="uniq_abc",
        media_type="photo",
    )

    assert meta.source == "Nature Channel"
    assert meta.source_id == "-1009999999"
    assert meta.source_username == "nature_ch"
    assert meta.message_id == "77"
    assert meta.sender == "Forwarder"
    assert meta.index == 2
    assert meta.media_type == "photo"
    assert meta.file_unique_id == "uniq_abc"
    assert meta.media_group_id == "group_123"
    assert meta.caption == "Beautiful view!_Line 2"

    assert meta.forward_author == "Photographer"
    # Date should be origin date converted to Asia/Shanghai (8:00 UTC -> 16:00 UTC+8)
    assert meta.date.hour == 16
    # msg_date should be message date converted to Asia/Shanghai (10:00 UTC -> 18:00 UTC+8)
    assert meta.msg_date is not None
    assert meta.msg_date.hour == 18

