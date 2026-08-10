-- Run this if DB already exists (migration)
CREATE TABLE IF NOT EXISTS banned_ocr_texts (
    id BIGSERIAL PRIMARY KEY,
    text TEXT UNIQUE NOT NULL,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_banned_ocr_texts_text ON banned_ocr_texts(text);
