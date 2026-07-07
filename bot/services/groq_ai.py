"""Groq AI — ultra-tez LLM generation + sentence-transformers embeddings."""
import asyncio
from typing import List
from loguru import logger

_client = None
_embedding_model = None

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


# ─────────────────────────────────────────────────
#  Lazy init
# ─────────────────────────────────────────────────

def _get_client():
    global _client
    if _client is None:
        from groq import AsyncGroq
        from bot.config import settings
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


def _load_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Embedding model yuklanmoqda: {EMBEDDING_MODEL_NAME} ...")
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("✅ Embedding model tayyor")
    return _embedding_model


# ─────────────────────────────────────────────────
#  Status check
# ─────────────────────────────────────────────────

def is_groq_ready() -> bool:
    from bot.config import settings
    return bool(settings.groq_api_key and len(settings.groq_api_key) > 10)


def is_rag_ready() -> bool:
    """sentence-transformers o'rnatilgan va model yuklanishi mumkin."""
    try:
        import sentence_transformers  # noqa
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────
#  Generation
# ─────────────────────────────────────────────────

async def generate_answer(system_prompt: str, context: str, question: str) -> str:
    """Groq LLM orqali javob generatsiya qiladi."""
    from bot.config import settings
    client = _get_client()

    if context and context.strip():
        user_content = (
            f"Quyidagi hujjatlardan olingan ma'lumotlar:\n{context}\n\n"
            f"Savol: {question}"
        )
    else:
        user_content = question

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content or "Javob berib bo'lmadi."
    except Exception as e:
        logger.error(f"Groq generation error: {e}")
        return "❌ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring."


# ─────────────────────────────────────────────────
#  Embeddings (sentence-transformers, 384-dim)
# ─────────────────────────────────────────────────

async def get_embedding(text: str) -> List[float]:
    """Bitta matn uchun embedding vektori (384-dim)."""
    loop = asyncio.get_event_loop()

    def _embed():
        model = _load_embedding_model()
        vec = model.encode([text], show_progress_bar=False)
        return vec[0].tolist()

    try:
        return await loop.run_in_executor(None, _embed)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Bir vaqtda ko'p matnlar uchun embedding (batch)."""
    loop = asyncio.get_event_loop()

    def _embed_batch():
        model = _load_embedding_model()
        vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    try:
        return await loop.run_in_executor(None, _embed_batch)
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise
