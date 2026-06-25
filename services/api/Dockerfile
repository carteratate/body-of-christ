FROM python:3.11-slim

# Run as non-root user
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

USER appuser

# Pre-download BGE cross-encoder weights as appuser so the cache path at
# build time (/home/appuser/.cache/huggingface/) matches the runtime path.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health')"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
