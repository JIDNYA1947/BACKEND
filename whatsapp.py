"""
WhatsApp messaging layer.

In DEMO_MODE=true (default), no Twilio credentials are required. Messages
are simply logged/printed and returned as if sent, so the whole project
can be demoed and tested with zero external dependencies.

In DEMO_MODE=false, messages are sent via the Twilio WhatsApp Sandbox API.
Credentials are read only from environment variables - never hardcoded.
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger("whatsapp")
logging.basicConfig(level=logging.INFO)

SURVEY_TEMPLATE = (
    "Business Health Check\n\n"
    "1) How are sales?\n"
    "GOOD / FALLING\n\n"
    "2) EMI status?\n"
    "ON_TIME / MISSED\n\n"
    "3) Any issue?\n"
    "NO / YES\n\n"
    "Reply like:\n"
    "GOOD, ON_TIME, NO"
)


class WhatsAppSendError(Exception):
    """Raised when a real Twilio send fails or credentials are missing/invalid."""


def _get_twilio_client():
    """Lazily import & construct the Twilio client. Only used when DEMO_MODE=false."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise WhatsAppSendError(
            "DEMO_MODE is false but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are not set. "
            "Set DEMO_MODE=true to run without Twilio credentials, or configure them in .env."
        )
    try:
        from twilio.rest import Client
    except ImportError as e:
        raise WhatsAppSendError(
            "The 'twilio' package is not installed. Run: pip install twilio"
        ) from e

    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def send_whatsapp_message(to_phone_number: str, body: str) -> dict:
    """
    Send (or simulate sending) a WhatsApp message.

    Returns a dict describing the outcome: {status, demo_mode, sid (optional)}
    Never raises for DEMO_MODE. May raise WhatsAppSendError in live mode.
    """
    to_whatsapp = to_phone_number if to_phone_number.startswith("whatsapp:") else f"whatsapp:{to_phone_number}"

    if settings.DEMO_MODE:
        logger.info("[DEMO_MODE] Simulated WhatsApp message to %s:\n%s", to_whatsapp, body)
        return {"status": "simulated", "demo_mode": True, "sid": None, "to": to_whatsapp}

    client = _get_twilio_client()
    try:
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to_whatsapp,
            body=body,
        )
    except Exception as e:  # Twilio raises various TwilioRestException subclasses
        raise WhatsAppSendError(f"Failed to send WhatsApp message via Twilio: {e}") from e

    logger.info("Sent WhatsApp message to %s, sid=%s", to_whatsapp, message.sid)
    return {"status": "sent", "demo_mode": False, "sid": message.sid, "to": to_whatsapp}


def build_survey_message(business_name: Optional[str] = None) -> str:
    if business_name:
        return f"Hi, this is a check-in for {business_name}.\n\n{SURVEY_TEMPLATE}"
    return SURVEY_TEMPLATE
