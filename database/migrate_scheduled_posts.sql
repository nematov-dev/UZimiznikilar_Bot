-- Rejalashtirilgan xabarlar jadvali (migration — mavjud jadvallar saqlanadi)
CREATE TABLE IF NOT EXISTS scheduled_posts (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    content       TEXT,
    media_file_id TEXT,
    media_type    TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    send_times    JSONB NOT NULL DEFAULT '[]',
    target_groups JSONB NOT NULL DEFAULT '[]',
    created_by    BIGINT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
