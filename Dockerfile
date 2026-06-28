FROM python:3.15.0b3-alpine3.24 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	EXPORTER_PORT=9163 \
	LOG_LEVEL=INFO \
	SCRAPE_INTERVAL=86400 \
	EDF_CHOSEN_DAY=wednesday

WORKDIR /app

COPY requirements.txt parse_edf.py /app/

RUN pip install --no-cache-dir -r requirements.txt && \
	adduser -D -u 1001 exporter && \
	chown -R exporter:exporter /app

USER exporter
EXPOSE ${EXPORTER_PORT}
CMD ["python", "parse_edf.py"]
