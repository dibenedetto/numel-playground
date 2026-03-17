# Numel Playground — Docker image
#
# Build:  docker build -t numel-playground .
# Run:    docker run -p 11360:11360 numel-playground
# GPU:    docker run --gpus all -p 11360:11360 numel-playground

FROM python:3.12-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency spec first (for layer caching)
COPY pyproject.toml ./
COPY README.md ./

# Install Python deps
RUN pip install --no-cache-dir -e ".[all]" 2>/dev/null || pip install --no-cache-dir -e . || true

# Copy application code
COPY app/ ./app/
COPY web/ ./web/
COPY contrib/ ./contrib/
COPY examples/ ./examples/
COPY docs/ ./docs/
COPY models/ ./models/

# Create required directories
RUN mkdir -p app/storage app/workspaces app/gallery

# Default port
ENV NUMEL_PORT=11360
EXPOSE 11360

# Health check
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:${NUMEL_PORT}/ping || exit 1

# Run
CMD ["python", "app/app.py", "--port", "11360"]
