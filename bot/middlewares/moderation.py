"""Middleware: ro'yxatga olish + to'liq moderatsiya (outer)."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject, ChatPermissions
from database import queries
from bot.services.moderation import check_message
from bot.services.image_hash import (
    compute_all_hashes_async, phash_distance, is_imagehash_available,
    PHASH_THRESHOLD, SEGMENT_THRESHOLD, MIN_SEGMENT_MATCHES,
    segment_hashes_from_str, check_segment_match
)
from loguru import logger
import time
import hashlib
from collections import defaultdict

# ── Banned images cache ───────────────────────────────────────
_banned_images_cache: list[dict] = []
_banned_images_loaded = False

# ── Cross-group spam detection ────────────────────────────────
# Tuzilma: { user_id: { text_key: [(chat_id, message_id, timestamp), ...] } }
_cross_spam: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
_CROSS_SPAM_WINDOW   = 60    # soniya: shu vaqt ichida tekshiriladi
_CROSS_SPAM_THRESHOLD = 3    # nechta guruhga yuborganda spam hisoblanadi


def _text_key(text: str) -> str:
    """Matnni normallashtirb, MD5 hash oladi — bir xil xabarlarni aniqlash uchun."""
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()


def _cleanup_cross_spam(user_id: int, now: float):
    """Eski (window'dan tashqari) yozuvlarni tozalaydi."""
    keys_to_del = []
    for key, entries in _cross_spam[user_id].items():
        fresh = [(cid, mid, ts) for cid, mid, ts in entries if now - ts < _CROSS_SPAM_WINDOW]
        if fresh:
            _cross_spam[user_id][key] = fresh
        else:
            keys_to_del.append(key)
    for k in keys_to_del:
        del _cross_spam[user_id][k]
    if not _cross_spam[user_id]:
        del _cross_spam[user_id]


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

        # ── 3. Xabar ID ni DB ga yozish (delete uchun kerak) ────────
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

        # ── 4. Guruh moderatsiyasi ────────────────────────────────
        if is_group and bot:
            blocked = await _moderate_group(event, bot)
            if blocked:
                return

        # ── 5. Cross-group spam tekshiruvi ───────────────────────
        if is_group and bot and event.from_user:
            cross_spam = await _check_cross_group_spam(event, bot)
            if cross_spam:
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


# ── Yordamchi: foydalanuvchining hamma xabarini o'chirib, restrict qilish ──

async def _delete_all_and_restrict(bot: Bot, message: Message, reason: str):
    """
    1. Tetiklovchi xabarni darhol o'chiradi (DB ga bog'liq emas — kafolatlangan).
    2. Foydalanuvchining guruhdagi qolgan barcha xabarlarini DB dan topib o'chiradi.
    3. Umrbod yozolmaydigan qilib restrict qiladi.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    deleted = 0

    # 1. Joriy xabar — darhol, hech nimaga qaramay
    if await _delete_msg(message, reason.upper()):
        deleted += 1

    # 2. Qolgan eski xabarlar — DB dan
    try:
        msg_ids = await queries.get_user_message_ids(chat_id, user_id)
    except Exception:
        msg_ids = []
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

    logger.info(f"DELETED {deleted} messages ({reason}): user={user_id} chat={chat_id}")

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
        logger.info(f"RESTRICTED forever ({reason}): user={user_id} chat={chat_id}")
    except Exception as e:
        logger.warning(f"restrict xato: {e}")


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
                await _delete_all_and_restrict(bot, message, "banned_contact")
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
                await _delete_all_and_restrict(bot, message, "apk_file")
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

        # @username reklama — faqat o'chirish, restrict YO'Q
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
                await _delete_all_and_restrict(bot, message, "profanity")
            else:
                await _delete_msg(message, "PROFANITY")
            return True

    # ── D. Taqiqlangan rasm tekshiruvi (pHash) ────────────────────
    # media_group bo'lsa ham (bir nechta rasm), butun xabar o'chiriladi
    if message.photo and is_imagehash_available():
        banned = await _check_banned_image(message, bot)
        if banned:
            uid = message.from_user.id if message.from_user else None
            logger.info(f"BANNED IMAGE: user={uid} chat={message.chat.id}")
            if uid:
                # Butun xabarni + barcha eski xabarlarni o'chiradi va restrict qo'yadi
                await _delete_all_and_restrict(bot, message, "banned_image")
            else:
                await _delete_msg(message, "BANNED_IMAGE")
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
                await _delete_all_and_restrict(bot, message, "banned_sticker")
            else:
                await _delete_msg(message, "BANNED_SET")
            return True

    return False


# ── Cross-group spam o'chirish ────────────────────────────────

async def _check_cross_group_spam(message: Message, bot: Bot) -> bool:
    """
    Bir foydalanuvchi 60 soniya ichida 3+ ta guruhga bir xil xabar
    yuborganda — barchasini o'chiradi (restrict yo'q, faqat delete).
    True => xabar spam sifatida topildi va o'chirildi.
    """
    if not message.from_user:
        return False

    # Faqat matn yoki caption bo'lgan xabarlar
    text = message.text or message.caption or ""
    if not text.strip():
        return False

    user_id  = message.from_user.id
    chat_id  = message.chat.id
    msg_id   = message.message_id
    now      = time.time()
    key      = _text_key(text)

    # Eski yozuvlarni tozala
    _cleanup_cross_spam(user_id, now)

    # Joriy guruh allaqachon ro'yxatda bor-yo'qligini tekshir
    existing_chats = {cid for cid, _, _ in _cross_spam[user_id][key]}
    if chat_id not in existing_chats:
        _cross_spam[user_id][key].append((chat_id, msg_id, now))

    entries = _cross_spam[user_id][key]
    unique_chats = {cid for cid, _, _ in entries}

    if len(unique_chats) < _CROSS_SPAM_THRESHOLD:
        return False

    # === SPAM TOPILDI: barcha guruhlardagi xabarlarni o'chir ===
    logger.info(
        f"CROSS-GROUP SPAM: user={user_id} "
        f"groups={list(unique_chats)} text={text[:60]!r}"
    )

    for spam_chat_id, spam_msg_id, _ in entries:
        try:
            await bot.delete_message(spam_chat_id, spam_msg_id)
            logger.info(
                f"CROSS-SPAM DELETED: chat={spam_chat_id} msg={spam_msg_id} user={user_id}"
            )
        except Exception as e:
            logger.warning(f"cross-spam delete xato: chat={spam_chat_id} msg={spam_msg_id}: {e}")

    # Joriy xabarni ham o'chir (entries da bo'lmasligi mumkin — yangi guruh)
    if chat_id not in existing_chats:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Cache dan tozala (qayta trigger bo'lmasin)
    _cross_spam[user_id].pop(key, None)

    return True


# ── Taqiqlangan rasm tekshiruvi (pHash + segment) ────────────

# Sezgirlik sozlamalari (noto'g'ri bloklashni kamaytirish uchun)
# PHASH_THRESHOLD — import qilinadi (image_hash.py dan)
# Segment uchun: ko'proq segment mos kelishi shart
_LOCAL_SEGMENT_THRESHOLD = 4    # (image_hash.py dagi 6 dan qattiqroq)
_LOCAL_MIN_SEGMENT_MATCHES = 4  # (image_hash.py dagi 2 dan ko'proq mos kelishi kerak)


async def _check_banned_image(message: Message, bot: Bot) -> bool:
    """
    pHash (tez) + segment hash (kesish/screenshot) tekshiruvi.
    True => taqiqlangan rasm.

    Sezgirlik:
      - pHash: <= PHASH_THRESHOLD (8) => bir xil rasm
      - Segment: kamida _LOCAL_MIN_SEGMENT_MATCHES (4) ta segment
        _LOCAL_SEGMENT_THRESHOLD (4) masofasida mos kelsa => topildi
        (bu noto'g'ri bloklashni sezilarli kamaytiradi)
    """
    global _banned_images_cache, _banned_images_loaded

    if not _banned_images_loaded:
        await _load_banned_images()

    if not _banned_images_cache:
        return False

    try:
        photo = message.photo[-1]
        tg_file = await bot.get_file(photo.file_id)
        if tg_file.file_size and tg_file.file_size > 10 * 1024 * 1024:
            return False
        buf = await bot.download_file(tg_file.file_path)
        image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
    except Exception as e:
        logger.warning(f"Rasm yuklab olishda xato (banned check): {e}")
        return False

    # Kelayotgan rasmning pHash + segmentlari
    incoming_phash, incoming_segments = await compute_all_hashes_async(image_bytes)
    if not incoming_phash:
        return False

    uid = message.from_user.id if message.from_user else "?"

    for entry in _banned_images_cache:
        banned_phash = entry["phash"]
        banned_segs = segment_hashes_from_str(entry.get("segment_hashes") or "")

        # 1. Tez tekshiruv: butun rasm pHash (asosiy, eng aniq)
        dist = phash_distance(incoming_phash, banned_phash)
        if dist <= PHASH_THRESHOLD:
            logger.info(
                f"BANNED IMAGE (phash dist={dist}): chat={message.chat.id} user={uid}"
            )
            return True

        # 2. Segment tekshiruv: faqat aniq kesish/screenshot uchun
        #    Noto'g'ri bloklashni kamaytirish uchun qattiqroq sozlamalar
        if banned_segs and incoming_segments:
            if check_segment_match(
                incoming_segments,
                banned_segs,
                threshold=_LOCAL_SEGMENT_THRESHOLD,
                min_matches=_LOCAL_MIN_SEGMENT_MATCHES,
            ):
                logger.info(
                    f"BANNED IMAGE (segment match): chat={message.chat.id} user={uid}"
                )
                return True

    return False