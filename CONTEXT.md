# Immich Telegram Bot

Telegram bot that ingests forwarded photos, videos, documents, and archives into a self-hosted Immich instance.

## Language

### Ingestion

**IngestItem**:
A single inbound file or media payload designated for upload.
_Avoid_: UploadTask, Job, FileMessage

**IngestionPipeline**:
The pipeline coordinating end-to-end asset ingestion, metadata resolution, deduplication, and album association.
_Avoid_: IngestionService, Uploader, ProcessingManager

**IngestSummary**:
The aggregated status outcome of a processed batch of ingestion items.
_Avoid_: UploadResult, ProcessResponse

**Deduplication**:
The two-phase identity and content verification ensuring assets and messages are not uploaded repeatedly.
_Avoid_: DedupCheck, Filter

### Naming and Organization

**NamingTemplate**:
A parameterized template string resolved against message metadata to generate human-readable file stems or album names.
_Avoid_: FilePattern, NameFormat, Rule

**MessageMetadata**:
The normalized context extracted from a Telegram message (sender, chat, forward origin, timestamp, caption, index) used for dynamic naming and album routing.
_Avoid_: TelegramContext, OriginInfo, MessageData

**AlbumRouting**:
The dynamic resolution of target Immich albums evaluated per ingestion item, with batch grouping and static fallback.
_Avoid_: AlbumMapping, FolderDispatch

### Localization

**LanguagePreference**:
The resolved target language tag ('en', 'zh', 'ja', 'ru') derived from Telegram message sender metadata and default configuration, used to select localized reply messages.
_Avoid_: UserLanguage, LocaleSetting, MessageLanguage
