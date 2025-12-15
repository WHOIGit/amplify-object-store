FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUTH_TOKENS_FILE=/app/tokens.json \
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

# Copy dependency files and source code
COPY pyproject.toml README.md src/ ./

# Install the package with deploy extras
RUN pip install --no-cache-dir .[deploy]

# Remove git now that dependencies are installed
RUN apt-get purge -y --auto-remove git && \
    rm -rf /var/lib/apt/lists/*

# Expose port
EXPOSE 8000

# Start server
CMD uvicorn objectstore.app:app \
    --host ${HOST} \
    --port ${PORT} \
    --workers ${WORKERS} \
    --log-level ${LOG_LEVEL}
