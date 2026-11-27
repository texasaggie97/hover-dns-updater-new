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

    git("init", "--quiet", "--initial-branch=main")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.invalid")
    (repo / "Dockerfile").write_text("committed\n")
    (repo / "README.md").write_text("| Versions | v1.0.1 |\n")
    (repo / "scripts").mkdir()
    shutil.copy(SCRIPT, repo / "scripts/create-release.sh")
    git("add", "Dockerfile", "README.md", "scripts/create-release.sh")
    git("commit", "--quiet", "-m", "Test snapshot")
    subprocess.run(
        ["git", "init", "--bare", "--quiet", str(remote)], check=True, env=env
    )
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "HEAD:refs/heads/main")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
        'if [ "$1" = build ]; then\n'
        '  cat > "$DOCKER_ARCHIVE"\n'
        '  tar -xOf "$DOCKER_ARCHIVE" Dockerfile > "$DOCKER_CONTEXT"\n'
        '  tar -xOf "$DOCKER_ARCHIVE" README.md > "$DOCKER_README"\n'
        "fi\n"
        'if [ "$1" = push ] && [ "${FAIL_PUSH:-}" = 1 ]; then exit 1; fi\n'
    )
    docker.chmod(0o755)
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = api ]; then\n'
        '  printf "%s\\n" "$GH_REPO $*" >> "$GH_API_LOG"\n'
        '  if [ "${FAIL_API:-}" = 1 ]; then echo "API failed" >&2; exit 1; fi\n'
        '  if [ "${CHANGE_DURING_API:-}" = 1 ]; then echo changed >> Dockerfile; fi\n'
        '  printf "%s" "${OPEN_PRS:-}"\n'
        "  exit 0\n"
        "fi\n"
        'printf "%s\\n" "$*" >> "$GH_LOG"\n'
        'if [ "$1" != release ] || [ "$2" != create ]; then exit 1; fi\n'
        "remote=$(git remote get-url --push origin) || exit 1\n"
        'git ls-remote --refs "$remote" "refs/tags/$3" | grep -q . || exit 1\n'
        'remote_commit=$(git ls-remote --refs "$remote" "refs/heads/main")\n'
        '[ "${remote_commit%%	*}" = "$(git rev-parse "$3")" ] || exit 1\n'
        'git show "$3:README.md" > "$RELEASE_README"\n'
        'if [ "${FAIL_GH:-}" = 1 ]; then echo "release failed" >&2; exit 1; fi\n'
    )
    gh.chmod(0o755)
    env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
    env["DOCKER_LOG"] = str(tmp_path / "docker.log")
    env["DOCKER_CONTEXT"] = str(tmp_path / "context")
    env["DOCKER_ARCHIVE"] = str(tmp_path / "context.tar")
    env["DOCKER_README"] = str(tmp_path / "docker-readme")
    env["RELEASE_README"] = str(tmp_path / "release-readme")
    env["GH_LOG"] = str(tmp_path / "gh.log")
    env["GH_API_LOG"] = str(tmp_path / "gh-api.log")
    return repo, env, git


def run_release(release_repo, *args, input_text=None):
    repo, env, _ = release_repo
    return subprocess.run(
        ["bash", str(repo / "scripts/create-release.sh"), *args],
        cwd=repo.parent,
        env=env,
        capture_output=True,
        text=True,
        input=input_text,
    )


@pytest.mark.parametrize(
    ("args", "tag", "stable"),
    [
        (("1.2.3",), "v1.2.3", True),
        (("v1.2.3",), "v1.2.3", True),
        (("1.2.4", "--prerelease"), "v1.2.4-rc.1", False),
        (("v1.2.4", "--prerelease"), "v1.2.4-rc.1", False),
        (("1.2.4-beta.2", "--prerelease"), "v1.2.4-beta.2", False),
        (("v1.2.4-beta.2", "--prerelease"), "v1.2.4-beta.2", False),
    ],
)
def test_publishes_matching_image_and_committed_git_tag(
    release_repo, args, tag, stable
):
    _, env, git = release_repo
    result = run_release(release_repo, *args)
    assert result.returncode == 0, result.stderr
    assert Path(env["DOCKER_CONTEXT"]).read_text() == "committed\n"
    expected_versions = tag if stable else f"v1.0.1, {tag}"
    expected_readme = f"| Versions | {expected_versions} |\n"
    assert (release_repo[0] / "README.md").read_text() == expected_readme
    assert Path(env["DOCKER_README"]).read_text() == expected_readme
    assert Path(env["RELEASE_README"]).read_text() == expected_readme
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
    assert git("log", "-1", "--format=%s") == f"Update README versions for {tag}"
    assert git("ls-remote", "--refs", "origin", f"refs/tags/{tag}").split()[0] == git(
        "rev-parse", "HEAD"
    )
    prerelease_flag = "" if stable else " --prerelease"
    assert Path(env["GH_LOG"]).read_text().splitlines() == [
        f"release create {tag} --repo {git('remote', 'get-url', '--push', 'origin')}"
        f" --verify-tag --title {tag} --generate-notes{prerelease_flag}"
    ]


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("v",),
        ("vv1.2.3",),
        ("V1.2.3",),
        ("v01.2.3",),
        ("1.2.3-rc.1",),
        ("v1.2.3-rc.1",),
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
    assert git("tag", "--list", "v1.2.3") == ""
    assert not Path(env["DOCKER_LOG"]).exists()


@pytest.mark.parametrize(
    "versions", ["1.0.1", "v1.0.1, 1.2.4-rc.1", "v1.0.1, v1.2.4-rc.1, v1.2.5"]
)
def test_invalid_readme_versions_do_not_publish(release_repo, versions):
    repo, env, git = release_repo
    (repo / "README.md").write_text(f"| Versions | {versions} |\n")
    git("add", "README.md")
    git("commit", "--quiet", "-m", "Invalid versions")
    git("push", "origin", "main")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "exactly one valid Versions row" in result.stderr
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
    assert (release_repo[0] / "README.md").read_text() == (
        "| Versions | v1.0.1, v1.2.4-rc.11 |\n"
    )


def test_prerelease_before_latest_release_is_not_listed(release_repo):
    _, _, git = release_repo
    previous_commit = git("rev-parse", "HEAD")
    result = run_release(release_repo, "1.0.1-rc.1", "--prerelease")
    assert result.returncode == 0, result.stderr
    assert (release_repo[0] / "README.md").read_text() == "| Versions | v1.0.1 |\n"
    assert git("rev-parse", "HEAD") == previous_commit


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
    assert not Path(env["GH_LOG"]).exists()


def test_github_release_failure_does_not_push_latest(release_repo):
    _, env, git = release_repo
    env["FAIL_GH"] = "1"
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "release failed" in result.stderr
    assert git("ls-remote", "--refs", "origin", "refs/tags/v1.2.3")
    assert Path(env["DOCKER_LOG"]).read_text().splitlines() == [
        f"build -t {IMAGE}:v1.2.3 -t {IMAGE}:latest -",
        f"push {IMAGE}:v1.2.3",
    ]
    assert (release_repo[0] / "README.md").read_text() == "| Versions | v1.2.3 |\n"


@pytest.mark.parametrize("change", ["unstaged", "staged", "untracked"])
@pytest.mark.parametrize("branch", ["main", "feature"])
def test_dirty_worktree_aborts_before_switching_or_publishing(
    release_repo, change, branch
):
    repo, env, git = release_repo
    if branch == "feature":
        git("checkout", "-b", branch)
    path = repo / ("new.txt" if change == "untracked" else "Dockerfile")
    path.write_text("local changes\n")
    if change == "staged":
        git("add", "Dockerfile")
    previous_commit = git("rev-parse", "HEAD")
    previous_status = git("status", "--porcelain")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "working tree must be clean" in result.stderr
    assert path.name in result.stderr
    assert path.read_text() == "local changes\n"
    assert git("status", "--porcelain") == previous_status
    assert git("branch", "--show-current") == branch
    assert git("rev-parse", "HEAD") == previous_commit
    assert not Path(env["GH_API_LOG"]).exists()
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_LOG"]).exists()


def test_ignored_files_do_not_block_release(release_repo):
    repo, _, _ = release_repo
    (repo / ".git/info/exclude").write_text("ignored.txt\n")
    (repo / "ignored.txt").write_text("ignored\n")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode == 0, result.stderr
    assert (repo / "ignored.txt").read_text() == "ignored\n"


@pytest.mark.parametrize("existing_main", [True, False])
def test_checkout_does_not_overwrite_ignored_files(release_repo, existing_main):
    repo, env, git = release_repo
    path = repo / "ignored.txt"
    path.write_text("tracked on main\n")
    git("add", "ignored.txt")
    git("commit", "--quiet", "-m", "Add file to main")
    git("push", "origin", "main")
    git("checkout", "-b", "feature")
    git("rm", "ignored.txt")
    git("commit", "--quiet", "-m", "Remove file from feature")
    if not existing_main:
        git("branch", "-d", "main")
    (repo / ".git/info/exclude").write_text("ignored.txt\n")
    path.write_text("preserve local file\n")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "ignored.txt" in result.stderr
    assert git("branch", "--show-current") == "feature"
    assert path.read_text() == "preserve local file\n"
    assert not Path(env["GH_API_LOG"]).exists()
    assert not Path(env["DOCKER_LOG"]).exists()


def test_fast_forward_does_not_overwrite_ignored_files(release_repo):
    repo, env, git = release_repo
    git("checkout", "-b", "remote-update")
    path = repo / "ignored.txt"
    path.write_text("tracked on remote\n")
    git("add", "ignored.txt")
    git("commit", "--quiet", "-m", "Add file on remote")
    git("push", "origin", "HEAD:refs/heads/main")
    git("checkout", "main")
    (repo / ".git/info/exclude").write_text("ignored.txt\n")
    path.write_text("preserve local file\n")
    previous_commit = git("rev-parse", "HEAD")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "ignored.txt" in result.stderr
    assert path.read_text() == "preserve local file\n"
    assert git("rev-parse", "HEAD") == previous_commit
    assert not Path(env["GH_API_LOG"]).exists()
    assert not Path(env["DOCKER_LOG"]).exists()


def test_changes_during_preparation_abort_release(release_repo):
    _, env, git = release_repo
    env["CHANGE_DURING_API"] = "1"
    previous_commit = git("rev-parse", "HEAD")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "working tree must be clean" in result.stderr
    assert git("rev-parse", "HEAD") == previous_commit
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_LOG"]).exists()


def test_branch_push_failure_prevents_publication(release_repo):
    _, env, git = release_repo
    remote = Path(git("remote", "get-url", "origin"))
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert git("show", "HEAD:README.md") == "| Versions | v1.2.3 |"
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_LOG"]).exists()


@pytest.mark.parametrize("checkout_args", [("--detach",), ("-b", "feature")])
def test_checks_out_main_before_publishing(release_repo, checkout_args):
    _, env, git = release_repo
    git("checkout", *checkout_args)
    result = run_release(release_repo, "1.2.3")
    assert result.returncode == 0, result.stderr
    assert git("branch", "--show-current") == "main"
    assert git("ls-remote", "--refs", "origin", "refs/heads/main").split()[0] == git(
        "rev-parse", "v1.2.3"
    )
    assert Path(env["DOCKER_LOG"]).exists()


def test_checks_out_remote_main_when_no_local_main_exists(release_repo):
    _, _, git = release_repo
    git("checkout", "-b", "feature")
    git("branch", "-d", "main")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode == 0, result.stderr
    assert git("branch", "--show-current") == "main"
    assert git("ls-remote", "--refs", "origin", "refs/heads/main").split()[0] == git(
        "rev-parse", "v1.2.3"
    )


def test_fast_forwards_main_before_release(release_repo, tmp_path):
    repo, env, git = release_repo
    remote = git("remote", "get-url", "origin")
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", "main", remote, str(other)],
        check=True,
        env=env,
    )
    subprocess.run(["git", "-C", str(other), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(other), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (other / "README.md").write_text("| Versions | v1.1.0 |\n")
    subprocess.run(
        ["git", "-C", str(other), "commit", "-am", "Remote update", "--quiet"],
        check=True,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(other), "push", "--quiet", "origin", "main"],
        check=True,
        env=env,
    )
    result = run_release(release_repo, "1.2.4", "--prerelease")
    assert result.returncode == 0, result.stderr
    assert (repo / "README.md").read_text() == "| Versions | v1.1.0, v1.2.4-rc.1 |\n"
    assert git("log", "-2", "--format=%s").splitlines()[1] == "Remote update"


def test_ahead_main_does_not_publish(release_repo):
    repo, env, git = release_repo
    (repo / "extra.txt").write_text("local commit\n")
    git("add", "extra.txt")
    git("commit", "--quiet", "-m", "Local commit")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "ahead of or has diverged" in result.stderr
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_API_LOG"]).exists()


def test_uses_push_destination_for_release_preparation(release_repo, tmp_path):
    _, env, git = release_repo
    push_remote = git("remote", "get-url", "origin")
    git("remote", "set-url", "origin", str(tmp_path / "unavailable-fetch-remote"))
    git("remote", "set-url", "--push", "origin", push_remote)
    result = run_release(release_repo, "1.2.3")
    assert result.returncode == 0, result.stderr
    assert git("ls-remote", "--refs", push_remote, "refs/heads/main").split()[0] == git(
        "rev-parse", "v1.2.3"
    )
    assert push_remote in Path(env["GH_API_LOG"]).read_text()


def test_checkout_conflict_aborts_without_overwriting_changes(release_repo):
    repo, env, git = release_repo
    git("checkout", "-b", "feature")
    (repo / "Dockerfile").write_text("feature change\n")
    git("add", "Dockerfile")
    git("commit", "--quiet", "-m", "Feature change")
    (repo / "Dockerfile").write_text("local edits\n")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert git("branch", "--show-current") == "feature"
    assert (repo / "Dockerfile").read_text() == "local edits\n"
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_API_LOG"]).exists()


@pytest.mark.parametrize(
    ("response", "proceeds"),
    [("y\n", True), ("YES\n", True), ("n\n", False), ("", False)],
)
def test_open_pull_requests_require_confirmation(release_repo, response, proceeds):
    _, env, git = release_repo
    env["OPEN_PRS"] = (
        "#12 First https://github.com/example/repo/pull/12\n"
        "#13 Second https://github.com/example/repo/pull/13\n"
    )
    previous_commit = git("rev-parse", "HEAD")
    result = run_release(release_repo, "1.2.3", input_text=response)
    assert (result.returncode == 0) == proceeds, result.stderr
    assert "https://github.com/example/repo/pull/12" in result.stdout
    assert "https://github.com/example/repo/pull/13" in result.stdout
    api_call = Path(env["GH_API_LOG"]).read_text()
    assert "--paginate" in api_call
    assert git("remote", "get-url", "--push", "origin") in api_call
    if not proceeds:
        assert git("rev-parse", "HEAD") == previous_commit
        assert not Path(env["DOCKER_LOG"]).exists()
        assert not Path(env["GH_LOG"]).exists()


def test_pull_request_lookup_failure_aborts_release(release_repo):
    _, env, git = release_repo
    env["FAIL_API"] = "1"
    previous_commit = git("rev-parse", "HEAD")
    result = run_release(release_repo, "1.2.3")
    assert result.returncode != 0
    assert "Could not retrieve open pull requests" in result.stderr
    assert git("rev-parse", "HEAD") == previous_commit
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not Path(env["GH_LOG"]).exists()
