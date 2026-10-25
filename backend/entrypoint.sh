#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py purge_assistant_history
python manage.py collectstatic --noinput
if [ "${DEMO_MODE:-false}" = "true" ]; then
    python manage.py seed_demo
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 90
