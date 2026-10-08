# ======== STAGE 1: Build dependencies ========
FROM python:3.13-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Use the image's Python instead of letting uv download one
ENV UV_PYTHON_DOWNLOADS=never

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv

# Set workdir and copy dependency files
WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install runtime dependencies into /app/.venv (no dev/test groups)
RUN uv sync --frozen --no-default-groups

# Set GIT_HASH environment variable and write to file using build-arg
ARG GIT_HASH=unknown
RUN echo "GIT_HASH=$(echo $GIT_HASH | cut -c1-7)" > /app/.git_hash

# ======== STAGE 2: Runtime image ========
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gettext \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy the virtualenv from builder and put it first on PATH
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy project files
COPY . .

# Copy .git_hash from builder
COPY --from=builder /app/.git_hash /app/.git_hash

# Set GIT_HASH environment variable
RUN echo "export $(cat /app/.git_hash | xargs)" >> /etc/environment

# Collect static files
RUN python manage.py collectstatic --noinput

# Compile translation messages
RUN python manage.py compilemessages

# Expose port
EXPOSE 8000

# Health check hits the app's own /health/ endpoint (checks DB + cache)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/', timeout=3).status == 200 else 1)"

# Start Django app using gunicorn, running migrations first
CMD ["/bin/sh", "-c", "export $(cat /app/.git_hash | xargs) && python manage.py migrate --noinput && exec gunicorn tcgptracker.wsgi:application --bind 0.0.0.0:8000"]
