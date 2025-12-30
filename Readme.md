# Email Summarizer & Tone Detector

An AI‑powered email assistant that summarizes emails, analyzes tone, and highlights urgent Gmail threads based on deadlines and days left.

---

## Features

- Upload **.eml** files and get:
  - Concise bullet‑point **summary**
  - Overall **tone** description
  - Raw extracted email text
- Connect to **Gmail** (OAuth) and:
  - Fetch recent inbox messages
  - Extract **deadlines** from email bodies
  - Compute **days left** and an **urgency score**
  - Display emails with an **urgency bar**
- Uses **OpenRouter** LLMs for summary + tone  
- Frontend built with **React + Vite**, backend with **FastAPI**

---

## Tech Stack

- **Backend**: FastAPI, Uvicorn, Requests, Google API Client, BeautifulSoup, python‑dotenv  
- **Frontend**: React, Vite  
- **LLM Provider**: OpenRouter (e.g. `meta-llama/llama-3.1-8b-instruct:free`)  
- **Auth**: Gmail OAuth (Installed App flow)

---

## Backend Setup (Overview)

- Create a virtual environment and install backend dependencies from `requirements.txt`.  
- Configure environment variables in `.env` (OpenRouter API key, model name, site URL, app title).  
- Obtain `credentials.json` from Google Cloud Console for a Desktop OAuth client and place it in the backend.  
- Start the FastAPI app with Uvicorn and open the interactive docs at `/docs`.  
- Visit `/gmail/dev-login` once in a browser to complete Gmail OAuth and generate `token.json`.

---

## Frontend Setup (Overview)

- Install frontend dependencies from `package.json` using your preferred package manager.  
- Run the Vite dev server and open the app in the browser.  
- Ensure API requests from the frontend point to the backend (via Vite proxy in development or full backend URL in production).

---

## Key API Endpoints

### `GET /`

Simple health check for the backend.

---

### `POST /summarize_email`

Upload a `.eml` file and get summary + tone.

- **Request**: `multipart/form-data` with field `file` (`.eml` file).
- **Response** (`EmailSummaryResponse`):

{
"summary": "bullet point summary...",
"tone": "tone label + short explanation...",
"raw_email": "plain text body..."
}


---

### `GET /gmail/dev-login`

- Starts the Gmail OAuth flow and stores `token.json` so that subsequent Gmail API calls can be made on behalf of the user.

---

### `GET /gmail/urgent-emails?max_results=N`

- Fetches up to `N` recent inbox messages, extracts body text, detects deadlines, computes days left and urgency, and runs summary + tone for each email.

Example response:

{
"items": [
{
"id": "18c9f...",
"subject": "Project deadline reminder",
"from_": "Manager manager@example.com",
"date": "Mon, 23 Dec 2025 10:00:00 +0000",
"snippet": "Just a reminder that the report is due...",
"days_left": 2,
"urgency": 4,
"summary": "- Report due on Dec 25...\n- Submit via email...",
"tone": "Formal and moderately urgent."
}
]
}


---

## Usage

- **Upload flow**
  - Select a `.eml` file in the UI.
  - Click **Summarize Email** to send it to `/summarize_email`.
  - The app displays:
    - Summary
    - Tone
    - Extracted email text.

- **Gmail flow**
  - Complete `/gmail/dev-login` once to authorize Gmail access.
  - Click **Fetch Gmail Urgent Emails**.
  - The app calls `/gmail/urgent-emails` and shows:
    - Subject, sender, days left
    - An urgency meter bar
    - Summary and tone for each email.

---

##**System Architecture Diagram**

<img width="1121" height="829" alt="diagram-export-12-31-2025-12_09_58-AM" src="https://github.com/user-attachments/assets/b3c925ef-2f16-4e8d-b6ca-06fb0222a2f0" />





