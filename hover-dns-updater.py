#!/usr/bin/env python
"""Backward-compatible script entry point for the Hover DNS updater."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hover_dns_updater.main import main  # noqa: E402


if __name__ == "__main__":
    main()
