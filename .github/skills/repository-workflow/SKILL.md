---
name: repository-workflow
description: Work on the Hover DNS updater repository, including its layout, isolated Python environment, builds, tests, and linting.
---

# Repository workflow

Use this skill when changing, building, or validating this repository. Run
commands from the repository root.

## Repository structure

- `hover-dns-updater.py` is a backward-compatible CLI wrapper.
- `src/hover_dns_updater/` contains the extracted configuration, Hover API,
  constants, exception, and CLI orchestration modules. Poetry installs the
  `hover-dns-updater` console entry point.
- `tests/` contains config and API unit tests, integration tests, installer
  tests, and shared fixtures in `conftest.py`.
- `pyproject.toml` and `poetry.lock` define Python dependencies and tooling.
- `Dockerfile` defines the container; `INSTALL.sh` and
  `hover-dns-updater.service` install and run the systemd service.
- `.github/workflows/` contains the Python and Docker CI workflows.

## Isolated Python environment

Use one repository-local virtual environment at `<repository-root>/.venv` for
local builds, tests, and linting. It is ignored by Git. Do not install project
dependencies into an unrelated active environment or the system Python.

With a compatible Python interpreter and Poetry installed, create the
environment if it does not already exist:

```sh
python3.15 -m venv .venv
```

Install the locked project and development dependencies into that environment.
Explicitly set `VIRTUAL_ENV` and `PATH` so Poetry does not use a different
environment inherited from the shell:

```sh
VIRTUAL_ENV="$PWD/.venv" PATH="$PWD/.venv/bin:$PATH" poetry install
```

Reuse `.venv` on subsequent tasks. If it is invalid or uses an incompatible
Python version, report the problem rather than silently using another
environment or deleting it. Reinstall dependencies when the lockfile or
dependency manifest changes.

## Validation and builds

Use the local environment's executables explicitly:

```sh
.venv/bin/python -m pytest tests/ --cov-fail-under=80
.venv/bin/black --check .
.venv/bin/flake8 hover-dns-updater.py src tests
VIRTUAL_ENV="$PWD/.venv" PATH="$PWD/.venv/bin:$PATH" poetry build
```

Run the smallest relevant tests first, and run broader checks when needed. The
Python CI workflow runs Black in formatting mode before flake8 and pytest;
`black --check` above does not modify files. Formatting the whole repository
can change unrelated files, so inspect its effects before including them.
CI tests Python 3.15, enforces 80% statement coverage, and uploads
the Python 3.15 coverage report to Coveralls.
Check the Docker workflow and Dockerfile when changing container behavior.

Always restrict local flake8 to project paths as shown above, so an unrestricted
scan does not lint installed dependencies. The root `.flake8` file configures
flake8 and excludes `.venv`.

## Maintenance

When a change modifies the repository structure, environment setup, build
process, or validation commands, update this skill in the same change. Verify
the instructions against the current files and workflows; do not retain
outdated paths or commands.
