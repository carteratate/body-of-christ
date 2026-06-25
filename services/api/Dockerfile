FROM python:3.11-slim

# Run as non-root user
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Pre-download BGE cross-encoder weights so the first request isn't blocked
# downloading ~1GB from HuggingFace. Weights are baked into this image layer.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"

COPY app/ app/

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health')"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
