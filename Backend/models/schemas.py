from pydantic import BaseModel

class EmailSummaryResponse(BaseModel):
    summary: str
    tone: str
    raw_email: str
