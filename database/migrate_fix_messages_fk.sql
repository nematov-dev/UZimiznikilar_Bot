-- messages.group_id/user_id noto'g'ri FK ga bog'langan edi (groups.id / users.id —
-- ichki serial ID), lekin kod har doim Telegram ID yozadi. Natijada har bir
-- log_message() chaqiruvi jimgina xato berib, jadval bo'sh qolar edi va
-- "taqiqlangan so'z/rasm yuborgan foydalanuvchining barcha xabarini o'chirish"
-- funksiyasi hech narsa topolmas edi.

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_group_id_fkey;
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_user_id_fkey;

ALTER TABLE messages
    ADD CONSTRAINT messages_group_id_fkey
    FOREIGN KEY (group_id) REFERENCES groups(telegram_id) ON DELETE CASCADE;

ALTER TABLE messages
    ADD CONSTRAINT messages_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE;

SELECT 'migrate_fix_messages_fk.sql bajarildi: messages.group_id/user_id endi telegram_id ga bog''langan' AS result;
