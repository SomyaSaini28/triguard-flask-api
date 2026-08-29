"""Verification-email delivery with a safe local console mode and SMTP for production."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

from .config import Settings


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when a configured email provider cannot accept a verification message."""


def send_verification_email(app_settings: Settings, recipient: str, token: str) -> str | None:
    """Deliver a time-limited verification link, returning it only in local console mode."""
    verification_url = f"{app_settings.public_base_url}/verify-email?{urlencode({'token': token})}"
    if app_settings.email_delivery_mode == "console":
        logger.info("development_verification_email recipient=%s verification_url=%s", recipient, verification_url)
        return verification_url
    if app_settings.email_delivery_mode != "smtp" or not app_settings.smtp_host:
        raise EmailDeliveryError("Email delivery is not configured for this deployment.")

    message = EmailMessage()
    message["Subject"] = "Verify your TriGuard account"
    message["From"] = app_settings.email_from
    message["To"] = recipient
    message.set_content(
        "Verify your TriGuard planner account by opening this link within 24 hours:\n\n"
        f"{verification_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    try:
        with smtplib.SMTP(app_settings.smtp_host, app_settings.smtp_port, timeout=10) as smtp:
            if app_settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if app_settings.smtp_username and app_settings.smtp_password:
                smtp.login(app_settings.smtp_username, app_settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("The verification email could not be delivered.") from error
    return None
