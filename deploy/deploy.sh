#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fail() { log "ERROR: $*"; exit 1; }

# Parse the whole function before checkout replaces this script.
main() {
    local app_dir=/docker/email-service
    local state_dir=/docker/email-service-state
    local image=ghcr.io/speedle-phd/email_provider
    local source_label=org.opencontainers.image.source=https://github.com/Speedle-phd/email_provider
    local sha digest extra previous="" head
    # CI sends "<sha> <digest>"; manual runs may pass only the SHA.
    read -r sha digest extra <<<"${SSH_ORIGINAL_COMMAND:-$*}" || true
    [[ "${sha:-}" =~ ^[0-9a-f]{40}$ ]] || fail "Expected a full commit SHA"
    [[ -z "${digest:-}" || "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] ||
        fail "Expected an image digest of the form sha256:<64 hex>"
    [[ -z "${extra:-}" ]] || fail "Unexpected extra arguments"

    mkdir -p "$state_dir"
    exec 9>"$state_dir/.deploy.lock"
    flock -n 9 || fail "Another deploy is running"

    cd "$app_dir"
    [[ -f .env && -f .notification.env ]] || fail "Missing server environment files"
    [[ -z "$(git status --porcelain --untracked-files=no)" ]] ||
        fail "Tracked files have local changes; inspect git status before deploying"
    git fetch --quiet origin main
    git merge-base --is-ancestor "$sha" FETCH_HEAD || fail "Commit is not on origin/main"
    head="$(git rev-parse HEAD)"
    if [[ -f "$state_dir/deployed-commit" ]]; then
        previous="$(<"$state_dir/deployed-commit")"
        [[ "$previous" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid deployed-commit state"
        git cat-file -e "$previous^{commit}" || fail "Previous commit is missing locally"
    fi

    compose() {
        APP_IMAGE="$image" APP_TAG="$1" docker compose \
            --project-name email-service --env-file .env -f docker-compose.yaml "${@:2}"
    }
    start() {
        compose "$1" up -d --no-build --pull never --wait --wait-timeout 300
    }
    # Pulling by digest guarantees the bytes CI tested; the local SHA tag is
    # what Compose and rollback use afterwards.
    fetch() {
        if [[ -n "${digest:-}" ]]; then
            docker pull --quiet "$image@$digest" &&
                docker tag "$image@$digest" "$image:$sha"
        else
            log "No digest given; pulling by tag"
            docker pull --quiet "$image:$sha"
        fi
    }
    # Keep only the current and previous release images of this app.
    prune() {
        local tag
        docker image ls "$image" --format '{{.Tag}}' | sort -u | while read -r tag; do
            [[ "$tag" =~ ^[0-9a-f]{40}$ && "$tag" != "$sha" && "$tag" != "${previous:-}" ]] ||
                continue
            docker image rm "$image:$tag" >/dev/null || log "Could not remove $image:$tag"
        done
        docker image prune --force --filter "label=$source_label" >/dev/null
    }

    log "Deploying $sha${digest:+ ($digest)}"
    git -c advice.detachedHead=false checkout --quiet --detach "$sha"
    if fetch && start "$sha" && docker tag "$image:$sha" "$image:main"; then
        printf '%s\n' "$sha" > "$state_dir/deployed-commit.tmp"
        mv "$state_dir/deployed-commit.tmp" "$state_dir/deployed-commit"
        compose "$sha" ps
        prune || log "Image cleanup failed; the deployment itself succeeded"
        log "Deployed $sha"
    else
        log "Deployment failed; collecting diagnostics"
        compose "$sha" ps || log "Could not read container status"
        compose "$sha" logs --tail 40 email || log "Could not read container logs"
        if [[ -n "$previous" ]]; then
            log "Rolling back to $previous"
            git -c advice.detachedHead=false checkout --quiet --detach "$previous"
            if start "$previous"; then
                docker tag "$image:$previous" "$image:main"
                log "Previous release restored"
            else
                fail "Rollback failed; inspect the server immediately"
            fi
        else
            log "No recorded release to roll back to; removing the failed first deployment"
            compose "$sha" down
            git -c advice.detachedHead=false checkout --quiet --detach "$head"
        fi
        fail "Deployment of $sha failed"
    fi
}

main "$@"
exit
