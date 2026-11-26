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
commit=$(git rev-parse --verify 'HEAD^{commit}')

if [[ $prerelease == true && $version != *-* ]]; then
    prefix="refs/tags/v${version}-rc."
    remote_rc_tags=$(git ls-remote --tags --refs origin "${prefix}*")
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

tag="v${version}"
if [[ ${#tag} -gt 128 ]]; then
    echo "Version tag exceeds Docker's 128-character limit." >&2
    exit 2
fi

if git show-ref --verify --quiet "refs/tags/$tag"; then
    echo "Local tag $tag already exists." >&2
    exit 1
fi
remote_tag=$(git ls-remote --tags --refs origin "refs/tags/$tag")
if [[ -n $remote_tag ]]; then
    echo "Tag $tag already exists on origin." >&2
    exit 1
fi

image=texasaggie97/hover-dns-updater
build_tags=(-t "$image:$tag")
if [[ $prerelease == false ]]; then
    build_tags+=(-t "$image:latest")
fi

git archive --format=tar "$commit" | docker build "${build_tags[@]}" -
docker push "$image:$tag"
git tag "$tag" "$commit"
git push origin "refs/tags/$tag:refs/tags/$tag"
if [[ $prerelease == false ]]; then
    docker push "$image:latest"
fi

echo "Published $image:$tag and Git tag $tag at $commit."
