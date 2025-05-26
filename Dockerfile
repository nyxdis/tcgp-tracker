# ======== STAGE 1: Build dependencies ========
FROM python:3.13-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies and Poetry
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Set workdir and copy poetry files
WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev, no root package)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root --only=main

# ======== STAGE 2: Runtime image ========
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gettext \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (for manage.py/compilemessages if needed)
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Set workdir
WORKDIR /app

# Copy installed site-packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput --settings tcgptracker.settings.development

# Compile translation messages
RUN python manage.py compilemessages --settings tcgptracker.settings.development

# Expose port
EXPOSE 8000

# Start Django app using gunicorn
CMD ["gunicorn", "tcgptracker.wsgi:application", "--bind", "0.0.0.0:8000"]
