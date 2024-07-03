| | |
| --- | --- |
| main branch status | ![Python test Status - main branch](https://github.com/texasaggie97/hover-dns-updater-new/actions/workflows/test-package.yml/badge.svg "Python test Status - main branch") ![Docker test Status - main branch](https://github.com/texasaggie97/hover-dns-updater-new/actions/workflows/test-docker.yml/badge.svg "Docker test Status - main branch") ![GPL License](https://img.shields.io/badge/License-GPL-yellow.svg "GPL License") ![Test Coverage - main branch](https://coveralls.io/repos/github/texasaggie97/hover-dns-updater-new/badge.svg?branch=main&dummy=no_cache_please_1 "Test Coverage - main branch") |
| GitHub status | ![Open Issues + Pull Requests](https://img.shields.io/github/issues/texasaggie97/hover-dns-updater-new.svg "Open Issues + Pull Requests") ![Open Pull Requests](https://img.shields.io/github/issues-pr/texasaggie97/hover-dns-updater-new.svg "Open Pull Requests") |
| Versions | 0.1.0.dev0 |

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

- Python 3.10
    - [Download](https://www.python.org/downloads/)

- pip
    - Linux - `sudo apt-get install -y python3-pip`
    - Windows - `python -m ensurepip --upgrade`
    - `pip install -U pip`

- Poetry
    - `pip install -U poetry==1.5.1`
    - `poetry install` - this will create the poetry venv with all dependencies installed

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

-   Copy INSTALL.sh, hover-dns-updater.service, and hover-dns-updater.py
    to a folder on you Ubuntu system
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

Create Docker container
-----------------------

>     docker build -t hover-dns-updater . ; docker tag hover-dns-updater texasaggie97/hover-dns-updater:latest texasaggie97/hover-dns-updater:vX.X.X ; docker push texasaggie97/hover-dns-updater

RancherOS
---------

Here are the docker-compose.yml and rancher-compose.yml to easily recreate the container.

### docker-compose.yml:

>     version: '2'
>     volumes:
>         logs:
>             external: true
>             driver: rancher-nfs
>
>     services:
>         hover-dns-updater:
>             image: texasaggie97/hover-dns-updater
>             environment:
>                 USERNAME: "username"
>                 PASSWORD: "password"
>                 TOPTKEY: "secret code"
>                 DNS1: "dns00000000"
>                 DNS2: "dns00000001"
>                 LOGFILE: "/logs/docker-hover-dns-updater.log"
>             stdin_open: true
>             working_dir: /hover-dns-updater
>             volumes:
>             - logs:/logs
>             tty: true
>             command:
>             - python
>             - hover-dns-updater.py
>             - --service
>             labels:
>                 io.rancher.container.pull_image: always

### rancher-compose.yml:

>     version: '2'
>     services:
>         alarmserver:
>             scale: 1
>             start_on_create: true
>         hover-dns-updater:
>             scale: 1
>             start_on_create: true


Contributing
============

Contributions are welcome!

## Commands to use

- `poetry run black .` - linter, may update formatting if required
- `poetry run flake8`
- `poetry run pytest` - only test currently is a simple one that will pass if the file is loadable

Bugs / Feature Requests
=======================

To report a bug or submit a feature request, please use the [GitHub
issues page](https://github.com/texasaggie97/hover-dns-updater-new/issues).

License
=======

**hover-dns-updater** is licensed under an GPL-style license ([see
LICENSE](https://github.com/texasaggie97/hover-dns-updater-new/blob/master/LICENSE)).
Other incorporated projects may be licensed under different licenses.
