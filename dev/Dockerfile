# Dev toolbox — Poetry deps, Django, Google Drive client, pytest (no host install)
FROM python:3.12-slim

ARG POETRY_VERSION=2.2.1

ENV POETRY_VERSION=${POETRY_VERSION} \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace \
    DJANGO_SETTINGS_MODULE=pdfding.core.settings

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /workspace

# Dependency layer (cached until lockfile changes)
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --with dev

# Application source
COPY . .

WORKDIR /workspace/pdfding

CMD ["bash"]
