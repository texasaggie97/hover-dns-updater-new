| | |
| --- | --- |
| main branch status | ![Python test Status - main branch](https://github.com/texasaggie97/hover-dns-updater-new/actions/workflows/test-package.yml/badge.svg "Python test Status - main branch") ![Docker test Status - main branch](https://github.com/texasaggie97/hover-dns-updater-new/actions/workflows/test-docker.yml/badge.svg "Docker test Status - main branch") ![GPL License](https://img.shields.io/badge/License-GPL-yellow.svg "GPL License") ![Test Coverage - main branch](https://coveralls.io/repos/github/texasaggie97/hover-dns-updater-new/badge.svg?branch=main&dummy=no_cache_please_1 "Test Coverage - main branch") |
| GitHub status | ![Open Issues + Pull Requests](https://img.shields.io/github/issues/texasaggie97/hover-dns-updater-new.svg "Open Issues + Pull Requests") ![Open Pull Requests](https://img.shields.io/github/issues-pr/texasaggie97/hover-dns-updater-new.svg "Open Pull Requests") |
| Versions | v2.0.0 |

| | |
| --- | --- |
| Info | Hover DNS Updater for Dynamic IP. See [GitHub](https://github.com/texasaggie97/hover-dns-updater/)  for the latest source. |
| Author | Mark Silva, based on a script from [GitHub](https://gist.github.com/andybarilla/b0dd93e71ff18303c059) by Andrew Barilla |
| lmann99 | Kept it running while I did not have access to github and added 2FA support |

About
=====

**hover-dns-updater** will update the Hover DNS entries for one or more
DNS records based on the external IP address. **hover-dns-updater** can
do this one time or can run continuously checking after a certain amount
of time.

I lost access to my GitHub account and they were not able to help me recover
it. The old account has been renamed `texasaggie97-zz` and I have back 
`texasaggie97`. Given this though, the original repo name has been retired 
and cannot be used, so I have renamed the repo to `hover-dns-updater-new` :(

Installation
============

Prerequisites:
--------------

- Python 3.15
    - [Download](https://www.python.org/downloads/)

- pip
    - Linux - `sudo apt-get install -y python3-pip`
    - Windows - `python -m ensurepip --upgrade`
    - `pip install -U pip`

- Poetry
    - `pip install -U poetry==2.5.2`
    - `poetry install` - this will create the poetry venv with all dependencies installed

After installation, run `poetry run hover-dns-updater --help` for the
installed command. The existing `python hover-dns-updater.py --help` script
also remains available from a source checkout.
Use `--poll-time` to override the polling interval in whole seconds when
running with `--service`.

Run `poetry run hover-dns-updater --test` to check configuration offline.
It validates required values, DNS IDs, the Base32 TOTP key, the non-negative
polling interval, and the log path, then prints a summary with the password and
TOTP key redacted. It does not open the log file or verify Hover credentials or
DNS records. It exits nonzero for invalid configuration. As with normal
startup, a missing configuration file is created with defaults and the command
exits nonzero.

Hover TOPT Key:
---------------

-   Login to [Hover.com](https://hover.com)
-   Enable 2FA and manually setup mobile app with the secret key.  Save secret key as configuration value 'toptkey'.
    ** Note: remove spaces from key displayed at end of text "If you can't scan the code, enter this secret key manually: xxxx xxxx xxxx xxxx xxxx xxxx xx"
    (https://help.hover.com/hc/en-us/articles/217282267-Enable-two-step-sign-in-on-your-Hover-account)

Hover DNS IDs:
--------------

-   Login to [Hover.com](https://hover.com)
-   In the same browser go to
    https://www.hover.com/api/domains/YOURDOMAIN.COM/dns replacing
    YOURDOMAIN.COM with the domain you want to update
-   This will return a json file. If you use Firefox, this will be
    nicely formatted.
-   In the "entries" list, look for the DNS records you want to keep up
    to date and make a note of the associated "id"s. They should look
    something like "dns1234567"

Install Ubuntu service:
-----------------------

-   Copy INSTALL.sh, hover-dns-updater.service, hover-dns-updater.py, and
    the src directory (preserving its directory structure) to a folder on
    your Ubuntu system
-   Ensure `python3.15` and the required dependencies are available to the
    installer and systemd service.
-   ./INSTALL.sh
-   This will install and enable, but not start, the hover-dns-updater
    service
-   sudo nano /etc/hover-dns-updater/hover-dns-updater.json (or use the editor of your choice)  
    -   Fill in your hover username and password
    -   Add the dns ids you noted above
    -   Optional - change None to the log file name
    -   Optional - change poll time, in seconds. Default is 10 minutes
    -   When running as an Ubuntu service, the service value in the
        confg file is ignored.

-   After configuration file is updated, start the service
    sudo service hover-dns-updater start
-   Option - Verify service started correctly
    sudo service hover-dns-updater status

Docker
------


### Build the Docker image

From the repository root, build the image used by Docker Compose:

```sh
docker build -t texasaggie97/hover-dns-updater:latest .
```

The production image contains runtime dependencies only. The full test suite
runs separately in Python CI; Docker CI smoke-tests the production image.
The Docker Compose instructions below create and start the container.

To run the full pytest suite inside Docker without adding test files or
development dependencies to the production image, build and run the
`testing` stage:

```sh
docker build --target testing -t hover-dns-updater:testing .
docker run --rm hover-dns-updater:testing
```

### hover.env

Save the following as `hover.env` in the same directory as `docker-compose.yml`.
Replace the placeholders with your Hover credentials, TOTP key, and DNS record
IDs. Add or remove `DNS` entries as needed, numbering them consecutively from
`DNS1`. Keep this file private and do not commit it to source control.

```
USERNAME=hover_dns_username
PASSWORD=hover_dns_password
TOPTKEY=hover_dns_totp_key
DNS1=hover_dns_record_1
DNS2=hover_dns_record_2
LOGFILE=/logs/docker-hover-dns-updater.log
```

### docker-compose.yml:

```yaml
---
name: hover-dns-updater
services:
  hover-dns-updater:
    image: texasaggie97/hover-dns-updater:latest
    container_name: hover-dns-updater
    restart: unless-stopped
    env_file:
      - ./hover.env
    volumes:
      - "./logs:/logs"
    command: ["python", "hover-dns-updater.py", "--service"]
    healthcheck:
      test: ["CMD-SHELL", "find \"$${HOVER_HEALTHCHECK_FILE}\" -type f -mmin -15 -print | grep -q ."]
      interval: 5m
      timeout: 10s
      retries: 3
      start_period: 2m
```

Save the example as `docker-compose.yml` alongside `hover.env`. From that
directory, start the container and check its status:

```sh
docker compose up -d
docker compose ps
```

Use an image built from this version before enabling the healthcheck. The
image records a timestamp after each completed update cycle, including cycles
that require no DNS changes. The healthcheck requires a successful cycle
within the last 15 minutes; increase `-mmin -15` if the polling interval is
longer than the default 10 minutes, allowing extra time for retries. The
timestamp is cleared when the service starts. A healthy status does not
independently verify the DNS records, and Docker does not automatically
restart a container solely because it becomes unhealthy.

Releasing
=========

Before releasing, authenticate Docker to Docker Hub and the GitHub CLI (`gh`)
to GitHub, and ensure Git can push to the GitHub `origin` remote. The working
tree must be clean: no staged, unstaged, or untracked changes (ignored files
are allowed).

Run the script with a version, with or without a leading `v`:

```sh
./scripts/create-release.sh v1.2.3
./scripts/create-release.sh v1.2.4 --prerelease
```

The script:

1. Checks out `main` if necessary and fast-forwards it from `main` at the
   `origin` push destination. If local `main` is ahead or has diverged,
   reconcile it before retrying. Git must be able to switch and update
   branches without overwriting local or ignored files.
2. Lists open GitHub pull requests and asks for confirmation to continue. It
   exits if confirmation is not given.
3. Updates the README `Versions` row, commits it if changed, and pushes `main`
   to `origin` before building from committed `HEAD`.
4. Pushes the versioned Docker image and matching Git tag, then creates a
   GitHub Release with generated notes. It marks prereleases on GitHub and
   pushes `latest` only for stable releases.

Stable releases replace the listed version; a prerelease is also listed when
its version is newer than the latest stable version. For a prerelease without a
suffix, the script checks `origin` and uses the next RC number after the
highest existing matching tag, starting with `-rc.1`.
Specify a suffix such as `v1.2.4-beta.2` with `--prerelease` to use it unchanged.

If publishing fails partway through, inspect the README commit, remote `main`,
image, Git tag, and GitHub Release before completing or retrying manually.

Contributing
============

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for
development setup and testing guidelines.

## Testing

With the Poetry dependencies installed, run:

```sh
poetry run pytest tests/ --cov-fail-under=80
```

The suite reports coverage in the terminal and writes `coverage.xml`. CI
enforces 80% statement coverage on Python 3.15 and uploads the report to
Coveralls. Python 3.15 is the explicitly supported and tested version.

Bugs / Feature Requests
=======================

To report a bug or submit a feature request, please use the [GitHub
issues page](https://github.com/texasaggie97/hover-dns-updater-new/issues).

License
=======

**hover-dns-updater** is licensed under an GPL-style license ([see
LICENSE](https://github.com/texasaggie97/hover-dns-updater-new/blob/master/LICENSE)).
Other incorporated projects may be licensed under different licenses.
