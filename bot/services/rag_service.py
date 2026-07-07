"""RAG pipeline: hujjat → chunk → embed → qidirish → Groq javob."""
import asyncio
from pathlib import Path
from typing import List, Tuple
from loguru import logger

from langchain_text_splitters import RecursiveCharacterTextSplitter
from bot.config import settings
from bot.services.groq_ai import (
    get_embedding, get_embeddings_batch, generate_answer, is_rag_ready
)
from database import queries

UPLOAD_DIR = Path("uploads/documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SYSTEM_PROMPT = (
    "Siz 'Uzimiznikilar' jamoasining AI yordamchisisiz. "
    "Uzimiznikilar — O'zbekistonlik mutaxassislar va professionallar hamjamiyati. "
    "Har qanday savolga o'zbek tilida, samimiy va foydali tarzda javob bering. "
    "Agar hujjatlardan kontekst berilgan bo'lsa, shuni asosida javob bering. "
    "Berilmagan bo'lsa — umumiy bilimingiz asosida yordam bering."
)


# ──────────────────────────────────────────────
# TEXT EXTRACTION
# ──────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    import PyPDF2
    text = []
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text.append(t)
    return "\n".join(text)


def extract_text_from_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text(file_path: str, file_type: str) -> str:
    ext = file_type.lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_path)
    elif ext in ("docx", "doc"):
        return extract_text_from_docx(file_path)
    elif ext in ("txt", "md"):
        return extract_text_from_txt(file_path)
    else:
        try:
            return extract_text_from_txt(file_path)
        except Exception:
            return ""


# ──────────────────────────────────────────────
# CHUNKING
# ──────────────────────────────────────────────

def chunk_text(text: str) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_text(text)
    return [c.strip() for c in chunks if len(c.strip()) > 50]


# ──────────────────────────────────────────────
# INGESTION
# ──────────────────────────────────────────────

async def ingest_document(doc_id: int, file_path: str, file_type: str) -> int:
    """Hujjatni bo'laklarga bo'lib, vectorlar bilan saqlaydi."""
    logger.info(f"Hujjat qayta ishlanmoqda: id={doc_id}, path={file_path}")

    text = extract_text(file_path, file_type)
    if not text.strip():
        logger.warning(f"Hujjatdan matn chiqmadi: {file_path}")
        return 0

    chunks = chunk_text(text)
    logger.info(f"Hujjat {doc_id}: {len(chunks)} bo'lak")

    if not chunks:
        return 0

    if not is_rag_ready():
        logger.warning("sentence-transformers o'rnatilmagan — RAG ishlamaydi")
        return 0

    embeddings = await get_embeddings_batch(chunks)

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        await queries.save_chunk(
            document_id=doc_id,
            chunk_index=i,
            chunk_text=chunk,
            embedding=emb,
            token_count=len(chunk.split()),
        )

    await queries.update_document_processed(doc_id, len(chunks))
    logger.info(f"Hujjat {doc_id} tayyor: {len(chunks)} bo'lak saqlandi")
    return len(chunks)


# ──────────────────────────────────────────────
# RETRIEVAL + GENERATION
# ──────────────────────────────────────────────

async def answer_question_direct(question: str) -> str:
    """
    Hujjatlarsiz, to'g'ridan-to'g'ri Groq orqali javob beradi.
    Har qanday savolga ishlaydi.
    """
    system_prompt = await queries.get_setting("ai_system_prompt") or DEFAULT_SYSTEM_PROMPT
    return await generate_answer(system_prompt, "", question)


async def answer_question(question: str) -> Tuple[str, List[str]]:
    """
    RAG pipeline:
    1. Savolni vektorga aylantiradi
    2. Tegishli hujjat bo'laklarini qidiradi
    3. Topilgan bo'laklar asosida Groq javob beradi
    4. Hujjat yo'q bo'lsa — to'g'ridan-to'g'ri Groq javob
    Returns: (answer, sources_list)
    """
    system_prompt = await queries.get_setting("ai_system_prompt") or DEFAULT_SYSTEM_PROMPT

    # Embedding mumkin bo'lmasa — to'g'ri Groq javob
    if not is_rag_ready():
        answer = await generate_answer(system_prompt, "", question)
        return answer, []

    try:
        q_embedding = await get_embedding(question)
    except Exception as e:
        logger.warning(f"Embedding xatosi, to'g'ri javob berilmoqda: {e}")
        answer = await generate_answer(system_prompt, "", question)
        return answer, []

    chunks = await queries.search_chunks(q_embedding, top_k=settings.top_k_results)
    relevant = [c for c in chunks if c["similarity"] > 0.6] if chunks else []

    if not relevant:
        answer = await generate_answer(system_prompt, "", question)
        return answer, []

    context_parts = []
    sources = []
    seen = set()
    for chunk in relevant:
        context_parts.append(chunk["chunk_text"])
        doc_name = chunk["title"] or chunk["file_name"]
        if doc_name not in seen:
            sources.append(doc_name)
            seen.add(doc_name)

    context = "\n\n---\n\n".join(context_parts)
    answer = await generate_answer(system_prompt, context, question)
    return answer, sources
