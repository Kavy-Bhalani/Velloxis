import logging
from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.core.security import verify_firebase_token
from app.schemas.report import ReportRequest, ReportResponse
from app.db import queries

logger = logging.getLogger("velloxis.api.report")
router = APIRouter()

@router.post("/reports", response_model=ReportResponse)
async def submit_content_report(
    payload: ReportRequest,
    firebase_uid: str = Depends(verify_firebase_token)
):
    """
    Mandatory Google Play AI Safety Reporting Endpoint.
    Allows end users to flag objectionable AI-generated content.
    """
    user_id, _ = await queries.sync_user(firebase_uid)
    report_id = await queries.create_report(
        generation_id=payload.generation_id,
        user_id=user_id,
        reason=payload.reason,
        details=payload.details
    )

    logger.info(f"Report logged: id={report_id} reason={payload.reason} gen_id={payload.generation_id}")

    return ReportResponse(
        report_id=report_id,
        status="received",
        message="Thank you for reporting. This helps keep Velloxis safe for everyone."
    )
