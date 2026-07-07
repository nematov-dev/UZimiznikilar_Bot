-- NSFW moderatsiya ustunini qo'shish
ALTER TABLE groups
    ADD COLUMN IF NOT EXISTS anti_nsfw BOOLEAN DEFAULT TRUE;

SELECT 'migrate_nsfw.sql bajarildi: anti_nsfw ustuni qo''shildi' AS result;
