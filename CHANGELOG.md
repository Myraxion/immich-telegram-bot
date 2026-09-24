# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-09-24

### Added
- **Dynamic File Naming**: Configurable file naming rules via `MEDIA_NAME_TEMPLATE` (default: `{source}_{message_id}_{index}`) for photos/videos and `DOCUMENT_NAME_TEMPLATE` (default: `{original_name}`) for documents.
- **Dynamic Album Routing**: Configurable target album resolution via `ALBUM_NAME_TEMPLATE`, automatically routing media into dynamically named Immich albums with fallback to `ALBUM_NAME`.
- **Rich Metadata Variables**:
  - Smart fallback variables: `{source}`, `{source_id}`, `{source_username}` / `{username}`, `{message_id}`, `{date}`.
  - Explicit variables: `{msg_date}`, `{forward_date}`, `{exif_date}`, `{sender}`, `{media_type}`, `{file_unique_id}`, `{media_group_id}`, `{caption}`, `{index}`, etc.
- **Timezone Awareness (`TZ`)**: Integrated `TZ` environment configuration (default `UTC`, e.g. `Asia/Shanghai`) converting all date/timestamp metadata to local timezone.
- **Fault-Tolerant Formatting**: Three-level error fallback ensuring unknown variables and malformed templates safely degrade to defaults without interrupting ingestion.
- **Batch Collision Disambiguation**: Deterministic collision avoidance algorithm preventing duplicate filenames in media groups or batch transfers.
- **Immich Album Caching**: Added in-memory album cache in `ImmichClient` to reduce redundant album lookup and creation requests.
- **Domain Modeling & ADR 0002**: Recorded architectural decisions in `docs/adr/0002-dynamic-naming-and-album-routing.md` and expanded `CONTEXT.md`.

## [0.1.1] - 2026-09-24


### Added
- **`IngestionPipeline` Deep Module**: Consolidated deduplication, archive handling, EXIF metadata extraction, Immich asset creation, and album grouping behind a single batch interface.
- **End-to-End Pipeline Tests**: Added comprehensive test suite in `tests/test_pipeline.py` covering deduplication, archive extraction, partial error isolation, and idempotent retry semantics.
- **Domain Modeling & ADR**: Added `CONTEXT.md` domain language glossary and `docs/adr/0001-consolidate-ingestion-pipeline.md`.
- **Type Checking Support**: Added `[tool.mypy]` configuration with `pydantic.mypy` plugin in `pyproject.toml`.

### Changed
- **Thin Adapter Architecture**: Refactored `bot.py` into a thin transport adapter, removing scattered state management and album API calls.
- **Strict Idempotency**: Messages are only marked as processed when all media items succeed; partial failures can be safely retried without re-uploading cached files.
- **Album Soft Degradation**: Failures in adding assets to an album now emit a warning without failing already uploaded library assets.

### Fixed
- **Windows Path Compatibility**: Fixed invalid colon in mock tokens in `tests/test_bot.py`.
- **Empty Archive Handling**: Archives with no recognized media are now correctly marked as processed.

## [0.1.0] - 2026-09-24

### Added
- Initial scaffold for Immich Telegram bot.
- Support for uploading photos, videos, audio, voice, video notes, and documents.
- Automatic archive extraction (zip, rar, 7z, tar) using `bsdtar`.
- Media group (album) debounce aggregation.
- SHA-1 content deduplication and SQLite state persistence.
- Local Telegram Bot API support for up to 2 GB files.
