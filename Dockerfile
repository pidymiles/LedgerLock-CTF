FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/ledgerlock.db \
    PORT=5000

RUN groupadd --system ledgerlock \
    && useradd --system --gid ledgerlock --home-dir /app ledgerlock \
    && mkdir -p /app/static /data \
    && chown -R ledgerlock:ledgerlock /app /data

WORKDIR /app
COPY --chown=ledgerlock:ledgerlock app.py manage.py ./
COPY --chown=ledgerlock:ledgerlock static ./static

USER ledgerlock
EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2)"

CMD ["python", "app.py"]
