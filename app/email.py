"""Email sending utilities for verification and notifications."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def verification_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS)


def build_verification_url(token: str) -> str:
    return f"{settings.APP_BASE_URL}/auth/verify?token={token}"


async def send_verification_email(to_email: str, username: str, token: str) -> bool:
    """Send a verification email. Returns True on success, False on failure."""
    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — skipping verification email to %s", to_email)
        return False

    url = build_verification_url(token)

    msg = EmailMessage()
    msg["Subject"] = "Verify your email — plntxt"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Hi {username},\n\n"
        f"Please verify your email by visiting this link:\n\n"
        f"{url}\n\n"
        f"This link expires in {settings.VERIFICATION_TOKEN_EXPIRE_HOURS} hours.\n\n"
        f"— plntxt"
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_USE_TLS,
        )
        logger.info("Verification email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        return False


async def send_resend_verification_email(to_email: str, username: str, token: str) -> bool:
    """Resend verification email (same implementation, different log context)."""
    return await send_verification_email(to_email, username, token)
