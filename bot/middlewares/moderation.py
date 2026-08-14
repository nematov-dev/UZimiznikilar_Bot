"""Middleware: ro'yxatga olish + to'liq moderatsiya (outer)."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject
from database import queries
from bot.services.moderation import check_message
from bot.services.image_hash import (
    compute_all_hashes_async, phash_distance, is_imagehash_available,
    PHASH_THRESHOLD, SEGMENT_THRESHOLD, MIN_SEGMENT_MATCHES,
    segment_hashes_from_str, check_segment_match
)
from bot.services.ocr import check_ocr_banned, is_ocr_available
from loguru import logger

# ── Banned images cache ───────────────────────────────────────
_banned_images_cache: list[dict] = []
_banned_images_loaded = False

# ── Taqiqlangan media group tracking ─────────────────────────
# Tuzilma: "{chat_id}_{media_group_id}" → timestamp
# Album (post) dagi barcha rasmlarni o'chirish uchun
import time as _time
_flagged_media_groups: dict[str, float] = {}
_MEDIA_GROUP_TTL = 30  # soniya


def _flag_media_group(chat_id: int, media_group_id: str):
    """Media groupni taqiqlangan deb belgilaydi."""
    key = f"{chat_id}_{media_group_id}"
    _flagged_media_groups[key] = _time.time()
    # Eski yozuvlarni tozalash
    now = _time.time()
    stale = [k for k, ts in _flagged_media_groups.items() if now - ts > _MEDIA_GROUP_TTL]
    for k in stale:
        del _flagged_media_groups[k]


def _is_flagged_media_group(chat_id: int, media_group_id: str | None) -> bool:
    """Bu media group taqiqlangan mi?"""
    if not media_group_id:
        return False
    key = f"{chat_id}_{media_group_id}"
    ts = _flagged_media_groups.get(key)
    if ts and _time.time() - ts < _MEDIA_GROUP_TTL:
        return True
    return False


async def _load_banned_images():
    global _banned_images_cache, _banned_images_loaded
    try:
        _banned_images_cache = await queries.get_all_banned_images_full()
        _banned_images_loaded = True
    except Exception as e:
        logger.warning(f"Banned images yuklanmadi: {e}")


async def invalidate_banned_hashes_cache():
    """Admin yangi rasm taqiqlasa, cacheni yangilash uchun chaqiriladi."""
    global _banned_images_loaded
    _banned_images_loaded = False


class BotMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        bot: Bot = data.get("bot")
        is_group = event.chat.type in ("group", "supergroup")

        # ── 1. Foydalanuvchini ro'yxatga olish ──────────────────
        if event.from_user:
            try:
                await queries.upsert_user(
                    telegram_id=event.from_user.id,
                    username=event.from_user.username,
                    first_name=event.from_user.first_name,
                    last_name=event.from_user.last_name,
                )
            except Exception as e:
                logger.warning(f"upsert_user: {e}")

        # ── 2. Guruhni ro'yxatga olish ───────────────────────────
        if is_group:
            try:
                await queries.upsert_group(
                    telegram_id=event.chat.id,
                    title=event.chat.title,
                    username=event.chat.username,
                )
            except Exception as e:
                logger.warning(f"upsert_group: {e}")

        # ── 3. Xabar ID ni DB ga yozish (delete uchun kerak) ────
        if is_group and event.from_user and event.message_id:
            try:
                await queries.log_message(
                    group_id=event.chat.id,
                    user_id=event.from_user.id,
                    message_id=event.message_id,
                    message_type=_get_msg_type(event),
                )
            except Exception:
                pass

        # ── 3.5. Media group taqiqlangan bo'lsa — darhol o'chir ────
        # Album (post) dagi barcha rasmlarni o'chirish uchun
        if is_group and bot and event.from_user and event.media_group_id:
            if _is_flagged_media_group(event.chat.id, event.media_group_id):
                try:
                    await bot.delete_message(event.chat.id, event.message_id)
                    logger.info(
                        f"MEDIA_GROUP DEL: msg={event.message_id} "
                        f"group={event.media_group_id} chat={event.chat.id}"
                    )
                except Exception:
                    pass
                return  # Boshqa tekshiruvlar shart emas

        # ── 4. Guruh moderatsiyasi ────────────────────────────────
        if is_group and bot:
            blocked = await _moderate_group(event, bot)
            if blocked:
                return

        return await handler(event, data)


# ── Yordamchi: xabar turi ────────────────────────────────────

def _get_msg_type(message: Message) -> str:
    if message.photo:        return "photo"
    if message.video:        return "video"
    if message.sticker:      return "sticker"
    if message.animation:    return "animation"
    if message.document:     return "document"
    if message.voice:        return "voice"
    if message.audio:        return "audio"
    return "text"


# ── Yordamchi: xabar o'chirish ───────────────────────────────

async def _delete_msg(message: Message, reason: str) -> bool:
    try:
        await message.delete()
        uid = message.from_user.id if message.from_user else "?"
        logger.info(
            f"DELETED [{reason}]: msg={message.message_id} "
            f"chat={message.chat.id} user={uid}"
        )
        return True
    except Exception as e:
        err = str(e).lower()
        if "not enough rights" in err or "can't delete" in err or "forbidden" in err:
            logger.warning(
                f"⚠️  Bot o'chirish HUQUQI YO'Q! chat={message.chat.id} "
                f"— Botni admin qiling (Delete messages)"
            )
        else:
            logger.warning(f"delete failed [{reason}]: {e}")
        return False


import asyncio

async def _delete_all_and_ban(bot: Bot, message: Message, reason: str):
    """
    1. Tetiklovchi xabarni darhol o'chiradi.
    2. Media group bo'lsa — flag qiladi (keyingi rasmlar ham o'chirilsin).
    3. DB dan barcha eski xabarlarni o'chiradi.
    4. Guruhdan BAN qiladi.
    5. 3 soniyadan keyin DB ni qayta tozalaydi.
    """
    import asyncio as _asyncio
    chat_id = message.chat.id
    user_id = message.from_user.id
    deleted = 0

    # 1. Joriy xabar — darhol
    if await _delete_msg(message, reason.upper()):
        deleted += 1

    # 2. Media group bo'lsa — flag qilamiz (boshqa rasmlar kelsa ham o'chirilsin)
    if message.media_group_id:
        _flag_media_group(chat_id, message.media_group_id)

    # 3. DB dan barcha eski xabarlarni o'chirish
    async def _sweep_db(extra_delay: float = 0):
        nonlocal deleted
        if extra_delay:
            await _asyncio.sleep(extra_delay)
        try:
            msg_ids = await queries.get_user_message_ids(chat_id, user_id)
        except Exception:
            return
        # Joriy xabarni chiqarib tashlaymiz (allaqachon o'chirilgan)
        msg_ids = [mid for mid in msg_ids if mid != message.message_id]
        for i in range(0, len(msg_ids), 100):
            batch = msg_ids[i:i + 100]
            try:
                if len(batch) == 1:
                    await bot.delete_message(chat_id, batch[0])
                else:
                    await bot.delete_messages(chat_id, batch)
                deleted += len(batch)
            except Exception as e:
                logger.warning(f"batch delete xato: {e}")

    # Birinchi sweep — darhol
    await _sweep_db()
    logger.info(f"DELETED {deleted} messages ({reason}): user={user_id} chat={chat_id}")

    # 4. Guruhdan BAN qilish
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        logger.info(f"BANNED ({reason}): user={user_id} chat={chat_id}")
    except Exception as e:
        logger.warning(f"ban xato: {e}")

    # 5. Ikkinchi sweep — 3 soniyadan keyin (album rasmlarini ushlash)
    #    Background task sifatida — handler ni bloklamaydi
    async def _sweep_and_cleanup():
        await _sweep_db(extra_delay=3.0)
        # 6. DB loglarni tozalash — musor to'planmasin
        try:
            cleaned = await queries.delete_user_messages_log(chat_id, user_id)
            if cleaned:
                logger.info(f"DB CLEANUP: {cleaned} log o'chirildi user={user_id} chat={chat_id}")
        except Exception as e:
            logger.warning(f"DB cleanup xato: {e}")

    asyncio.create_task(_sweep_and_cleanup())


# ── Asosiy moderatsiya ────────────────────────────────────────

async def _moderate_group(message: Message, bot: Bot) -> bool:
    """True → xabar bloklandi."""

    # ── Anonim admin (guruh nomidan yozilgan xabar) → tegilmaymiz ──
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return False

    # ── A. Kanal xabari → o'chirish ─────────────────────────────
    if message.sender_chat and message.sender_chat.type == "channel":
        await _delete_msg(message, "CHANNEL")
        return True

    # ── B. Boshqa bot → ban + o'chirish ─────────────────────────
    if message.from_user and message.from_user.is_bot:
        me = await bot.get_me()
        if message.from_user.id != me.id:
            try:
                await bot.ban_chat_member(message.chat.id, message.from_user.id)
                logger.info(f"BOT BANNED: {message.from_user.id} in {message.chat.id}")
            except Exception as e:
                logger.warning(f"bot ban xato: {e}")
            await _delete_msg(message, "BOT")
            return True

    # ── Guruh sozlamalari ─────────────────────────────────────────
    group = await queries.get_group(message.chat.id)
    if not group:
        return False

    # Guruh adminlarini skip qilamiz
    is_admin = False
    if message.from_user:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            is_admin = member.status in ("administrator", "creator")
        except Exception:
            pass
    if is_admin:
        return False

    # ── Kontakt (raqam) yuborilsa → taqiqlangan so'zlar ro'yxatidan tekshirish ──
    if message.contact and message.contact.phone_number:
        digits = "".join(ch for ch in message.contact.phone_number if ch.isdigit())
        result = await check_message(digits)
        if result["has_profanity"]:
            uid = message.from_user.id if message.from_user else None
            logger.info(f"BANNED CONTACT: phone={digits} user={uid} chat={message.chat.id}")
            if uid:
                await _delete_all_and_ban(bot, message, "banned_contact")
            else:
                await _delete_msg(message, "BANNED_CONTACT")
            return True

    # ── APK fayl → darhol o'chirish + yozolmaydigan qilish ─────────
    if message.document:
        fname = (message.document.file_name or "").lower()
        mime = (message.document.mime_type or "").lower()
        if fname.endswith(".apk") or mime == "application/vnd.android.package-archive":
            uid = message.from_user.id if message.from_user else None
            logger.info(f"APK FILE: name={fname!r} user={uid} chat={message.chat.id}")
            if uid:
                await _delete_all_and_ban(bot, message, "apk_file")
            else:
                await _delete_msg(message, "APK_FILE")
            return True

    # ── C. Matn/caption moderatsiyasi ─────────────────────────────
    text = message.text or message.caption or ""
    if text.strip():
        result = await check_message(text)

        # URL (http/www/t.me) — faqat o'chirish, restrict YO'Q
        if result["has_link"] and group["anti_links"]:
            logger.info(
                f"LINK: user={message.from_user.id if message.from_user else '?'} "
                f"chat={message.chat.id} text={text[:60]!r}"
            )
            await _delete_msg(message, "LINK")
            return True

        # @username reklama — faqat o'chirish
        if result.get("has_username_ad") and group["anti_links"]:
            uid = message.from_user.id if message.from_user else "?"
            logger.info(
                f"USERNAME_AD: user={uid} "
                f"chat={message.chat.id} text={text[:60]!r}"
            )
            await _delete_msg(message, "USERNAME_AD")
            return True

        if result["has_profanity"] and group["anti_profanity"]:
            word = result.get("profane_word", "?")
            uid = message.from_user.id if message.from_user else None
            logger.info(f"PROFANITY: word={word!r} user={uid} chat={message.chat.id}")
            if uid:
                await _delete_all_and_ban(bot, message, "profanity")
            else:
                await _delete_msg(message, "PROFANITY")
            return True

    # ── D. Taqiqlangan rasm + OCR tekshiruvi ───────────────────────
    # Rasm 1 MARTA yuklanadi, pHash va OCR ga beriladi
    if message.photo:
        image_bytes = await _download_photo(message, bot)
        if image_bytes:
            # D1. pHash tekshiruvi
            if is_imagehash_available():
                banned = await _check_banned_image_bytes(image_bytes, message)
                if banned:
                    uid = message.from_user.id if message.from_user else None
                    logger.info(f"BANNED IMAGE: user={uid} chat={message.chat.id}")
                    if uid:
                        await _delete_all_and_ban(bot, message, "banned_image")
                    else:
                        await _delete_msg(message, "BANNED_IMAGE")
                    return True

            # D2. OCR tekshiruvi
            if is_ocr_available():
                found, banned_text = await check_ocr_banned(image_bytes)
                if found:
                    uid = message.from_user.id if message.from_user else None
                    logger.info(f"OCR BANNED: '{banned_text}' | chat={message.chat.id} user={uid}")
                    if uid:
                        await _delete_all_and_ban(bot, message, "ocr_banned_text")
                    else:
                        await _delete_msg(message, "OCR_BANNED")
                    return True

    # ── E. Taqiqlangan stiker to'plami (18+ va h.k.) ──────────────────
    anti_nsfw = group.get("anti_nsfw", True)
    if anti_nsfw and message.sticker and message.sticker.set_name:
        set_name = message.sticker.set_name
        banned_set = await queries.get_setting(f"banned_sticker_set_{set_name}")
        if banned_set:
            uid = message.from_user.id if message.from_user else None
            logger.info(f"BANNED STICKER SET: {set_name} user={uid} chat={message.chat.id}")
            if uid:
                await _delete_all_and_ban(bot, message, "banned_sticker")
            else:
                await _delete_msg(message, "BANNED_SET")
            return True

    return False


# ── Yordamchi: rasmni yuklab olish (1 marta) ─────────────────

async def _download_photo(message: Message, bot: Bot) -> bytes | None:
    """Rasmni Telegram dan 1 marta yuklab oladi."""
    try:
        photo = message.photo[-1]
        tg_file = await bot.get_file(photo.file_id)
        if tg_file.file_size and tg_file.file_size > 10 * 1024 * 1024:
            return None
        buf = await bot.download_file(tg_file.file_path)
        return buf.read() if hasattr(buf, "read") else bytes(buf)
    except Exception as e:
        logger.warning(f"Rasm yuklab olishda xato: {e}")
        return None


# ── Taqiqlangan rasm tekshiruvi (pHash + segment) ────────────

_LOCAL_SEGMENT_THRESHOLD = 6   # Har bir segment uchun max masofa
_LOCAL_MIN_SEGMENT_MATCHES = 5  # 16 segmentdan 5 tasi mos kelsa → topilgan


async def _check_banned_image_bytes(image_bytes: bytes, message: Message) -> bool:
    """pHash + segment hash tekshiruvi (rasmni qayta yuklamasdan)."""
    global _banned_images_cache, _banned_images_loaded

    if not _banned_images_loaded:
        await _load_banned_images()

    if not _banned_images_cache:
        return False

    incoming_phash, incoming_segments = await compute_all_hashes_async(image_bytes)
    if not incoming_phash:
        return False

    uid = message.from_user.id if message.from_user else "?"

    for entry in _banned_images_cache:
        banned_phash = entry["phash"]
        banned_segs = segment_hashes_from_str(entry.get("segment_hashes") or "")

        dist = phash_distance(incoming_phash, banned_phash)
        if dist <= PHASH_THRESHOLD:
            logger.info(f"BANNED IMAGE (phash dist={dist}): chat={message.chat.id} user={uid}")
            return True

        if banned_segs and incoming_segments:
            if check_segment_match(
                incoming_segments, banned_segs,
                threshold=_LOCAL_SEGMENT_THRESHOLD,
                min_matches=_LOCAL_MIN_SEGMENT_MATCHES,
            ):
                logger.info(f"BANNED IMAGE (segment): chat={message.chat.id} user={uid}")
                return True

    return False