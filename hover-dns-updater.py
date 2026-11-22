#!/usr/bin/env python

"""Backward compatibility wrapper for hover-dns-updater.

This file provides backward compatibility by importing from the new package structure.
The main code has been moved to src/hover_dns_updater/__init__.py
"""

import sys
import os

# Add src directory to path so we can import hover_dns_updater
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from hover_dns_updater import (
    HoverConfig,
    HoverError,
    HoverAPI,
    configure_logging,
    _parse_args,
    _main,
    main,
)

__all__ = [
    "HoverConfig",
    "HoverError",
    "HoverAPI",
    "configure_logging",
    "_parse_args",
    "_main",
    "main",
]

if __name__ == "__main__":  # pragma: no cover
    main()
