"""Command-line interface and orchestration for the Hover DNS updater.

Based on a script by Andrew Barilla: https://gist.github.com/andybarilla/b0dd93e71ff18303c059
"""

import binascii
import json
import logging
import logging.handlers
import os
import pprint
import sys
import time
from pathlib import Path

import pyotp
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
        "--test",
        action="store_true",
        default=False,
        help="Validate configuration offline, print a redacted summary, and quit.",
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

    return args


def _test_config(config):
    errors = []
    for name in ("USERNAME", "PASSWORD", "TOPTKEY"):
        value = getattr(config, name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name} must be a non-empty string")

    if isinstance(config.TOPTKEY, str) and config.TOPTKEY.strip():
        try:
            pyotp.TOTP(config.TOPTKEY).byte_secret()
        except (binascii.Error, ValueError):
            errors.append("TOPTKEY must be a valid Base32 TOTP key")

    if (
        not isinstance(config.DNS_IDS, list)
        or not config.DNS_IDS
        or any(
            not isinstance(dns_id, str) or not dns_id.strip()
            for dns_id in config.DNS_IDS
        )
    ):
        errors.append("DNS_IDS must contain at least one non-empty DNS record ID")

    if (
        not isinstance(config.POLLTIME, int)
        or isinstance(config.POLLTIME, bool)
        or config.POLLTIME < 0
    ):
        errors.append("POLLTIME must be a non-negative integer")

    if config.LOGFILE is not None and (
        not isinstance(config.LOGFILE, str) or not config.LOGFILE.strip()
    ):
        errors.append("LOGFILE must be null or a non-empty path string")

    if errors:
        for error in errors:
            print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    print("HoverConfig():")
    print(f"    USERNAME = {config.USERNAME}")
    print("    PASSWORD = <redacted>")
    print("    TOPTKEY = <redacted>")
    print(f"    DNS_IDS = {pp.pformat(config.DNS_IDS)}")
    print(f"    LOGFILE = {config.LOGFILE}")
    print(f"    SERVICE = {config.SERVICE}")
    print(f"    POLLTIME = {config.POLLTIME}")
    print("Configuration is valid (offline check; Hover access was not verified).")
    return 0


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
    if args.test:
        try:
            config = HoverConfig(args)
        except SystemExit as exc:
            if exc.code != 1:
                raise
            print(
                f"Configuration file not found; created default: {args.config_file}",
                file=sys.stderr,
            )
            sys.exit(1)
        except KeyError as exc:
            print(
                f"Missing configuration value or environment variable: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, TypeError) as exc:
            print(f"Unable to load configuration: {exc}", file=sys.stderr)
            sys.exit(1)
        sys.exit(_test_config(config))

    config = HoverConfig(args)
    configure_logging(args.logging_level, config.LOGFILE)

    ret_code = _main(config)
    sys.exit(ret_code)
