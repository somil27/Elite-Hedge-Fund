#!/bin/bash
# Start Celery worker in the background
celery -A worker.celery_app worker --loglevel=info &

# Start Uvicorn in the foreground
# Render passes the $PORT environment variable automatically
uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
