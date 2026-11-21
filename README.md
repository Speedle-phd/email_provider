# Local notification email service

The service accepts authenticated requests from the host on `127.0.0.1:8085`
and sends only to the address in `MAIL_ALLOWED_RECIPIENT`. It uses the SMTP
account configured by `EMAIL` and `EMAIL_PW` in `.env`. The server defaults to
IONOS (`smtp.ionos.de`, port 587); set `SMTP_HOST` and `SMTP_PORT` in `.env` to
use another provider. The connection always uses STARTTLS, so the port must
support it (587 usually does; implicit-TLS port 465 does not work).

Store `MAIL_API_TOKEN` and `MAIL_ALLOWED_RECIPIENT` in `.notification.env`.
Both environment files must be readable only by the service operator and must
not be committed. Generate the token using a cryptographically secure random
generator. The token must contain at least 32 ASCII characters.

## Production (default)

Copy `.env.example` to `.env` and `.notification.env.example` to
`.notification.env`, then fill in your SMTP credentials, token, and recipient.

```sh
docker compose up -d
```

This uses the production image (and builds locally if it is unavailable).
Use `docker compose up -d --build` to explicitly build your current source.
Production has no source mount and no automatic reload.

## Development (explicit flag)

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

The development overlay builds locally and bind-mounts this directory at `/app`.
Edit Python files on the host: Gunicorn's polling reloader loads the changes
without rebuilding, including with Docker Desktop on Windows. The mount is
read-only inside the container; editing on the host still works. Changes to
dependencies require a rebuild; environment or Gunicorn configuration changes
require a restart. Debug mode and the interactive debugger remain disabled.

Both modes use the same environment files and port, so stop the active mode
before switching (`docker compose down`, or the same development flags followed
by `down`). Development still sends real email through IONOS; use a test account
and recipient if needed. This is an API service, not a browser UI.

## API and tests

Send a JSON POST to
`/api/v1/send_email` with the `x-auth-token` header and exactly these fields:
`email`, `subject`, and `message`. The email must match the configured recipient.
The response confirms SMTP submission, not final inbox delivery.

To send a real test email from the host, run this from the checkout. It reads
the token and recipient from `.notification.env`, so the token is not typed on
the command line, and the subshell keeps them out of your current shell:

```sh
(
  set -a; . ./.notification.env; set +a
  curl -sS -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8085/api/v1/send_email \
    -H 'Content-Type: application/json' \
    -H "x-auth-token: $MAIL_API_TOKEN" \
    -d "{\"email\":\"$MAIL_ALLOWED_RECIPIENT\",\"subject\":\"Test email\",\"message\":\"Test message from email-service.\"}"
)
```

A successful request returns `{"status":"sent"}` with `HTTP 200`. A `401`
response means the token is wrong; `403` means the recipient does not match
`MAIL_ALLOWED_RECIPIENT`; `502` means the SMTP server rejected the message or
could not be reached (see `docker compose logs email`).

`GET /health` returns `{"status":"ok"}` without authentication or sending mail.
It is exempt from rate limiting and verifies application startup, not SMTP
availability.

Run tests with the same production image used by CI (no real SMTP calls):

```sh
docker compose build
docker compose run --rm --no-deps -v ./test_app.py:/app/test_app.py:ro email python -B -m unittest -v test_app
```

## CI/CD

Pull requests and manual workflow runs lint the code and workflows, build the
production image, run tests, validate both Compose modes, and verify healthy
startup. Pushes to `main` also publish SHA-tagged images with a provenance
attestation to GHCR and deploy them by digest over restricted SSH. A weekly
workflow scans the published image for vulnerabilities, and another removes old
GHCR versions. See [DEPLOY.md](DEPLOY.md) for details, server setup, GitHub
secrets, and rollback.

Dependabot checks Python requirements, the pinned Docker base image digest and
GitHub Actions weekly and proposes updates as pull requests. Review the changes
and CI results before merging. Dependabot version updates are not a substitute
for enabling Dependabot alerts and security updates in repository settings.

## Dependencies

`requirements.in` lists the direct dependencies; `requirements.txt` is generated
from it with every transitive package pinned and hashed, and the image installs
it with `--require-hashes`. `requirements-lint.in`/`requirements-lint.txt` do
the same for CI's lint tools. After editing an `.in` file, regenerate its lock
file with the same Python as the image:

```sh
docker run --rm -v "$PWD:/src" -w /src python:3.15.2-slim-trixie sh -c \
  'pip install -q pip-tools && pip-compile -q --generate-hashes --strip-extras --allow-unsafe requirements.in'
```

Use `requirements-lint.in` in place of `requirements.in` for the lint tools.
Dependabot understands this layout and updates both files in one PR.

The rate limit is local to the service's single Gunicorn worker. Do not expose
the port to a network or increase the worker count without adding a shared
rate-limit store and reviewing authentication and transport security.
