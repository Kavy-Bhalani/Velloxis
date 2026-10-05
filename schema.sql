-- ============================================================================
-- PROJECT VELLOXIS: SUPABASE POSTGRESQL PRODUCTION SCHEMA & STORED PROCEDURES
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. USERS TABLE (Linked to Firebase Anonymous UID)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    last_seen_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    app_version VARCHAR(32) DEFAULT '1.0.0',
    is_blocked BOOLEAN DEFAULT FALSE,
    blocked_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON public.users(firebase_uid);

-- ============================================================================
-- 2. CREDIT ACCOUNTS TABLE (Authoritative Balance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.credit_accounts (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    balance INT NOT NULL DEFAULT 2 CHECK (balance >= 0), -- 2 Welcome Credits on signup
    lifetime_earned INT NOT NULL DEFAULT 2,
    lifetime_spent INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- ============================================================================
-- 3. CREDIT TRANSACTIONS LEDGER (Immutable Audit Trail)
-- ============================================================================
DO $$ BEGIN
    CREATE TYPE transaction_type AS ENUM (
        'WELCOME_BONUS',
        'REWARDED_AD',
        'GENERATION_DEBIT',
        'GENERATION_REFUND',
        'ADMIN_ADJUSTMENT'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.credit_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount INT NOT NULL, -- Positive for rewards/refunds, negative for debits
    type transaction_type NOT NULL,
    reference_id VARCHAR(128), -- AdMob SSV transaction_id or generation_id
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    CONSTRAINT uq_reference_transaction UNIQUE(user_id, reference_id, type)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON public.credit_transactions(user_id);

-- ============================================================================
-- 4. DAILY USAGE COUNTER (Protection Against Ad/Script Flooding)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.daily_usage (
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    usage_date DATE DEFAULT CURRENT_DATE,
    generation_count INT DEFAULT 0,
    rewarded_ad_count INT DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);

-- ============================================================================
-- 5. GENERATIONS LOG (Privacy-Safe: Hash Only, No Raw Prompts or Images)
-- ============================================================================
DO $$ BEGIN
    CREATE TYPE generation_status AS ENUM ('RESERVED', 'COMPLETED', 'FAILED', 'REFUNDED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.generations (
    id UUID PRIMARY KEY, -- Supplied by client or generated before call
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    model_alias VARCHAR(32) NOT NULL, -- e.g., 'fast', 'quality'
    provider VARCHAR(32) NOT NULL,    -- 'deepinfra', 'fal'
    provider_model_id VARCHAR(128) NOT NULL,
    status generation_status NOT NULL DEFAULT 'RESERVED',
    prompt_hash VARCHAR(64) NOT NULL, -- SHA-256 of prompt for rate/abuse detection
    estimated_cost_usd NUMERIC(8, 6) DEFAULT 0.000000,
    latency_ms INT DEFAULT 0,
    error_code VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_generations_user_created ON public.generations(user_id, created_at DESC);

-- ============================================================================
-- 6. CONTENT REPORTS (Mandatory Google Play AI Safety Policy Compliance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    generation_id UUID REFERENCES public.generations(id) ON DELETE SET NULL,
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    reason VARCHAR(64) NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    status VARCHAR(32) DEFAULT 'PENDING'
);

-- ============================================================================
-- 7. ATOMIC STORED PROCEDURES (Row-Lock Protected)
-- ============================================================================

-- Function: Register or sync anonymous user
CREATE OR REPLACE FUNCTION public.sync_anonymous_user(p_firebase_uid VARCHAR)
RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT id INTO v_user_id FROM public.users WHERE firebase_uid = p_firebase_uid;
    
    IF v_user_id IS NULL THEN
        INSERT INTO public.users (firebase_uid) VALUES (p_firebase_uid) RETURNING id INTO v_user_id;
        -- Create credit account with 2 welcome credits
        INSERT INTO public.credit_accounts (user_id, balance, lifetime_earned, lifetime_spent)
        VALUES (v_user_id, 2, 2, 0);
        -- Log transaction
        INSERT INTO public.credit_transactions (user_id, amount, type, reference_id)
        VALUES (v_user_id, 2, 'WELCOME_BONUS', 'welcome');
    ELSE
        UPDATE public.users SET last_seen_at = NOW() WHERE id = v_user_id;
    END IF;
    
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Reserve Generation Credit
CREATE OR REPLACE FUNCTION public.reserve_generation_credit(
    p_user_id UUID,
    p_cost INT,
    p_gen_id UUID,
    p_model_alias VARCHAR,
    p_provider VARCHAR,
    p_provider_model_id VARCHAR,
    p_prompt_hash VARCHAR,
    p_max_daily_generations INT DEFAULT 20
)
RETURNS BOOLEAN AS $$
DECLARE
    v_balance INT;
    v_daily_count INT;
BEGIN
    -- 1. Check daily generation limit
    INSERT INTO public.daily_usage (user_id, usage_date, generation_count, rewarded_ad_count)
    VALUES (p_user_id, CURRENT_DATE, 0, 0)
    ON CONFLICT (user_id, usage_date) DO NOTHING;

    SELECT generation_count INTO v_daily_count
    FROM public.daily_usage
    WHERE user_id = p_user_id AND usage_date = CURRENT_DATE
    FOR UPDATE;

    IF v_daily_count >= p_max_daily_generations THEN
        RAISE EXCEPTION 'DAILY_LIMIT_EXCEEDED';
    END IF;

    -- 2. Check and lock credit balance
    SELECT balance INTO v_balance
    FROM public.credit_accounts
    WHERE user_id = p_user_id
    FOR UPDATE;

    IF v_balance < p_cost THEN
        RETURN FALSE;
    END IF;

    -- 3. Deduct credit
    UPDATE public.credit_accounts
    SET balance = balance - p_cost,
        lifetime_spent = lifetime_spent + p_cost,
        updated_at = NOW()
    WHERE user_id = p_user_id;

    -- 4. Record ledger transaction
    INSERT INTO public.credit_transactions (user_id, amount, type, reference_id)
    VALUES (p_user_id, -p_cost, 'GENERATION_DEBIT', p_gen_id::text);

    -- 5. Record generation placeholder
    INSERT INTO public.generations (
        id, user_id, model_alias, provider, provider_model_id, status, prompt_hash
    ) VALUES (
        p_gen_id, p_user_id, p_model_alias, p_provider, p_provider_model_id, 'RESERVED', p_prompt_hash
    );

    -- 6. Increment daily counter
    UPDATE public.daily_usage
    SET generation_count = generation_count + 1
    WHERE user_id = p_user_id AND usage_date = CURRENT_DATE;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Refund Generation Credit (on failure)
CREATE OR REPLACE FUNCTION public.refund_generation_credit(
    p_user_id UUID,
    p_cost INT,
    p_gen_id UUID,
    p_error_code VARCHAR
)
RETURNS VOID AS $$
BEGIN
    -- 1. Refund credit balance
    UPDATE public.credit_accounts
    SET balance = balance + p_cost,
        lifetime_spent = lifetime_spent - p_cost,
        updated_at = NOW()
    WHERE user_id = p_user_id;

    -- 2. Record refund in ledger
    INSERT INTO public.credit_transactions (user_id, amount, type, reference_id)
    VALUES (p_user_id, p_cost, 'GENERATION_REFUND', p_gen_id::text);

    -- 3. Update generation record
    UPDATE public.generations
    SET status = 'REFUNDED',
        error_code = p_error_code,
        completed_at = NOW()
    WHERE id = p_gen_id;

    -- 4. Decrement daily usage
    UPDATE public.daily_usage
    SET generation_count = GREATEST(0, generation_count - 1)
    WHERE user_id = p_user_id AND usage_date = CURRENT_DATE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Finalize Generation (on success)
CREATE OR REPLACE FUNCTION public.finalize_generation_credit(
    p_gen_id UUID,
    p_estimated_cost_usd NUMERIC,
    p_latency_ms INT
)
RETURNS VOID AS $$
BEGIN
    UPDATE public.generations
    SET status = 'COMPLETED',
        estimated_cost_usd = p_estimated_cost_usd,
        latency_ms = p_latency_ms,
        completed_at = NOW()
    WHERE id = p_gen_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Credit Rewarded Ad via AdMob SSV
CREATE OR REPLACE FUNCTION public.reward_ad_ssv(
    p_firebase_uid VARCHAR,
    p_ssv_transaction_id VARCHAR,
    p_reward_amount INT DEFAULT 1,
    p_max_daily_rewards INT DEFAULT 10
)
RETURNS JSONB AS $$
DECLARE
    v_user_id UUID;
    v_daily_rewards INT;
    v_new_balance INT;
BEGIN
    -- 1. Get user_id
    SELECT id INTO v_user_id FROM public.users WHERE firebase_uid = p_firebase_uid;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'USER_NOT_FOUND';
    END IF;

    -- 2. Check daily ad limit
    INSERT INTO public.daily_usage (user_id, usage_date, generation_count, rewarded_ad_count)
    VALUES (v_user_id, CURRENT_DATE, 0, 0)
    ON CONFLICT (user_id, usage_date) DO NOTHING;

    SELECT rewarded_ad_count INTO v_daily_rewards
    FROM public.daily_usage
    WHERE user_id = v_user_id AND usage_date = CURRENT_DATE
    FOR UPDATE;

    IF v_daily_rewards >= p_max_daily_rewards THEN
        RETURN jsonb_build_object('success', false, 'error', 'DAILY_REWARD_LIMIT_EXCEEDED');
    END IF;

    -- 3. Add to ledger (Unique constraint prevents replay attacks on p_ssv_transaction_id)
    BEGIN
        INSERT INTO public.credit_transactions (user_id, amount, type, reference_id)
        VALUES (v_user_id, p_reward_amount, 'REWARDED_AD', p_ssv_transaction_id);
    EXCEPTION WHEN unique_violation THEN
        -- Already credited, idempotent return
        SELECT balance INTO v_new_balance FROM public.credit_accounts WHERE user_id = v_user_id;
        RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'idempotent', true);
    END;

    -- 4. Update balance
    UPDATE public.credit_accounts
    SET balance = balance + p_reward_amount,
        lifetime_earned = lifetime_earned + p_reward_amount,
        updated_at = NOW()
    WHERE user_id = v_user_id
    RETURNING balance INTO v_new_balance;

    -- 5. Increment daily count
    UPDATE public.daily_usage
    SET rewarded_ad_count = rewarded_ad_count + 1
    WHERE user_id = v_user_id AND usage_date = CURRENT_DATE;

    RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'idempotent', false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
