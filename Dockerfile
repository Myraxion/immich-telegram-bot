FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libarchive-tools \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /data
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TG_FILES_DIR=/var/lib/telegram-bot-api \
    TG_API_BASE=http://telegram-bot-api:8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -m immich_tg_bot.healthcheck || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "immich_tg_bot"]
