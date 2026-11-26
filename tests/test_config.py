"""Unit tests for HoverConfig class."""

import json
import pytest
from unittest.mock import Mock

from hover_dns_updater.config import HoverConfig


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "environment", "attribute"),
    [
        ("username", "USERNAME", "USERNAME"),
        ("password", "PASSWORD", "PASSWORD"),
        ("toptkey", "TOPTKEY", "TOPTKEY"),
        ("logfile", "LOGFILE", "LOGFILE"),
    ],
)
@pytest.mark.parametrize("value", ["from-environment", ""])
def test_config_substitutes_environment_values(
    field,
    environment,
    attribute,
    value,
    sample_config_data,
    sample_config_file,
    mock_args,
    monkeypatch,
):
    sample_config_data[field] = "ENV"
    sample_config_file.write_text(json.dumps(sample_config_data))
    monkeypatch.setenv(environment, value)

    assert getattr(HoverConfig(mock_args), attribute) == value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "environment"),
    [
        ("username", "USERNAME"),
        ("password", "PASSWORD"),
        ("toptkey", "TOPTKEY"),
        ("logfile", "LOGFILE"),
    ],
)
def test_config_missing_environment_value_reports_name(
    field, environment, sample_config_data, sample_config_file, mock_args, monkeypatch
):
    sample_config_data[field] = "ENV"
    sample_config_file.write_text(json.dumps(sample_config_data))
    monkeypatch.delenv(environment, raising=False)

    with pytest.raises(KeyError) as error:
        HoverConfig(mock_args)
    assert error.value.args == (environment,)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argument", "attribute", "override"),
    [
        ("service", "SERVICE", True),
        ("service", "SERVICE", False),
        ("poll_time", "POLLTIME", 0),
        ("poll_time", "POLLTIME", 120),
        ("log_file", "LOGFILE", ""),
        ("log_file", "LOGFILE", "override.log"),
    ],
)
def test_config_explicit_cli_overrides(
    argument, attribute, override, sample_config_data, sample_config_file, mock_args
):
    sample_config_file.write_text(json.dumps(sample_config_data))
    setattr(mock_args, argument, override)

    assert getattr(HoverConfig(mock_args), attribute) == override


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dns_ids", "environment", "expected"),
    [
        (["ENV"], {}, []),
        (["ENV"], {"DNS1": "first", "DNS2": "second"}, ["first", "second"]),
        (["ENV"], {"DNS1": "first", "DNS3": "third"}, ["first"]),
        (["ENV", "literal"], {"DNS1": "first"}, ["ENV", "literal"]),
    ],
)
def test_config_dns_environment_sequence(
    dns_ids,
    environment,
    expected,
    sample_config_data,
    sample_config_file,
    mock_args,
    monkeypatch,
):
    sample_config_data["dns_ids"] = dns_ids
    sample_config_file.write_text(json.dumps(sample_config_data))
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    assert HoverConfig(mock_args).DNS_IDS == expected


@pytest.mark.unit
@pytest.mark.parametrize("contents", ["", "{", "[] trailing"])
def test_config_rejects_malformed_json(contents, sample_config_file, mock_args):
    sample_config_file.write_text(contents)
    with pytest.raises(json.JSONDecodeError):
        HoverConfig(mock_args)


class TestHoverConfigInitialization:
    """Tests for HoverConfig initialization and defaults."""

    def test_config_requires_config_file_arg(self):
        """Test that HoverConfig requires config_file argument."""
        args = Mock(spec=[])  # Empty spec to cause AttributeError
        with pytest.raises(AttributeError):
            HoverConfig(args)

    def test_config_loads_all_required_fields(self, sample_config_file, mock_args):
        """Test that all required configuration fields are loaded."""
        config = HoverConfig(mock_args)

        assert hasattr(config, 'USERNAME')
        assert hasattr(config, 'PASSWORD')
        assert hasattr(config, 'TOPTKEY')
        assert hasattr(config, 'DNS_IDS')
        assert hasattr(config, 'SERVICE')
        assert hasattr(config, 'POLLTIME')
        assert hasattr(config, 'LOGFILE')

    def test_config_service_flag_defaults_to_false(self, sample_config_file, mock_args):
        """Test that SERVICE flag defaults to False from config file."""
        config = HoverConfig(mock_args)
        assert config.SERVICE is False

    def test_config_poll_time_defaults_to_config_value(self, sample_config_file, mock_args):
        """Test that POLLTIME defaults to value from config file."""
        config = HoverConfig(mock_args)
        assert config.POLLTIME == 600


class TestHoverConfigValidation:
    """Tests for HoverConfig validation of values."""

    def test_config_handles_missing_username(self, tmp_path, mocker, monkeypatch):
        """Test that config raises KeyError when username env var is missing."""
        # Ensure no USERNAME env var exists
        monkeypatch.delenv("USERNAME", raising=False)

        config_file = tmp_path / "config-no-user.json"
        config_data = {
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
        }
        config_file.write_text(json.dumps(config_data))

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        # Should raise KeyError when USERNAME env var is not found
        with pytest.raises(KeyError):
            HoverConfig(args)

    def test_config_handles_missing_password(self, tmp_path, mocker, monkeypatch):
        """Test that config raises KeyError when password env var is missing."""
        # Ensure no PASSWORD env var exists
        monkeypatch.delenv("PASSWORD", raising=False)
        # Set USERNAME to avoid that error
        monkeypatch.setenv("USERNAME", "testuser")

        config_file = tmp_path / "config-no-pass.json"
        config_data = {
            "username": "ENV",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
        }
        config_file.write_text(json.dumps(config_data))

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        # Should raise KeyError when PASSWORD env var is not found
        with pytest.raises(KeyError):
            HoverConfig(args)

    def test_config_handles_missing_toptkey(self, tmp_path, mocker, monkeypatch):
        """Test that config raises KeyError when toptkey env var is missing."""
        # Ensure no TOPTKEY env var exists
        monkeypatch.delenv("TOPTKEY", raising=False)
        # Set required env vars to avoid other errors
        monkeypatch.setenv("USERNAME", "testuser")
        monkeypatch.setenv("PASSWORD", "testpass")

        config_file = tmp_path / "config-no-topt.json"
        config_data = {
            "username": "ENV",
            "password": "ENV",
            "dns_ids": ["dns123"],
            "logfile": None,
        }
        config_file.write_text(json.dumps(config_data))

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        # Should raise KeyError when TOPTKEY env var is not found
        with pytest.raises(KeyError):
            HoverConfig(args)

    def test_config_handles_missing_dns_ids(self, tmp_path, mocker, monkeypatch):
        """Test that config has empty DNS_IDS when not provided and env vars missing."""
        # Ensure no DNS1-DNS5 env vars exist
        for i in range(1, 6):
            monkeypatch.delenv(f"DNS{i}", raising=False)
        # Set required env vars to get past auth checks
        monkeypatch.setenv("USERNAME", "testuser")
        monkeypatch.setenv("PASSWORD", "testpass")
        monkeypatch.setenv("TOPTKEY", "JBSWY3DPEBLW64TMMQ======")

        config_file = tmp_path / "config-no-dns.json"
        config_data = {
            "username": "ENV",
            "password": "ENV",
            "toptkey": "ENV",
            "logfile": None,
        }
        config_file.write_text(json.dumps(config_data))

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        # Should create config with empty DNS_IDS when not provided
        config = HoverConfig(args)
        assert config.DNS_IDS == [], f"Expected empty DNS_IDS, got {config.DNS_IDS}"


class TestHoverConfigCLIOverrides:
    """Tests for CLI argument overrides of config file values."""

    def test_config_cli_override_poll_time_to_zero(self, sample_config_file):
        """Test that poll_time can be overridden to 0."""
        args = Mock(
            config_file=str(sample_config_file),
            service=False,
            poll_time=0,  # Override to 0
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.POLLTIME == 0

    def test_config_cli_override_poll_time_to_large_value(self, sample_config_file):
        """Test that poll_time can be overridden to large value."""
        args = Mock(
            config_file=str(sample_config_file),
            service=False,
            poll_time=86400,  # Override to 24 hours
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.POLLTIME == 86400

    def test_config_cli_override_service_to_false_from_true(self, tmp_path):
        """Test that service flag can be overridden from true to false."""
        config_file = tmp_path / "config-service-true.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": True,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

        args = Mock(
            config_file=str(config_file),
            service=False,  # Override to False
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.SERVICE is False


class TestHoverConfigEnvVarSubstitution:
    """Tests for environment variable substitution in config."""

    def test_config_env_var_substitution_password(self, sample_config_file, monkeypatch):
        """Test environment variable substitution for PASSWORD."""
        config_data = {
            "username": "testuser",
            "password": "ENV",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-pass-env.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("PASSWORD", "envpass")

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
        assert config.PASSWORD == "envpass"

    def test_config_env_var_substitution_toptkey(self, sample_config_file, monkeypatch):
        """Test environment variable substitution for TOPTKEY."""
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "ENV",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-topt-env.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("TOPTKEY", "DIFFERENTKEY======")

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
        assert config.TOPTKEY == "DIFFERENTKEY======"

    def test_config_no_env_var_raises_error(self, sample_config_file, monkeypatch):
        """Test that missing ENV variable raises error."""
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "ENV",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-missing-env.json"
        config_file.write_text(json.dumps(config_data))

        # Make sure the env var doesn't exist
        monkeypatch.delenv("TOPTKEY", raising=False)

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        with pytest.raises((KeyError, ValueError)):
            HoverConfig(args)

    def test_config_env_var_dns_ids_maintains_order(self, sample_config_file, monkeypatch):
        """Test that DNS ID order is maintained from environment variables."""
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["ENV"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file = sample_config_file.parent / "config-dns-order.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("DNS1", "id-first")
        monkeypatch.setenv("DNS2", "id-second")
        monkeypatch.setenv("DNS3", "id-third")
        monkeypatch.setenv("DNS4", "id-fourth")

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
        assert config.DNS_IDS == ["id-first", "id-second", "id-third", "id-fourth"]


class TestHoverConfigFileOperations:
    """Tests for config file reading and writing."""

    def test_config_reads_valid_json(self, tmp_path):
        """Test that HoverConfig reads valid JSON file."""
        config_file = tmp_path / "valid.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.USERNAME == "testuser"

    def test_config_handles_malformed_json(self, tmp_path):
        """Test that HoverConfig handles malformed JSON gracefully."""
        config_file = tmp_path / "malformed.json"
        config_file.write_text("{ invalid json")

        args = Mock(
            config_file=str(config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        with pytest.raises(json.JSONDecodeError):
            HoverConfig(args)

    def test_config_logfile_can_be_none(self, sample_config_file):
        """Test that logfile can be None."""
        args = Mock(
            config_file=str(sample_config_file),
            service=False,
            poll_time=None,
            verbose=0,
            quiet=0,
            test=False,
            log_file=None,
        )

        config = HoverConfig(args)
        assert config.LOGFILE is None

    def test_config_logfile_can_be_path(self, tmp_path):
        """Test that logfile can be a file path."""
        config_file = tmp_path / "config.json"
        log_file = tmp_path / "app.log"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": str(log_file),
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.LOGFILE == str(log_file)


class TestHoverConfigEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_config_empty_dns_ids_list(self, tmp_path):
        """Test that empty DNS IDs list is accepted."""
        config_file = tmp_path / "empty-dns.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": [],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.DNS_IDS == []

    def test_config_single_dns_id(self, tmp_path):
        """Test that single DNS ID is handled correctly."""
        config_file = tmp_path / "single-dns.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["only-one"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.DNS_IDS == ["only-one"]

    def test_config_many_dns_ids(self, tmp_path):
        """Test that many DNS IDs are handled correctly."""
        dns_ids = [f"dns-{i}" for i in range(100)]
        config_file = tmp_path / "many-dns.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": dns_ids,
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.DNS_IDS == dns_ids

    def test_config_poll_time_zero(self, tmp_path):
        """Test that poll_time can be zero."""
        config_file = tmp_path / "poll-zero.json"
        config_data = {
            "username": "testuser",
            "password": "testpass",
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 0,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.POLLTIME == 0

    def test_config_very_long_credentials(self, tmp_path):
        """Test that very long credentials are handled."""
        config_file = tmp_path / "long-creds.json"
        long_string = "x" * 10000
        config_data = {
            "username": long_string,
            "password": long_string,
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.USERNAME == long_string
        assert config.PASSWORD == long_string

    def test_config_special_characters_in_credentials(self, tmp_path):
        """Test that special characters in credentials are preserved."""
        config_file = tmp_path / "special-creds.json"
        special_chars = "!@#$%^&*()_+-=[]{}|;':\"<>,.?/"
        config_data = {
            "username": "user" + special_chars,
            "password": "pass" + special_chars,
            "toptkey": "JBSWY3DPEBLW64TMMQ======",
            "dns_ids": ["dns123"],
            "logfile": None,
            "run-as-service": False,
            "poll-time": 600,
        }
        config_file.write_text(json.dumps(config_data))

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
        assert config.USERNAME == "user" + special_chars
        assert config.PASSWORD == "pass" + special_chars
