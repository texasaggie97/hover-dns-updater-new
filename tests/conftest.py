"""Shared fixtures and test configuration for hover-dns-updater tests."""

import json
import pytest
from unittest.mock import Mock
from hover_dns_updater.constants import default_config


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


@pytest.fixture(autouse=True)
def cleanup_dns_env_vars(monkeypatch):
    """Automatically clean up DNS environment variables for test isolation."""
    # Save the pristine default_config
    pristine_defaults = {
        "username": "ENV",
        "password": "ENV",
        "toptkey": "ENV",
        "dns_ids": ["ENV"],
        "logfile": "ENV",
        "run-as-service": False,
        "poll-time": 600,
    }

    # Reset to pristine state before each test
    default_config.clear()
    default_config.update(pristine_defaults)

    # Remove any DNS1-DNS9 environment variables that may have been set
    for i in range(1, 10):
        monkeypatch.delenv(f"DNS{i}", raising=False)
    # Also clean up auth environment variables to avoid test cross-contamination
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("PASSWORD", raising=False)
    monkeypatch.delenv("TOPTKEY", raising=False)
