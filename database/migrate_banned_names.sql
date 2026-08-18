-- BANNED NAMES TABLE
CREATE TABLE IF NOT EXISTS banned_names (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_banned_names_name ON banned_names(name);
