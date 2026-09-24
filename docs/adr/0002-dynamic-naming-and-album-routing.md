# Dynamic File Naming and Album Routing from Message Metadata

We introduce dynamic naming templates (`MEDIA_NAME_TEMPLATE`, `DOCUMENT_NAME_TEMPLATE`, `ALBUM_NAME_TEMPLATE`) driven by normalized `MessageMetadata` extracted from inbound Telegram messages.

Previously, Telegram Bot API compressed photos and videos were saved with non-descriptive names (`file_0.jpg`), and all uploaded assets were assigned to a single static `ALBUM_NAME`. Document files retained their original names without formatting flexibility.

By extracting normalized metadata (channel/chat titles, smart author attribution, smart source and message identifiers, and timezone-aware dates), templates evaluate safe file stems without extensions and dynamically route assets to Immich albums:
- `MEDIA_NAME_TEMPLATE` formats compressed photos, videos, and media notes (defaulting to `{source}_{message_id}_{index}`).
- `DOCUMENT_NAME_TEMPLATE` formats document payloads (defaulting to `{original_name}`).
- `ALBUM_NAME_TEMPLATE` resolves target albums dynamically, grouping multi-asset batches by album and falling back to `ALBUM_NAME`.
- `TZ` configures local timezone conversion for all timestamp variables (`{date}`, `{msg_date}`, `{forward_date}`, `{exif_date}`).
- Smart variables (`{source}`, `{source_id}`, `{source_username}`, `{message_id}`, `{date}`) gracefully fallback from forwarded origins to local message contexts.
- Explicit variables (`{media_type}`, `{file_unique_id}`, `{media_group_id}`, `{caption}`, `{exif_date}`, `{original_name}`, etc.) allow fine-grained customization.
- Template evaluations use safe formatters that substitute unrecognized variables with empty values and fallback to default templates upon formatting errors.
- Extension retention, illegal character sanitization, and batch deduplication ensure clean filenames and seamless library ingestion.



