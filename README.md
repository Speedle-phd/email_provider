# Local notification email service

The service accepts authenticated requests from the host on `127.0.0.1:8085`
and sends only to the address in `MAIL_ALLOWED_RECIPIENT`. It uses the IONOS
SMTP account configured by `EMAIL` and `EMAIL_PW` in `.env`.

Store `MAIL_API_TOKEN` and `MAIL_ALLOWED_RECIPIENT` in `.notification.env`.
Both environment files must be readable only by the service operator and must
not be committed. Generate the token using a cryptographically secure random
generator. The token must contain at least 32 ASCII characters.

Start with `docker compose up -d --build`. Send a JSON POST to
`/api/v1/send_email` with the `x-auth-token` header and exactly these fields:
`email`, `subject`, and `message`. The email must match the configured recipient.
The response confirms SMTP submission, not final inbox delivery.

The rate limit is local to the service's single Gunicorn worker. Do not expose
the port to a network or increase the worker count without adding a shared
rate-limit store and reviewing authentication and transport security.
