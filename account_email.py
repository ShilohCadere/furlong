"""Transactional account email delivery. No credentials or tokens are logged."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class EmailDeliveryError(RuntimeError):
    pass


def configured():
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("FURLONG_EMAIL_FROM")
                and os.environ.get("FURLONG_BASE_URL"))


def send_account_email(to, subject, body):
    """Send through Resend; fail closed if configuration or delivery fails."""
    if not configured():
        raise EmailDeliveryError("Email delivery is not configured")
    base = os.environ["FURLONG_BASE_URL"].rstrip("/")
    if not base.startswith("https://"):
        raise EmailDeliveryError("FURLONG_BASE_URL must use HTTPS")
    payload = json.dumps({
        "from": os.environ["FURLONG_EMAIL_FROM"],
        "to": [to],
        "subject": subject,
        "text": body,
    }).encode("utf-8")
    request = Request("https://api.resend.com/emails", data=payload, method="POST",
                      headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 201, 202):
                raise EmailDeliveryError("Email service rejected the message")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise EmailDeliveryError("Email delivery failed") from exc
