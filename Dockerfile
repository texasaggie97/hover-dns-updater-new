# Use an official Python runtime as a parent image
FROM python:3.10-slim AS base

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
  POETRY_VERSION=1.8.3
  # ^^^
  # Make sure to update it


# Copy the current directory contents into the container at /app
ADD hover-dns-updater.py hover-update.cfg poetry.lock pyproject.toml /hover-dns-updater/

# Install poetry
RUN pip install poetry==$POETRY_VERSION

RUN poetry install --no-interaction --no-ansi

# Define environment variable
ENV NAME=hover-dns-updater

FROM base AS test
RUN poetry run pytest hover-dns-updater.py

FROM base AS production
# Run app.py when the container launches
CMD ["python", "hover-dns-updater.py", "--service"]


