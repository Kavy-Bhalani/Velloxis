from typing import Optional, Literal
from pydantic import BaseModel, Field

class ReportRequest(BaseModel):
    generation_id: Optional[str] = Field(default=None, description="UUID of the reported generation")
    reason: Literal[
        "child_safety",
        "nudity_sexual",
        "violence_harm",
        "hate_harassment",
        "deceptive_impersonation",
        "other"
    ] = Field(..., description="Report category per Google Play AI safety guidelines")
    details: Optional[str] = Field(default=None, max_length=500, description="Optional user details")

class ReportResponse(BaseModel):
    report_id: str
    status: str = "received"
    message: str = "Thank you. Your report has been submitted for review."
