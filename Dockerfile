FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create volume mount point for persistent SQLite
RUN mkdir -p /data

# Collect static files
ENV SECRET_KEY=build-time-only
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
