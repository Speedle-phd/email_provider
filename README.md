# Local notification email service

The service accepts authenticated requests from the host on `127.0.0.1:8085`
and sends only to the address in `MAIL_ALLOWED_RECIPIENT`. It uses the IONOS
SMTP account configured by `EMAIL` and `EMAIL_PW` in `.env`.

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

`GET /health` returns `{"status":"ok"}` without authentication or sending mail.
It is exempt from rate limiting and verifies application startup, not SMTP
availability.

Run tests with the same production image used by CI (no real SMTP calls):

```sh
docker compose build
docker compose run --rm --no-deps -v ./test_app.py:/app/test_app.py:ro email python -B -m unittest -v test_app
```

## CI/CD

Pull requests and manual workflow runs build the production image, run tests,
validate both Compose modes, and verify healthy startup. Pushes to `main` also
publish SHA-tagged images to GHCR and automatically deploy over restricted SSH.
See [DEPLOY.md](DEPLOY.md) for server setup, GitHub secrets, and rollback.

The rate limit is local to the service's single Gunicorn worker. Do not expose
the port to a network or increase the worker count without adding a shared
rate-limit store and reviewing authentication and transport security.
