# Contributing

## Development setup

Use Python 3.9 or newer and Poetry. From the repository root, create a local
environment and install the locked dependencies:

```sh
python3 -m venv .venv
VIRTUAL_ENV="$PWD/.venv" PATH="$PWD/.venv/bin:$PATH" poetry install
```

## Tests and checks

Run the full suite and the same coverage gate used in CI:

```sh
.venv/bin/python -m pytest tests/ --cov-fail-under=80
```

The terminal report identifies missing lines, and `coverage.xml` contains the
machine-readable report. Coverage measures the package in
`src/hover_dns_updater`; the existing `main()` entry point is excluded.
The Coveralls upload step is currently disabled.

Run the relevant checks before submitting changes:

```sh
.venv/bin/black --check .
.venv/bin/pflake8 hover-dns-updater.py src tests
```

CI runs Black in formatting mode before linting and tests. To match that
sequence locally, run `.venv/bin/black .` before pflake8; review any resulting
formatting changes. Tests can be selected by file or with the `unit` and
`integration` markers, for example `.venv/bin/python -m pytest -m unit`.
Add focused tests for new behavior and regressions, using mocks and fixtures
for external services rather than requiring Hover credentials or network access.

CI tests Python 3.10, 3.11, and 3.12. The declared minimum is Python 3.9,
which is not currently in the CI matrix.
