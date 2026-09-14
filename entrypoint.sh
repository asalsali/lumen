#!/bin/bash
set -e

# Use /data for persistent storage if it exists (Fly volumes)
if [ -d /data ]; then
    export DATABASE_DIR=/data
    # Symlink db.sqlite3 to persistent volume
    if [ ! -f /data/db.sqlite3 ]; then
        cp /app/db.sqlite3 /data/db.sqlite3 2>/dev/null || true
    fi
    ln -sf /data/db.sqlite3 /app/db.sqlite3
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

echo "Creating default superuser if needed..."
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'forgelore.settings')
django.setup()
from django.contrib.auth.models import User
if not User.objects.exists():
    User.objects.create_superuser('admin', 'admin@lumen.app', os.getenv('ADMIN_PASSWORD', 'lumen2026'))
    print('Created default admin user')
else:
    print('Users exist, skipping')
" 2>/dev/null || true

echo "Starting Gunicorn..."
exec gunicorn forgelore.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 180 \
    --access-logfile - \
    --error-logfile -
