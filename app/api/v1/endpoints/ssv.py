import logging
from fastapi import APIRouter, Request, HTTPException, status, Response
from app.core.ssv_verifier import verify_admob_ssv
from app.core.config import get_settings
from app.db import queries

logger = logging.getLogger("velloxis.api.ssv")
settings = get_settings()

router = APIRouter()

@router.get("/webhooks/admob/ssv")
@router.post("/webhooks/admob/ssv")
async def admob_ssv_callback(request: Request):
    """
    AdMob Server-Side Verification (SSV) Webhook.
    Google sends query parameters for rewarded ad completion.
    """
    query_string = request.url.query
    query_params = dict(request.query_params)

    logger.info(f"Received AdMob SSV callback: tx_id={query_params.get('transaction_id')}")

    # Verify ECDSA signature
    is_valid = await verify_admob_ssv(query_string, query_params)
    if not is_valid:
        logger.warning("Rejected invalid AdMob SSV signature.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid SSV cryptographic signature."
        )

    # Extract user ID (passed in custom_data from Flutter client)
    firebase_uid = query_params.get("custom_data")
    transaction_id = query_params.get("transaction_id")
    reward_amount_str = query_params.get("reward_amount", "1")

    if not firebase_uid or not transaction_id:
        logger.warning("SSV missing required custom_data (firebase_uid) or transaction_id.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing custom_data or transaction_id."
        )

    try:
        reward_amount = int(reward_amount_str)
    except ValueError:
        reward_amount = 1

    # Atomic credit increment in database
    result = await queries.process_admob_reward(
        firebase_uid=firebase_uid,
        ssv_transaction_id=transaction_id,
        reward_amount=reward_amount,
        max_daily_rewards=settings.MAX_DAILY_REWARDS
    )

    if not result.get("success"):
        logger.warning(f"SSV reward not applied: {result.get('error')}")

    # AdMob expects 200 OK to acknowledge delivery
    return Response(content="OK", media_type="text/plain", status_code=200)
