"""Tests for the release publishing script."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/create-release.sh"
IMAGE = "texasaggie97/hover-dns-updater"


@pytest.fixture
def release_repo(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--quiet")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.invalid")
    (repo / "Dockerfile").write_text("committed\n")
    git("add", "Dockerfile")
    git("commit", "--quiet", "-m", "Test snapshot")
    subprocess.run(
        ["git", "init", "--bare", "--quiet", str(remote)], check=True, env=env
    )
    git("remote", "add", "origin", str(remote))

    (repo / "scripts").mkdir()
    shutil.copy(SCRIPT, repo / "scripts/create-release.sh")
    (repo / "Dockerfile").write_text("uncommitted\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
        'if [ "$1" = build ]; then tar -xOf - Dockerfile > "$DOCKER_CONTEXT"; fi\n'
        'if [ "$1" = push ] && [ "${FAIL_PUSH:-}" = 1 ]; then exit 1; fi\n'
    )
    docker.chmod(0o755)
    env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
    env["DOCKER_LOG"] = str(tmp_path / "docker.log")
    env["DOCKER_CONTEXT"] = str(tmp_path / "context")
    return repo, env, git


def run_release(release_repo, *args):
    repo, env, _ = release_repo
    return subprocess.run(
        ["bash", str(repo / "scripts/create-release.sh"), *args],
        cwd=repo.parent,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("args", "tag", "stable"),
    [
        (("1.2.3",), "v1.2.3", True),
        (("1.2.4", "--prerelease"), "v1.2.4-rc.1", False),
        (("1.2.4-beta.2", "--prerelease"), "v1.2.4-beta.2", False),
    ],
)
def test_publishes_matching_image_and_committed_git_tag(
    release_repo, args, tag, stable
):
    _, env, git = release_repo
    result = run_release(release_repo, *args)
    assert result.returncode == 0, result.stderr
    assert Path(env["DOCKER_CONTEXT"]).read_text() == "committed\n"
    calls = Path(env["DOCKER_LOG"]).read_text().splitlines()
    build_tags = f"-t {IMAGE}:{tag}"
    if stable:
        build_tags += f" -t {IMAGE}:latest"
    assert calls == [
        f"build {build_tags} -",
        f"push {IMAGE}:{tag}",
        *([f"push {IMAGE}:latest"] if stable else []),
    ]
    assert git("rev-parse", tag) == git("rev-parse", "HEAD")
    assert git("ls-remote", "--refs", "origin", f"refs/tags/{tag}").split()[0] == git(
        "rev-parse", "HEAD"
    )


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("v1.2.3",),
        ("1.2.3-rc.1",),
        ("1.2.3", "--bad"),
        ("1.2.3", "--prerelease", "extra"),
    ],
)
def test_invalid_arguments_do_not_publish(release_repo, args):
    _, env, _ = release_repo
    result = run_release(release_repo, *args)
    assert result.returncode != 0
    assert not Path(env["DOCKER_LOG"]).exists()


def test_existing_remote_tag_does_not_publish(release_repo):
    _, env, git = release_repo
    git("tag", "v1.2.3")
    git("push", "origin", "refs/tags/v1.2.3")
    git("tag", "-d", "v1.2.3")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "already exists on origin" in result.stderr
    assert not Path(env["DOCKER_LOG"]).exists()


def test_prerelease_uses_next_remote_rc_number(release_repo):
    _, env, git = release_repo
    for tag in (
        "v1.2.4-rc.1",
        "v1.2.4-rc.2",
        "v1.2.4-rc.10",
        "v1.2.4-rc.12-extra",
        "v1.2.40-rc.99",
    ):
        git("tag", tag)
        git("push", "origin", f"refs/tags/{tag}")
        git("tag", "-d", tag)

    result = run_release(release_repo, "1.2.4", "--prerelease")
    assert result.returncode == 0, result.stderr
    assert git("ls-remote", "--refs", "origin", "refs/tags/v1.2.4-rc.11")
    calls = Path(env["DOCKER_LOG"]).read_text().splitlines()
    assert calls == [
        f"build -t {IMAGE}:v1.2.4-rc.11 -",
        f"push {IMAGE}:v1.2.4-rc.11",
    ]


def test_prerelease_fails_if_remote_tags_cannot_be_read(release_repo):
    _, env, git = release_repo
    git("remote", "set-url", "origin", str(Path(env["DOCKER_LOG"]).parent / "missing"))
    result = run_release(release_repo, "1.2.4", "--prerelease")
    assert result.returncode != 0
    assert not Path(env["DOCKER_LOG"]).exists()


def test_prerelease_rejects_number_too_large_for_shell_arithmetic(release_repo):
    _, env, git = release_repo
    tag = "v1.2.4-rc.9999999999999999999"
    git("tag", tag)
    git("push", "origin", f"refs/tags/{tag}")
    result = run_release(release_repo, "1.2.4", "--prerelease")
    assert result.returncode != 0
    assert "number is too large" in result.stderr
    assert not Path(env["DOCKER_LOG"]).exists()


def test_prerelease_fails_if_next_tag_exists_locally(release_repo):
    _, env, git = release_repo
    git("tag", "v1.2.4-rc.1")
    result = run_release(release_repo, "1.2.4", "--prerelease")
    assert result.returncode != 0
    assert "Local tag v1.2.4-rc.1 already exists" in result.stderr
    assert not Path(env["DOCKER_LOG"]).exists()


def test_image_push_failure_does_not_create_git_tag(release_repo):
    _, env, git = release_repo
    env["FAIL_PUSH"] = "1"
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert git("tag", "--list") == ""
    assert git("ls-remote", "--tags", "origin") == ""
