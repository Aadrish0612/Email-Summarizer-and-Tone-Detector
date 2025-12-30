from pathlib import Path
from datetime import datetime, timezone
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Import ASYNC versions
from agents.summarizer_agent import summarizer as summarize_agent, summarizer_async
from agents.tone_agent import summarizer, summarizer_async as tone_async
from utils.email_parser import parse_eml
from models.schemas import EmailSummaryResponse
import re
import base64
from bs4 import BeautifulSoup

# Gmail API configuration
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


# Lifespan context manager for cleanup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(">>> Starting up...")
    yield
    # Shutdown - clean up aiohttp sessions
    print(">>> Shutting down, cleaning up...")
    from agents.summarizer_agent import close_aiohttp_session
    from agents.tone_agent import close_aiohttp_session as close_tone_session
    await close_aiohttp_session()
    await close_tone_session()
    print(">>> Cleanup complete")


# 1) CREATE APP
app = FastAPI(
    title="Email Summarizer + Tone Agent API",
    version="1.0.0",
    lifespan=lifespan
)

# 2) CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper Functions
def chunk_email_text(text: str, max_chunk_chars: int = 1500) -> list[str]:
    """Split long email into manageable chunks with overlap"""
    if len(text) <= max_chunk_chars:
        return [text]

    chunks = []
    words = text.split()
    current_chunk = []
    current_length = 0

    for word in words:
        test_length = current_length + len(word) + 1
        if test_length > max_chunk_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            overlap_start = max(0, len(current_chunk) - 50)  # 50 word overlap
            current_chunk = current_chunk[overlap_start:]
            current_length = sum(len(w) + 1 for w in current_chunk)
        current_chunk.append(word)
        current_length = test_length
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


# ASYNC Map-Reduce (MUCH FASTER)
async def map_reduce_summary_async(chunks: list[str]) -> str:
    """Map: summarize chunks concurrently → Reduce: summarize summaries"""
    if not chunks:
        return ""
    
    if len(chunks) == 1:
        return await summarizer_async(chunks[0])
    
    print(f">>> Map-reduce: {len(chunks)} chunks")
    
    # Map phase - ALL CHUNKS PROCESSED CONCURRENTLY
    chunk_tasks = [summarizer_async(chunk) for chunk in chunks]
    chunk_summaries = await asyncio.gather(*chunk_tasks, return_exceptions=True)
    
    # Filter out failures
    valid_summaries = [
        s for s in chunk_summaries 
        if isinstance(s, str) and not s.startswith("Summary unavailable")
    ]
    
    if not valid_summaries:
        return "Summary unavailable (all chunks failed)"
    
    # Reduce phase
    combined = " ".join(valid_summaries)
    final_summary = await summarizer_async(
        f"Summarize these email summaries briefly:\n\n{combined[:3000]}"
    )
    
    return final_summary[:800]


def get_gmail_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        print(">>> Refreshing token...")
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
    
    if not creds or not creds.valid:
        raise HTTPException(status_code=401, detail="Not authenticated with Gmail")

    service = build("gmail", "v1", credentials=creds)
    return service


def days_to_urgency(days_left: int) -> int:
    if days_left <= 0:
        return 6
    if days_left <= 1:
        return 5
    if days_left <= 3:
        return 4
    if days_left <= 7:
        return 3
    if days_left <= 14:
        return 2
    return 1


def _decode_part_body(body_dict: dict) -> str:
    data = body_dict.get("data")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_plain_text_body(message: dict) -> str:
    """Extract plain text from Gmail message"""
    payload = message.get("payload", {})
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    parts = payload.get("parts", [])

    if mime_type == "text/plain":
        return _decode_part_body(body)

    if mime_type == "text/html":
        html = _decode_part_body(body)
        try:
            return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
        except Exception:
            return html or ""

    def walk_parts(part_list):
        plain_candidates = []
        html_candidates = []
        for p in part_list or []:
            p_mime = p.get("mimeType", "")
            p_body = p.get("body", {})
            p_parts = p.get("parts", [])

            if p_mime == "text/plain":
                plain_candidates.append(_decode_part_body(p_body))
            elif p_mime == "text/html":
                html_candidates.append(_decode_part_body(p_body))
            
            if p_parts:
                sub_plain, sub_html = walk_parts(p_parts)
                if sub_plain:
                    plain_candidates.append(sub_plain)
                if sub_html:
                    html_candidates.append(sub_html)
        
        return " ".join(plain_candidates).strip(), " ".join(html_candidates).strip()

    plain, html = walk_parts(parts)

    if plain:
        return plain
    if html:
        try:
            return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
        except Exception:
            return html

    return ""


DATE_PATTERNS = [
    r"\b(\d{4}-\d{1,2}-\d{1,2})\b",
    r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
    r"\b(\d{1,2}-\d{1,2}-\d{4})\b",
    r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4})\b",
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{4})\b",
]

date_regexes = [re.compile(p) for p in DATE_PATTERNS]


def extract_deadline_date(text: str) -> datetime | None:
    """Extract deadline date from email text"""
    for regex in date_regexes:
        m = regex.search(text)
        if not m:
            continue
        s = m.group(1)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt
            except ValueError:
                continue
    return None


# Process single email with timeout protection
async def process_single_email(msg_data, service, timeout_seconds=60):
    """Process one email with timeout protection"""
    try:
        return await asyncio.wait_for(
            _process_email_logic(msg_data, service),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        print(f">>> TIMEOUT processing email {msg_data['id']}")
        return {
            "id": msg_data["id"],
            "subject": "(Processing timeout)",
            "from_": "(unknown)",
            "date": "",
            "snippet": "",
            "days_left": 999,
            "urgency": 1,
            "summary": "⚠️ Email too large to process (timeout)",
            "tone": "unavailable",
        }
    except Exception as e:
        print(f">>> ERROR processing email {msg_data['id']}: {e}")
        return {
            "id": msg_data["id"],
            "subject": "(Error)",
            "from_": "(unknown)",
            "date": "",
            "snippet": "",
            "days_left": 999,
            "urgency": 1,
            "summary": f"Error: {str(e)[:100]}",
            "tone": "unavailable",
        }


async def _process_email_logic(msg_data, service):
    """Main email processing logic"""
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=msg_data["id"], format="full")
        .execute()
    )

    headers = msg.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(no subject)")
    sender = next((h["value"] for h in headers if h["name"] == "From"), "(unknown sender)")
    date_header = next((h["value"] for h in headers if h["name"] == "Date"), "")
    
    print(f">>> Processing: {subject[:60]}...")
    
    now = datetime.now(timezone.utc)
    full_body = extract_plain_text_body(msg)
    
    # Truncate very long emails BEFORE processing
    if len(full_body) > 8000:
        print(f">>> WARNING: Large email ({len(full_body)} chars), truncating")
        full_body = full_body[:8000] + "\n\n[Email truncated due to length]"
    
    # Deadline detection
    deadline_dt = extract_deadline_date(full_body[:1000])  # Only scan first 1000 chars
    if deadline_dt:
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        days_left = (deadline_dt.date() - now.date()).days
    else:
        days_left = 999

    urgency = days_to_urgency(days_left)
    
    # Process with async (MUCH FASTER)
    try:
        chunks = chunk_email_text(full_body, max_chunk_chars=1500)
        print(f">>> Chunks: {len(chunks)}")
        
        # Process summary and tone IN PARALLEL
        summary_task = map_reduce_summary_async(chunks)
        summary = await asyncio.wait_for(summary_task, timeout=45)
        
        # Get tone from summary
        tone_task = tone_async(summary) if summary else ""
        tone = await asyncio.wait_for(tone_task, timeout=20) if summary else ""
        
    except asyncio.TimeoutError:
        print(">>> API timeout, using fallback")
        summary = "⚠️ Summary unavailable (processing timeout)"
        tone = "unavailable"
    except Exception as e:
        print(f">>> Processing error: {e}")
        summary = f"Error: {str(e)[:100]}"
        tone = "unavailable"

    print(f">>> ✓ Completed: {subject[:40]}...")
    
    return {
        "id": msg.get("id"),
        "subject": subject,
        "from_": sender,
        "date": date_header,
        "snippet": msg.get("snippet", ""),
        "days_left": days_left,
        "urgency": urgency,
        "summary": summary,
        "tone": tone,
    }


# ROUTES

@app.get("/gmail/dev-login")
def gmail_dev_login():
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return {"message": "Gmail authenticated. token.json created."}


@app.get("/gmail/refresh-token")
def refresh_token():
    """Force token refresh"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        return {"message": "Token deleted. Please visit /gmail/dev-login to re-authenticate"}
    return {"message": "No token file found"}


@app.get("/gmail/debug-inbox")
def debug_inbox():
    """See what's actually in your inbox right now"""
    service = get_gmail_service()
    
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=20
    ).execute()
    
    messages = results.get("messages", [])
    
    debug_data = []
    for m in messages[:10]:
        msg = service.users().messages().get(
            userId="me", 
            id=m["id"], 
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        
        debug_data.append({
            "id": m["id"],
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "labels": msg.get("labelIds", []),
            "internal_date": msg.get("internalDate", "")
        })
    
    return {"total_found": len(messages), "emails": debug_data}


@app.get("/gmail/urgent-emails")
async def get_urgent_emails(
    max_results: int = 10,
    include_updates: bool = True,  # Changed to True to see recent emails
    include_promotions: bool = False
):
    """Get urgent emails with async processing"""
    service = get_gmail_service()
    
    # Build query
    query_parts = []
    if not include_updates:
        query_parts.append("-category:updates")
    if not include_promotions:
        query_parts.append("-category:promotions")
    
    query = " ".join(query_parts) if query_parts else None

    print(f">>> Fetching {max_results} emails")
    print(f">>> Query: {query}")
    
    results = (
        service.users()
        .messages()
        .list(
            userId="me", 
            labelIds=["INBOX"],
            q=query,
            maxResults=max_results
        )
        .execute()
    )
    
    messages = results.get("messages", [])
    print(f">>> Found {len(messages)} messages")

    if not messages:
        return {"items": []}

    # Process all emails concurrently with timeout protection
    items = []
    for msg_data in messages:
        item = await process_single_email(msg_data, service, timeout_seconds=60)
        items.append(item)

    print(f">>> ✓ All {len(items)} emails processed")
    return {"items": items}


@app.post("/summarize_email", response_model=EmailSummaryResponse)
async def summarize_email(file: UploadFile = File(...)):
    """Upload a .eml file and get summary + tone"""
    if not file.filename.lower().endswith(".eml"):
        raise HTTPException(status_code=400, detail="Only .eml files are supported")

    raw_bytes = await file.read()

    # parse_eml returns a dict like {"subject": ..., "body": ...}
    parsed = parse_eml(raw_bytes)

    # If parse_eml sometimes returns a plain string, handle both cases
    if isinstance(parsed, dict):
        email_text = parsed.get("body", "")
    else:
        email_text = parsed

    if not isinstance(email_text, str):
        raise HTTPException(status_code=500, detail="Parsed email body is not text.")

    if not email_text.strip():
        raise HTTPException(status_code=422, detail="Email contains no readable text.")

    # Truncate if too long
    if len(email_text) > 8000:
        email_text = email_text[:8000]

    chunks = chunk_email_text(email_text, max_chunk_chars=1500)

    # Use async processing
    summary = await map_reduce_summary_async(chunks)
    tone = await tone_async(summary) if summary else ""

    return EmailSummaryResponse(
        summary=summary,
        tone=tone,
        raw_email=email_text,
    )



@app.get("/")
def home():
    return {"message": "Email Summarizer + Tone Agent API Running"}