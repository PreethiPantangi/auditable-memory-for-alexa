DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS claim_statuses;
DROP TABLE IF EXISTS source_types;

CREATE TABLE claim_statuses(
	status VARCHAR(25) PRIMARY KEY
);
INSERT INTO claim_statuses(status) VALUES('ACTIVE');
INSERT INTO claim_statuses(status) VALUES('SUPERSEDED');
INSERT INTO claim_statuses(status) VALUES('FORGOTTEN');

CREATE TABLE source_types(
	source_type VARCHAR(25) PRIMARY KEY
);
INSERT INTO source_types(source_type) VALUES('EXPLICIT');
INSERT INTO source_types(source_type) VALUES('DERIVED');

DROP TABLE IF EXISTS claims;
CREATE TABLE claims(
	id serial PRIMARY KEY,
	user_id VARCHAR(50) NOT NULL, -- User Id
	category VARCHAR(25) NOT NULL, -- Diet, Recipe, etc.
	value TEXT NOT NULL, -- Ex: Vegetarian
	source_type TEXT NOT NULL REFERENCES source_types(source_type), -- EXPLICIT
	source_utterance TEXT NOT NULL, -- Actual statement. Ex: Remember that I'm a Vegetarian
	status VARCHAR(25) NOT NULL REFERENCES claim_statuses(status), -- ACTIVE, SUPERSEDED, etc.
	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
	superseded_by_claim_id INTEGER REFERENCES claims(id)
);

ALTER TABLE claims ADD COLUMN memory_key TEXT;

UPDATE claims SET memory_key = gen_random_uuid()::text WHERE memory_key IS NULL;

DROP INDEX IF EXISTS unique_active_claim_per_category;

CREATE UNIQUE INDEX one_active_claim_per_memory_key ON claims (user_id, category, memory_key) WHERE status = 'ACTIVE';

CREATE TABLE events (
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

CREATE INDEX idx_events_user_domain_time ON events (user_id, domain, occurred_at DESC, id DESC);

ALTER TABLE events ADD COLUMN request_id UUID;

CREATE UNIQUE INDEX idx_events_user_request ON events (user_id, request_id) WHERE request_id IS NOT NULL;

ALTER TABLE events ADD COLUMN IF NOT EXISTS request_hash TEXT;

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
        status IN (
            'PENDING_CONFIRMATION',
            'CONFIRMED',
            'REJECTED'
        )
    ),

    CONSTRAINT insight_decision_consistency CHECK (
        (status = 'PENDING_CONFIRMATION'
            AND decided_at IS NULL
            AND confirmed_claim_id IS NULL)
        OR
        (status = 'REJECTED'
            AND decided_at IS NOT NULL
            AND confirmed_claim_id IS NULL)
        OR
        (status = 'CONFIRMED'
            AND decided_at IS NOT NULL
            AND confirmed_claim_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_insights_user_rule_subject_adjustment ON insights (user_id, domain, insight_type, subject, adjustment);

CREATE TABLE IF NOT EXISTS insight_evidence (
    insight_id BIGINT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    event_id BIGINT NOT NULL REFERENCES events(id),
    PRIMARY KEY (insight_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_insights_user_status ON insights (user_id, status);


CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS pending_clarifications (
    conversation_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('recall')),
    original_question TEXT NOT NULL,
    category TEXT NOT NULL,
    candidate_memory_keys JSONB NOT NULL,
    clarification_question TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '15 minutes'),

    FOREIGN KEY (conversation_id, user_id)
        REFERENCES conversations (id, user_id)
        ON DELETE CASCADE,

    CHECK (
        jsonb_typeof(candidate_memory_keys) = 'array'
    )
);

CREATE INDEX IF NOT EXISTS idx_pending_clarifications_expiry ON pending_clarifications (expires_at);

CREATE TABLE conversation_memory_context (
    user_id TEXT NOT NULL,
    conversation_id UUID NOT NULL,
    memory_key UUID NOT NULL,
    category TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, conversation_id)
);

ALTER TABLE pending_clarifications
ADD COLUMN target_memory_key UUID;