from __future__ import annotations
import os
import resend


def send_email(subject: str, html: str, to_emails: list[str]) -> dict:
    resend.api_key = os.environ['RESEND_API_KEY']
    params = {
        'from': os.environ['DIGEST_FROM_EMAIL'],
        'to': to_emails,
        'subject': subject,
        'html': html,
    }
    return resend.Emails.send(params)
