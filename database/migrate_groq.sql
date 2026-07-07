-- Groq ga o'tish: document_chunks vektori 768 → 384 (sentence-transformers)
-- Bu migration ishga tushirilganda eski Vertex AI embeddinglar o'chadi.
-- Hujjatlarni qayta yuklash kerak bo'ladi.

-- 1. Eski jadval o'chirish
DROP TABLE IF EXISTS document_chunks CASCADE;

-- 2. Yangi jadval: vector(384)
CREATE TABLE document_chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    chunk_text   TEXT NOT NULL,
    embedding    vector(384),
    token_count  INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_document_chunks_doc_id
    ON document_chunks (document_id);

CREATE INDEX idx_document_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 3. Hujjatlarni qayta ishlash uchun flagni reset qilish
UPDATE documents SET is_processed = FALSE, chunk_count = 0;

SELECT 'migrate_groq.sql bajarildi: document_chunks vector(384) ga yangilandi' AS result;
