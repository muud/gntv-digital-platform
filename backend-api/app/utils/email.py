# utils/email.py
"""Async email sending abstraction.

Development uses a local SMTP server (host/port from env).
Production will use Alibaba DirectMail – the same interface works as long as
environment variables are set.
"""
import os
from email.message import EmailMessage
from aiosmtplib import send
from typing import List

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TLS = os.getenv("SMTP_TLS", "false").lower() == "true"

async def send_email(to: List[str] | str, subject: str, body: str, html: str | None = None) -> None:
    """Send an email.

    Args:
        to: Recipient address or list of addresses.
        subject: Email subject.
        body: Plain‑text body.
        html: Optional HTML body.
    """
    if isinstance(to, str):
        to = [to]
    message = EmailMessage()
    message["From"] = SMTP_USERNAME or f"noreply@{SMTP_HOST}"
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    await send(message, hostname=SMTP_HOST, port=SMTP_PORT, username=SMTP_USERNAME or None,
               password=SMTP_PASSWORD or None, start_tls=SMTP_TLS)
