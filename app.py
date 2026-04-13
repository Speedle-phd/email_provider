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

# TODO: rate limiter and maybe some sort of human verification

app = Flask(__name__)
cors = CORS(
    app,
    resources={r"/api/*": {"origins": "http://localhost:5173"}},
    supports_credentials=True,
)
app.config['CORS_HEADERS'] = 'Content-Type'
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

    return jsonify(statuscode=200, description="Server is running and my email is: " + EMAIL)

@app.route("/api/v1/send_email", methods=["POST"])
def email():
    if request.method == "POST":
        name = request.json.get("name")
        email = request.json.get("email")
        subject = request.json.get("subject")
        message = request.json.get("message")
        x_auth = request.headers["x-auth-token"]
        
        if x_auth != "panda-punch#panda-bear-yeah":
            abort(401, description="User not authorized to send email")
        # Validate the input
        if validators.email(email) is not True:
            abort(400, description="Invalid email address!")
        if validators.between(len(name), min_val=3) is not True:
            abort(400, description="Name must be at least 3 characters")
        if validators.between(len(subject), min_val=5) is not True:
            abort(400, description="Subject must be at least 5 characters")
        if validators.between(len(message), min_val=10) is not True:
            abort(400, description="Message must be at least 10 characters")
        # Check if the user is authorized to send an email
        # auth = request.headers.get('x-auth-token')
        # if auth != "panda":
        #     abort(401, description="User not authorized to send email")
        try:
            send_email(name=name, message=message, email=email, subject=subject)
        except smtplib.SMTPRecipientsRefused as error:
            abort(501, description=f"Email could not be sent due to: {error}")
        except Exception as e:
            print(e.__class__)
            abort(400, description=f"An error occurred: {e}")
        return jsonify(statuscode=200, description="Email was sent successfully")


def send_email(name: str, message: str, email: str, subject: str):
    with smtplib.SMTP("smtp.ionos.de", 587, None, 30) as connection:
        connection.starttls()
        connection.login(user=EMAIL, password=PW)
        em = EmailMessage()
        em.set_content(message)
        em["To"] = EMAIL
        em["From"] = EMAIL
        em["Subject"] = f"Query from {name}: {subject} with email: {email}"
        connection.send_message(em)
    with smtplib.SMTP("smtp.ionos.de", 587, None, 30) as connection:
        connection.starttls()
        connection.login(user=EMAIL, password=PW)
        em2 = EmailMessage()
        em2["To"] = email
        em2["From"] = EMAIL
        em2["Subject"] = f"Re: {subject}"
        em2.set_content(f"Hello,\n\nThank you for reaching out to me. I will get back to you as soon as possible.\n\nBest regards")
        connection.send_message(em2)

if __name__ == "__main__":
    app.run(debug=True)
