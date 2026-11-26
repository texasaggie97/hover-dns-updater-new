# Use an official Python runtime as a parent image
FROM python:3.15-slim AS base

# Set the working directory to /app
WORKDIR /hover-dns-updater

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  # Poetry's configuration:
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_CREATE=false \
  POETRY_CACHE_DIR='/var/cache/pypoetry' \
  POETRY_HOME='/usr/local' \
  POETRY_VERSION=2.5.2
  # ^^^
  # Make sure to update it


# Copy the current directory contents into the container at /app
ADD hover-dns-updater.py hover-update.cfg poetry.lock pyproject.toml README.md /hover-dns-updater/
ADD src /hover-dns-updater/src

# Install poetry
RUN pip install poetry==$POETRY_VERSION

RUN poetry install --no-interaction --no-ansi

# Define environment variable
ENV NAME=hover-dns-updater

FROM base AS test
ADD INSTALL.sh hover-dns-updater.service /hover-dns-updater/
ADD tests /hover-dns-updater/tests
RUN poetry run pytest tests/

FROM base AS production
ENV HOVER_HEALTHCHECK_FILE=/tmp/hover-dns-updater-health
# Run app.py when the container launches
CMD ["python", "hover-dns-updater.py", "--service"]


