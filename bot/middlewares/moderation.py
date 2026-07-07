"""Middleware: ro'yxatga olish + to'liq moderatsiya (outer)."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject
from database import queries
from bot.services.moderation import check_message
from bot.services.nsfw_checker import is_nsfw, is_nsfw_available
from bot.services.image_hash import (
    compute_all_hashes_async, phash_distance, is_imagehash_available,
    PHASH_THRESHOLD, segment_hashes_from_str, check_segment_match
)
from loguru import logger

# Cache: {phash: segment_hashes_str}
_banned_images_cache: list[dict] = []
_banned_images_loaded = False


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

        # ── 3. Guruh moderatsiyasi ────────────────────────────────
        if is_group and bot:
            blocked = await _moderate_group(event, bot)
            if blocked:
                return

        return await handler(event, data)


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


# ── Asosiy moderatsiya ────────────────────────────────────────

async def _moderate_group(message: Message, bot: Bot) -> bool:
    """True → xabar bloklandi."""

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

    # ── C. Matn/caption moderatsiyasi ─────────────────────────────
    text = message.text or message.caption or ""
    if text.strip():
        result = await check_message(text)


        if result["has_link"] and group["anti_links"]:
            logger.info(
                f"LINK: user={message.from_user.id if message.from_user else '?'} "
                f"chat={message.chat.id} text={text[:60]!r}"
            )
            await _delete_msg(message, "LINK")
            return True

        if result["has_profanity"] and group["anti_profanity"]:
            logger.info(
                f"PROFANITY: word={result['profane_word']!r} chat={message.chat.id}"
            )
            await _delete_msg(message, "PROFANITY")
            return True

    # ── D. Taqiqlangan rasm tekshiruvi (pHash) ────────────────────
    if message.photo and is_imagehash_available():
        banned = await _check_banned_image(message, bot)
        if banned:
            await _delete_msg(message, "BANNED_IMAGE")
            return True

    # ── E. NSFW tekshiruvi ─────────────────────────────────────────
    anti_nsfw = group.get("anti_nsfw", True)
    if anti_nsfw:
        # E1. Stiker to'plami blacklist (AI dan ham tezroq)
        if message.sticker and message.sticker.set_name:
            set_name = message.sticker.set_name
            banned_set = await queries.get_setting(f"banned_sticker_set_{set_name}")
            if banned_set:
                logger.info(f"BANNED STICKER SET: {set_name} in {message.chat.id}")
                await _delete_msg(message, "BANNED_SET")
                return True

        # E2. AI orqali media tekshiruvi
        if is_nsfw_available():
            nsfw = await _check_media_nsfw(message, bot)
            if nsfw:
                if message.sticker and message.sticker.set_name:
                    await _auto_blacklist_sticker_set(
                        message.sticker.set_name, message.chat.id
                    )
                await _delete_msg(message, "NSFW")
                return True

    return False


# ── Taqiqlangan rasm tekshiruvi (pHash + segment) ────────────

async def _check_banned_image(message: Message, bot: Bot) -> bool:
    """
    pHash (tez) + segment hash (kesish/screenshot) tekshiruvi.
    True => taqiqlangan rasm.
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

        # 1. Tez tekshiruv: butun rasm pHash
        if phash_distance(incoming_phash, banned_phash) <= PHASH_THRESHOLD:
            logger.info(f"BANNED IMAGE (phash): chat={message.chat.id} user={uid}")
            return True

        # 2. Segment tekshiruv: kesish/screenshot uchun
        if banned_segs and incoming_segments:
            if check_segment_match(incoming_segments, banned_segs):
                logger.info(f"BANNED IMAGE (segment): chat={message.chat.id} user={uid}")
                return True

    return False


# ── Media NSFW tekshiruvi ─────────────────────────────────────

async def _check_media_nsfw(message: Message, bot: Bot) -> bool:
    """Rasm/GIF/stiker/video => NSFW tekshiruvi. True => 18+."""
    file_id = None
    ext = "jpg"

    if message.photo:
        file_id = message.photo[-1].file_id
        ext = "jpg"
    elif message.animation:
        anim = message.animation
        if anim.thumbnail:
            file_id = anim.thumbnail.file_id
            ext = "jpg"
        else:
            file_id = anim.file_id
            ext = "mp4"
    elif message.sticker:
        sticker = message.sticker
        if sticker.is_video:
            if sticker.thumbnail:
                file_id = sticker.thumbnail.file_id
                ext = "jpg"
            else:
                file_id = sticker.file_id
                ext = "webm"
        elif sticker.is_animated:
            if sticker.thumbnail:
                file_id = sticker.thumbnail.file_id
                ext = "jpg"
            else:
                return False
        else:
            file_id = sticker.file_id
            ext = "webp"
    elif message.video:
        if message.video.thumbnail:
            file_id = message.video.thumbnail.file_id
            ext = "jpg"
        else:
            file_id = message.video.file_id
            ext = "mp4"
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("image/"):
            file_id = message.document.file_id
            ext = mime.split("/")[-1].replace("jpeg", "jpg")

    if not file_id:
        return False

    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_size and tg_file.file_size > 15 * 1024 * 1024:
            logger.debug(f"Fayl juda katta ({tg_file.file_size}), skip")
            return False
        buf = await bot.download_file(tg_file.file_path)
        file_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
        return await is_nsfw(file_bytes, ext)
    except Exception as e:
        logger.warning(f"NSFW media yuklab olishda xato: {e}")
        return False


# ── Stiker to'plamini avtomat blacklistga qo'shish ────────────

async def _auto_blacklist_sticker_set(set_name: str, chat_id: int):
    try:
        existing = await queries.get_setting(f"banned_sticker_set_{set_name}")
        if not existing:
            await queries.set_setting(f"banned_sticker_set_{set_name}", "1")
            logger.info(
                f"AUTO BLACKLIST sticker set: {set_name} "
                f"(NSFW topildi, chat={chat_id})"
            )
    except Exception as e:
        logger.warning(f"Auto blacklist xato: {e}")
