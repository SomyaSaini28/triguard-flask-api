FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --shell /usr/sbin/nologin triguard \
    && mkdir -p /app/outputs/audit \
    && chown -R triguard:triguard /app

USER triguard
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import os; from urllib.request import urlopen; urlopen(f\"http://127.0.0.1:{os.getenv('PORT', '8000')}/health\", timeout=3)" || exit 1

CMD ["sh", "-c", "gunicorn --workers ${WEB_CONCURRENCY:-1} --threads 4 --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile - --timeout 60 api.main:app"]
