"""Tests for the Ubuntu service installer."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


SUDO_STUB = """#!/usr/bin/env python3
import os
import subprocess
import sys

args = sys.argv[1:]
if args[0] in {"sh", "systemctl", "chown"}:
    sys.exit(0)

root = os.environ["INSTALLER_TEST_ROOT"]
for index, arg in enumerate(args):
    if arg == "/etc" or arg.startswith("/etc/"):
        args[index] = root + arg

if args[0] == "python3.15":
    args[0] = sys.executable

sys.exit(subprocess.run(args, check=False).returncode)
"""


def test_installer_deploys_package_and_generates_default_config(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo_stub = fake_bin / "sudo"
    sudo_stub.write_text(SUDO_STUB)
    sudo_stub.chmod(0o755)

    root = tmp_path / "root"
    (root / "etc/systemd/system").mkdir(parents=True)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(fake_bin), env["PATH"]))
    env["INSTALLER_TEST_ROOT"] = str(root)

    result = subprocess.run(
        ["sh", str(REPOSITORY_ROOT / "INSTALL.sh")],
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    install_dir = root / "etc/hover-dns-updater"
    assert (install_dir / "hover-dns-updater.py").is_file()
    assert (install_dir / "src/hover_dns_updater/constants.py").is_file()
    assert (install_dir / "src/hover_dns_updater/config.py").is_file()
    assert (install_dir / "src/hover_dns_updater/api.py").is_file()
    assert (install_dir / "src/hover_dns_updater/main.py").is_file()
    service_file = root / "etc/systemd/system/hover-dns-updater.service"
    assert service_file.is_file()
    config = json.loads((install_dir / "hover-dns-updater.json").read_text())
    assert config["username"] == "ENV"

    exec_start = next(
        line.split("=", 1)[1].strip()
        for line in service_file.read_text().splitlines()
        if line.startswith("ExecStart")
    )
    command = shlex.split(exec_start)
    assert command[:2] == ["/usr/bin/env", "python3.15"]
    service_args = command[3:]
    for index, arg in enumerate(service_args):
        if arg.startswith("/etc/hover-dns-updater/"):
            service_args[index] = str(install_dir) + arg.removeprefix(
                "/etc/hover-dns-updater"
            )

    parser_code = (
        "import sys; sys.path.insert(0, 'src'); "
        "from hover_dns_updater.main import _parse_args; _parse_args(sys.argv[1:])"
    )
    result = subprocess.run(
        [sys.executable, "-c", parser_code, *service_args],
        cwd=install_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("arguments", "expected_status"), [(["--help"], 0), (["--unknown-option"], 2)]
)
def test_script_and_installed_command_match_from_another_directory(
    tmp_path, arguments, expected_status
):
    script = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "hover-dns-updater.py"), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    command = subprocess.run(
        [str(Path(sys.executable).parent / "hover-dns-updater"), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert script.returncode == command.returncode == expected_status
    assert script.stdout.replace(
        "hover-dns-updater.py", "hover-dns-updater"
    ).split() == (command.stdout.split())
    assert script.stderr.replace(
        "hover-dns-updater.py", "hover-dns-updater"
    ).split() == (command.stderr.split())


@pytest.mark.parametrize("installed", [False, True])
@pytest.mark.parametrize(
    ("toptkey", "poll_time"), [("JBSWY3DPEBLW64TMMQ======", 600), ("mzxw6", 0)]
)
def test_offline_config_check_redacts_secrets_and_succeeds(
    tmp_path, sample_config_data, installed, toptkey, poll_time
):
    sample_config_data["toptkey"] = toptkey
    sample_config_data["poll-time"] = poll_time
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(sample_config_data))
    log_path = tmp_path / "test.log"
    command = (
        [str(Path(sys.executable).parent / "hover-dns-updater")]
        if installed
        else [sys.executable, str(REPOSITORY_ROOT / "hover-dns-updater.py")]
    )
    result = subprocess.run(
        [
            *command,
            "--config-file",
            str(config_path),
            "--test",
            "--log-file",
            str(log_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PASSWORD = <redacted>" in result.stdout
    assert "TOPTKEY = <redacted>" in result.stdout
    assert sample_config_data["password"] not in result.stdout + result.stderr
    assert sample_config_data["toptkey"] not in result.stdout + result.stderr
    assert "Hover access was not verified" in result.stdout
    assert not log_path.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("username", "", "USERNAME"),
        ("password", " ", "PASSWORD"),
        ("toptkey", "", "TOPTKEY"),
        ("toptkey", "invalid-secret!", "Base32"),
        ("dns_ids", [], "DNS_IDS"),
        ("dns_ids", [""], "DNS_IDS"),
        ("dns_ids", [123], "DNS_IDS"),
        ("dns_ids", None, "configuration"),
        ("poll-time", -1, "POLLTIME"),
        ("poll-time", "60", "POLLTIME"),
        ("poll-time", True, "POLLTIME"),
    ],
)
def test_offline_config_check_rejects_invalid_values(
    tmp_path, sample_config_data, field, value, message
):
    sample_config_data[field] = value
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(sample_config_data))
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "hover-dns-updater.py"),
            "--config-file",
            str(config_path),
            "--test",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert message in result.stderr
    assert "testpass" not in result.stdout + result.stderr
    assert "invalid-secret!" not in result.stdout + result.stderr
    assert "JBSWY3DPEBLW64TMMQ======" not in result.stdout + result.stderr


def test_installed_config_check_returns_failure_for_invalid_configuration(
    tmp_path, sample_config_data
):
    sample_config_data["poll-time"] = -1
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(sample_config_data))
    result = subprocess.run(
        [
            str(Path(sys.executable).parent / "hover-dns-updater"),
            "--config-file",
            str(config_path),
            "--test",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "POLLTIME" in result.stderr


def test_offline_config_check_reports_missing_environment_and_bad_json(
    tmp_path, sample_config_data, monkeypatch
):
    config_path = tmp_path / "config.json"
    sample_config_data["username"] = "ENV"
    config_path.write_text(json.dumps(sample_config_data))
    monkeypatch.delenv("USERNAME", raising=False)
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "hover-dns-updater.py"),
        "--config-file",
        str(config_path),
        "--test",
    ]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "USERNAME" in result.stderr

    config_path.write_text("{")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Unable to load configuration" in result.stderr


def test_offline_config_check_creates_missing_default_config(tmp_path):
    config_path = tmp_path / "missing.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "hover-dns-updater.py"),
            "--config-file",
            str(config_path),
            "--test",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "created default" in result.stderr
    assert json.loads(config_path.read_text())["username"] == "ENV"
