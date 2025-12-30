import email
from email import policy
from .html_utils import strip_html_tags


def parse_eml(raw_bytes: bytes) -> dict:
    """
    Fully robust .eml parser for Gmail / Outlook messages.
    Extracts:
    - plain/text body (preferred)
    - text/html body (fallback, HTML stripped)
    - subject
    - from
    - to

    Returns a dict:
    {
        "subject": ...,
        "from": ...,
        "to": ...,
        "body": ...
    }
    """

    msg = email.message_from_bytes(raw_bytes, policy=policy.default)

    subject = msg.get("subject", "")
    sender = msg.get("from", "")
    receiver = msg.get("to", "")

    body_text = None
    html_text = None

    # Walk through all MIME parts & extract text
    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))

        # Skip attachments
        if "attachment" in content_disposition:
            continue

        # ✓ Prefer plain text content
        if content_type == "text/plain":
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    text = payload.decode(errors="ignore").strip()
                    if text:
                        body_text = text
                        break   # best version discovered → stop scanning
            except:
                pass

        # ✓ Fallback to HTML if plain text missing
        if content_type == "text/html":
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(errors="ignore").strip()
                    if html:
                        html_text = html
            except:
                pass

    # -------------------------
    # Final fallback selection
    # -------------------------

    # 1. Plain text found
    if body_text:
        return {
            "subject": subject,
            "from": sender,
            "to": receiver,
            "body": body_text
        }

    # 2. Only HTML found → strip tags
    if html_text:
        clean_html = strip_html_tags(html_text)
        return {
            "subject": subject,
            "from": sender,
            "to": receiver,
            "body": clean_html
        }

    # 3. Last fallback — decode entire payload
    try:
        payload = msg.get_payload(decode=True)
        if payload:
            fallback_text = payload.decode(errors="ignore")
            return {
                "subject": subject,
                "from": sender,
                "to": receiver,
                "body": fallback_text
            }
    except:
        pass

    # 4. No usable text found
    return {
        "subject": subject,
        "from": sender,
        "to": receiver,
        "body": ""
    }
