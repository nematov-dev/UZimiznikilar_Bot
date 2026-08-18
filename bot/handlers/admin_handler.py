"""Admin buyruqlari — faqat shaxsiy chat."""
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, KeyboardButton,
    ReplyKeyboardMarkup, InlineKeyboardMarkup
)
from loguru import logger

from bot.config import settings
from database import queries
from database.connection import get_pool

router = Router()
router.message.filter(F.chat.type == "private")

# Rasm taqiqlash uchun vaqtinchalik cache (phash → (phash, segment_hashes))
_image_cache: dict = {}


# ── Admin tekshiruvi ──────────────────────────────────────────

async def is_bot_admin(user_id: int) -> bool:
    if user_id in settings.admin_ids:
        return True
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM bot_settings WHERE key = 'extra_admin_' || $1::text", str(user_id)
    )
    return row is not None


# ── FSM ───────────────────────────────────────────────────────

class BannedWordState(StatesGroup):
    add = State()
    delete = State()

class BroadcastState(StatesGroup):
    message = State()
    target = State()

class OcrTextState(StatesGroup):
    add = State()
    delete = State()

class BannedNameState(StatesGroup):
    add = State()
    delete = State()


# ── Klaviaturalar ─────────────────────────────────────────────

def admin_menu() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🚫 Taqiqlangan so'zlar"))
    b.row(KeyboardButton(text="🏘️ Guruhlar"), KeyboardButton(text="📢 Xabar yuborish"))
    b.row(KeyboardButton(text="📅 Rejalashtirilgan xabarlar"), KeyboardButton(text="🖼 Taqiqlangan rasmlar"))
    b.row(KeyboardButton(text="📝 Rasm matni (OCR)"), KeyboardButton(text="👤 Taqiqlangan Niklar"))
    b.row(KeyboardButton(text="👤 Adminlar boshqaruvi"))
    return b.as_markup(resize_keyboard=True)

def cancel_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.add(KeyboardButton(text="❌ Bekor"))
    return b.as_markup(resize_keyboard=True)

def bn_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Nik qo'shish", callback_data="bn_add"),
        InlineKeyboardButton(text="🗑 Nik o'chirish", callback_data="bn_del"),
    )
    b.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="bn_refresh"))
    return b.as_markup()

def bw_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Qo'shish", callback_data="bw_add"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data="bw_del"),
    )
    b.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="bw_refresh"))
    return b.as_markup()

def broadcast_target_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="👤 Foydalanuvchilarga", callback_data="bcast:users"),
        InlineKeyboardButton(text="🏘️ Guruhlarga", callback_data="bcast:groups"),
    )
    b.row(InlineKeyboardButton(text="🌐 Hammaga (user + guruh)", callback_data="bcast:all"))
    b.row(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bcast:cancel"))
    return b.as_markup()

def groups_kb(groups: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups[:15]:
        b.row(InlineKeyboardButton(
            text=f"⚙️ {g['title'][:30]}",
            callback_data=f"grp:{g['telegram_id']}"
        ))
    return b.as_markup()

def group_settings_kb(gid: int, g: dict) -> InlineKeyboardMarkup:
    def s(v): return "✅" if v else "❌"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"{s(g['anti_links'])} Reklama/havolalar",
        callback_data=f"gtoggle:{gid}:anti_links"
    ))
    b.row(InlineKeyboardButton(
        text=f"{s(g['anti_profanity'])} Haqoratli so'zlar",
        callback_data=f"gtoggle:{gid}:anti_profanity"
    ))
    b.row(InlineKeyboardButton(
        text=f"{s(g.get('anti_nsfw', True))} 🔞 18+ kontent (rasm/gif/stiker)",
        callback_data=f"gtoggle:{gid}:anti_nsfw"
    ))
    b.row(InlineKeyboardButton(
        text=f"{s(g['delete_join_leave'])} Kirdi/chiqdi o'chirish",
        callback_data=f"gtoggle:{gid}:delete_join_leave"
    ))
    b.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="grp_back"))
    return b.as_markup()


# ── /start ────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not await is_bot_admin(message.from_user.id):
        await message.answer(
            "Salom! Men <b>Uzimiznikilar</b> guruh boshqaruv botiman 🤖",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "Salom, Admin! Nima qilishni xohlaysiz?",
        reply_markup=admin_menu()
    )


# ── 📊 Statistika ─────────────────────────────────────────────

@router.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    if not await is_bot_admin(message.from_user.id):
        return

    stats = await queries.get_stats_overview()
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"🚫 Banlangan: <b>{stats['banned_users']}</b>\n"
        f"🏘️ Guruhlar: <b>{stats['total_groups']}</b>\n"
        f"💬 Bugungi xabarlar: <b>{stats['messages_today']}</b>\n"
        f"🗑 O'chirilgan: <b>{stats['deleted_today']}</b>",
        parse_mode="HTML"
    )


# ── 🚫 Taqiqlangan so'zlar ────────────────────────────────────

def _words_text(words):
    count = len(words)
    text = f"🚫 <b>Taqiqlangan so'zlar</b> ({count} ta)\n\n"
    if words:
        for i, w in enumerate(words[:50], 1):
            text += f"{i}. <code>{w['word']}</code>\n"
        if count > 50:
            text += f"... va yana {count-50} ta"
    else:
        text += "Ro'yxat bo'sh."
    return text


@router.message(F.text == "🚫 Taqiqlangan so'zlar")
async def bw_menu(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.clear()
    words = await queries.get_banned_words()
    await message.answer(_words_text(words), parse_mode="HTML", reply_markup=bw_menu_kb())


@router.callback_query(F.data == "bw_refresh")
async def bw_refresh(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    words = await queries.get_banned_words()
    await cb.message.edit_text(_words_text(words), parse_mode="HTML", reply_markup=bw_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "bw_add")
async def bw_add_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(BannedWordState.add)
    await cb.message.answer(
        "So'z yozing (bir nechta bo'lsa — har biri yangi qatorda):",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(BannedWordState.add)
async def bw_add_receive(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_menu())

    lines = [w.strip().lower() for w in message.text.splitlines() if w.strip()]
    added, skipped = [], []
    for w in lines:
        ok = await queries.add_banned_word(w, message.from_user.id)
        (added if ok else skipped).append(w)

    if added:
        from bot.services.moderation import refresh_banned_words_cache
        await refresh_banned_words_cache()

    await state.clear()
    parts = []
    if added:
        parts.append("✅ Qo'shildi:\n" + "\n".join(f"• <code>{w}</code>" for w in added))
    if skipped:
        parts.append("⚠️ Allaqachon bor:\n" + "\n".join(f"• <code>{w}</code>" for w in skipped))

    await message.answer("\n\n".join(parts), parse_mode="HTML", reply_markup=admin_menu())
    words = await queries.get_banned_words()
    await message.answer(_words_text(words), parse_mode="HTML", reply_markup=bw_menu_kb())


@router.callback_query(F.data == "bw_del")
async def bw_del_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(BannedWordState.delete)
    await cb.message.answer(
        "O'chirmoqchi bo'lgan so'zni yozing — bot topib tasdiqlatadi:",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(BannedWordState.delete)
async def bw_del_search(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_menu())

    q = message.text.strip().lower()
    words = await queries.get_banned_words()
    found = [w for w in words if q in w["word"]]

    if not found:
        return await message.answer(f"❌ <b>«{q}»</b> topilmadi. Qayta yozing.", parse_mode="HTML")

    await state.clear()
    b = InlineKeyboardBuilder()
    text = f"🔍 «{q}» bo'yicha topildi:\n\n"
    for w in found[:10]:
        text += f"• <code>{w['word']}</code>\n"
        b.row(InlineKeyboardButton(
            text=f"🗑 «{w['word']}»",
            callback_data=f"bwdel:{w['id']}:{w['word'][:20]}"
        ))
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data="bwdel_cancel"))

    await message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("bwdel:"))
async def bw_del_confirm(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, wid, wtext = cb.data.split(":", 2)
    pool = await get_pool()
    await pool.execute("DELETE FROM banned_words WHERE id = $1", int(wid))
    from bot.services.moderation import refresh_banned_words_cache
    await refresh_banned_words_cache()
    await cb.message.edit_text(f"✅ <b>«{wtext}»</b> o'chirildi.", parse_mode="HTML")
    words = await queries.get_banned_words()
    await cb.message.answer(_words_text(words), parse_mode="HTML", reply_markup=bw_menu_kb())
    await cb.answer("O'chirildi!")


@router.callback_query(F.data == "bwdel_cancel")
async def bw_del_cancel(cb: CallbackQuery):
    await cb.message.edit_text("Bekor qilindi.")
    await cb.answer()


# ── 🏘️ Guruhlar ───────────────────────────────────────────────

@router.message(F.text == "🏘️ Guruhlar")
async def show_groups(message: Message):
    if not await is_bot_admin(message.from_user.id):
        return
    groups = await queries.get_all_groups()
    if not groups:
        return await message.answer("Hali birorta guruhga qo'shilmadim.")
    text = f"🏘️ <b>Guruhlar</b> ({len(groups)} ta)\n\nSozlamoqchi bo'lgan guruhni tanlang:"
    await message.answer(text, parse_mode="HTML", reply_markup=groups_kb(groups))


@router.callback_query(F.data.startswith("grp:"))
async def group_detail(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    gid = int(cb.data.split(":")[1])
    group = await queries.get_group(gid)
    if not group:
        return await cb.answer("Guruh topilmadi")
    text = (
        f"⚙️ <b>{group['title']}</b>\n\n"
        f"ID: <code>{group['telegram_id']}</code>\n"
        f"Sozlamalarni o'zgartiring:"
    )
    await cb.message.edit_text(text, parse_mode="HTML",
                                reply_markup=group_settings_kb(gid, dict(group)))
    await cb.answer()


@router.callback_query(F.data.startswith("gtoggle:"))
async def group_toggle(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, gid, field = cb.data.split(":")
    gid = int(gid)
    group = await queries.get_group(gid)
    if not group:
        return await cb.answer("Topilmadi")
    new_val = not group[field]
    await queries.update_group_settings(gid, **{field: new_val})
    group = await queries.get_group(gid)
    text = f"⚙️ <b>{group['title']}</b>\n\nSozlamalarni o'zgartiring:"
    await cb.message.edit_text(text, parse_mode="HTML",
                                reply_markup=group_settings_kb(gid, dict(group)))
    await cb.answer("Yangilandi!")


@router.callback_query(F.data == "grp_back")
async def group_back(cb: CallbackQuery):
    groups = await queries.get_all_groups()
    text = f"🏘️ <b>Guruhlar</b> ({len(groups)} ta)\n\nSozlamoqchi bo'lgan guruhni tanlang:"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=groups_kb(groups))
    await cb.answer()


# ── 📢 Xabar yuborish ─────────────────────────────────────────

@router.message(F.text == "📢 Xabar yuborish")
async def broadcast_start(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.message)
    await message.answer(
        "📢 <b>Xabar yuborish</b>\n\n"
        "Yubormoqchi bo'lgan xabarni yozing:\n"
        "• Oddiy matn\n"
        "• Rasm (caption bilan yoki siz)\n"
        "• Video\n\n"
        "Keyin kimga yuborishni tanlaysiz.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


@router.message(BroadcastState.message)
async def broadcast_get_msg(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor.", reply_markup=admin_menu())

    msg_data = {
        "text": message.text or message.caption or "",
        "file_id": None, "media_type": None,
    }
    if message.photo:
        msg_data["file_id"] = message.photo[-1].file_id
        msg_data["media_type"] = "photo"
    elif message.video:
        msg_data["file_id"] = message.video.file_id
        msg_data["media_type"] = "video"

    await state.update_data(msg=msg_data)
    await state.set_state(BroadcastState.target)
    await message.answer(
        "📨 <b>Kimga yuborilsin?</b>\n\n"
        "👤 <b>Foydalanuvchilarga</b> — botga /start bosgan odamlarga\n"
        "🏘️ <b>Guruhlarga</b> — bot qo'shilgan guruhlarga\n"
        "🌐 <b>Hammaga</b> — ikkalasiga ham",
        parse_mode="HTML",
        reply_markup=broadcast_target_kb()
    )


@router.callback_query(F.data.startswith("bcast:"), BroadcastState.target)
async def broadcast_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    target = cb.data.split(":")[1]
    if target == "cancel":
        await state.clear()
        await cb.message.edit_text("Bekor qilindi.")
        return await cb.answer()

    data = await state.get_data()
    msg_data = data["msg"]
    await state.clear()

    broadcast_id = await queries.create_broadcast(
        message_text=msg_data["text"],
        sent_by=cb.from_user.id,
        target=target,
        media_file_id=msg_data["file_id"],
        media_type=msg_data["media_type"],
    )

    await cb.message.edit_text("📤 Yuborilmoqda...")
    asyncio.create_task(_do_broadcast(bot, broadcast_id, msg_data, target, cb.message))
    await cb.answer()


async def _do_broadcast(bot: Bot, bid: int, msg_data: dict, target: str, status_msg):
    success = fail = 0
    recipients = []

    if target in ("users", "all"):
        users = await queries.get_all_users(limit=100000)
        recipients += [(u["telegram_id"], "user") for u in users if not u["is_banned"]]
    if target in ("groups", "all"):
        groups = await queries.get_all_groups()
        recipients += [(g["telegram_id"], "group") for g in groups]

    for chat_id, _ in recipients:
        try:
            mt = msg_data.get("media_type")
            fid = msg_data.get("file_id")
            txt = msg_data.get("text", "")
            if mt == "photo":
                await bot.send_photo(chat_id, fid, caption=txt)
            elif mt == "video":
                await bot.send_video(chat_id, fid, caption=txt)
            else:
                await bot.send_message(chat_id, txt)
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    await queries.update_broadcast_stats(bid, success, fail)
    try:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="go_main_menu"))
        await status_msg.edit_text(
            f"✅ <b>Xabar yuborildi!</b>\n\n"
            f"👥 Muvaffaqiyatli: <b>{success}</b>\n"
            f"❌ Xato: <b>{fail}</b>\n"
            f"📊 Jami: <b>{success + fail}</b>",
            parse_mode="HTML",
            reply_markup=b.as_markup()
        )
    except Exception:
        pass


# ── 👤 Adminlar boshqaruvi ────────────────────────────────────

class AdminState(StatesGroup):
    add_id = State()


async def _admins_text_kb():
    pool = await get_pool()
    extra = await pool.fetch(
        "SELECT key, value FROM bot_settings WHERE key LIKE 'extra_admin_%'"
    )
    text = "👤 <b>Bot adminlari</b>\n\n"
    text += "<b>Asosiy (.env):</b>\n"
    for aid in settings.admin_ids:
        text += f"• <code>{aid}</code>\n"
    if extra:
        text += "\n<b>Qo'shimcha:</b>\n"
        for row in extra:
            uid = row["key"].replace("extra_admin_", "")
            text += f"• <code>{uid}</code> — {row['value']}\n"

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm_add"),
    )
    for row in extra:
        uid = row["key"].replace("extra_admin_", "")
        b.row(InlineKeyboardButton(
            text=f"🗑 {row['value']} ({uid}) ni o'chirish",
            callback_data=f"adm_del:{uid}"
        ))
    return text, b.as_markup()


@router.message(F.text == "👤 Adminlar boshqaruvi")
async def admins_menu(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.clear()
    text, kb = await _admins_text_kb()
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "adm_add")
async def adm_add_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(AdminState.add_id)
    await cb.message.answer(
        "Yangi admin Telegram ID sini yozing:\n<i>(Foydalanuvchi botga /start bosgan bo'lishi kerak)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(AdminState.add_id)
async def adm_add_receive(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor.", reply_markup=admin_menu())

    if not message.text.isdigit():
        return await message.answer("Faqat raqam kiriting (Telegram ID).")

    uid = message.text.strip()
    pool = await get_pool()
    user_row = await pool.fetchrow(
        "SELECT first_name, username FROM users WHERE telegram_id = $1", int(uid)
    )
    name = user_row["first_name"] if user_row else uid

    await pool.execute(
        "INSERT INTO bot_settings(key, value) VALUES ($1, $2) "
        "ON CONFLICT(key) DO UPDATE SET value=$2",
        f"extra_admin_{uid}", name
    )
    await state.clear()
    await message.answer(f"✅ <code>{uid}</code> ({name}) admin qilindi.", parse_mode="HTML",
                         reply_markup=admin_menu())
    text, kb = await _admins_text_kb()
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("adm_del:"))
async def adm_del(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    uid = cb.data.split(":")[1]
    if int(uid) in settings.admin_ids:
        return await cb.answer("Asosiy adminni o'chirib bo'lmaydi!", show_alert=True)
    pool = await get_pool()
    await pool.execute("DELETE FROM bot_settings WHERE key = $1", f"extra_admin_{uid}")
    await cb.answer(f"{uid} adminlikdan olindi.")
    text, kb = await _admins_text_kb()
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── /addword /delword ─────────────────────────────────────────

@router.message(Command("addword"))
async def cmd_addword(message: Message):
    if not await is_bot_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Ishlatish: /addword <so'z>")
    word = parts[1].strip().lower()
    ok = await queries.add_banned_word(word, message.from_user.id)
    if ok:
        from bot.services.moderation import refresh_banned_words_cache
        await refresh_banned_words_cache()
        await message.answer(f"✅ <code>{word}</code> qo'shildi.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Allaqachon bor.")


@router.message(Command("delword"))
async def cmd_delword(message: Message):
    if not await is_bot_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Ishlatish: /delword <so'z>")
    word = parts[1].strip().lower()
    ok = await queries.remove_banned_word(word)
    if ok:
        from bot.services.moderation import refresh_banned_words_cache
        await refresh_banned_words_cache()
        await message.answer(f"✅ <code>{word}</code> o'chirildi.", parse_mode="HTML")
    else:
        await message.answer("❌ Topilmadi.")


# ── Rejalashtirilgan xabarlar menyusi ────────────────────────

@router.message(F.text == "📅 Rejalashtirilgan xabarlar")
async def open_scheduled_posts(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.clear()
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📋 Xabarlarni ko'rish", callback_data="sp_list:0"),
        InlineKeyboardButton(text="➕ Yangi post", callback_data="sp_new"),
    )
    await message.answer(
        "📅 <b>Rejalashtirilgan xabarlar</b>\n\n"
        "Har kuni belgilangan vaqtlarda guruhlarga avtomatik xabar yuboradi.",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


# ── PM da rasm yuborish → taqiqlash ──────────────────────────

@router.message(F.photo, F.chat.type == "private")
async def pm_photo_ban(message: Message, bot: Bot):
    """Admin PM ga rasm yuborganda — taqiqlash taklif etiladi."""
    if not await is_bot_admin(message.from_user.id):
        return  # Oddiy foydalanuvchi rasm yuborganda — ignore

    from bot.services.image_hash import compute_all_hashes_async, segment_hashes_to_str, is_imagehash_available
    if not is_imagehash_available():
        return await message.reply(
            "imagehash o'rnatilmagan: pip install imagehash"
        )

    photo = message.photo[-1]
    try:
        tg_file = await bot.get_file(photo.file_id)
        buf = await bot.download_file(tg_file.file_path)
        image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
    except Exception as e:
        return await message.reply(f"Rasm yuklab bo'lmadi: {e}")

    phash, seg_hashes = await compute_all_hashes_async(image_bytes)
    if not phash:
        return await message.reply("Hash hisoblashda xatolik.")

    seg_str = segment_hashes_to_str(seg_hashes)

    # Hash + segment hashni callback data ga yozmaslik uchun FSM cache ishlatamiz
    # Uning o'rniga faqat phash + segment_hashes ni state ga saqlaymiz
    import hashlib
    cache_key = hashlib.md5(phash.encode()).hexdigest()[:8]
    # Muvaqqat xotira — bot ishlab turganda saqlanadi
    _image_cache[cache_key] = (phash, seg_str)

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🚫 Taqiqlash", callback_data=f"ban_img:{cache_key}"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="ban_img:cancel"),
    )
    await message.reply(
        "🖼 Bu rasmni taqiqlasinmi?\n"
        "Kimdir shu rasmni guruhga yuborganda bot o'chiradi.",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.startswith("ban_img:"))
async def cb_ban_image(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")

    data = cb.data.split(":", 1)[1]

    if data == "cancel":
        await cb.message.edit_text("Bekor qilindi.")
        return await cb.answer()

    phash = data
    phash, seg_str = _image_cache.pop(data, (data, ""))
    ok = await queries.add_banned_image(phash, cb.from_user.id, "", seg_str)
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    await invalidate_banned_hashes_cache()

    # Taqiqlangandan keyin "Yana qo'shish" tugmasi
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Yana rasm qo'shish", callback_data="ban_img_more"))
    b.row(InlineKeyboardButton(text="📋 Ro'yxat", callback_data="bi_refresh"))

    if ok:
        logger.info(f"IMAGE BANNED via PM: hash={phash} by={cb.from_user.id}")
        await cb.message.edit_text(
            "✅ Rasm taqiqlandi!\n"
            "Endi bu rasmni kim guruhga yuborsа — bot o'chiradi.\n\n"
            "Yana rasm qo'shish uchun menga rasm yuboring.",
            reply_markup=b.as_markup()
        )
    else:
        await cb.message.edit_text(
            "ℹ️ Bu rasm allaqachon taqiqlangan.\n\n"
            "Yana rasm qo'shish uchun menga rasm yuboring.",
            reply_markup=b.as_markup()
        )
    await cb.answer()


@router.callback_query(F.data == "ban_img_more")
async def cb_ban_img_more(cb: CallbackQuery):
    """'Yana rasm qo'shish' tugmasi — faqat yo'riqnoma ko'rsatadi."""
    await cb.message.edit_text(
        "📤 Taqiqlamoqchi bo'lgan rasmni yuboring.\n\n"
        "Galереyangizdan istalgan rasmni shu chatga yuboring — "
        "bot tasdiqlamanı so'raydi."
    )
    await cb.answer()


# ── Taqiqlangan rasmlar menyusi ──────────────────────────────

def _banned_images_text_kb(images: list):
    """Matn va keyboard — open va refresh uchun umumiy."""
    if not images:
        text = (
            "🖼 <b>Taqiqlangan rasmlar</b>\n\n"
            "Hozircha taqiqlangan rasm yo'q.\n\n"
            "Rasm qo'shish uchun menga rasm yuboring."
        )
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="➕ Rasm qo'shish", callback_data="ban_img_more"))
        b.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="bi_refresh"))
        return text, b.as_markup()

    lines = [f"🖼 <b>Taqiqlangan rasmlar</b> ({len(images)} ta)\n"]
    for img in images[:20]:
        note = f" — {img['note']}" if img.get("note") else ""
        lines.append(f"• <code>{img['phash'][:16]}...</code>{note}")
    if len(images) > 20:
        lines.append(f"\n...va yana {len(images)-20} ta")
    text = "\n".join(lines)

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Rasm qo'shish", callback_data="ban_img_more"))
    # Har bir rasm uchun alohida "O'chirish" tugmasi
    for img in images[:15]:
        short = img['phash'][:12] + "..."
        b.row(InlineKeyboardButton(
            text=f"🗑 {short}",
            callback_data=f"bi_del:{img['id']}"
        ))
    b.row(
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="bi_refresh"),
        InlineKeyboardButton(text="🗑 Hammasini o'chirish", callback_data="bi_clear"),
    )
    return text, b.as_markup()


@router.message(F.text == "🖼 Taqiqlangan rasmlar")
async def open_banned_images(message: Message):
    if not await is_bot_admin(message.from_user.id):
        return
    images = await queries.get_banned_images_list()
    text, kb = _banned_images_text_kb(images)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "bi_refresh")
async def bi_refresh(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    await invalidate_banned_hashes_cache()
    images = await queries.get_banned_images_list()
    text, kb = _banned_images_text_kb(images)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Yangilandi")


@router.callback_query(F.data.startswith("bi_del:"))
async def bi_del_one(cb: CallbackQuery):
    """Bitta rasmni o'chirish."""
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    image_id = int(cb.data.split(":")[1])
    await queries.delete_banned_image_by_id(image_id)
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    await invalidate_banned_hashes_cache()
    # Ro'yxatni yangilash
    images = await queries.get_banned_images_list()
    text, kb = _banned_images_text_kb(images)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("O'chirildi")


@router.callback_query(F.data == "bi_clear")
async def bi_clear(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Ha, o'chirish", callback_data="bi_clear_confirm"),
        InlineKeyboardButton(text="Bekor", callback_data="bi_refresh"),
    )
    await cb.message.edit_text(
        "Barcha taqiqlangan rasmlarni o'chirmoqchimisiz?",
        reply_markup=b.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data == "bi_clear_confirm")
async def bi_clear_confirm(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    from database.connection import get_pool
    from bot.middlewares.moderation import invalidate_banned_hashes_cache
    pool = await get_pool()
    await pool.execute("DELETE FROM banned_images")
    await invalidate_banned_hashes_cache()
    await cb.message.edit_text("Barcha taqiqlangan rasmlar o'chirildi.")
    await cb.answer()


# ── 📝 Rasm matni (OCR) ───────────────────────────────────────

def _ocr_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Qo'shish", callback_data="ocr_add"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data="ocr_del"),
    )
    b.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="ocr_refresh"))
    return b.as_markup()


def _ocr_list_text(items: list) -> str:
    count = len(items)
    text = f"📝 <b>Taqiqlangan rasm matnlari (OCR)</b> ({count} ta)\n\n"
    text += "ℹ️ Rasm ichida shu matn bo'lsa — bot o'chiradi + taqiqlaydi.\n\n"
    if items:
        for i, row in enumerate(items[:50], 1):
            text += f"{i}. <code>{row['text']}</code>\n"
        if count > 50:
            text += f"... va yana {count - 50} ta"
    else:
        text += "Ro'yxat bo'sh.\n\nQo'shish uchun ➕ Qo'shish tugmasini bosing."
    return text


@router.message(F.text == "📝 Rasm matni (OCR)")
async def ocr_menu(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.clear()
    items = await queries.get_banned_ocr_texts()
    await message.answer(
        _ocr_list_text(items), parse_mode="HTML", reply_markup=_ocr_menu_kb()
    )


@router.callback_query(F.data == "ocr_refresh")
async def ocr_refresh(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    from bot.services.ocr import refresh_ocr_cache
    await refresh_ocr_cache()
    items = await queries.get_banned_ocr_texts()
    await cb.message.edit_text(
        _ocr_list_text(items), parse_mode="HTML", reply_markup=_ocr_menu_kb()
    )
    await cb.answer("Yangilandi")


@router.callback_query(F.data == "ocr_add")
async def ocr_add_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(OcrTextState.add)
    await cb.message.answer(
        "📝 <b>Taqiqlangan rasm matni qo'shish</b>\n\n"
        "Misol: <code>reklama.uz</code> yoki <code>+998901234567</code>\n"
        "Har biri yangi qatorda yozishingiz mumkin.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(OcrTextState.add)
async def ocr_add_receive(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_menu())

    lines = [ln.strip().lower() for ln in message.text.splitlines() if ln.strip()]
    added, skipped = [], []
    for ln in lines:
        ok = await queries.add_banned_ocr_text(ln, message.from_user.id)
        (added if ok else skipped).append(ln)

    if added:
        from bot.services.ocr import refresh_ocr_cache
        await refresh_ocr_cache()

    await state.clear()
    parts = []
    if added:
        parts.append("✅ Qo'shildi:\n" + "\n".join(f"• <code>{t}</code>" for t in added))
    if skipped:
        parts.append("⚠️ Allaqachon bor:\n" + "\n".join(f"• <code>{t}</code>" for t in skipped))
    await message.answer(
        "\n\n".join(parts) or "Hech narsa qo'shilmadi.",
        parse_mode="HTML", reply_markup=admin_menu()
    )
    items = await queries.get_banned_ocr_texts()
    await message.answer(_ocr_list_text(items), parse_mode="HTML", reply_markup=_ocr_menu_kb())


@router.callback_query(F.data == "ocr_del")
async def ocr_del_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(OcrTextState.delete)
    await cb.message.answer(
        "O'chirmoqchi bo'lgan matnni yozing — bot topib ko'rsatadi:",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(OcrTextState.delete)
async def ocr_del_search(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor.", reply_markup=admin_menu())

    q = message.text.strip().lower()
    items = await queries.get_banned_ocr_texts()
    found = [row for row in items if q in row["text"]]

    if not found:
        return await message.answer(
            f"❌ <b>«{q}»</b> topilmadi. Qayta yozing.", parse_mode="HTML"
        )

    await state.clear()
    b = InlineKeyboardBuilder()
    text = f"🔍 «{q}» bo'yicha topildi:\n\n"
    for row in found[:10]:
        text += f"• <code>{row['text']}</code>\n"
        b.row(InlineKeyboardButton(
            text=f"🗑 {row['text'][:30]}",
            callback_data=f"ocrdel:{row['id']}"
        ))
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data="ocrdel_cancel"))
    await message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("ocrdel:"))
async def ocr_del_confirm(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    item_id = int(cb.data.split(":")[1])
    ok = await queries.remove_banned_ocr_text(item_id)
    if ok:
        from bot.services.ocr import refresh_ocr_cache
        await refresh_ocr_cache()
        await cb.message.edit_text("✅ O'chirildi.")
    else:
        await cb.message.edit_text("❌ Topilmadi.")
    items = await queries.get_banned_ocr_texts()
    await cb.message.answer(
        _ocr_list_text(items), parse_mode="HTML", reply_markup=_ocr_menu_kb()
    )
    await cb.answer()


@router.callback_query(F.data == "ocrdel_cancel")
async def ocr_del_cancel(cb: CallbackQuery):
    await cb.message.edit_text("Bekor qilindi.")
    await cb.answer()


# ── 👤 Taqiqlangan Niklar ─────────────────────────────────────

def _bn_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Qo'shish", callback_data="bn_add"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data="bn_del"),
    )
    b.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="bn_refresh"))
    return b.as_markup()


def _bn_list_text(items: list) -> str:
    count = len(items)
    text = f"👤 <b>Taqiqlangan ism/niklar</b> ({count} ta)\n\n"
    text += "ℹ️ Foydalanuvchi ismida (First/Last name) yoki username'ida shu matn bo'lsa — bot darhol guruhdan ban qiladi va barcha xabarlarini o'chiradi.\n\n"
    text += "ℹ️ <i>Eslatma: agar <code>@spammer</code> ko'rinishida yozsangiz - faqat username aniq mos kelganda ban qiladi. Agar <code>spammer</code> deb yozsangiz, ismida yoki username'ida 'spammer' so'zi qatnashgan hammani ban qiladi.</i>\n\n"
    if items:
        for i, row in enumerate(items[:50], 1):
            text += f"{i}. <code>{row['name']}</code>\n"
        if count > 50:
            text += f"... va yana {count - 50} ta"
    else:
        text += "Ro'yxat bo'sh.\n\nQo'shish uchun ➕ Qo'shish tugmasini bosing."
    return text


@router.message(F.text == "👤 Taqiqlangan Niklar")
async def bn_menu(message: Message, state: FSMContext):
    if not await is_bot_admin(message.from_user.id):
        return
    await state.clear()
    items = await queries.get_banned_names()
    await message.answer(
        _bn_list_text(items), parse_mode="HTML", reply_markup=_bn_menu_kb()
    )


@router.callback_query(F.data == "bn_refresh")
async def bn_refresh(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    from bot.services.moderation import refresh_banned_names_cache
    await refresh_banned_names_cache()
    items = await queries.get_banned_names()
    await cb.message.edit_text(
        _bn_list_text(items), parse_mode="HTML", reply_markup=_bn_menu_kb()
    )
    await cb.answer("Yangilandi")


@router.callback_query(F.data == "bn_add")
async def bn_add_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(BannedNameState.add)
    await cb.message.answer(
        "👤 <b>Taqiqlangan ism/nik qo'shish</b>\n\n"
        "Misol:\n"
        "1. <code>@spammer_bot</code> (faqat username mos kelganda ban qiladi)\n"
        "2. <code>trading</code> (ismida yoki username'ida shu so'z qatnashgan hammani ban qiladi)\n\n"
        "Har birini yangi qatorda yozing.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(BannedNameState.add)
async def bn_add_receive(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_menu())

    lines = [ln.strip().lower() for ln in message.text.splitlines() if ln.strip()]
    added, skipped = [], []
    for ln in lines:
        ok = await queries.add_banned_name(ln, message.from_user.id)
        (added if ok else skipped).append(ln)

    if added:
        from bot.services.moderation import refresh_banned_names_cache
        await refresh_banned_names_cache()

    await state.clear()
    parts = []
    if added:
        parts.append("✅ Qo'shildi:\n" + "\n".join(f"• <code>{t}</code>" for t in added))
    if skipped:
        parts.append("⚠️ Allaqachon bor:\n" + "\n".join(f"• <code>{t}</code>" for t in skipped))
    await message.answer(
        "\n\n".join(parts) or "Hech narsa qo'shilmadi.",
        parse_mode="HTML", reply_markup=admin_menu()
    )
    items = await queries.get_banned_names()
    await message.answer(_bn_list_text(items), parse_mode="HTML", reply_markup=_bn_menu_kb())


@router.callback_query(F.data == "bn_del")
async def bn_del_start(cb: CallbackQuery, state: FSMContext):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.set_state(BannedNameState.delete)
    await cb.message.answer(
        "O'chirmoqchi bo'lgan nik/ismni yozing — bot topib ko'rsatadi:",
        reply_markup=cancel_kb()
    )
    await cb.answer()


@router.message(BannedNameState.delete)
async def bn_del_search(message: Message, state: FSMContext):
    if message.text == "❌ Bekor":
        await state.clear()
        return await message.answer("Bekor.", reply_markup=admin_menu())

    q = message.text.strip().lower()
    items = await queries.get_banned_names()
    found = [row for row in items if q in row["name"]]

    if not found:
        return await message.answer(
            f"❌ <b>«{q}»</b> topilmadi. Qayta yozing.", parse_mode="HTML"
        )

    await state.clear()
    b = InlineKeyboardBuilder()
    text = f"🔍 «{q}» bo'yicha topildi:\n\n"
    for row in found[:10]:
        text += f"• <code>{row['name']}</code>\n"
        b.row(InlineKeyboardButton(
            text=f"🗑 {row['name'][:30]}",
            callback_data=f"bndel:{row['id']}"
        ))
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data="bndel_cancel"))
    await message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("bndel:"))
async def bn_del_confirm(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    item_id = int(cb.data.split(":")[1])
    ok = await queries.remove_banned_name(item_id)
    if ok:
        from bot.services.moderation import refresh_banned_names_cache
        await refresh_banned_names_cache()
        await cb.message.edit_text("✅ O'chirildi.")
    else:
        await cb.message.edit_text("❌ Topilmadi.")
    items = await queries.get_banned_names()
    await cb.message.answer(
        _bn_list_text(items), parse_mode="HTML", reply_markup=_bn_menu_kb()
    )
    await cb.answer()


@router.callback_query(F.data == "bndel_cancel")
async def bn_del_cancel(cb: CallbackQuery):
    await cb.message.edit_text("Bekor qilindi.")
    await cb.answer()


# ── Menyuga qaytish ───────────────────────────────────────────

@router.callback_query(F.data == "go_main_menu")
async def go_main_menu(cb: CallbackQuery):
    if not await is_bot_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await cb.message.answer("Bosh menyu:", reply_markup=admin_menu())
    await cb.answer()


# ── PM fallback ──────────────────────────────────────────────

@router.message(StateFilter(None))
async def pm_fallback(message: Message):
    is_admin = await is_bot_admin(message.from_user.id)

    if is_admin:
        await message.answer("Menyu:", reply_markup=admin_menu())
        return

    await message.answer("Salom! Men Uzimiznikilar guruh boshqaruv botiman.")