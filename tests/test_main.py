"""Unit tests for command-line parsing, logging, and updater orchestration."""

import logging
from unittest.mock import Mock, call

import pytest
import requests

from hover_dns_updater.main import _main, _parse_args, configure_logging


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], logging.INFO),
        (["-v"], logging.DEBUG),
        (["-vv"], logging.DEBUG),
        (["-vvvvv"], logging.DEBUG),
        (["-q"], logging.WARNING),
        (["-qq"], logging.ERROR),
        (["-qqq"], logging.CRITICAL),
        (["-qqqqq"], logging.CRITICAL),
        (["--verbose"], logging.DEBUG),
        (["--quiet"], logging.WARNING),
    ],
)
def test_parse_logging_levels(arguments, expected):
    assert _parse_args(arguments).logging_level == expected


@pytest.mark.parametrize(
    "arguments",
    [
        ["-v", "-q"],
        ["--verbose", "--quiet"],
        ["--unknown"],
        ["--config-file"],
        ["--poll-time"],
        ["--log-file"],
    ],
)
def test_parse_invalid_arguments_exits_with_error(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        _parse_args(arguments)
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["-c", "--config-file"])
def test_parse_config_file_aliases(option):
    assert _parse_args([option, "custom.json"]).config_file == "custom.json"


def test_parse_defaults_and_options():
    defaults = _parse_args([])
    assert (defaults.config_file, defaults.service, defaults.poll_time) == (
        "hover-update.cfg",
        False,
        None,
    )
    assert (defaults.test, defaults.log_file) == (False, None)

    args = _parse_args(
        ["--service", "--poll-time", "30", "--test", "--log-file", "test.log"]
    )
    assert (args.service, args.poll_time, args.test, args.log_file) == (
        True,
        "30",
        True,
        "test.log",
    )


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING])
def test_configure_logging_to_stdout(level, mocker, capsys):
    root = mocker.patch("hover_dns_updater.main.logging.getLogger").return_value
    configure_logging(level)
    handler = root.addHandler.call_args.args[0]
    try:
        root.setLevel.assert_called_once_with(level)
        handler.emit(logging.LogRecord("test", level, __file__, 1, "message", (), None))
        assert "message" in capsys.readouterr().out
    finally:
        handler.close()


def test_configure_logging_to_file(tmp_path, mocker, capsys):
    root = mocker.patch("hover_dns_updater.main.logging.getLogger").return_value
    path = tmp_path / "updater.log"
    configure_logging(logging.ERROR, path)
    handler = root.addHandler.call_args.args[0]
    try:
        handler.emit(
            logging.LogRecord("test", logging.ERROR, __file__, 1, "failure", (), None)
        )
        assert "failure" in path.read_text()
        assert str(path) in capsys.readouterr().out
    finally:
        handler.close()


def test_single_run_initializes_and_updates_once(mocker):
    config = Mock(SERVICE=False)
    client = mocker.patch("hover_dns_updater.main.HoverAPI").return_value
    sleep = mocker.patch("hover_dns_updater.main.time.sleep")

    assert _main(config) == 0
    client.get_current_ips.assert_called_once_with()
    client.update.assert_called_once_with()
    sleep.assert_not_called()


def test_service_reuses_initialized_client(mocker):
    config = Mock(SERVICE=True, POLLTIME=60)
    factory = mocker.patch("hover_dns_updater.main.HoverAPI")
    client = factory.return_value
    sleep = mocker.patch(
        "hover_dns_updater.main.time.sleep", side_effect=[None, KeyboardInterrupt]
    )

    assert _main(config) == 0
    factory.assert_called_once_with(config)
    client.get_current_ips.assert_called_once_with()
    assert client.update.call_count == 2
    assert sleep.call_args_list == [call(60), call(60)]


@pytest.mark.parametrize("phase", ["initialization", "dns", "update"])
@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_non_service_network_error_returns_failure(phase, exception, mocker, caplog):
    config = Mock(SERVICE=False)
    factory = mocker.patch("hover_dns_updater.main.HoverAPI")
    client = factory.return_value
    error = exception("offline")
    if phase == "initialization":
        factory.side_effect = error
    elif phase == "dns":
        client.get_current_ips.side_effect = error
    else:
        client.update.side_effect = error
    sleep = mocker.patch("hover_dns_updater.main.time.sleep")

    assert _main(config) == 1
    assert "offline" in caplog.text
    sleep.assert_not_called()


@pytest.mark.parametrize("phase", ["initialization", "dns", "update"])
def test_service_retries_failure_at_each_phase(phase, mocker, caplog):
    caplog.set_level(logging.INFO)
    config = Mock(SERVICE=True, POLLTIME=60)
    factory = mocker.patch("hover_dns_updater.main.HoverAPI")
    client = factory.return_value
    error = requests.ConnectionError("offline")
    if phase == "initialization":
        factory.side_effect = [error, client]
    elif phase == "dns":
        client.get_current_ips.side_effect = [error, None]
    else:
        client.update.side_effect = [error, None]
    sleep = mocker.patch(
        "hover_dns_updater.main.time.sleep", side_effect=[None, KeyboardInterrupt]
    )

    assert _main(config) == 0
    assert sleep.call_args_list == [call(10), call(60)]
    assert factory.call_count == (2 if phase == "initialization" else 1)
    assert client.get_current_ips.call_count == (2 if phase == "dns" else 1)
    assert client.update.call_count == (2 if phase == "update" else 1)
    assert "Network recovered after 1 failed request(s)" in caplog.text
    assert "offline" in caplog.text


def test_service_retry_backoff_caps_and_resets_after_recovery(mocker):
    config = Mock(SERVICE=True, POLLTIME=60)
    client = mocker.patch("hover_dns_updater.main.HoverAPI").return_value
    error = requests.Timeout("offline")
    client.update.side_effect = [error] * 7 + [None, error, None]
    sleep = mocker.patch(
        "hover_dns_updater.main.time.sleep",
        side_effect=[None] * 9 + [KeyboardInterrupt],
    )

    assert _main(config) == 0
    assert sleep.call_args_list == [
        call(10),
        call(20),
        call(40),
        call(80),
        call(160),
        call(300),
        call(300),
        call(60),
        call(10),
        call(60),
    ]
    client.get_current_ips.assert_called_once_with()


@pytest.mark.parametrize("phase", ["initialization", "dns", "update"])
@pytest.mark.parametrize("service", [False, True])
def test_unexpected_error_is_logged_and_returns_failure(phase, service, mocker, caplog):
    config = Mock(SERVICE=service)
    factory = mocker.patch("hover_dns_updater.main.HoverAPI")
    client = factory.return_value
    if phase == "initialization":
        factory.side_effect = ValueError("invalid")
    elif phase == "dns":
        client.get_current_ips.side_effect = ValueError("invalid")
    else:
        client.update.side_effect = ValueError("invalid")
    sleep = mocker.patch("hover_dns_updater.main.time.sleep")

    assert _main(config) == 1
    assert "invalid" in caplog.text
    sleep.assert_not_called()


@pytest.mark.parametrize("phase", ["initialization", "dns", "update"])
def test_keyboard_interrupt_stops_cleanly(phase, mocker):
    factory = mocker.patch("hover_dns_updater.main.HoverAPI")
    client = factory.return_value
    if phase == "initialization":
        factory.side_effect = KeyboardInterrupt
    elif phase == "dns":
        client.get_current_ips.side_effect = KeyboardInterrupt
    else:
        client.update.side_effect = KeyboardInterrupt
    assert _main(Mock(SERVICE=True)) == 0
