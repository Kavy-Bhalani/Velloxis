import logging
import uuid
import json
from typing import Optional, Dict, Any, Tuple
from app.db.session import db_manager
from app.core.config import get_settings

logger = logging.getLogger("velloxis.queries")
settings = get_settings()

# In-memory mock storage for dev testing when running without live Supabase
_DEV_MOCK_USERS: Dict[str, Dict[str, Any]] = {
    "dev-mock-firebase-uid-001": {
        "id": "11111111-1111-1111-1111-111111111111",
        "firebase_uid": "dev-mock-firebase-uid-001",
        "balance": 5,
        "daily_gens": 0,
        "daily_ads": 0,
    }
}

async def sync_user(firebase_uid: str) -> Tuple[str, int]:
    """
    Syncs or creates user record, returns (user_id_uuid, balance).
    """
    pool = db_manager.pool
    if not pool:
        # Dev fallback
        if firebase_uid not in _DEV_MOCK_USERS:
            _DEV_MOCK_USERS[firebase_uid] = {
                "id": str(uuid.uuid4()),
                "firebase_uid": firebase_uid,
                "balance": 2,
                "daily_gens": 0,
                "daily_ads": 0,
            }
        u = _DEV_MOCK_USERS[firebase_uid]
        return u["id"], u["balance"]

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT public.sync_anonymous_user($1)", firebase_uid)
        balance = await conn.fetchval(
            "SELECT balance FROM public.credit_accounts WHERE user_id = $1",
            user_id
        )
        return str(user_id), int(balance or 0)

async def get_credit_balance(firebase_uid: str) -> Dict[str, Any]:
    pool = db_manager.pool
    if not pool:
        u = _DEV_MOCK_USERS.get(firebase_uid, {"balance": 2, "daily_gens": 0, "daily_ads": 0})
        return {
            "balance": u["balance"],
            "daily_generations_used": u["daily_gens"],
            "max_daily_generations": settings.MAX_DAILY_GENERATIONS,
            "daily_rewards_used": u["daily_ads"],
            "max_daily_rewards": settings.MAX_DAILY_REWARDS,
        }

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT u.id, c.balance,
                   COALESCE(d.generation_count, 0) as gen_count,
                   COALESCE(d.rewarded_ad_count, 0) as ad_count
            FROM public.users u
            JOIN public.credit_accounts c ON c.user_id = u.id
            LEFT JOIN public.daily_usage d ON d.user_id = u.id AND d.usage_date = CURRENT_DATE
            WHERE u.firebase_uid = $1
        """, firebase_uid)

        if not row:
            # Sync user if not yet initialized
            uid, bal = await sync_user(firebase_uid)
            return {
                "balance": bal,
                "daily_generations_used": 0,
                "max_daily_generations": settings.MAX_DAILY_GENERATIONS,
                "daily_rewards_used": 0,
                "max_daily_rewards": settings.MAX_DAILY_REWARDS,
            }

        return {
            "balance": row["balance"],
            "daily_generations_used": row["gen_count"],
            "max_daily_generations": settings.MAX_DAILY_GENERATIONS,
            "daily_rewards_used": row["ad_count"],
            "max_daily_rewards": settings.MAX_DAILY_REWARDS,
        }

async def reserve_credit(
    user_id: str,
    cost: int,
    gen_id: str,
    model_alias: str,
    provider: str,
    provider_model_id: str,
    prompt_hash: str,
    max_daily_generations: int
) -> bool:
    pool = db_manager.pool
    if not pool:
        # Dev fallback
        for u in _DEV_MOCK_USERS.values():
            if u["id"] == user_id:
                if u["daily_gens"] >= max_daily_generations:
                    raise Exception("DAILY_LIMIT_EXCEEDED")
                if u["balance"] < cost:
                    return False
                u["balance"] -= cost
                u["daily_gens"] += 1
                return True
        return False

    async with pool.acquire() as conn:
        try:
            success = await conn.fetchval(
                "SELECT public.reserve_generation_credit($1, $2, $3, $4, $5, $6, $7, $8)",
                uuid.UUID(user_id),
                cost,
                uuid.UUID(gen_id),
                model_alias,
                provider,
                provider_model_id,
                prompt_hash,
                max_daily_generations
            )
            return bool(success)
        except asyncpg.exceptions.RaiseException as e:
            if "DAILY_LIMIT_EXCEEDED" in str(e):
                raise Exception("DAILY_LIMIT_EXCEEDED")
            raise e

async def refund_credit(user_id: str, cost: int, gen_id: str, error_code: str):
    pool = db_manager.pool
    if not pool:
        for u in _DEV_MOCK_USERS.values():
            if u["id"] == user_id:
                u["balance"] += cost
                u["daily_gens"] = max(0, u["daily_gens"] - 1)
        return

    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT public.refund_generation_credit($1, $2, $3, $4)",
            uuid.UUID(user_id),
            cost,
            uuid.UUID(gen_id),
            error_code
        )

async def finalize_generation(gen_id: str, estimated_cost_usd: float, latency_ms: int):
    pool = db_manager.pool
    if not pool:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT public.finalize_generation_credit($1, $2, $3)",
            uuid.UUID(gen_id),
            estimated_cost_usd,
            latency_ms
        )

async def process_admob_reward(
    firebase_uid: str,
    ssv_transaction_id: str,
    reward_amount: int,
    max_daily_rewards: int
) -> Dict[str, Any]:
    pool = db_manager.pool
    if not pool:
        u = _DEV_MOCK_USERS.get(firebase_uid)
        if not u:
            return {"success": False, "error": "USER_NOT_FOUND"}
        if u["daily_ads"] >= max_daily_rewards:
            return {"success": False, "error": "DAILY_REWARD_LIMIT_EXCEEDED"}
        u["balance"] += reward_amount
        u["daily_ads"] += 1
        return {"success": True, "balance": u["balance"], "idempotent": False}

    async with pool.acquire() as conn:
        raw_result = await conn.fetchval(
            "SELECT public.reward_ad_ssv($1, $2, $3, $4)",
            firebase_uid,
            ssv_transaction_id,
            reward_amount,
            max_daily_rewards
        )
        return json.loads(raw_result) if isinstance(raw_result, str) else raw_result

async def create_report(
    generation_id: Optional[str],
    user_id: Optional[str],
    reason: str,
    details: Optional[str]
) -> str:
    pool = db_manager.pool
    report_id = str(uuid.uuid4())
    if not pool:
        logger.info(f"Dev report created: {report_id} reason: {reason}")
        return report_id

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO public.reports (id, generation_id, user_id, reason, details)
            VALUES ($1, $2, $3, $4, $5)
        """,
            uuid.UUID(report_id),
            uuid.UUID(generation_id) if generation_id else None,
            uuid.UUID(user_id) if user_id else None,
            reason,
            details
        )
        return report_id
