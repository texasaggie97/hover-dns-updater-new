# Contributing

## Development setup

Use Python 3.15 and Poetry. From the repository root, create a local
environment and install the locked dependencies:

```sh
python3.15 -m venv .venv
VIRTUAL_ENV="$PWD/.venv" PATH="$PWD/.venv/bin:$PATH" poetry install
```

## Tests and checks

Run the full suite and the same coverage gate used in CI:

```sh
.venv/bin/python -m pytest tests/ --cov-fail-under=80
```

The terminal report identifies missing lines, and `coverage.xml` contains the
machine-readable report uploaded to Coveralls by the Python 3.15 CI job.
Coverage measures the package in
`src/hover_dns_updater`; the existing `main()` entry point is excluded.

Run the relevant checks before submitting changes:

```sh
.venv/bin/black --check .
.venv/bin/flake8 hover-dns-updater.py src tests
```

CI runs Black in formatting mode before linting and tests. To match that
sequence locally, run `.venv/bin/black .` before flake8; review any resulting
formatting changes. Tests can be selected by file or with the `unit` and
`integration` markers, for example `.venv/bin/python -m pytest -m unit`.
Add focused tests for new behavior and regressions, using mocks and fixtures
for external services rather than requiring Hover credentials or network access.

CI tests Python 3.15, the explicitly supported version.
The Docker workflow also builds the production image and smoke-tests its
entry points and configuration with networking disabled and dummy credentials.
The existing `--test` option prints configuration, including credentials; use
only dummy values when testing it in logs.
