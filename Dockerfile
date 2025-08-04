FROM python:3.12.8-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VENV_IN_PROJECT=1
ENV POETRY_CACHE_DIR=/tmp/poetry_cache
ENV PORT=8080

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && apt-get dist-upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Set work directory
WORKDIR /app

# Copy poetry files
COPY pyproject.toml poetry.lock ./

# Install dependencies and gunicorn
RUN poetry install --only=main && \
    poetry add gunicorn && \
    rm -rf $POETRY_CACHE_DIR

# Copy project
COPY . .

# Collect static files
RUN poetry run python manage.py collectstatic --noinput || true

# Create a non-root user
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

EXPOSE $PORT

# Start server with gunicorn for production
CMD ["sh", "-c", "poetry run gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 politiekmatcher.wsgi:application"]
