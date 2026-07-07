-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── USERS ────────────────────────────────────────────────────
DROP TABLE IF EXISTS group_members CASCADE;
DROP TABLE IF EXISTS muted_users CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS admin_actions CASCADE;
DROP TABLE IF EXISTS broadcasts CASCADE;
DROP TABLE IF EXISTS document_chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS daily_stats CASCADE;
DROP TABLE IF EXISTS banned_words CASCADE;
DROP TABLE IF EXISTS bot_settings CASCADE;
DROP TABLE IF EXISTS groups CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_banned BOOLEAN DEFAULT FALSE,
    ban_reason TEXT,
    warnings INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_telegram_id ON users(telegram_id);

-- ── GROUPS ───────────────────────────────────────────────────
CREATE TABLE groups (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    username TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    delete_join_leave BOOLEAN DEFAULT TRUE,
    anti_spam BOOLEAN DEFAULT TRUE,
    anti_links BOOLEAN DEFAULT TRUE,
    anti_profanity BOOLEAN DEFAULT TRUE,
    ai_enabled BOOLEAN DEFAULT TRUE,
    member_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_groups_telegram_id ON groups(telegram_id);

-- ── GROUP MEMBERS ─────────────────────────────────────────────
CREATE TABLE group_members (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    is_admin BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

-- ── MUTED USERS ───────────────────────────────────────────────
CREATE TABLE muted_users (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    muted_by BIGINT,
    muted_until TIMESTAMPTZ,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, group_id)
);

-- ── MESSAGES LOG ─────────────────────────────────────────────
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL,
    message_type TEXT DEFAULT 'text',
    was_deleted BOOLEAN DEFAULT FALSE,
    delete_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_messages_group_id ON messages(group_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);

-- ── BANNED WORDS ──────────────────────────────────────────────
CREATE TABLE banned_words (
    id BIGSERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL,
    added_by BIGINT,
    is_regex BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_banned_words_trgm ON banned_words USING gin(word gin_trgm_ops);

-- ── DOCUMENTS (RAG) ───────────────────────────────────────────
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    file_id TEXT,
    file_name TEXT,
    file_type TEXT,
    file_path TEXT,
    added_by BIGINT,
    chunk_count INTEGER DEFAULT 0,
    is_processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── DOCUMENT CHUNKS (vector store) ───────────────────────────
CREATE TABLE document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(768),
    token_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── BROADCASTS ────────────────────────────────────────────────
CREATE TABLE broadcasts (
    id BIGSERIAL PRIMARY KEY,
    message_text TEXT NOT NULL,
    media_file_id TEXT,
    media_type TEXT,
    sent_by BIGINT,
    target TEXT DEFAULT 'all',
    recipients_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

-- ── ADMIN ACTIONS LOG ─────────────────────────────────────────
CREATE TABLE admin_actions (
    id BIGSERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    action_type TEXT NOT NULL,
    target_user_id BIGINT,
    group_id BIGINT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_admin_actions_created_at ON admin_actions(created_at);

-- ── BOT SETTINGS ──────────────────────────────────────────────
CREATE TABLE bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO bot_settings(key, value) VALUES
    ('max_warnings', '3'),
    ('mute_duration_minutes', '60'),
    ('welcome_message', 'Guruhga xush kelibsiz!'),
    ('ai_system_prompt', 'Siz Uzimiznikilar jamoasining AI yordamchisisiz. Uzimiznikilar — O''zbekistonlik mutaxassislar, ishbilarmonlar va professionallar hamjamiyati. Har qanday savolga o''zbek tilida, samimiy, qisqa va foydali tarzda javob bering. Agar hujjatlardan ma''lumot berilgan bo''lsa, shuni asosida javob bering.');

-- ── DAILY STATS ───────────────────────────────────────────────
CREATE TABLE daily_stats (
    id BIGSERIAL PRIMARY KEY,
    stat_date DATE DEFAULT CURRENT_DATE UNIQUE,
    total_users INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    total_groups INTEGER DEFAULT 0,
    messages_count INTEGER DEFAULT 0,
    deleted_messages INTEGER DEFAULT 0,
    ai_queries INTEGER DEFAULT 0,
    bans_count INTEGER DEFAULT 0
);
