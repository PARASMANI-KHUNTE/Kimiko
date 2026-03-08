# ── Build stage ──
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install package
RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ──
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ src/
COPY alembic.ini .
COPY alembic/ alembic/

# Create non-root user
RUN useradd --create-home kimiko
USER kimiko

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "kimiko.main:app", \
    "--host", "0.0.0.0", "--port", "8000", \
    "--workers", "1", "--loop", "uvloop"]
