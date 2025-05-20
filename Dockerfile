# ======== STAGE 1: Build dependencies ========
FROM python:3.13-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set workdir and copy requirements
WORKDIR /app
COPY requirements.txt .

# Create virtualenv and install dependencies
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r requirements.txt

# ======== STAGE 2: Runtime image ========
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Set path to use virtualenv
ENV PATH="/opt/venv/bin:$PATH"

# Set workdir
WORKDIR /app

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
