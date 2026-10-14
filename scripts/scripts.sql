BEGIN;

CREATE TABLE IF NOT EXISTS claim_statuses (
    status VARCHAR(25) PRIMARY KEY
);
INSERT INTO claim_statuses(status) VALUES ('ACTIVE'), ('SUPERSEDED'), ('FORGOTTEN') ON CONFLICT (status) DO NOTHING;

CREATE TABLE IF NOT EXISTS source_types (
    source_type VARCHAR(25) PRIMARY KEY
);
INSERT INTO source_types(source_type) VALUES ('EXPLICIT'), ('DERIVED'), ('INFERRED_CONFIRMED') ON CONFLICT (source_type) DO NOTHING;
-- Confirm your MCP insight confirmation uses INFERRED_CONFIRMED or DERIVED.

CREATE TABLE IF NOT EXISTS claims (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    category VARCHAR(25) NOT NULL,
    value TEXT NOT NULL,
    source_type TEXT NOT NULL REFERENCES source_types(source_type),
    source_utterance TEXT NOT NULL,
    status VARCHAR(25) NOT NULL REFERENCES claim_statuses(status),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superseded_by_claim_id INTEGER REFERENCES claims(id),
    memory_key TEXT NOT NULL DEFAULT (gen_random_uuid()::text)
);

ALTER TABLE claims ADD COLUMN IF NOT EXISTS memory_key TEXT;
ALTER TABLE claims ALTER COLUMN memory_key SET DEFAULT (gen_random_uuid()::text);

UPDATE claims
SET memory_key = gen_random_uuid()::text
WHERE memory_key IS NULL;
ALTER TABLE claims ALTER COLUMN memory_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_memory_key
    ON claims (user_id, category, memory_key)
    WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_claims_user_category_status
    ON claims (user_id, category, status);
CREATE INDEX IF NOT EXISTS idx_claims_user_memory_history
    ON claims (user_id, memory_key, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    event_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome TEXT,
    source_type TEXT NOT NULL DEFAULT 'EXPLICIT',
    source_utterance TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id UUID,
    request_hash TEXT,
    CONSTRAINT valid_event_attributes
        CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT valid_event_identity
        CHECK (
            LENGTH(TRIM(domain)) > 0
            AND LENGTH(TRIM(event_type)) > 0
            AND LENGTH(TRIM(subject)) > 0
            AND LENGTH(TRIM(user_id)) > 0
            AND LENGTH(TRIM(source_utterance)) > 0
        )
);
ALTER TABLE events ADD COLUMN IF NOT EXISTS request_id UUID;
ALTER TABLE events ADD COLUMN IF NOT EXISTS request_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_events_user_domain_time
    ON events (user_id, domain, occurred_at DESC, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_user_request
    ON events (user_id, request_id) WHERE request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS insights (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    adjustment TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    confirmed_claim_id BIGINT REFERENCES claims(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CONSTRAINT valid_insight_status CHECK (
        status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'REJECTED')
    ),
    CONSTRAINT insight_decision_consistency CHECK (
        (status = 'PENDING_CONFIRMATION'
            AND decided_at IS NULL AND confirmed_claim_id IS NULL)
        OR (status = 'REJECTED'
            AND decided_at IS NOT NULL AND confirmed_claim_id IS NULL)
        OR (status = 'CONFIRMED'
            AND decided_at IS NOT NULL AND confirmed_claim_id IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_insights_user_rule_subject_adjustment
    ON insights (user_id, domain, insight_type, subject, adjustment);
CREATE INDEX IF NOT EXISTS idx_insights_user_status
    ON insights (user_id, status);

CREATE TABLE IF NOT EXISTS insight_evidence (
    insight_id BIGINT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    event_id BIGINT NOT NULL REFERENCES events(id),
    PRIMARY KEY (insight_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_insight_evidence_event_id
    ON insight_evidence (event_id);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS pending_clarifications (
    conversation_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    original_question TEXT NOT NULL,
    category TEXT NOT NULL,
    candidate_memory_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    clarification_question TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '15 minutes'),
    target_memory_key UUID,
    FOREIGN KEY (conversation_id, user_id)
        REFERENCES conversations(id, user_id) ON DELETE CASCADE,
    CONSTRAINT valid_candidate_memory_keys
        CHECK (jsonb_typeof(candidate_memory_keys) = 'array'),
    CONSTRAINT pending_clarifications_operation_check
        CHECK (operation IN ('recall', 'correct_memory'))
);

ALTER TABLE pending_clarifications
    ADD COLUMN IF NOT EXISTS target_memory_key UUID;
ALTER TABLE pending_clarifications
    DROP CONSTRAINT IF EXISTS pending_clarifications_operation_check;
ALTER TABLE pending_clarifications
    ADD CONSTRAINT pending_clarifications_operation_check
    CHECK (operation IN ('recall', 'correct_memory'));
CREATE INDEX IF NOT EXISTS idx_pending_clarifications_expiry
    ON pending_clarifications(expires_at);

CREATE TABLE IF NOT EXISTS conversation_memory_context (
    user_id TEXT NOT NULL,
    conversation_id UUID NOT NULL,
    memory_key UUID NOT NULL,
    category TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, conversation_id),
    CONSTRAINT conversation_memory_context_owner_fk
        FOREIGN KEY (conversation_id, user_id)
        REFERENCES conversations(id, user_id) ON DELETE CASCADE
);

DO $ddl$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'conversation_memory_context'::regclass
          AND conname = 'conversation_memory_context_owner_fk'
    ) THEN
        ALTER TABLE conversation_memory_context
            ADD CONSTRAINT conversation_memory_context_owner_fk
            FOREIGN KEY (conversation_id, user_id)
            REFERENCES conversations(id, user_id) ON DELETE CASCADE;
    END IF;
END;
$ddl$;

COMMIT;

