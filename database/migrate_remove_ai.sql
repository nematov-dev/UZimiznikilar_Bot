-- AI (Groq/RAG/Vertex) funksiyasi olib tashlandi — mos jadval/ustunlarni tozalash.

DROP TABLE IF EXISTS document_chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

ALTER TABLE groups DROP COLUMN IF EXISTS ai_enabled;
ALTER TABLE daily_stats DROP COLUMN IF EXISTS ai_queries;

DELETE FROM bot_settings WHERE key = 'ai_system_prompt';

SELECT 'migrate_remove_ai.sql bajarildi: AI jadval/ustunlari o''chirildi' AS result;
