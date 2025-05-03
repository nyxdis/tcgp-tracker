FROM python:3.12-alpine

# Install system dependencies
RUN apk update && apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev \
    build-base \
    python3-dev \
    libpq \
    jpeg-dev \
    zlib-dev \
    tzdata \
    && pip install --upgrade pip

# Set timezone (optional, gut für logging)
ENV TZ=Europe/Berlin

# Create working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Set environment variable for production settings
ENV DJANGO_SETTINGS_MODULE=tcgptracker.settings.production

# Start Django app using gunicorn
CMD ["gunicorn", "tcgptracker.wsgi:application", "--bind", "0.0.0.0:8000"]
