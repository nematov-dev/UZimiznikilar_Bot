"""Utility helpers."""
from aiogram.types import ChatPermissions
from datetime import datetime, timedelta
from bot.config import settings


def full_mute_permissions() -> ChatPermissions:
    """Permissions object that silences a user completely."""
    return ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )


def default_permissions() -> ChatPermissions:
    """Restore normal permissions."""
    return ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )


def mute_until(minutes: int = None) -> datetime:
    mins = minutes or settings.mute_duration_minutes
    return datetime.utcnow() + timedelta(minutes=mins)


def format_user_mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def human_timedelta(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} soniya"
    elif seconds < 3600:
        return f"{seconds // 60} daqiqa"
    elif seconds < 86400:
        return f"{seconds // 3600} soat"
    else:
        return f"{seconds // 86400} kun"
