# ShopSathi backend: ONE image that runs as the API, the Celery worker or the Celery beat scheduler, chosen by the command
# (see docker-entrypoint.sh). The AI engine is installed into it (it is a separate package; it never imports the backend).
#
# Build from the REPOSITORY ROOT, because the image needs ai_engine/ and database/seed/ as well:
#     docker build -f backend/Dockerfile -t shopsathi-backend .
#
# No secret is baked in: every setting comes from environment variables at run time (backend/.env.example).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Same folder layout as the repository: the code finds database/seed/ relative to backend/app/.
WORKDIR /srv/shopsathi

# 1. dependencies first (cached until a requirements file changes). pytest/respx are test tools: not installed here.
COPY backend/requirements.txt backend/requirements.txt
COPY ai_engine ai_engine
RUN grep -Ev '^(-e|pytest|respx)' backend/requirements.txt > /tmp/requirements.runtime.txt \
 && pip install -r /tmp/requirements.runtime.txt \
 && pip install "./ai_engine[llm]" \
 && rm -rf ai_engine/tests

# 2. the application
COPY backend/alembic.ini backend/alembic.ini
COPY backend/alembic backend/alembic
COPY backend/app backend/app
COPY backend/docker-entrypoint.sh backend/docker-entrypoint.sh
COPY database/seed database/seed

# 3. run as a normal user; product photos live on a volume at /data/media
RUN useradd --system --uid 10001 --home-dir /srv/shopsathi --shell /usr/sbin/nologin shopsathi \
 && mkdir -p /data/media \
 && chown -R shopsathi:shopsathi /data /srv/shopsathi \
 && chmod +x backend/docker-entrypoint.sh
USER shopsathi
WORKDIR /srv/shopsathi/backend
ENV MEDIA_ROOT=/data/media \
    PORT=8000
VOLUME ["/data/media"]
EXPOSE 8000

# Healthy = the API answers /api/v1/health with 200 (it answers 503 when the database or Redis is down).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
