-- Taqiqlangan rasmlar jadvali (pHash asosida)
CREATE TABLE IF NOT EXISTS banned_images (
    id         BIGSERIAL PRIMARY KEY,
    phash      TEXT        NOT NULL UNIQUE,
    note       TEXT        DEFAULT '',
    added_by   BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_banned_images_phash ON banned_images(phash);

SELECT 'migrate_banned_images.sql bajarildi' AS result;
