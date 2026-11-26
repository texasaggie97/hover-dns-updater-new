"""Command-line interface and orchestration for the Hover DNS updater.

Based on a script by Andrew Barilla: https://gist.github.com/andybarilla/b0dd93e71ff18303c059
"""

import logging
import logging.handlers
import os
import pprint
import sys
import time
from pathlib import Path

import requests

from .api import HoverAPI
from .config import HoverConfig


pp = pprint.PrettyPrinter(width=120)


def configure_logging(lvl=logging.INFO, logfile=None):
    root = logging.getLogger()
    root.setLevel(lvl)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)8s] --- %(message)s (%(filename)s:%(funcName)s:%(lineno)s)",
        "%Y-%m-%d %H:%M:%S",
    )
    if logfile is None:
        hndlr = logging.StreamHandler(sys.stdout)
    else:
        print("Logging to file %s" % logfile)
        hndlr = logging.handlers.RotatingFileHandler(
            logfile, maxBytes=20000000, backupCount=5
        )
    hndlr.setFormatter(formatter)
    root.addHandler(hndlr)


def _parse_args(argv):
    import argparse

    parser = argparse.ArgumentParser()

    config_group = parser.add_argument_group("Configuration options")
    config_group.add_argument(
        "-c",
        "--config-file",
        default="hover-update.cfg",
        action="store",
        help="Config file, in json format. If it does not exist, one will be created with default values.",
    )
    config_group.add_argument(
        "--service", default=False, action="store_true", help="Run as a service"
    )
    config_group.add_argument(
        "--poll-time",
        default=None,
        action="store",
        type=int,
        help="Time in whole seconds to sleep between polling the ip address",
    )

    verbosity_group = parser.add_argument_group("Verbosity, Logging & Debugging")
    verbosity_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Print debug information.  Can be repeated for more detailed output.",
    )
    verbosity_group.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Print only essential information.  Can be repeated for quieter output.",
    )
    verbosity_group.add_argument(
        "--test", action="store_true", default=False, help="Run doctests then quit."
    )
    verbosity_group.add_argument(
        "--log-file",
        action="store",
        default=None,
        help="Send logging to listed file instead of stdout",
    )

    args = parser.parse_args(argv)

    # We want to default to WARNING
    # Verbosity gives us granularity to control past that
    if 0 < args.verbose and 0 < args.quiet:
        parser.error("Mixing --verbose and --quiet is contradictory")
    # We start logging level at INFO
    verbosity = 1 + args.quiet - args.verbose
    verbosity = max(verbosity, 0)
    verbosity = min(verbosity, 4)
    args.logging_level = {
        0: logging.DEBUG,
        1: logging.INFO,
        2: logging.WARNING,
        3: logging.ERROR,
        4: logging.CRITICAL,
    }[verbosity]

    if args.test:
        return args

    return args


def _main(config):
    healthcheck_file = os.environ.get("HOVER_HEALTHCHECK_FILE")
    healthcheck_path = (
        Path(healthcheck_file) if config.SERVICE and healthcheck_file else None
    )
    if healthcheck_path is not None:
        try:
            healthcheck_path.unlink(missing_ok=True)
        except OSError as e:
            logging.error("Unable to clear healthcheck timestamp: %s", e)
            return 1

    client = None
    dns_initialized = False
    retry_delay = 10
    retry_attempt = 0
    phase = "initialization"
    while True:
        try:
            if client is None:
                phase = "initialization"
                client = HoverAPI(config)
            if not dns_initialized:
                phase = "DNS initialization"
                client.get_current_ips()
                dns_initialized = True
            phase = "update"
            client.update()
            if healthcheck_path is not None:
                try:
                    healthcheck_path.touch()
                except OSError as e:
                    logging.error("Unable to update healthcheck timestamp: %s", e)
                    return 1
            if retry_attempt:
                logging.info(
                    "Network recovered after %s failed request(s); update succeeded",
                    retry_attempt,
                )
                retry_attempt = 0
            retry_delay = 10
            # If we are not running as a service we only want to update once
            if not config.SERVICE:
                break

            logging.debug("Sleeping.... Z Z Z Z")
            time.sleep(config.POLLTIME)
        except KeyboardInterrupt:
            logging.info("Exiting from Control-C")
            break
        except requests.RequestException as e:
            if not config.SERVICE:
                logging.error(e)
                return 1
            retry_attempt += 1
            logging.error(
                "Transient network failure during %s (attempt %s); retrying in %s seconds: %s",
                phase,
                retry_attempt,
                retry_delay,
                e,
            )
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 300)
        except Exception as e:
            logging.error(e)
            return 1
    return 0


def main():  # pragma: no cover
    args = _parse_args(sys.argv[1:])
    config = HoverConfig(args)

    configure_logging(args.logging_level, config.LOGFILE)

    if args.test:
        # import doctest
        # print(doctest.testmod())
        pp.pprint(config)
        return 0

    ret_code = _main(config)
    sys.exit(ret_code)
