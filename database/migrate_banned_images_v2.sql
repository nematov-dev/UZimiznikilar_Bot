-- Segment hashes ustuni: kesilgan/screenshottagi rasmlarni aniqlash uchun
ALTER TABLE banned_images
    ADD COLUMN IF NOT EXISTS segment_hashes TEXT DEFAULT '';

SELECT 'migrate_banned_images_v2.sql bajarildi' AS result;
