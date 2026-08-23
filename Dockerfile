FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Set non-sensitive environment variables
ARG APP_ENV=production

ENV APP_ENV=${APP_ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && pip install --upgrade pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first to leverage Docker cache
COPY pyproject.toml .
# --python 3.14 pins uv to the image's own system interpreter instead of
# downloading a separate uv-managed standalone build, which was leaving the
# venv pointing at a Python install that didn't exist at container runtime
# (ModuleNotFoundError: No module named 'encodings').
RUN uv venv --python 3.14 && . .venv/bin/activate && uv pip install -e .

# Copy the application
COPY . .

# Create log directory and non-root user
RUN mkdir -p /app/logs \
    && useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default port
EXPOSE 8000

# Command to run the application
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
