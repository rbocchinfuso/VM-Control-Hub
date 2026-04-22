#!/bin/sh
set -e

echo "Initializing database..."
python init_db.py

echo "Starting vCenter Manager..."
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers ${WORKERS:-4} \
    --worker-class sync \
    --timeout 120 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    run:app
