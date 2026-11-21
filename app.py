import hmac
import os
import smtplib
import ssl
from email.message import EmailMessage

import validators
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def create_app():
    sender = os.environ.get("EMAIL", "")
    password = os.environ.get("EMAIL_PW", "")
    token = os.environ.get("MAIL_API_TOKEN", "")
    recipient = os.environ.get("MAIL_ALLOWED_RECIPIENT", "")
    if not sender or not password or validators.email(sender) is not True:
        raise ValueError("A valid EMAIL and EMAIL_PW are required")
    if len(token) < 32 or not token.isascii():
        raise ValueError("MAIL_API_TOKEN must contain at least 32 ASCII characters")
    if validators.email(recipient) is not True:
        raise ValueError("A valid MAIL_ALLOWED_RECIPIENT is required")

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    Limiter(
        get_remote_address,
        app=app,
        storage_uri="memory://",
        default_limits=["10 per minute"],
    )

    @app.route("/api/v1/send_email", methods=["POST"])
    def email():
        supplied_token = request.headers.get("x-auth-token", "")
        if not hmac.compare_digest(supplied_token.encode("utf-8"), token.encode("ascii")):
            return jsonify(error="Unauthorized"), 401

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {"email", "subject", "message"}:
            return jsonify(error="Expected email, subject and message"), 400
        if payload["email"] != recipient:
            return jsonify(error="Recipient is not allowed"), 403
        subject, message = payload["subject"], payload["message"]
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or len(subject) > 160
            or "\r" in subject
            or "\n" in subject
            or not isinstance(message, str)
            or not message.strip()
            or len(message) > 10000
        ):
            return jsonify(error="Invalid subject or message"), 400

        mail = EmailMessage()
        mail["To"] = recipient
        mail["From"] = sender
        mail["Subject"] = subject
        mail.set_content(message)
        try:
            with smtplib.SMTP("smtp.ionos.de", 587, timeout=30) as connection:
                connection.starttls(context=ssl.create_default_context())
                connection.login(sender, password)
                connection.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            app.logger.error("Email delivery failed: %s", type(exc).__name__)
            return jsonify(error="Email delivery failed"), 502
        return jsonify(status="sent")

    return app


app = create_app()
