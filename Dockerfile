
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY Bot.py market_data.py paper_ledger.py ./
COPY tests/ ./tests/

RUN python -m unittest discover -s tests -v

CMD ["sh", "-c", "test \"$RAILWAY_VOLUME_MOUNT_PATH\" = /data || { echo 'ERROR: Attach a Railway volume at /data before running.'; exit 1; }; exec python -u Bot.py --interval 120 --state /data/ledger.json"]
