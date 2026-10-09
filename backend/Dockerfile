# syntax=docker/dockerfile:1
# One image runs all three processes (API, Celery worker, Celery beat); the start
# command decides which. See docs/deployment.md.

# ---- build stage: install dependencies into a virtualenv --------------------
FROM python:3.14-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- runtime stage: only the venv and the app, running as a non-root user ----
FROM python:3.14-slim
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

# Default process: the API. uvicorn's own proxy-header handling is switched off on
# purpose: with a wildcard allow-list it believes whatever X-Forwarded-For says, which
# lets callers fake their IP. The app reads the header itself and only trusts the number
# of proxies set in TRUSTED_PROXY_HOPS (see app/core/client_ip.py).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
