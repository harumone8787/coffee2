import smtplib
from email.message import EmailMessage
from flask import current_app

def send_email(subject: str, recipient: str, body: str):
    smtp_server = current_app.config.get("SMTP_SERVER")
    smtp_port = current_app.config.get("SMTP_PORT", 587)
    smtp_username = current_app.config.get("SMTP_USERNAME")
    smtp_password = current_app.config.get("SMTP_PASSWORD")
    use_tls = current_app.config.get("SMTP_USE_TLS", True)
    sender = current_app.config.get("EMAIL_SENDER") or smtp_username

    if not (smtp_server and smtp_username and smtp_password):
        # Fail gracefully but inform in logs.
        current_app.logger.warning("SMTP is not configured; email not sent to %s", recipient)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
    return True
