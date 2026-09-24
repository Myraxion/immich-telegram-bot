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
