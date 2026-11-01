FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ATLAS_DATA_DIR=/data

WORKDIR /app

# Runtime dependencies resolve to wheels on slim images; no build toolchain needed.
COPY pyproject.toml README.md ./
COPY atlas ./atlas
COPY datasets ./datasets
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /data \
    && chown -R atlas:atlas /app /data
USER atlas

EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=4s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["atlas", "--host", "0.0.0.0", "--port", "8080"]
