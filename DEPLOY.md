# Deployment

## Pipeline

Pull requests, pushes to `main`, and manual runs execute the checks in
[ci.yml](.github/workflows/ci.yml):

- **Lint:** ruff (Python), zizmor (workflow security), actionlint (workflow
  syntax) and shellcheck (`deploy/deploy.sh`).
- **Checks:** Compose validation, production image build, unit tests inside that
  image, healthy startup with test-only settings, and a non-blocking Trivy
  report of HIGH/CRITICAL vulnerabilities in the job log.

Only pushes to `main` publish `ghcr.io/speedle-phd/email_provider:<full-sha>`
and `:main`, record a signed build provenance attestation, then deploy over SSH.
Manual runs perform checks only. The tested image is transferred between jobs
as a one-day artifact and pushed without rebuilding. CI sends the server the
commit SHA **and the pushed image digest**; the server pulls by digest, so it
runs exactly the bytes that were tested even if a tag were overwritten.
All actions are pinned to full commit SHAs with the version in a comment.
The Trivy and actionlint container images are pinned by digest in the
workflows' `env:` blocks; Dependabot does not update those, so bump them by hand.

[security.yml](.github/workflows/security.yml) scans the published `:main` image
every Monday: all findings go to the repository's **Security → Code scanning**
tab, and the run fails (sending GitHub's failure email) when a HIGH or CRITICAL
vulnerability has a fix available.
[cleanup-images.yml](.github/workflows/cleanup-images.yml) deletes all but the
newest 40 GHCR package versions every Sunday (about 20 releases, since each
release also stores an attestation).

To check an image's provenance yourself (requires the GitHub CLI):

```sh
gh attestation verify oci://ghcr.io/speedle-phd/email_provider:<full-sha> --owner Speedle-phd
```
Pushes to `main` that change only Markdown files or `.github/dependabot.yml`
skip the pipeline, so they neither rebuild nor restart production.
Dependabot opens weekly update PRs for pip, the Docker base image (including its
pinned digest), and GitHub Actions. It waits three days after a release before
proposing it, groups minor/patch pip updates and all action updates into one PR
each, and prefixes commits with `deps`. Review and merge those PRs only after CI
passes; merging deploys automatically. Enable
Dependabot alerts and security updates in repository settings separately.

Production is the default [Compose file](docker-compose.yaml). There is no
database or persistent application data to back up. SMTP settings and the API
token stay on the server. Back these files up securely outside the checkout;
the deploy script neither copies secrets nor changes them. After a successful
deploy the script removes this app's older release images from the server,
keeping only the current and previous SHA (the rollback target). It never
touches other images.

### Required checks on `main` (repository setting)

To stop untested commits from deploying, add a ruleset under **Settings →
Rules → Rulesets → New branch ruleset**: target the default branch, enable
**Require a pull request before merging** and **Require status checks to
pass**, and add the checks `Lint Python, workflows, and deploy script` and
`Production image, tests, and startup`. Direct pushes to `main` are then
rejected; changes land through pull requests.

## Server preparation (Linux, amd64)

Docker Engine, the Compose v2 plugin (v2.24 or newer), Git, Bash, and `flock`
must be installed. Port 8085 remains bound to `127.0.0.1`; do not expose this
notification API publicly or add a public reverse proxy.

Run as an administrator, reusing the `deploy` user if it already exists:

The commands below are for a **new installation**. For the existing checkout
at `/docker/email-service`, do not clone over it, overwrite environment files,
or regenerate the API token. Preserve the Compose project name `email-service`
so deployment updates the existing service rather than creating another stack.

```sh
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /docker/email-service /docker/email-service-state
sudo chown deploy:deploy /docker/email-service /docker/email-service-state
sudo -u deploy git clone https://github.com/Speedle-phd/email_provider.git /docker/email-service
sudo -u deploy cp /docker/email-service/.env.example /docker/email-service/.env
sudo -u deploy cp /docker/email-service/.notification.env.example /docker/email-service/.notification.env
sudo chmod 600 /docker/email-service/.env /docker/email-service/.notification.env
```

Fill in both environment files before deploying. Generate `MAIL_API_TOKEN`
with a cryptographically secure generator, for example:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Docker group membership is root-equivalent; the SSH restriction below limits
the CI key, not the deploy user's operating-system privileges. Log in again
after changing group membership. For a private repository, configure a
separate read-only repository key/token for `git fetch`; do not reuse the
restricted CI key.

## Restricted SSH key and GitHub settings

Generate a dedicated Ed25519 key on your own machine:

```sh
ssh-keygen -t ed25519 -f email_provider_deploy -C github-actions-email-provider
```

Use an empty passphrase for this dedicated automation key. Keep the private
key out of this repository. Add its public key to the deploy user's
`/home/deploy/.ssh/authorized_keys` as one line:

```text
command="/bin/bash /docker/email-service/deploy/deploy.sh",restrict ssh-ed25519 <public-key> github-actions-email-provider
```

The `.ssh` directory must be owned by `deploy` with mode 700, and
`authorized_keys` with mode 600. The script accepts only a full 40-character
commit SHA already on `origin/main`. It refuses tracked local edits and takes
an exclusive lock. Ensure your administrator key login works before disabling
SSH password authentication.

Set these GitHub Actions secrets (prefer the `production` environment):

| Secret | Value |
| --- | --- |
| `SSH_HOST` | Server hostname or IP, no username |
| `SSH_PRIVATE_KEY` | Entire dedicated private key |
| `SSH_KNOWN_HOSTS` | Verified `<host> ssh-ed25519 <host-public-key>` line |

Get the host public key directly from the server's
`/etc/ssh/ssh_host_ed25519_key.pub`, over an already trusted connection. Use
exactly the host spelling from `SSH_HOST`; CI uses port 22 and strict checking.
Do not trust an unverified `ssh-keyscan` result.

The `production` environment records deployments. Leave required reviewers
disabled for automatic deployment; add reviewers there to require approval.
The built-in `GITHUB_TOKEN` publishes GHCR images, so no publishing token is
needed. After the first publish, make the GHCR package **public** in its package
settings (public repository visibility alone is not sufficient). If you keep
it private, log in to GHCR on the server as `deploy` with a `read:packages` token.

## Bootstrap and verify

**Upgrading a server that runs the older `deploy.sh`:** the old script accepts
only a SHA, so the first CI deploy that also sends a digest fails before
touching anything (production keeps running). Run the new script once by hand,
as `deploy`, with that commit's SHA; afterwards the server has the new script
and CI deploys work again:

```sh
cd /docker/email-service
git fetch origin main && git show FETCH_HEAD:deploy/deploy.sh > /tmp/deploy.sh
bash /tmp/deploy.sh <full-sha-of-the-failed-run> && rm /tmp/deploy.sh
```

Commit and push this setup yourself. CI can publish before the server has the
script; prepare the checkout above (or update an existing clean checkout)
to a commit containing it, then rerun the failed deployment job. Ensure the
image package is public before rerunning.

The first successful scripted deployment establishes rollback state.
Run as `deploy`, substituting the full SHA of the successful image build:

```sh
cd /docker/email-service
bash deploy/deploy.sh <full-sha>
docker compose ps
curl --fail http://127.0.0.1:8085/health
```

Use the script for the first deployment rather than starting unrecorded
containers manually. If migrating an already-running instance, schedule a
maintenance window: without recorded state, a failed first deploy removes
the failed stack and restores the checkout, but cannot restore an unrecorded
old image.

## Deploys and rollback

Each deploy fetches `main`, checks out the requested SHA, pulls its image by
digest (or by SHA tag when run manually without a digest) without building,
then waits up to 300 seconds for `/health`. Pull or startup
failure restores the recorded previous checkout and cached image, and the CI
job still fails. A rollback failure is reported explicitly.

State lives at `/docker/email-service-state/deployed-commit`, outside Git.
On success the script atomically records the SHA and retags the local image
as `:main`. A plain `docker compose up -d` therefore uses the deployed image
already cached on the server. `docker compose pull` explicitly fetches the
registry's newest `:main`; use the script to avoid bypassing rollback state.

To deploy or roll back manually, as `deploy`:

```sh
cd /docker/email-service
bash deploy/deploy.sh <full-sha-on-main>
```

The image for that SHA must still exist in GHCR. Keep current and previous
release images available on the server. Do not use `--build` for automated
deployment or edit tracked files on the server.

Diagnostics:

```sh
docker compose ps
docker compose logs --tail 40 email
cat /docker/email-service-state/deployed-commit
```

Application health does not prove SMTP delivery. Unit tests mock SMTP;
verify a real authenticated notification separately after server setup.
Rollback does not change credentials or undo mail already submitted.
