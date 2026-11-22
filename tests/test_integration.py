"""Integration tests for hover-dns-updater."""

import pytest
import json
from unittest.mock import Mock
import sys

from hover_dns_updater import HoverConfig, HoverAPI, HoverError, _main


class TestHoverConfigLoading:
    """Tests for HoverConfig class."""

    def test_config_loads_from_file(self, sample_config_file, mock_args):
        """Test that HoverConfig loads configuration from JSON file."""
        config = HoverConfig(mock_args)

        assert config.USERNAME == "testuser"
        assert config.PASSWORD == "testpass"
        assert config.TOPTKEY == "JBSWY3DPEBLW64TMMQ======"
        assert config.DNS_IDS == ["dns123", "dns456"]

    def test_config_creates_default_on_missing_file(self, tmp_path, mocker):
        """Test that HoverConfig creates default config file if missing."""
        config_file = tmp_path / "new-config.json"
        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        # Mock sys.exit to prevent test from exiting
        with pytest.raises(SystemExit):
            HoverConfig(args)

        # Verify file was created
        assert config_file.exists()
        created_config = json.loads(config_file.read_text())
        assert "username" in created_config
        assert created_config["username"] == "ENV"

    def test_config_cli_override_service(self, sample_config_file):
        """Test that CLI args override config file for service flag."""
        args = Mock(
            config_file=str(sample_config_file),
            service=True,  # Override to True
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.SERVICE is True

    def test_config_cli_override_poll_time(self, sample_config_file):
        """Test that CLI args override config file for poll time."""
        args = Mock(
            config_file=str(sample_config_file),
            service=False,
            poll_time=1200,  # Override poll time
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.POLLTIME == 1200

    def test_config_env_var_substitution_username(
        self, sample_config_file, monkeypatch
    ):
        """Test environment variable substitution for USERNAME."""
        config_data = {
            "username": "ENV",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-env.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("USERNAME", "envuser")

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.USERNAME == "envuser"

    def test_config_env_var_substitution_dns_ids(
        self, sample_config_file, monkeypatch
    ):
        """Test environment variable substitution for DNS_IDS."""
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["ENV"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-dns-env.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("DNS1", "dns-id-1")
        monkeypatch.setenv("DNS2", "dns-id-2")
        monkeypatch.setenv("DNS3", "dns-id-3")

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.DNS_IDS == ["dns-id-1", "dns-id-2", "dns-id-3"]

    def test_config_repr(self, sample_config_file, mock_args):
        """Test string representation of HoverConfig."""
        config = HoverConfig(mock_args)
        config_str = repr(config)

        assert "HoverConfig" in config_str
        assert "testuser" in config_str
        assert "dns123" in config_str


class TestHoverAPIAuthentication:
    """Tests for HoverAPI authentication."""

    def test_api_successful_authentication(self, sample_config_data, mocker):
        """Test successful authentication flow."""
        # Create mock config
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        # Mock requests
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth_response = Mock()
        auth_response.ok = True

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        get_mock = mocker.patch("requests.get", return_value=signin_response)
        post_mock = mocker.patch(
            "requests.post", side_effect=[auth_response, auth2_response]
        )

        # Create API instance
        api = HoverAPI(config)

        # Verify authentication succeeded
        assert api._cookies["hover_session"] == "test_session_cookie"
        assert api._cookies["hoverauth"] == "test_hoverauth_cookie"
        assert get_mock.called
        assert post_mock.call_count == 2

    def test_api_auth_failure_no_hoverauth(self, sample_config_data, mocker):
        """Test authentication failure when hoverauth cookie missing."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth_response = Mock()
        auth_response.ok = True

        auth2_response = Mock()
        auth2_response.ok = False  # Failure
        auth2_response.cookies = {}  # No hoverauth cookie

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[auth_response, auth2_response])

        # Verify HoverError is raised
        with pytest.raises(HoverError):
            HoverAPI(config)


class TestHoverAPIDNSOperations:
    """Tests for HoverAPI DNS operations."""

    def test_api_get_current_ips(self, sample_config_data, mocker, mock_dns_response):
        """Test retrieving current IPs from Hover API."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123", "dns456"]
        config.SERVICE = False
        config.POLLTIME = 600

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        # Mock auth
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        # Mock DNS API call
        dns_call_response = Mock()
        dns_call_response.ok = True
        dns_call_response.content = True
        dns_call_response.json.return_value = mock_dns_response

        mocker.patch("requests.request", return_value=dns_call_response)

        # Create API and get IPs
        api = HoverAPI(config)
        api.get_current_ips()

        # Verify results
        assert api._current_dns_ips["dns123"] == "192.168.1.1"
        assert api._current_dns_ips["dns456"] == "192.168.1.1"
        assert "dns789" not in api._current_dns_ips  # Filtered out

    def test_api_update_ip_no_change(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that update skips DNS record if IP hasn't changed."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123", "dns456"]
        config.SERVICE = False
        config.POLLTIME = 600

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        # Setup auth mocks
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        # Mock DNS API call and ipify call
        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        ipify_response = Mock()
        ipify_response.text = "192.168.1.1"  # Same as DNS record

        request_mock = mocker.patch("requests.request", return_value=dns_response)
        mocker.patch(
            "requests.get",
            side_effect=[signin_response, ipify_response],
        )

        # Create API
        api = HoverAPI(config)
        api.get_current_ips()

        # Reset mocks
        request_mock.reset_mock()

        # Update - should not make PUT request since IP hasn't changed
        api.update()

        # Verify no PUT request was made
        put_calls = [
            c for c in request_mock.call_args_list if c[0][0].lower() == "put"
        ]
        assert len(put_calls) == 0

    def test_api_update_ip_changed(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that update makes request when IP has changed."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        # Setup auth mocks
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        # Mock DNS API call with old IP
        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        # Mock ipify with new IP
        ipify_response = Mock()
        ipify_response.text = "203.0.113.45"  # Different IP

        # Mock update response
        update_response = Mock()
        update_response.ok = True
        update_response.content = True
        update_response.json.return_value = {"succeeded": True}

        mocker.patch(
            "requests.get",
            side_effect=[signin_response, ipify_response],
        )
        request_mock = mocker.patch(
            "requests.request",
            side_effect=[dns_response, update_response],
        )

        # Create API
        api = HoverAPI(config)
        api.get_current_ips()

        # Update with new IP
        api.update()

        # Verify PUT request was made
        put_calls = [
            c for c in request_mock.call_args_list if len(c[0]) > 0
            and c[0][0].lower() == "put"
        ]
        assert len(put_calls) == 1
        assert "203.0.113.45" in str(put_calls[0])


class TestMainLoop:
    """Tests for main application loop."""

    def test_main_single_run_mode(self, sample_config_data, mocker):
        """Test _main in single run mode (service=False)."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False  # Single run mode
        config.POLLTIME = 600

        # Mock pyotp
        mocker.patch("pyotp.TOTP")

        # Setup mocks
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = {
            "succeeded": True,
            "domains": [{"entries": [{"id": "dns123", "content": "192.168.1.1"}]}],
        }

        ipify_response = Mock()
        ipify_response.text = "192.168.1.1"

        update_response = Mock()
        update_response.ok = True
        update_response.content = True
        update_response.json.return_value = {"succeeded": True}

        mocker.patch("requests.get", side_effect=[signin_response, ipify_response])
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", side_effect=[dns_response, update_response])

        # Run main
        result = _main(config)

        # Should complete successfully and return 0
        assert result == 0

    def test_main_handles_keyboard_interrupt(self, sample_config_data, mocker):
        """Test that _main handles KeyboardInterrupt gracefully."""
        config = Mock()
        config.SERVICE = True  # Service mode so it doesn't exit naturally
        config.POLLTIME = 1

        # Setup mocks that will raise KeyboardInterrupt
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        # Mock HoverAPI to raise on get_current_ips
        api_mock = Mock()
        api_mock.get_current_ips.side_effect = KeyboardInterrupt()

        mocker.patch("hover_dns_updater.HoverAPI", return_value=api_mock)

        # Run main - should handle the interrupt
        result = _main(config)

        # Should complete successfully (0 return code)
        assert result == 0

    def test_main_handles_network_error_non_service(
        self, sample_config_data, mocker
    ):
        """Test that _main handles network errors in non-service mode."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        # Setup mocks that will raise on first HoverAPI call
        import requests

        mocker.patch(
            "requests.get",
            side_effect=requests.ConnectionError("Network error"),
        )

        # Run main - should return error code
        result = _main(config)

        # Should return error code 1
        assert result == 1
