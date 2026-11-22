"""Shared fixtures and test configuration for hover-dns-updater tests."""

import json
import pytest
from unittest.mock import Mock
import datetime


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing.

    Note: toptkey is a base32-encoded secret for TOTP.
    """
    return {
        "username": "testuser",
        "password": "testpass",
        "toptkey": "JBSWY3DPEBLW64TMMQ======",  # Valid base32 for 'secret' in TOTP
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
def mock_signin_response(mocker):
    """Mock the signin page GET response."""
    response = Mock()
    response.cookies = {"hover_session": "test_session_cookie"}
    return response


@pytest.fixture
def mock_auth_response(mocker):
    """Mock the auth.json POST response."""
    response = Mock()
    response.ok = True
    response.cookies = {}
    return response


@pytest.fixture
def mock_auth2_response(mocker):
    """Mock the auth2.json POST response with hoverauth cookie."""
    response = Mock()
    response.ok = True
    response.cookies = {"hoverauth": "test_hoverauth_cookie"}
    return response


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


@pytest.fixture
def mock_ipify_response(mocker):
    """Mock the ipify.org IP address response."""
    response = Mock()
    response.text = "203.0.113.45"
    return response


@pytest.fixture
def configured_hover_api(mock_args, mock_requests, mocker):
    """Setup a fully configured HoverAPI instance with mocked requests."""
    # We need to import here to avoid issues with module loading
    import sys

    # Add the repo root to path
    sys.path.insert(0, "/home/mark/github/hover-dns-updater-new")

    from hover_dns_updater import HoverConfig, HoverAPI

    # Setup mock responses for auth
    signin_response = Mock()
    signin_response.cookies = {"hover_session": "test_session_cookie"}

    auth2_response = Mock()
    auth2_response.ok = True
    auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

    mock_requests["get"].return_value = signin_response
    mock_requests["post"].return_value = auth2_response

    config = HoverConfig(mock_args)
    api = HoverAPI(config)
    return api


@pytest.fixture
def mock_client(sample_config_data, mocker):
    """Mock HoverAPI client with pre-configured state."""
    import sys

    sys.path.insert(0, "/home/mark/github/hover-dns-updater-new")

    from hover_dns_updater import HoverAPI, HoverConfig

    config = Mock(spec=HoverConfig)
    config.USERNAME = sample_config_data["username"]
    config.PASSWORD = sample_config_data["password"]
    config.TOPTKEY = sample_config_data["toptkey"]
    config.DNS_IDS = sample_config_data["dns_ids"]
    config.LOGFILE = None
    config.SERVICE = sample_config_data["run-as-service"]
    config.POLLTIME = sample_config_data["poll-time"]

    client = Mock(spec=HoverAPI)
    client._config = config
    client._current_dns_ips = {
        "dns123": "192.168.1.1",
        "dns456": "192.168.1.1",
    }
    client._cookies = {
        "hover_session": "test_session",
        "hoverauth": "test_hoverauth",
    }
    client._auth_timestamp = datetime.datetime.now()

    return client
