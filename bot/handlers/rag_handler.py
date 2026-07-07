"""RAG handler: AI savol-javob (guruh + PM) va hujjat yuklash."""
import asyncio
import re
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, Document
from aiogram.filters import Command
from loguru import logger

from bot.services.rag_service import answer_question, answer_question_direct, ingest_document
from bot.services.groq_ai import is_groq_ready, is_rag_ready
from bot.config import settings
from database import queries

router = Router()

UPLOAD_DIR = Path("uploads/documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_processing: set = set()


# ── GURUHDA AI: /ai, @mention, "ai savol", bot ga reply ──────────────

@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def ai_group_handler(message: Message, bot: Bot):
    text = (message.text or "").strip()
    if not text:
        return

    bot_info = await bot.get_me()
    bot_username = f"@{bot_info.username}"

    # Trigger shartlarini aniqlash
    is_mention   = bot_username.lower() in text.lower()
    is_reply_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_info.id
    )
    is_ai_cmd    = text.lower().startswith("/ai")
    is_ai_prefix = re.match(r"^ai[\s,!?]+", text, re.IGNORECASE) is not None

    if not any([is_mention, is_reply_bot, is_ai_cmd, is_ai_prefix]):
        return  # Bot ga aloqasi yo'q xabar — o'tkazib yuboramiz

    # Guruhda AI yoqilganmi tekshirish
    group = await queries.get_group(message.chat.id)
    if group and not group["ai_enabled"]:
        return

    # Savolni ajratib olish
    if is_ai_cmd:
        # /ai <savol>
        question = text[3:].strip()
    elif is_ai_prefix:
        # "ai savol" → "savol"
        question = re.sub(r"^ai[\s,!?]+", "", text, flags=re.IGNORECASE).strip()
    elif is_mention:
        # "@botuser savol" → "savol"
        question = re.sub(re.escape(bot_username), "", text, flags=re.IGNORECASE).strip()
    else:
        # Bot ga reply
        question = text.strip()

    if not question:
        return await message.reply("Savolingizni yozing 💬")

    await _handle_question(message, question)


# ── UMUMIY JAVOB FUNKSIYASI ───────────────────────────────────────────

async def _handle_question(message: Message, question: str):
    if not is_groq_ready():
        return await message.reply(
            "⚠️ AI sozlanmagan. .env ga GROQ_API_KEY ni qo'shing."
        )

    user_key = f"{message.from_user.id}:{message.chat.id}"
    if user_key in _processing:
        return  # Bir vaqtda ikki so'rov bo'lmasin
    _processing.add(user_key)

    is_group = message.chat.type in ("group", "supergroup")
    typing = await message.reply("🤔 AI o'ylamoqda...")
    try:
        # Guruhda: to'g'ridan-to'g'ri Groq (embedding yuklashni kutmasdan, tezroq)
        # PMda: to'liq RAG pipeline (hujjatlardan qidiradi)
        if is_group:
            answer = await asyncio.wait_for(
                answer_question_direct(question), timeout=45
            )
            sources = []
        else:
            answer, sources = await asyncio.wait_for(
                answer_question(question), timeout=60
            )

        source_text = ""
        if sources:
            source_text = "\n\n📄 <i>Manbalar: " + ", ".join(sources[:3]) + "</i>"
        await typing.edit_text(answer + source_text, parse_mode="HTML")
    except asyncio.TimeoutError:
        logger.warning(f"AI timeout: user={message.from_user.id}")
        await typing.edit_text("⏱ Javob vaqt tugdi. Iltimos, qayta urinib ko'ring.")
    except Exception as e:
        logger.error(f"RAG xato: {e}")
        await typing.edit_text("❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
    finally:
        _processing.discard(user_key)


# ── HUJJAT YUKLASH (faqat admin, PM da) ──────────────────────────────

@router.message(F.document, F.chat.type == "private")
async def handle_document_upload(message: Message, bot: Bot):
    if message.from_user.id not in settings.admin_ids:
        return

    doc: Document = message.document
    file_name = doc.file_name or "document"
    ext = Path(file_name).suffix.lstrip(".").lower()

    if ext not in ("pdf", "docx", "doc", "txt", "md"):
        return await message.reply(
            "Qo'llab-quvvatlanadigan formatlar: PDF, DOCX, TXT, MD"
        )

    if not is_rag_ready():
        return await message.reply(
            "⚠️ RAG uchun <b>sentence-transformers</b> o'rnatilmagan.\n"
            "Buyruq: <code>pip install sentence-transformers</code>",
            parse_mode="HTML"
        )

    status_msg = await message.reply(
        f"📥 <b>{file_name}</b> yuklanmoqda...", parse_mode="HTML"
    )

    try:
        file = await bot.get_file(doc.file_id)
        local_path = UPLOAD_DIR / f"{doc.file_id}.{ext}"
        await bot.download_file(file.file_path, destination=str(local_path))

        title = message.caption or file_name
        doc_id = await queries.create_document(
            title=title,
            file_id=doc.file_id,
            file_name=file_name,
            file_type=ext,
            file_path=str(local_path),
            added_by=message.from_user.id,
        )

        await status_msg.edit_text(
            f"⚙️ <b>{file_name}</b> RAG ga qo'shilmoqda...", parse_mode="HTML"
        )

        asyncio.create_task(
            _ingest_and_notify(doc_id, str(local_path), ext, status_msg, file_name)
        )

    except Exception as e:
        logger.error(f"Hujjat yuklash xatosi: {e}")
        await status_msg.edit_text(f"❌ Xatolik: {e}")


async def _ingest_and_notify(
    doc_id: int, file_path: str, file_type: str,
    status_msg: Message, file_name: str,
):
    try:
        chunk_count = await ingest_document(doc_id, file_path, file_type)
        await status_msg.edit_text(
            f"✅ <b>{file_name}</b> muvaffaqiyatli qo'shildi!\n"
            f"📊 {chunk_count} ta bo'lak indekslandi.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Hujjat ingestion xatosi (id={doc_id}): {e}")
        await status_msg.edit_text(f"❌ Hujjatni qayta ishlashda xatolik: {e}")
