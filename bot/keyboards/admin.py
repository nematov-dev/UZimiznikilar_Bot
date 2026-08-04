"""Admin keyboard layouts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def admin_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(
        KeyboardButton(text="📊 Statistika"),
        KeyboardButton(text="👥 Foydalanuvchilar"),
    )
    kb.row(
        KeyboardButton(text="🚫 Taqiqlangan so'zlar"),
    )
    kb.row(
        KeyboardButton(text="📢 Xabar yuborish"),
        KeyboardButton(text="⚙️ Sozlamalar"),
    )
    kb.row(KeyboardButton(text="📋 Admin harakatlar"))
    return kb.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="❌ Bekor qilish"))
    return kb.as_markup(resize_keyboard=True)


def confirm_broadcast_kb(broadcast_id: int = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Yuborish", callback_data="broadcast_confirm"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="broadcast_cancel"),
    )
    return builder.as_markup()


def broadcast_target_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Barcha foydalanuvchilar", callback_data="bcast_target:users"),
    )
    builder.row(
        InlineKeyboardButton(text="🏘️ Barcha guruhlar", callback_data="bcast_target:groups"),
    )
    builder.row(
        InlineKeyboardButton(text="🌐 Hammasi", callback_data="bcast_target:all"),
    )
    return builder.as_markup()


def group_settings_kb(group_id: int, settings: dict) -> InlineKeyboardMarkup:
    def toggle(val: bool) -> str:
        return "✅" if val else "❌"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"{toggle(settings.get('anti_links', True))} Reklama/havolalar",
        callback_data=f"grp_toggle:{group_id}:anti_links"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{toggle(settings.get('anti_profanity', True))} Haqoratli so'zlar",
        callback_data=f"grp_toggle:{group_id}:anti_profanity"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{toggle(settings.get('delete_join_leave', True))} Kirdi/chiqdi xabarlar",
        callback_data=f"grp_toggle:{group_id}:delete_join_leave"
    ))
    return builder.as_markup()


def user_action_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚫 Ban", callback_data=f"usr_ban:{user_id}"),
        InlineKeyboardButton(text="✅ Unban", callback_data=f"usr_unban:{user_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⚠️ Warn", callback_data=f"usr_warn:{user_id}"),
        InlineKeyboardButton(text="🔄 Resetlash", callback_data=f"usr_reset:{user_id}"),
    )
    return builder.as_markup()
