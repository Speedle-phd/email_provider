import smtplib
import os
from email.message import EmailMessage
from flask import Flask, abort, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import validators

load_dotenv()
PW = os.getenv("EMAIL_PW")
EMAIL = os.getenv("EMAIL")
MONGO_URI = os.getenv("MONGO_URI")

# Validate required environment variables
if not EMAIL or not PW:
    raise ValueError("EMAIL and EMAIL_PW environment variables are required")

app = Flask(__name__)
cors = CORS(
    app,
    resources={r"/api/*": {"origins": os.getenv("ORIGIN", "*")}},
    supports_credentials=True,
)
app.config["CORS_HEADERS"] = "Content-Type"
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=MONGO_URI,
    strategy="fixed-window",
    default_limits=["10 per minute"],
)


@app.errorhandler(404)
def page_not_found(e):
    return jsonify(error=str(e)), 404


@app.errorhandler(500)
def internal_server_error(e):
    return jsonify(error=str(e)), 500


@app.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(401)
def unauthorized(e):
    return jsonify(error=str(e)), 401


@app.errorhandler(501)
def not_implemented(e):
    return jsonify(error=str(e)), 501


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        statuscode=200, description=f"Server is running and my email is: {EMAIL}"
    )


@app.route("/api/v1/send_email", methods=["POST"])
def email():
    # Validate request has JSON data
    if not request.json:
        abort(400, description="Request must contain JSON data")

    # Define allowed keys
    allowed_keys = {"email", "subject", "message", "cc", "bcc"}
    provided_keys = set(request.json.keys())

    # Check for any unauthorized keys
    invalid_keys = provided_keys - allowed_keys
    if invalid_keys:
        abort(
            400,
            description=f"Invalid keys in request: {', '.join(invalid_keys)}. Only allowed: {', '.join(sorted(allowed_keys))}",
        )

    # Extract required fields
    email = request.json.get("email")
    subject = request.json.get("subject")
    message = request.json.get("message")

    # Extract optional fields
    cc = request.json.get("cc")  # Can be string or list
    bcc = request.json.get("bcc")  # Can be string or list

    # Validate required fields are present
    if not email:
        abort(400, description="Email field is required")
    if not subject:
        abort(400, description="Subject field is required")
    if not message:
        abort(400, description="Message field is required")

    # Validate auth header exists
    x_auth = request.headers.get("x-auth-token")
    if not x_auth:
        abort(401, description="x-auth-token header is required")
    if x_auth != os.getenv("X-AUTH-TOKEN"):
        abort(401, description="User not authorized to send email")

    # Validate email formats
    if validators.email(email) is not True:
        abort(400, description="Invalid email address!")

    # Validate CC emails if provided
    if cc:
        cc_emails = cc if isinstance(cc, list) else [cc]
        for cc_email in cc_emails:
            if validators.email(cc_email) is not True:
                abort(400, description=f"Invalid CC email address: {cc_email}")

    # Validate BCC emails if provided
    if bcc:
        bcc_emails = bcc if isinstance(bcc, list) else [bcc]
        for bcc_email in bcc_emails:
            if validators.email(bcc_email) is not True:
                abort(400, description=f"Invalid BCC email address: {bcc_email}")

    # Validate field lengths
    if validators.between(len(subject), min_val=5) is not True:
        abort(400, description="Subject must be at least 5 characters")
    if validators.between(len(message), min_val=10) is not True:
        abort(400, description="Message must be at least 10 characters")

    try:
        send_email(message=message, email=email, subject=subject, cc=cc, bcc=bcc)
    except smtplib.SMTPRecipientsRefused as error:
        abort(501, description=f"Email could not be sent due to: {error}")
    except Exception as e:
        abort(400, description=f"An error occurred: {e}")
    return jsonify(statuscode=200, description="Email was sent successfully")


def send_email(message: str, email: str, subject: str, cc=None, bcc=None):
    if not EMAIL or not PW:
        raise ValueError("Email credentials not configured")
    with smtplib.SMTP("smtp.ionos.de", 587, None, 30) as connection:
        connection.starttls()
        connection.login(user=EMAIL, password=PW)
        em = EmailMessage()
        em.set_content(message)
        em["To"] = email
        em["From"] = EMAIL
        em["Subject"] = f"{subject}"

        # Add CC if provided
        if cc:
            if isinstance(cc, list):
                em["Cc"] = ", ".join(cc)
            else:
                em["Cc"] = cc

        # Add BCC if provided
        if bcc:
            if isinstance(bcc, list):
                em["Bcc"] = ", ".join(bcc)
            else:
                em["Bcc"] = bcc

        connection.send_message(em)
    # with smtplib.SMTP("smtp.ionos.de", 587, None, 30) as connection:
    #     connection.starttls()
    #     connection.login(user=EMAIL, password=PW)
    #     em2 = EmailMessage()
    #     em2["To"] = email
    #     em2["From"] = EMAIL
    #     em2["Subject"] = f"Re: {subject}"
    #     em2.set_content(
    #         f"Hello,\n\nThank you for reaching out to me. I will get back to you as soon as possible.\n\nBest regards"
    #     )
    #     connection.send_message(em2)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 8085)))
