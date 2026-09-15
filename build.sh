#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput

# Create default admin if no users exist
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'forgelore.settings')
django.setup()
from django.contrib.auth.models import User
if not User.objects.exists():
    User.objects.create_superuser('admin', 'admin@lumen.app', os.environ.get('ADMIN_PASSWORD', 'lumen2026'))
    print('Created default admin user')
"
