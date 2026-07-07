"""Group admin commands: /ban /unban /mute /unmute /kick /warn /clear /info."""
from aiogram import Router, Bot, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from datetime import datetime, timedelta
from loguru import logger

from bot.utils.helpers import full_mute_permissions, default_permissions, mute_until, format_user_mention
from database import queries

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def get_target_user(message: Message):
    """Extract target user from reply or mention."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


def parse_reason(text: str) -> str:
    """Extract reason from command text like '/ban sabab matni'"""
    parts = text.strip().split(maxsplit=1)
    return parts[1] if len(parts) > 1 else "Sabab ko'rsatilmadi"


# ─────────────────────────── /ban ───────────────────────────

@router.message(Command("ban"))
async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Banlash uchun xabarni reply qiling.")

    reason = parse_reason(message.text)
    name = format_user_mention(target.id, target.first_name)

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await queries.ban_user(target.id, reason)
        await queries.log_admin_action(
            admin_id=message.from_user.id,
            action_type="ban",
            target_user_id=target.id,
            group_id=message.chat.id,
            details={"reason": reason}
        )
        await message.reply(f"🚫 {name} guruhdan ban qilindi.\n📝 Sabab: {reason}", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────── /unban ───────────────────────────

@router.message(Command("unban"))
async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Unbanlash uchun xabarni reply qiling.")

    try:
        await bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
        await queries.unban_user(target.id)
        await queries.log_admin_action(
            admin_id=message.from_user.id,
            action_type="unban",
            target_user_id=target.id,
            group_id=message.chat.id,
        )
        name = format_user_mention(target.id, target.first_name)
        await message.reply(f"✅ {name} ban ro'yxatidan chiqarildi.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────── /kick ───────────────────────────

@router.message(Command("kick"))
async def cmd_kick(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Chiqarish uchun xabarni reply qiling.")

    reason = parse_reason(message.text)
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id)  # kick = ban + unban
        await queries.log_admin_action(
            admin_id=message.from_user.id,
            action_type="kick",
            target_user_id=target.id,
            group_id=message.chat.id,
            details={"reason": reason}
        )
        name = format_user_mention(target.id, target.first_name)
        await message.reply(f"👢 {name} guruhdan chiqarildi.\n📝 Sabab: {reason}", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────── /mute ───────────────────────────

@router.message(Command("mute"))
async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ O'chirish uchun xabarni reply qiling.")

    # Parse optional duration: /mute 30 sabab → 30 daqiqa
    parts = (message.text or "").split(maxsplit=2)
    duration_minutes = 60
    reason = "Sabab ko'rsatilmadi"
    if len(parts) >= 2:
        try:
            duration_minutes = int(parts[1])
            reason = parts[2] if len(parts) > 2 else reason
        except ValueError:
            reason = " ".join(parts[1:])

    until = mute_until(duration_minutes)
    try:
        await bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=full_mute_permissions(),
            until_date=until
        )
        user_row = await queries.get_user(target.id)
        group_row = await queries.get_group(message.chat.id)
        if user_row and group_row:
            await queries.mute_user(user_row["id"], group_row["id"], message.from_user.id, until, reason)

        await queries.log_admin_action(
            admin_id=message.from_user.id,
            action_type="mute",
            target_user_id=target.id,
            group_id=message.chat.id,
            details={"reason": reason, "duration_minutes": duration_minutes}
        )
        name = format_user_mention(target.id, target.first_name)
        await message.reply(
            f"🔇 {name} {duration_minutes} daqiqaga o'chirildi.\n📝 Sabab: {reason}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────── /unmute ───────────────────────────

@router.message(Command("unmute"))
async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Unmute uchun xabarni reply qiling.")

    try:
        await bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=default_permissions()
        )
        user_row = await queries.get_user(target.id)
        group_row = await queries.get_group(message.chat.id)
        if user_row and group_row:
            await queries.unmute_user(user_row["id"], group_row["id"])

        await queries.log_admin_action(
            admin_id=message.from_user.id,
            action_type="unmute",
            target_user_id=target.id,
            group_id=message.chat.id,
        )
        name = format_user_mention(target.id, target.first_name)
        await message.reply(f"🔊 {name} unmute qilindi.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────── /warn ───────────────────────────

@router.message(Command("warn"))
async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Ogohlantirish uchun xabarni reply qiling.")

    reason = parse_reason(message.text)
    warnings = await queries.increment_warnings(target.id)
    max_w = int(await queries.get_setting("max_warnings") or "3")

    await queries.log_admin_action(
        admin_id=message.from_user.id,
        action_type="warn",
        target_user_id=target.id,
        group_id=message.chat.id,
        details={"reason": reason, "warnings": warnings}
    )

    name = format_user_mention(target.id, target.first_name)

    if warnings >= max_w:
        until = mute_until()
        try:
            await bot.restrict_chat_member(
                message.chat.id, target.id,
                permissions=full_mute_permissions(),
                until_date=until
            )
            await queries.reset_warnings(target.id)
            text = (
                f"⛔ {name} {max_w} ta ogohlantirish to'pladi — "
                f"60 daqiqaga o'chirildi.\n📝 Sabab: {reason}"
            )
        except Exception as e:
            text = f"⚠️ {name} ogohlantirish ({warnings}/{max_w}). Sabab: {reason}"
    else:
        text = f"⚠️ {name} ogohlantirish oldi ({warnings}/{max_w}).\n📝 Sabab: {reason}"

    await message.reply(text, parse_mode="HTML")


# ─────────────────────────── /clear ───────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message, bot: Bot):
    """Delete last N messages in chat. Usage: /clear [count=50]"""
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Bu buyruq faqat adminlar uchun.")

    parts = (message.text or "").split()
    count = 50
    if len(parts) > 1:
        try:
            count = min(int(parts[1]), 200)  # max 200
        except ValueError:
            pass

    deleted = 0
    errors = 0
    # Delete from current message upward
    start_id = message.message_id
    for msg_id in range(start_id, max(start_id - count - 1, 0), -1):
        try:
            await bot.delete_message(message.chat.id, msg_id)
            deleted += 1
        except Exception:
            errors += 1
            if errors > 10:
                break

    await queries.log_admin_action(
        admin_id=message.from_user.id,
        action_type="clear",
        group_id=message.chat.id,
        details={"deleted": deleted, "requested": count}
    )

    try:
        info = await bot.send_message(message.chat.id, f"🗑️ {deleted} ta xabar o'chirildi.")
        import asyncio
        await asyncio.sleep(5)
        await info.delete()
    except Exception:
        pass


# ─────────────────────────── /del ───────────────────────────

@router.message(Command("del"))
async def cmd_del(message: Message, bot: Bot):
    """Delete replied-to message."""
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return
    if message.reply_to_message:
        try:
            await message.reply_to_message.delete()
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass


# ─────────────────────────── /info ───────────────────────────

@router.message(Command("info"))
async def cmd_info(message: Message, bot: Bot):
    """Show info about replied-to user."""
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return

    target = get_target_user(message)
    if not target:
        return await message.reply("ℹ️ Foydalanuvchi haqida ma'lumot olish uchun xabarni reply qiling.")

    user_row = await queries.get_user(target.id)
    if not user_row:
        return await message.reply("❌ Foydalanuvchi topilmadi.")

    text = (
        f"👤 <b>Foydalanuvchi ma'lumoti</b>\n\n"
        f"🆔 ID: <code>{target.id}</code>\n"
        f"👤 Ism: {target.first_name or '-'}\n"
        f"🔖 Username: @{target.username or '-'}\n"
        f"⚠️ Ogohlantirishlar: {user_row['warnings']}\n"
        f"🚫 Ban: {'Ha' if user_row['is_banned'] else 'Yoq'}\n"
        f"📅 Ro'yxatdan o'tgan: {user_row['created_at'].strftime('%Y-%m-%d %H:%M')}"
    )
    await message.reply(text, parse_mode="HTML")


# ─────────────────────────── /rules ───────────────────────────

@router.message(Command("rules"))
async def cmd_rules(message: Message):
    """Show group rules."""
    text = (
        "📋 <b>Guruh qoidalari:</b>\n\n"
        "1️⃣ Reklama va havolalar taqiqlangan\n"
        "2️⃣ Haqoratli so'zlar taqiqlangan\n"
        "3️⃣ Spam taqiqlangan\n"
        "4️⃣ Adminlarga hurmat bilan munosabatda bo'ling\n\n"
        "⚠️ Qoidalarni buzish ogohlantirish yoki ban bilan yakunlanadi."
    )
    await message.reply(text, parse_mode="HTML")


# ─────────────────────────── /banset ──────────────────────────

@router.message(Command("banset"))
async def cmd_banset(message: Message, bot: Bot):
    """
    Stiker to'plamini blacklistga qo'shish.
    Ishlatish: /banset — taqiqlanadigan stikerga reply qiling
    """
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Faqat adminlar uchun.")

    # Reply stikerga tekshirish
    reply = message.reply_to_message
    if not reply or not reply.sticker:
        return await message.reply(
            "❌ Taqiqlamoqchi bo'lgan <b>stikerga reply</b> qilib /banset yozing.",
            parse_mode="HTML"
        )

    set_name = reply.sticker.set_name
    if not set_name:
        return await message.reply("❌ Bu stiker alohida to'plamda emas.")

    await queries.set_setting(f"banned_sticker_set_{set_name}", "1")
    logger.info(f"STICKER SET BANNED: {set_name} by admin {message.from_user.id}")

    await message.reply(
        f"🚫 <b>{set_name}</b> stiker to'plami taqiqlandi.\n"
        f"Ushbu to'plamdagi barcha stikerlar o'chiriladi.",
        parse_mode="HTML"
    )
    # Stikerning o'zini ham o'chiramiz
    try:
        await reply.delete()
    except Exception:
        pass


# ─────────────────────────── /unbanset ────────────────────────

@router.message(Command("unbanset"))
async def cmd_unbanset(message: Message, bot: Bot):
    """
    Stiker to'plamini blacklistdan chiqarish.
    Ishlatish: /unbanset — stikerga reply qiling
    """
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Faqat adminlar uchun.")

    reply = message.reply_to_message
    if not reply or not reply.sticker:
        return await message.reply(
            "❌ Chiqarmoqchi bo'lgan <b>stikerga reply</b> qilib /unbanset yozing.",
            parse_mode="HTML"
        )

    set_name = reply.sticker.set_name
    if not set_name:
        return await message.reply("❌ Bu stiker alohida to'plamda emas.")

    existing = await queries.get_setting(f"banned_sticker_set_{set_name}")
    if not existing:
        return await message.reply(f"ℹ️ <b>{set_name}</b> blacklistda emas.", parse_mode="HTML")

    # bot_settings dan o'chirish
    from database.connection import get_pool
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM bot_settings WHERE key = $1",
        f"banned_sticker_set_{set_name}"
    )
    logger.info(f"STICKER SET UNBANNED: {set_name} by admin {message.from_user.id}")
    await message.reply(
        f"✅ <b>{set_name}</b> blacklistdan chiqarildi.",
        parse_mode="HTML"
    )


# ── Bot admini tekshiruvi (banimage/unbanimage uchun) ─────────────────

async def _is_bot_admin(user_id: int) -> bool:
    """Faqat bot admini (config da yoki bot_settings da) — guruh admini emas."""
    from bot.config import settings
    if user_id in settings.admin_ids:
        return True
    from database.connection import get_pool
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM bot_settings WHERE key = 'extra_admin_' || $1::text", str(user_id)
    )
    return row is not None


# ── /banimage — rasmni taqiqlash ─────────────────────────────────────

@router.message(Command("banimage"))
async def cmd_banimage(message: Message, bot: Bot):
    if not await _is_bot_admin(message.from_user.id):
        return

    from bot.services.image_hash import compute_all_hashes_async, segment_hashes_to_str, is_imagehash_available
    if not is_imagehash_available():
        return await message.reply(
            "imagehash o'rnatilmagan. Buyruq: pip install imagehash Pillow"
        )

    reply = message.reply_to_message
    if not reply or not reply.photo:
        return await message.reply(
            "Taqiqlamoqchi bo'lgan rasmga reply qilib /banimage yozing.\n"
            "Yoki bot lichkasiga rasm yuboring — u yerdan ham qo'shish mumkin."
        )

    photo = reply.photo[-1]
    try:
        tg_file = await bot.get_file(photo.file_id)
        buf = await bot.download_file(tg_file.file_path)
        image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
    except Exception as e:
        return await message.reply(f"Rasm yuklab bo'lmadi: {e}")

    phash, seg_hashes = await compute_all_hashes_async(image_bytes)
    if not phash:
        return await message.reply("Rasmdan hash hisoblashda xatolik.")

    seg_str = segment_hashes_to_str(seg_hashes)
    parts = (message.text or "").split(maxsplit=1)
    note = parts[1].strip() if len(parts) > 1 else ""

    ok = await queries.add_banned_image(phash, message.from_user.id, note, seg_str)
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    await invalidate_banned_hashes_cache()

    if ok:
        logger.info(f"IMAGE BANNED: hash={phash} by={message.from_user.id}")
        note_text = f"\nIzoh: {note}" if note else ""
        await message.reply(
            f"Rasm taqiqlandi!\nHash: {phash[:20]}...{note_text}"
        )
    else:
        await message.reply("Bu rasm allaqachon taqiqlangan.")


# ── /unbanimage — rasmdan taqiqni olib tashlash ──────────────────────


@router.message(Command("unbanimage"))
async def cmd_unbanimage(message: Message, bot: Bot):
    if not await _is_bot_admin(message.from_user.id):
        return

    from bot.services.image_hash import compute_phash_async, is_imagehash_available
    if not is_imagehash_available():
        return await message.reply("imagehash o'rnatilmagan.")

    reply = message.reply_to_message
    if not reply or not reply.photo:
        return await message.reply("Rasmga reply qilib /unbanimage yozing.")

    photo = reply.photo[-1]
    try:
        tg_file = await bot.get_file(photo.file_id)
        buf = await bot.download_file(tg_file.file_path)
        image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
    except Exception as e:
        return await message.reply(f"Rasm yuklab bo'lmadi: {e}")

    phash = await compute_phash_async(image_bytes)
    if not phash:
        return await message.reply("Rasmdan hash hisoblashda xatolik.")

    ok = await queries.remove_banned_image(phash)
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    await invalidate_banned_hashes_cache()

    if ok:
        logger.info(f"IMAGE UNBANNED: hash={phash} by={message.from_user.id}")
        await message.reply("Rasmdan taqiq olib tashlandi.")
    else:
        await message.reply("Bu rasm taqiqlangan emas edi.")