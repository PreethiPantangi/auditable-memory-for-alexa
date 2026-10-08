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

ALTER TABLE claims ADD COLUMN memory_key TEXT NOT NULL;

UPDATE claims SET memory_key = gen_random_uuid()::text WHERE memory_key IS NULL;

DROP INDEX IF EXISTS unique_active_claim_per_category;

CREATE UNIQUE INDEX one_active_claim_per_memory_key ON claims (user_id, category, memory_key) WHERE status = 'ACTIVE';
