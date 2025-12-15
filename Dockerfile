FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUTH_TOKENS_FILE=/data/tokens.json \
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=1 \
    LOG_LEVEL=info

# Install git temporarily for GitHub dependency, then install packages and clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    pip install --no-cache-dir --upgrade pip && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files and README (needed for package build)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .[deploy]

# Copy application code
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir .

# Remove git now that dependencies are installed
RUN apt-get purge -y --auto-remove git && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and data directory
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /app /data

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Start server
CMD uvicorn objectstore.app:app \
    --host ${HOST} \
    --port ${PORT} \
    --workers ${WORKERS} \
    --log-level ${LOG_LEVEL}
