"""Shared fixtures and test configuration for hover-dns-updater tests."""

import json
import pytest
from unittest.mock import Mock
import datetime
import importlib.util
import sys
from pathlib import Path


def _load_hover_dns_updater():
    """Load the hover-dns-updater module."""
    spec = importlib.util.spec_from_file_location(
        "hover_dns_updater",
        str(Path(__file__).parent.parent / "hover-dns-updater.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["hover_dns_updater"] = module
    spec.loader.exec_module(module)
    return module


# Initial import
_load_hover_dns_updater()


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing."""
    return {
        "username": "testuser",
        "password": "testpass",
        "toptkey": "JBSWY3DPEBLW64TMMQ======",
        "dns_ids": ["dns123", "dns456"],
        "logfile": None,
        "run-as-service": False,
        "poll-time": 600,
    }


@pytest.fixture
def sample_config_file(tmp_path, sample_config_data):
    """Create a temporary config file with sample data."""
    config_file = tmp_path / "hover-update.cfg"
    config_file.write_text(json.dumps(sample_config_data))
    return config_file


@pytest.fixture
def mock_args(sample_config_file):
    """Mock command-line arguments."""
    return Mock(
        config_file=str(sample_config_file),
        service=False,
        poll_time=None,
        verbose=0,
        quiet=0,
        test=False,
        log_file=None,
        logging_level=20,  # logging.INFO
    )


@pytest.fixture
def mock_requests(mocker):
    """Mock the requests library."""
    return {
        "get": mocker.patch("requests.get"),
        "post": mocker.patch("requests.post"),
        "request": mocker.patch("requests.request"),
    }


@pytest.fixture
def mock_dns_response():
    """Mock a successful DNS API response."""
    return {
        "succeeded": True,
        "domains": [
            {
                "domain_name": "example.com",
                "entries": [
                    {
                        "id": "dns123",
                        "name": "@",
                        "type": "A",
                        "content": "192.168.1.1",
                    },
                    {
                        "id": "dns456",
                        "name": "www",
                        "type": "A",
                        "content": "192.168.1.1",
                    },
                    {
                        "id": "dns789",
                        "name": "mail",
                        "type": "A",
                        "content": "192.168.1.1",
                    },
                ],
            }
        ],
    }
