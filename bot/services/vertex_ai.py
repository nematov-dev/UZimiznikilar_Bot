"""Vertex AI — embeddings & text generation. Lazy initialization."""
import asyncio
from typing import List, Optional
from loguru import logger
from bot.config import settings

_vertex_ready = False
_embedding_model = None
_chat_model = None


def _is_placeholder_credentials() -> bool:
    """Check if service account JSON is still a placeholder (empty private_key)."""
    sa_info = settings.get_service_account_info()
    if not sa_info:
        return False
    private_key = sa_info.get("private_key", "")
    return not private_key or private_key.strip() == ""


def _init_vertex() -> bool:
    """
    Vertex AI ni ishga tushirish.
    Muvaffaqiyatli bo'lsa True, bo'lmasa False qaytaradi.
    """
    global _vertex_ready
    if _vertex_ready:
        return True

    # Placeholder credentials bo'lsa — umuman urinma
    if _is_placeholder_credentials():
        logger.warning(
            "⚠️  Vertex AI: placeholder credentials aniqlandi. "
            "RAG funksiyasi o'chirilgan. "
            "GOOGLE_SERVICE_ACCOUNT_JSON ni .env ga to'liq qo'ying."
        )
        return False

    try:
        import vertexai
        from google.oauth2 import service_account

        sa_info = settings.get_service_account_info()

        if sa_info:
            credentials = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            vertexai.init(
                project=settings.google_project_id,
                location=settings.google_location,
                credentials=credentials,
            )
            logger.info("✅ Vertex AI: JSON credentials bilan ulandi")
        else:
            logger.warning("⚠️  Vertex AI credentials topilmadi. RAG o'chirilgan.")
            return False

        _vertex_ready = True
        return True

    except Exception as e:
        logger.warning(f"⚠️  Vertex AI init xatosi: {e}\nRAG funksiyasi o'chirilgan.")
        return False


def _get_embedding_model():
    global _embedding_model
    if not _init_vertex():
        raise RuntimeError("Vertex AI sozlanmagan. .env ga credentials qo'ying.")
    if _embedding_model is None:
        from vertexai.language_models import TextEmbeddingModel
        _embedding_model = TextEmbeddingModel.from_pretrained(settings.vertex_embedding_model)
    return _embedding_model


def _get_chat_model():
    global _chat_model
    if not _init_vertex():
        raise RuntimeError("Vertex AI sozlanmagan. .env ga credentials qo'ying.")
    if _chat_model is None:
        from vertexai.generative_models import (
            GenerativeModel, SafetySetting, HarmCategory, HarmBlockThreshold
        )
        _chat_model = GenerativeModel(
            settings.vertex_chat_model,
            safety_settings=[
                SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
                SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
            ]
        )
    return _chat_model


def is_vertex_ready() -> bool:
    """RAG ishlash uchun Vertex AI tayyor yoki yo'qligini tekshirish."""
    return _init_vertex()


async def get_embedding(text: str) -> List[float]:
    """Get text embedding vector (768-dim)."""
    loop = asyncio.get_event_loop()
    model = _get_embedding_model()

    def _embed():
        return model.get_embeddings([text])[0].values

    try:
        return await loop.run_in_executor(None, _embed)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Batch embedding — Vertex AI max 250 per request."""
    loop = asyncio.get_event_loop()
    model = _get_embedding_model()

    def _embed_batch():
        results = []
        for i in range(0, len(texts), 50):
            batch = texts[i:i + 50]
            embeddings = model.get_embeddings(batch)
            results.extend([e.values for e in embeddings])
        return results

    try:
        return await loop.run_in_executor(None, _embed_batch)
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise


async def generate_answer(system_prompt: str, context: str, question: str) -> str:
    """Generate answer using Gemini. context ixtiyoriy — bo'sh bo'lsa to'g'ridan-to'g'ri javob."""
    loop = asyncio.get_event_loop()
    model = _get_chat_model()

    if context and context.strip():
        prompt = (
            f"{system_prompt}\n\n"
            f"Quyidagi hujjatlardan olingan ma'lumotlar:\n{context}\n\n"
            f"Savol: {question}\n\n"
            "Javob:"
        )
    else:
        prompt = (
            f"{system_prompt}\n\n"
            f"Savol: {question}\n\n"
            "Javob:"
        )

    def _generate():
        response = model.generate_content(prompt)
        return response.text

    try:
        return await loop.run_in_executor(None, _generate)
    except Exception as e:
        logger.error(f"Generation error: {e}")
        return "Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring."
