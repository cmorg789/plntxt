"""Email sending utilities for verification and notifications."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy import select

from app.config import settings

logger = logging.getLogger(__name__)


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


async def verification_token_expiry(cfg: dict | None = None) -> datetime:
    if cfg is None:
        cfg = await load_smtp_config()
    hours = int(cfg.get("verification_token_expire_hours", 48))
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def build_verification_url(token: str) -> str:
    return f"{settings.APP_BASE_URL}/auth/verify?token={token}"


async def load_smtp_config() -> dict:
    """Load SMTP settings from the config table, falling back to env vars."""
    try:
        from app.db import async_session
        from app.models.config import Config

        async with async_session() as session:
            result = await session.execute(select(Config).where(Config.key == "email"))
            config = result.scalar_one_or_none()
            if config and isinstance(config.value, dict) and config.value.get("smtp_host"):
                return config.value
    except Exception:
        logger.debug("Could not load email config from DB, falling back to env vars")

    # Return empty defaults — SMTP must be configured via admin UI
    return {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "noreply@plntxt.dev",
        "use_tls": True,
        "verification_token_expire_hours": 48,
    }


async def send_verification_email(to_email: str, username: str, token: str, *, cfg: dict | None = None) -> bool:
    """Send a verification email. Returns True on success, False on failure."""
    if cfg is None:
        cfg = await load_smtp_config()

    if not cfg.get("smtp_host"):
        logger.warning("SMTP not configured — skipping verification email to %s", to_email)
        return False

    url = build_verification_url(token)
    expire_hours = cfg.get("verification_token_expire_hours", 48)

    msg = EmailMessage()
    msg["Subject"] = "Verify your email — plntxt"
    msg["From"] = cfg.get("smtp_from", "noreply@plntxt.dev")
    msg["To"] = to_email
    msg.set_content(
        f"Hi {username},\n\n"
        f"Please verify your email by visiting this link:\n\n"
        f"{url}\n\n"
        f"This link expires in {expire_hours} hours.\n\n"
        f"— plntxt"
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["smtp_host"],
            port=int(cfg.get("smtp_port", 587)),
            username=cfg.get("smtp_user") or None,
            password=cfg.get("smtp_password") or None,
            start_tls=cfg.get("use_tls", True),
        )
        logger.info("Verification email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        return False
