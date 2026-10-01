#!/bin/sh
# Starts one ShopSathi backend component. Usage: docker run shopsathi-backend <command>
#
#   api      (default) run the database migrations, then the web API
#   worker   Celery worker: answers customers' Messenger messages with the AI
#   beat     Celery beat: the weekly AI summary schedule (run exactly ONE)
#   migrate  only run the database migrations and exit
#   cli ...  the management commands, e.g.  cli create-admin --email you@example.com   |   cli seed
#
# Settings are environment variables (see backend/.env.example). RUN_MIGRATIONS=false skips the migrations of `api`.
set -eu

wait_for_migrations() {
  tries=0
  until alembic upgrade head; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
      echo "The database migrations failed 30 times: giving up." >&2
      exit 1
    fi
    echo "Database not ready yet (attempt $tries of 30); trying again in 3 seconds ..." >&2
    sleep 3
  done
}

cmd="${1:-api}"
[ "$#" -gt 0 ] && shift

case "$cmd" in
  api)
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then wait_for_migrations; fi
    # No --reload and no debug mode. Forwarded headers are handled by the app (TRUSTED_PROXIES), not by uvicorn.
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers --workers "${WEB_CONCURRENCY:-1}" "$@"
    ;;
  worker)
    # A thread pool: the AI replies wait for the network, so many fit in one process (docs/TEST_REPORT.md).
    exec celery -A app.workers.celery_app worker --pool=threads --concurrency="${WORKER_CONCURRENCY:-50}" \
      --hostname="worker@%h" --loglevel="${LOG_LEVEL:-info}" "$@"
    ;;
  beat)
    exec celery -A app.workers.celery_app beat --schedule=/tmp/celerybeat-schedule --loglevel="${LOG_LEVEL:-info}" "$@"
    ;;
  migrate)
    wait_for_migrations
    ;;
  cli)
    exec python -m app.cli "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
