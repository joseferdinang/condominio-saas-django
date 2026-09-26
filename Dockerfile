# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        fonts-dejavu-core \
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
RUN pip install --requirement requirements/base.txt

FROM base AS development

COPY requirements/development.txt requirements/development.txt
RUN pip install --requirement requirements/development.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS production

ENV DJANGO_SETTINGS_MODULE=config.settings.production \
    XDG_CACHE_HOME=/tmp/.cache

COPY requirements/production.txt requirements/production.txt
RUN pip install --requirement requirements/production.txt

COPY . .

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/staticfiles /app/media \
    && chown app:app /app/staticfiles /app/media

USER 10001:10001

EXPOSE 8000

CMD ["gunicorn", "--config", "config/gunicorn.conf.py", "config.wsgi:application"]
