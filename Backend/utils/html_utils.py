import re
from html import unescape

def strip_html_tags(html: str) -> str:
    """
    Removes HTML tags, scripts, styles, and decodes HTML entities.
    Produces clean plain text from Gmail / Outlook HTML email bodies.
    """

    if not html:
        return ""

    # Remove <script> and <style> blocks completely
    html = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html)

    # Remove all remaining HTML tags
    text = re.sub(r"(?s)<.*?>", " ", html)

    # Unescape HTML entities (&amp; → &, &nbsp; → space, etc)
    text = unescape(text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text
