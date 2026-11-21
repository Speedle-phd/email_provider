import os
import unittest
from unittest.mock import patch

os.environ.update(
    EMAIL="sender@example.com",
    EMAIL_PW="test-password",
    MAIL_API_TOKEN="a" * 64,
    MAIL_ALLOWED_RECIPIENT="recipient@example.com",
)

from app import create_app


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()
        self.headers = {"x-auth-token": "a" * 64}
        self.payload = {
            "email": "recipient@example.com",
            "subject": "Update report",
            "message": "No updates found.",
        }

    def post(self, payload=None, headers=None):
        return self.client.post(
            "/api/v1/send_email",
            json=self.payload if payload is None else payload,
            headers=self.headers if headers is None else headers,
        )

    @patch("app.smtplib.SMTP")
    def test_allowed_request_sends_only_to_configured_recipient(self, smtp):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        connection = smtp.return_value.__enter__.return_value
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with("sender@example.com", "test-password")
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertEqual(message["Subject"], "Update report")

    @patch("app.smtplib.SMTP")
    def test_unauthorized_requests_do_not_send(self, smtp):
        self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={"x-auth-token": "wrong"}).status_code, 401)
        smtp.assert_not_called()

    @patch("app.smtplib.SMTP")
    def test_other_recipients_and_cc_are_rejected(self, smtp):
        self.assertEqual(self.post({**self.payload, "email": "other@example.com"}).status_code, 403)
        self.assertEqual(self.post({**self.payload, "cc": "other@example.com"}).status_code, 400)
        smtp.assert_not_called()

    @patch("app.smtplib.SMTP")
    def test_invalid_content_is_rejected(self, smtp):
        for value in ("", "Hello\nBcc: other@example.com", 5):
            with self.subTest(subject=value):
                self.assertEqual(self.post({**self.payload, "subject": value}).status_code, 400)
        self.assertEqual(self.post({**self.payload, "message": "x" * 20000}).status_code, 413)
        smtp.assert_not_called()

    @patch("app.smtplib.SMTP", side_effect=OSError("sensitive SMTP details"))
    def test_delivery_errors_are_not_exposed(self, smtp):
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b"sensitive", response.data)

    def test_missing_or_weak_configuration_fails_at_startup(self):
        with patch.dict(os.environ, {"MAIL_API_TOKEN": "short"}), self.assertRaises(ValueError):
            create_app()
        for port in ("", "abc", "0", "70000"):
            with (
                self.subTest(port=port),
                patch.dict(os.environ, {"SMTP_PORT": port}),
                self.assertRaises(ValueError),
            ):
                create_app()

    @patch("app.smtplib.SMTP")
    def test_smtp_server_defaults_to_ionos_and_is_configurable(self, smtp):
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(smtp.call_args.args, ("smtp.ionos.de", 587))
        with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "2587"}):
            client = create_app().test_client()
        client.post("/api/v1/send_email", json=self.payload, headers=self.headers)
        self.assertEqual(smtp.call_args.args, ("smtp.example.com", 2587))

    @patch("app.smtplib.SMTP")
    def test_health_checks_are_public_and_do_not_consume_mail_rate_limit(self, smtp):
        for _ in range(15):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {"status": "ok"})
        for _ in range(10):
            self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={}).status_code, 429)
        smtp.assert_not_called()

    @patch("app.smtplib.SMTP")
    def test_requests_are_rate_limited(self, smtp):
        for _ in range(10):
            self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={}).status_code, 429)
        smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
