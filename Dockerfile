FROM python:3.15-slim AS builder

WORKDIR /hover-dns-updater

ENV POETRY_NO_INTERACTION=1 \
  POETRY_VERSION=2.5.2

RUN pip install "poetry==$POETRY_VERSION" && python -m venv /opt/venv

ENV VIRTUAL_ENV=/opt/venv \
  PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml poetry.lock README.md hover-dns-updater.py hover-update.cfg ./
COPY src ./src
RUN poetry install --only main --no-interaction --no-ansi

FROM builder AS testing

# git is required by the release script tests.
RUN apt-get update \
  && apt-get install -y --no-install-recommends git \
  && rm -rf /var/lib/apt/lists/*

RUN poetry install --no-interaction --no-ansi

COPY INSTALL.sh hover-dns-updater.service ./
COPY scripts ./scripts
COPY tests ./tests

CMD ["python", "-m", "pytest", "tests/", "--cov-fail-under=80"]

FROM python:3.15-slim AS production

WORKDIR /hover-dns-updater

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  VIRTUAL_ENV=/opt/venv \
  PATH="/opt/venv/bin:$PATH" \
  NAME=hover-dns-updater \
  HOVER_HEALTHCHECK_FILE=/tmp/hover-dns-updater-health

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /hover-dns-updater/hover-dns-updater.py /hover-dns-updater/hover-update.cfg ./
COPY --from=builder /hover-dns-updater/src ./src

CMD ["python", "hover-dns-updater.py", "--service"]
