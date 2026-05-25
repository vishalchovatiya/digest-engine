from __future__ import annotations
import os
import resend


def _required_env(name: str) -> str:
    value = (os.environ.get(name) or '').strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set (or is empty). "
            f"Set it as a repository secret / .env value before sending."
        )
    return value


def send_email(subject: str, html: str, to_emails: list[str]) -> dict:
    resend.api_key = _required_env('RESEND_API_KEY')
    params = {
        'from': _required_env('DIGEST_FROM_EMAIL'),
        'to': to_emails,
        'subject': subject,
        'html': html,
    }
    return resend.Emails.send(params)
