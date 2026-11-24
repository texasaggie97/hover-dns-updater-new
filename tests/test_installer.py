"""Tests for the Ubuntu service installer."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

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

if args[0] == "python3":
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
    service_file = root / "etc/systemd/system/hover-dns-updater.service"
    assert service_file.is_file()
    config = json.loads((install_dir / "hover-dns-updater.json").read_text())
    assert config["username"] == "ENV"

    exec_start = next(
        line.split("=", 1)[1].strip()
        for line in service_file.read_text().splitlines()
        if line.startswith("ExecStart")
    )
    service_args = shlex.split(exec_start)[2:]
    for index, arg in enumerate(service_args):
        if arg.startswith("/etc/hover-dns-updater/"):
            service_args[index] = str(install_dir) + arg.removeprefix(
                "/etc/hover-dns-updater"
            )

    parser_code = (
        "import runpy, sys; "
        "runpy.run_path('hover-dns-updater.py')['_parse_args'](sys.argv[1:])"
    )
    result = subprocess.run(
        [sys.executable, "-c", parser_code, *service_args],
        cwd=install_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
