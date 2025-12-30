import { useState } from "react";
import "./App.css";
import { UrgencyMeter } from "./UrgencyMeter";

function EmailRow({ email }) {
  return (
    <div className="email-row">
      <div>
        <div>
          <strong>{email.subject}</strong>
        </div>
        <div>{email.from_}</div>
        <div>Days left: {email.days_left}</div>

        {email.summary && (
          <div style={{ marginTop: "8px" }}>
            <strong>Summary:</strong>
            <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
              {email.summary}
            </pre>
          </div>
        )}

        {email.tone && (
          <div style={{ marginTop: "4px" }}>
            <strong>Tone:</strong> {email.tone}
          </div>
        )}
      </div>

      <UrgencyMeter level={email.urgency} />
    </div>
  );
}

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState("");
  const [tone, setTone] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [error, setError] = useState("");
  const [gmailItems, setGmailItems] = useState([]);

  const API_URL = "/api/summarize_email";
  const GMAIL_URL = "/api/gmail/urgent-emails";

  const handleFileSelect = (e) => {
    setFile(e.target.files[0]);
    setError("");
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a .eml file.");
      return;
    }

    setLoading(true);
    setError("");
    setSummary("");
    setTone("");
    setEmailBody("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        body: formData,
      });

      const text = await response.text();

      if (!response.ok) {
        try {
          const err = JSON.parse(text);
          setError(err.detail || "Something went wrong.");
        } catch {
          setError(text || "Something went wrong.");
        }
        setLoading(false);
        return;
      }

      const data = JSON.parse(text);
      setSummary(data.summary);
      setTone(data.tone);
      setEmailBody(data.raw_email);
    } catch (error) {
      setError("Unable to connect to backend.");
      console.error(error);
    }

    setLoading(false);
  };

  const handleFetchGmail = async () => {
    setError("");
    setLoading(true);

    try {
      const res = await fetch(GMAIL_URL);
      const text = await res.text();
      console.log("Gmail raw response:", text);

      if (!res.ok) {
        try {
          const err = JSON.parse(text);
          setError(err.detail || "Failed to fetch Gmail emails.");
        } catch {
          setError(text || "Failed to fetch Gmail emails.");
        }
        setLoading(false);
        return;
      }

      let data = null;
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }

      if (data && Array.isArray(data.items)) {
        setGmailItems(data.items);
      } else if (Array.isArray(data)) {
        setGmailItems(data);
      } else {
        setGmailItems([]);
        setError("No email data returned from Gmail endpoint.");
      }
    } catch (e) {
      console.error(e);
      setError("Unable to connect to Gmail endpoint.");
    }

    setLoading(false);
  };

  return (
    <>
      {/* Global loading overlay */}
      {loading && (
        <div className="loader-overlay">
          <div className="loader-spinner" />
        </div>
      )}

            {/* Idle breathing glow */}
        <div className="idle-glow" />

        <div className="ribbon-bar"> 
         <div>
            <div className="ribbon-title">EMAIL SUMMARIZER</div>
            <div className="ribbon-subtitle">
              created by Aadrish Guha Majumdar
           </div>
          </div>

          {/* Pearlescent triangle on the extreme right */}
          <div className="triangle-stage triangle-stage--header">
            <div className="triangle-shadow triangle-shadow--header" />
            <div className="triangle-jumper triangle-jumper--pearlescent" />
          </div>
        </div>
      

      <div className="app-root">
        <div className="page-band">
          <main className="container">
            <header className="header">
              <h1>Email Summarizer &amp; Tone Detector</h1>
              <p className="subtitle">
                Upload an email or pull urgent threads from Gmail to get a
                concise summary and tone analysis.
              </p>
            </header>

            <div className="upload-section">
              <div className="upload-row-top">
                <input type="file" accept=".eml" onChange={handleFileSelect} />
              </div>

              <div className="upload-row-bottom">
                <button onClick={handleUpload} disabled={loading}>
                  {loading ? "Processing..." : "Summarize Email"}
                </button>
                <button onClick={handleFetchGmail} disabled={loading}>
                  Fetch Gmail Urgent Emails
                </button>
              </div>
            </div>

            {error && <div className="error">{error}</div>}

            {(summary || tone || emailBody) && (
              <div className="output">
                <div className="box">
                  <h2>📌 Summary</h2>
                  <pre>{summary}</pre>
                </div>

                <div className="box">
                  <h2>🎭 Tone</h2>
                  <p>{tone}</p>
                </div>

                <div className="box">
                  <h2>📄 Extracted Email Text</h2>
                  <pre>{emailBody}</pre>
                </div>
              </div>
            )}

            {gmailItems.length > 0 && (
              <div className="output" style={{ marginTop: "20px" }}>
                <div className="box">
                  <h2>📬 Urgent Gmail Emails</h2>
                  {gmailItems.map((item) => (
                    <EmailRow key={item.id} email={item} />
                  ))}
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </>
  );
}

export default App;
