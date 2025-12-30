import os
import re
import email
from email import policy
from dotenv import load_dotenv
import requests
import asyncio
import aiohttp
import hashlib

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Email Summarizer App")

# Simple in-memory cache for tone analysis
_tone_cache = {}

# Shared aiohttp session (created once, reused many times)
_aiohttp_session = None


async def get_aiohttp_session():
    """Get or create shared aiohttp session"""
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        _aiohttp_session = aiohttp.ClientSession()
    return _aiohttp_session


async def close_aiohttp_session():
    """Close shared aiohttp session"""
    global _aiohttp_session
    if _aiohttp_session and not _aiohttp_session.closed:
        await _aiohttp_session.close()
        _aiohttp_session = None


def strip_html_tags(html: str) -> str:
    clean = re.compile(r"<.*?>")
    return re.sub(clean, "", html)


def parse_eml(raw_bytes: bytes) -> str:
    """Optimized email parsing - prioritizes plain text over HTML"""
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    
    # Try to get plain text directly first for multipart messages
    if msg.is_multipart():
        for part in msg.iter_parts():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if "attachment" in content_disposition:
                continue
            
            # Prioritize plain text
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = payload.decode(errors="ignore").strip()
                        if text:
                            return text
                except Exception:
                    pass
        
        # Fall back to HTML if no plain text found
        for part in msg.iter_parts():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if "attachment" in content_disposition:
                continue
            
            if content_type == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(errors="ignore").strip()
                        if html:
                            return strip_html_tags(html)
                except Exception:
                    pass
    else:
        # Single part message
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(errors="ignore").strip()
                if text:
                    # Check if it's HTML
                    if msg.get_content_type() == "text/html":
                        return strip_html_tags(text)
                    return text
        except Exception:
            pass
    
    return ""


TONE_SYSTEM_PROMPT = (
    "You are an email tone analysis assistant. "
    "Identify the overall tone of the email in a short phrase "
    "(for example: formal, urgent, friendly, frustrated, promotional, neutral)."
    "Return in 2-3 words."
)


def get_cache_key(email_text: str) -> str:
    """Generate cache key from email content hash"""
    return hashlib.md5(email_text.encode()).hexdigest()


def truncate_email(email_text: str, max_chars: int = 2000) -> str:
    """Truncate very long emails to reduce tokens and API cost"""
    if len(email_text) > max_chars:
        return email_text[:max_chars] + "\n\n[Email truncated...]"
    return email_text


# ============================================================================
# ASYNC VERSION (Recommended for best performance)
# ============================================================================

async def summarizer_async(email_text: str) -> str:
    """
    Async tone analyzer using OpenRouter.
    Use this for concurrent processing of multiple emails.
    Return in 2-3 words
    """
    if not email_text.strip():
        return ""
    
    # Check cache first
    cache_key = get_cache_key(email_text)
    if cache_key in _tone_cache:
        return _tone_cache[cache_key]
    
    # Truncate long emails
    email_text = truncate_email(email_text)

    user_prompt = (
        "Analyze the tone of the following email. Limit answers to 2-3 words\n\n"
        "Return:\n"
        "1) One short label for the tone (e.g., 'formal and urgent', 'friendly and casual').\n"
        "2) Return in 2-3 words.\n\n"
        f"Email:\n{email_text}\n\nTone analysis:"
    )

    try:
        session = await get_aiohttp_session()  # Get shared session
        
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_TITLE,
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": TONE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 100,
            },
            timeout=aiohttp.ClientTimeout(total=90)  # Increased timeout
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Cache the result
            _tone_cache[cache_key] = content
            
            return content
                
    except Exception as e:
        error_msg = f"Tone unavailable (OpenRouter error: {e})"
        print(f">>> ERROR: {error_msg}")
        return error_msg


async def analyze_tone_batch_async(email_texts: list[str]) -> list[str]:
    """
    Analyze tone of multiple emails concurrently - MUCH faster than sequential processing.
    
    Example usage:
        emails = ["email1 text...", "email2 text...", "email3 text..."]
        tones = await analyze_tone_batch_async(emails)
    """
    tasks = [summarizer_async(email) for email in email_texts]
    return await asyncio.gather(*tasks, return_exceptions=True)


# ============================================================================
# SYNC VERSION (Drop-in replacement - maintains backward compatibility)
# ============================================================================

def summarizer(email_text: str) -> str:
    """
    Synchronous tone analyzer using OpenRouter with caching and truncation.
    Returns in 2-3 words.
    Drop-in replacement for your existing code.
    
    For better performance with multiple emails, use summarizer_async() instead.
    """
    if not email_text.strip():
        return ""
    
    # Check cache first
    cache_key = get_cache_key(email_text)
    if cache_key in _tone_cache:
        return _tone_cache[cache_key]
    
    # Truncate long emails
    email_text = truncate_email(email_text)

    user_prompt = (
        "Analyze the tone of the following email. Limit answers to 2-3 words\n\n"
        "Return:\n"
        "1) One short label for the tone (e.g., 'formal and urgent', 'friendly and casual').\n"
        "2) No short explanation.\n\n"
        f"Email:\n{email_text}\n\nTone analysis:"
    )

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_TITLE,
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": TONE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 100,
            },
            timeout=90,  # Increased timeout
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        # Cache the result
        _tone_cache[cache_key] = content
        
        return content
        
    except Exception as e:
        error_msg = f"Tone unavailable (OpenRouter error: {e})"
        print(f">>> ERROR: {error_msg}")
        return error_msg


def clear_cache():
    """Clear the tone cache - useful for testing or memory management"""
    global _tone_cache
    _tone_cache = {}
    print(">>> Tone cache cleared")


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example 1: Command line usage (backward compatible)
    filepath = input("Enter path to .eml file: ").strip()
    if not filepath.lower().endswith(".eml"):
        print("Error: Please provide a .eml file.")
        raise SystemExit(1)

    with open(filepath, "rb") as f:
        raw_bytes = f.read()

    email_text = parse_eml(raw_bytes)
    print("\n--- Extracted Email Text ---\n")
    print(email_text)

    print("\n--- Tone ---\n")
    tone_output = summarizer(email_text)
    print(tone_output)