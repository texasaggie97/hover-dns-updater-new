#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 VERSION [--prerelease]" >&2
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 2
fi

version=$1
prerelease=false
if [[ $# -eq 2 ]]; then
    if [[ $2 != --prerelease ]]; then
        usage
        exit 2
    fi
    prerelease=true
fi

if [[ ! $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$ ]]; then
    echo "Invalid version: use MAJOR.MINOR.PATCH with an optional prerelease suffix (without a leading v)." >&2
    exit 2
fi
if [[ $prerelease == false && $version == *-* ]]; then
    echo "A version with a prerelease suffix requires --prerelease." >&2
    exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
if ! command -v gh >/dev/null; then
    echo "GitHub CLI (gh) is required to create a release." >&2
    exit 1
fi
repository=$(git remote get-url --push origin)

require_clean_worktree() {
    local changes
    if ! changes=$(git status --porcelain=v1 --untracked-files=normal --ignore-submodules=none); then
        echo "Could not check the working tree; release aborted." >&2
        return 1
    fi
    if [[ -n $changes ]]; then
        printf 'The working tree must be clean before releasing:\n%s\n' "$changes" >&2
        return 1
    fi
}

prepare_release() {
    local current_branch pull_requests answer

    git fetch --no-tags "$repository" main
    if ! current_branch=$(git symbolic-ref --quiet HEAD) || [[ $current_branch != refs/heads/main ]]; then
        if git show-ref --verify --quiet refs/heads/main; then
            git checkout --no-overwrite-ignore main
        else
            git checkout --no-overwrite-ignore -b main FETCH_HEAD
        fi
    fi
    if ! git merge-base --is-ancestor HEAD FETCH_HEAD; then
        echo "Local main is ahead of or has diverged from the remote main; reconcile it before releasing." >&2
        return 1
    fi
    git merge --ff-only --no-overwrite-ignore FETCH_HEAD

    if ! pull_requests=$(GH_REPO="$repository" gh api --paginate \
        'repos/{owner}/{repo}/pulls?state=open&per_page=100' \
        --jq '.[] | "#\(.number) \(.title) \(.html_url)"'); then
        echo "Could not retrieve open pull requests; release aborted." >&2
        return 1
    fi
    if [[ -n $pull_requests ]]; then
        printf 'Open pull requests:\n%s\n' "$pull_requests"
        if ! read -r -p "Continue with these open pull requests? [y/N] " answer; then
            echo "No confirmation received; release aborted." >&2
            return 1
        fi
        if [[ ${answer,,} != y && ${answer,,} != yes ]]; then
            echo "Release aborted." >&2
            return 1
        fi
    fi
}

require_clean_worktree
prepare_release
require_clean_worktree

readme_versions_pattern='^\|[[:space:]]*Versions[[:space:]]*\|[[:space:]]*v([0-9]+\.[0-9]+\.[0-9]+)([[:space:]]*,[[:space:]]*v[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?[[:space:]]*\|$'
readme_versions_count=0
readme_release_version=
while IFS= read -r line || [[ -n $line ]]; do
    if [[ $line =~ ^\|[[:space:]]*Versions[[:space:]]*\| ]]; then
        ((readme_versions_count += 1))
        if [[ $line =~ $readme_versions_pattern ]]; then
            readme_release_version=${BASH_REMATCH[1]}
        fi
    fi
done < README.md
if [[ $readme_versions_count -ne 1 || -z $readme_release_version ]]; then
    echo "README.md must contain exactly one valid Versions row." >&2
    exit 1
fi

version_is_after() {
    local LC_ALL=C
    local candidate=$1 current=$2
    local -a candidate_parts current_parts
    local index
    IFS=. read -r -a candidate_parts <<< "$candidate"
    IFS=. read -r -a current_parts <<< "$current"
    for index in 0 1 2; do
        if (( ${#candidate_parts[index]} > ${#current_parts[index]} )); then
            return 0
        fi
        if (( ${#candidate_parts[index]} < ${#current_parts[index]} )); then
            return 1
        fi
        if [[ ${candidate_parts[index]} > ${current_parts[index]} ]]; then
            return 0
        fi
        if [[ ${candidate_parts[index]} < ${current_parts[index]} ]]; then
            return 1
        fi
    done
    return 1
}

if [[ $prerelease == true && $version != *-* ]]; then
    prefix="refs/tags/v${version}-rc."
    remote_rc_tags=$(git ls-remote --tags --refs "$repository" "${prefix}*")
    max_rc=0
    while IFS=$'\t' read -r _ ref; do
        [[ $ref == "$prefix"* ]] || continue
        number=${ref#"$prefix"}
        [[ $number =~ ^[1-9][0-9]*$ ]] || continue
        if (( ${#number} > 18 )); then
            echo "Remote prerelease number is too large: $ref" >&2
            exit 1
        fi
        if (( 10#$number > max_rc )); then
            max_rc=$((10#$number))
        fi
    done <<< "$remote_rc_tags"
    version="${version}-rc.$((max_rc + 1))"
fi

if [[ $prerelease == true ]]; then
    prerelease_base=${version%%-*}
    if version_is_after "$prerelease_base" "$readme_release_version"; then
        readme_version="v${readme_release_version}, v${version}"
    else
        readme_version="v${readme_release_version}"
    fi
else
    readme_version="v${version}"
fi

tag="v${version}"
if [[ ${#tag} -gt 128 ]]; then
    echo "Version tag exceeds Docker's 128-character limit." >&2
    exit 2
fi

if git show-ref --verify --quiet "refs/tags/$tag"; then
    echo "Local tag $tag already exists." >&2
    exit 1
fi
remote_tag=$(git ls-remote --tags --refs "$repository" "refs/tags/$tag")
if [[ -n $remote_tag ]]; then
    echo "Tag $tag already exists on origin." >&2
    exit 1
fi

image=texasaggie97/hover-dns-updater
build_tags=(-t "$image:$tag")
release_args=(--repo "$repository" --verify-tag --title "$tag" --generate-notes)
if [[ $prerelease == false ]]; then
    build_tags+=(-t "$image:latest")
else
    release_args+=(--prerelease)
fi

readme_tmp=$(mktemp README.md.XXXXXX)
trap 'rm -f "$readme_tmp"' EXIT
cp -p README.md "$readme_tmp"
awk -v version="$readme_version" '
    /^\|[[:space:]]*Versions[[:space:]]*\|/ {
        print "| Versions | " version " |"
        found++
        next
    }
    { print }
    END { if (found != 1) exit 1 }
' README.md > "$readme_tmp"
mv "$readme_tmp" README.md
trap - EXIT

if ! git diff --quiet -- README.md; then
    git commit --only -m "Update README versions for $tag" -- README.md
fi
commit=$(git rev-parse --verify 'HEAD^{commit}')
git push origin "HEAD:refs/heads/main"

git archive --format=tar "$commit" | docker build "${build_tags[@]}" -
docker push "$image:$tag"
git tag "$tag" "$commit"
git push origin "refs/tags/$tag:refs/tags/$tag"
gh release create "$tag" "${release_args[@]}"
if [[ $prerelease == false ]]; then
    docker push "$image:latest"
fi

echo "Published $image:$tag and GitHub release $tag at $commit."
