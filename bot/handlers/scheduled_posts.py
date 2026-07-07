"""Rejalashtirilgan xabarlar — admin panel handler."""
import json
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from database import queries

router = Router()
router.message.filter(F.chat.type == "private")

PAGE = 10  # sahifadagi elementlar soni


# ── FSM ────────────────────────────────────────────────────────

class SPState(StatesGroup):
    select_groups  = State()   # guruhlarni tanlash
    enter_title    = State()   # post nomini kiriting
    enter_content  = State()   # xabar matnini kiriting
    enter_count    = State()   # necha marta/kun
    enter_times    = State()   # har bir vaqtni kiriting
    edit_title     = State()   # tahrirlash — yangi nom
    edit_content   = State()   # tahrirlash — yangi matn


# ── Yordamchi funksiyalar ───────────────────────────────────────

def _parse(v) -> list:
    if isinstance(v, list): return v
    try: return json.loads(v)
    except: return []


def _post_status(is_active: bool) -> str:
    return "✅ Faol" if is_active else "😴 Faol emas"


def _post_status_emoji(is_active: bool) -> str:
    return "✅" if is_active else "🔴"


async def _is_admin(user_id: int) -> bool:
    from bot.handlers.admin_handler import is_bot_admin
    return await is_bot_admin(user_id)


# ── Sahifali post ro'yxati klaviaturasi ────────────────────────

async def _posts_list_kb(page: int) -> tuple[str, InlineKeyboardMarkup]:
    posts = await queries.get_all_scheduled_posts()
    total = len(posts)
    total_pages = max(1, (total + PAGE - 1) // PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE
    chunk = posts[start:start + PAGE]

    text = f"📅 <b>Rejalashtirilgan xabarlar</b> ({total} ta)\n\nPostni tanlang:"

    b = InlineKeyboardBuilder()
    if not chunk:
        text = "📅 <b>Rejalashtirilgan xabarlar</b>\n\nHozircha hech qanday post yo'q."
    else:
        for p in chunk:
            b.row(InlineKeyboardButton(
                text=f"{_post_status_emoji(p['is_active'])} {p['title'][:40]}",
                callback_data=f"sp_view:{p['id']}:{page}"
            ))

    # Navigatsiya
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sp_list:{page-1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{total_pages}", callback_data="sp_noop"
    ))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sp_list:{page+1}"))
    if nav:
        b.row(*nav)

    b.row(InlineKeyboardButton(text="➕ Yangi post", callback_data="sp_new"))
    b.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="go_main_menu"))

    return text, b.as_markup()


# ── Guruhlar tanlash klaviaturasi ──────────────────────────────

async def _groups_select_kb(
    page: int, selected: list
) -> tuple[str, InlineKeyboardMarkup]:
    groups = await queries.get_all_groups()
    total = len(groups)
    total_pages = max(1, (total + PAGE - 1) // PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE
    chunk = groups[start:start + PAGE]

    sel_set = set(selected)
    text = (
        f"🏘️ <b>Guruhlarni tanlang</b>\n"
        f"Sahifa {page+1}/{total_pages} · Tanlangan: <b>{len(selected)}</b> ta\n\n"
        "Guruh ustiga bosib tanlang:"
    )

    b = InlineKeyboardBuilder()
    for g in chunk:
        gid = g["telegram_id"]
        check = "✅" if gid in sel_set else "☐"
        b.row(InlineKeyboardButton(
            text=f"{check} {g['title'][:38]}",
            callback_data=f"sp_grp:{gid}:{page}"
        ))

    # Navigatsiya
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sp_grp_page:{page-1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{total_pages}", callback_data="sp_noop"
    ))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sp_grp_page:{page+1}"))
    if nav:
        b.row(*nav)

    confirm_text = (
        f"✅ Tasdiqlash ({len(selected)} ta tanlangan)"
        if selected else "✅ Tasdiqlash (0 ta)"
    )
    b.row(InlineKeyboardButton(text=confirm_text, callback_data="sp_grp_confirm"))
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data="sp_cancel"))

    return text, b.as_markup()


# ── Post detail view ────────────────────────────────────────────

async def _post_detail_text_kb(
    post_id: int, back_page: int
) -> tuple[str, InlineKeyboardMarkup]:
    p = await queries.get_scheduled_post(post_id)
    if not p:
        return "❌ Post topilmadi.", InlineKeyboardBuilder().as_markup()

    times = _parse(p["send_times"])
    groups = _parse(p["target_groups"])
    times_str = ", ".join(times) if times else "—"
    status = _post_status(p["is_active"])

    content_preview = (p["content"] or "")[:200]
    if len(p["content"] or "") > 200:
        content_preview += "..."

    text = (
        f"📝 <b>{p['title']}</b>\n\n"
        f"📄 <b>Matn:</b>\n{content_preview}\n\n"
        f"⏰ <b>Vaqtlar:</b> {times_str}\n"
        f"👥 <b>Guruhlar:</b> {len(groups)} ta\n"
        f"📊 <b>Holat:</b> {status}"
    )
    if p["media_type"]:
        text += f"\n🖼 <b>Media:</b> {p['media_type']}"

    b = InlineKeyboardBuilder()
    toggle_text = "🔴 Faolsizlashtirish" if p["is_active"] else "🟢 Faollashtirish"
    b.row(InlineKeyboardButton(
        text=toggle_text, callback_data=f"sp_toggle:{post_id}:{back_page}"
    ))
    b.row(
        InlineKeyboardButton(
            text="✏️ Tahrirlash", callback_data=f"sp_edit:{post_id}:{back_page}"
        ),
        InlineKeyboardButton(
            text="🗑 O'chirish", callback_data=f"sp_del_ask:{post_id}:{back_page}"
        ),
    )
    b.row(InlineKeyboardButton(
        text="◀️ Orqaga", callback_data=f"sp_list:{back_page}"
    ))

    return text, b.as_markup()


# ── Asosiy menyu: 📅 Rejalashtirilgan xabarlar ─────────────────

@router.message(F.text == "📅 Rejalashtirilgan xabarlar")
async def sp_main(message: Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
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
        reply_markup=b.as_markup()
    )


# ── Postlar ro'yxati ────────────────────────────────────────────

@router.callback_query(F.data.startswith("sp_list:"))
async def sp_list(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    await state.clear()
    page = int(cb.data.split(":")[1])
    text, kb = await _posts_list_kb(page)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# ── Post detail ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sp_view:"))
async def sp_view(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, post_id, back_page = cb.data.split(":")
    text, kb = await _post_detail_text_kb(int(post_id), int(back_page))
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# ── Toggle faol/faol emas ───────────────────────────────────────

@router.callback_query(F.data.startswith("sp_toggle:"))
async def sp_toggle(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, post_id, back_page = cb.data.split(":")
    is_active = await queries.toggle_scheduled_post(int(post_id))

    if is_active:
        await cb.answer("✅ Post faollashtirildi!", show_alert=True)
    else:
        await cb.answer("😴 Post faolsizlashtirildi!", show_alert=True)

    text, kb = await _post_detail_text_kb(int(post_id), int(back_page))
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── O'chirish so'rash ───────────────────────────────────────────

@router.callback_query(F.data.startswith("sp_del_ask:"))
async def sp_del_ask(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, post_id, back_page = cb.data.split(":")
    p = await queries.get_scheduled_post(int(post_id))
    if not p:
        return await cb.answer("Topilmadi")

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ Ha, o'chir", callback_data=f"sp_del_yes:{post_id}:{back_page}"
        ),
        InlineKeyboardButton(
            text="❌ Yo'q", callback_data=f"sp_view:{post_id}:{back_page}"
        ),
    )
    await cb.message.edit_text(
        f"🗑 <b>«{p['title']}»</b> postini o'chirishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("sp_del_yes:"))
async def sp_del_yes(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, post_id, back_page = cb.data.split(":")
    await queries.delete_scheduled_post(int(post_id))
    await cb.answer("🗑 O'chirildi!", show_alert=True)

    text, kb = await _posts_list_kb(int(back_page))
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── Tahrirlash ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sp_edit:"))
async def sp_edit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")
    _, post_id, back_page = cb.data.split(":")
    p = await queries.get_scheduled_post(int(post_id))
    if not p:
        return await cb.answer("Topilmadi")

    await state.set_state(SPState.edit_title)
    await state.update_data(edit_post_id=int(post_id), edit_back_page=int(back_page))

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏩ Nomni o'zgartirmasdan", callback_data="sp_edit_skip_title"))
    await cb.message.answer(
        f"✏️ <b>Post nomini kiriting</b>\n\n"
        f"Hozirgi nom: <code>{p['title']}</code>\n\n"
        "Yangi nomni yozing (yoki o'zgartirmasdan davom etish uchun tugmani bosing):",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data == "sp_edit_skip_title", SPState.edit_title)
async def sp_edit_skip_title(cb: CallbackQuery, state: FSMContext):
    p_data = await state.get_data()
    p = await queries.get_scheduled_post(p_data["edit_post_id"])
    await state.update_data(edit_new_title=p["title"])
    await state.set_state(SPState.edit_content)
    await cb.message.answer(
        "✏️ Yangi xabar matnini yozing (yoki rasm/video yuboring):"
    )
    await cb.answer()


@router.message(SPState.edit_title)
async def sp_edit_title(message: Message, state: FSMContext):
    await state.update_data(edit_new_title=message.text.strip())
    await state.set_state(SPState.edit_content)
    await message.answer("✏️ Yangi xabar matnini yozing (yoki rasm/video yuboring):")


@router.message(SPState.edit_content)
async def sp_edit_content(message: Message, state: FSMContext):
    p_data = await state.get_data()
    post_id = p_data["edit_post_id"]
    new_title = p_data["edit_new_title"]
    back_page = p_data.get("edit_back_page", 0)

    content = message.text or message.caption or ""
    media_file_id = None
    media_type = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"

    await queries.update_scheduled_post_content(
        post_id, new_title, content, media_file_id, media_type
    )
    await state.clear()

    text, kb = await _post_detail_text_kb(post_id, back_page)
    await message.answer("✅ Post yangilandi!", parse_mode="HTML")
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ── Yangi post yaratish ─────────────────────────────────────────

@router.callback_query(F.data == "sp_new")
async def sp_new_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q")

    groups = await queries.get_all_groups()
    if not groups:
        return await cb.answer("Hali birorta guruh yo'q!", show_alert=True)

    await state.set_state(SPState.select_groups)
    await state.update_data(
        selected_groups=[], groups_page=0
    )

    text, kb = await _groups_select_kb(0, [])
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# Guruh toggle
@router.callback_query(F.data.startswith("sp_grp:"), SPState.select_groups)
async def sp_grp_toggle(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    group_id = int(parts[1])
    page = int(parts[2])

    data = await state.get_data()
    selected = list(data.get("selected_groups", []))

    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)

    await state.update_data(selected_groups=selected, groups_page=page)
    text, kb = await _groups_select_kb(page, selected)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# Sahifa navigatsiya
@router.callback_query(F.data.startswith("sp_grp_page:"), SPState.select_groups)
async def sp_grp_page(cb: CallbackQuery, state: FSMContext):
    page = int(cb.data.split(":")[1])
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    await state.update_data(groups_page=page)
    text, kb = await _groups_select_kb(page, selected)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# Guruhlarni tasdiqlash → post nomini so'rash
@router.callback_query(F.data == "sp_grp_confirm", SPState.select_groups)
async def sp_grp_confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    if not selected:
        return await cb.answer("Kamida 1 ta guruh tanlang!", show_alert=True)

    await state.set_state(SPState.enter_title)
    await cb.message.answer(
        f"✅ <b>{len(selected)} ta guruh tanlandi.</b>\n\n"
        "📝 Endi postga <b>nom</b> bering (masalan: «Ertalabki salom»):",
        parse_mode="HTML"
    )
    await cb.answer()


# Post nomini qabul qilish
@router.message(SPState.enter_title)
async def sp_enter_title(message: Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if not title:
        return await message.answer("Iltimos, faqat matn kiriting.")
    await state.update_data(post_title=title)
    await state.set_state(SPState.enter_content)
    await message.answer(
        "📄 Xabar <b>matnini</b> yozing (yoki rasm/video yuboring):",
        parse_mode="HTML"
    )


# Post matnini qabul qilish
@router.message(SPState.enter_content)
async def sp_enter_content(message: Message, state: FSMContext):
    content = message.text or message.caption or ""
    media_file_id = None
    media_type = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"

    await state.update_data(
        post_content=content,
        post_media_id=media_file_id,
        post_media_type=media_type,
    )
    await state.set_state(SPState.enter_count)
    await message.answer(
        "⏰ Kuniga <b>necha marta</b> yuborilsin?\n\n"
        "Faqat raqam kiriting (masalan: <code>2</code>):",
        parse_mode="HTML"
    )


# Kunlik takrorlanish sonini qabul qilish
@router.message(SPState.enter_count)
async def sp_enter_count(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 24):
        return await message.answer("1 dan 24 gacha raqam kiriting.")

    count = int(text)
    await state.update_data(times_count=count, times_entered=[], times_current=1)
    await state.set_state(SPState.enter_times)
    await message.answer(
        f"🕐 <b>1-vaqtni kiriting</b> (jami {count} ta)\n\n"
        "Format: <code>HH:MM</code>  (masalan: <code>09:30</code>)",
        parse_mode="HTML"
    )


# Har bir vaqtni qabul qilish
@router.message(SPState.enter_times)
async def sp_enter_time(message: Message, state: FSMContext):
    import re
    text = (message.text or "").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        return await message.answer(
            "Noto'g'ri format. HH:MM shaklida kiriting (masalan: <code>09:30</code>).",
            parse_mode="HTML"
        )

    # Normalize: "9:05" → "09:05"
    h, m = text.split(":")
    normalized = f"{int(h):02d}:{int(m):02d}"
    if int(h) > 23 or int(m) > 59:
        return await message.answer("Vaqt noto'g'ri. 00:00–23:59 oralig'ida kiriting.")

    data = await state.get_data()
    times_entered = data.get("times_entered", [])
    times_current = data.get("times_current", 1)
    times_count = data.get("times_count", 1)

    times_entered.append(normalized)
    await state.update_data(times_entered=times_entered)

    if times_current < times_count:
        await state.update_data(times_current=times_current + 1)
        await message.answer(
            f"✅ {times_current}-vaqt: <b>{normalized}</b>\n\n"
            f"🕐 <b>{times_current + 1}-vaqtni kiriting</b>:\n"
            f"Format: <code>HH:MM</code>",
            parse_mode="HTML"
        )
    else:
        # Hamma vaqtlar kiritildi — postni saqlash
        await _save_new_post(message, state)


async def _save_new_post(message: Message, state: FSMContext):
    """Barcha ma'lumotlar to'planganda postni DBga saqlaydi."""
    data = await state.get_data()

    title = data["post_title"]
    content = data["post_content"]
    media_id = data.get("post_media_id")
    media_type = data.get("post_media_type")
    times = sorted(data["times_entered"])
    groups = data["selected_groups"]

    await state.clear()

    try:
        post_id = await queries.create_scheduled_post(
            title=title,
            content=content,
            media_file_id=media_id,
            media_type=media_type,
            send_times=times,
            target_groups=groups,
            created_by=message.from_user.id,
        )

        times_str = " · ".join(times)
        await message.answer(
            f"✅ <b>Post saqlandi!</b>\n\n"
            f"📝 Nom: <b>{title}</b>\n"
            f"⏰ Vaqtlar: <b>{times_str}</b>\n"
            f"👥 Guruhlar: <b>{len(groups)} ta</b>\n\n"
            f"Har kuni avtomatik yuboriladi 🚀",
            parse_mode="HTML"
        )

        # Ro'yxatga qaytish
        text, kb = await _posts_list_kb(0)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        logger.error(f"Post save error: {e}")
        await message.answer(f"❌ Xatolik yuz berdi: {e}")


# ── Bekor qilish ────────────────────────────────────────────────

@router.callback_query(F.data == "sp_cancel")
async def sp_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await _posts_list_kb(0)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Bekor qilindi")


@router.callback_query(F.data == "sp_noop")
async def sp_noop(cb: CallbackQuery):
    await cb.answer()
