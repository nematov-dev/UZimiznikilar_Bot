"""All database queries — single source of truth."""
from typing import Optional, List, Any
import asyncpg
from database.connection import get_pool
from loguru import logger


# ─────────────────────────── USERS ───────────────────────────

async def upsert_user(telegram_id: int, username: str = None,
                      first_name: str = None, last_name: str = None) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow("""
        INSERT INTO users (telegram_id, username, first_name, last_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (telegram_id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            updated_at = NOW()
        RETURNING *
    """, telegram_id, username, first_name, last_name)


async def get_user(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


async def get_user_by_id(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def ban_user(telegram_id: int, reason: str = None) -> bool:
    pool = await get_pool()
    result = await pool.execute("""
        UPDATE users SET is_banned = TRUE, ban_reason = $2, updated_at = NOW()
        WHERE telegram_id = $1
    """, telegram_id, reason)
    return result == "UPDATE 1"


async def unban_user(telegram_id: int) -> bool:
    pool = await get_pool()
    result = await pool.execute("""
        UPDATE users SET is_banned = FALSE, ban_reason = NULL, warnings = 0, updated_at = NOW()
        WHERE telegram_id = $1
    """, telegram_id)
    return result == "UPDATE 1"


async def increment_warnings(telegram_id: int) -> int:
    pool = await get_pool()
    row = await pool.fetchrow("""
        UPDATE users SET warnings = warnings + 1, updated_at = NOW()
        WHERE telegram_id = $1
        RETURNING warnings
    """, telegram_id)
    return row["warnings"] if row else 0


async def reset_warnings(telegram_id: int):
    pool = await get_pool()
    await pool.execute("UPDATE users SET warnings = 0 WHERE telegram_id = $1", telegram_id)


async def get_all_users(limit: int = 1000, offset: int = 0) -> List[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("""
        SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2
    """, limit, offset)


async def count_users() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users")
    return row["cnt"]


async def count_banned_users() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE is_banned = TRUE")
    return row["cnt"]


# ─────────────────────────── GROUPS ───────────────────────────

async def upsert_group(telegram_id: int, title: str, username: str = None) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow("""
        INSERT INTO groups (telegram_id, title, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE SET
            title = EXCLUDED.title,
            username = EXCLUDED.username,
            updated_at = NOW()
        RETURNING *
    """, telegram_id, title, username)


async def get_group(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM groups WHERE telegram_id = $1", telegram_id)


async def get_all_groups() -> List[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM groups WHERE is_active = TRUE ORDER BY created_at DESC")


async def update_group_settings(telegram_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    pool = await get_pool()
    set_parts = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    values = list(kwargs.values())
    result = await pool.execute(
        f"UPDATE groups SET {set_parts}, updated_at = NOW() WHERE telegram_id = $1",
        telegram_id, *values
    )
    return result == "UPDATE 1"


async def count_groups() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM groups WHERE is_active = TRUE")
    return row["cnt"]


# ─────────────────────────── BANNED WORDS ───────────────────────────

async def add_banned_word(word: str, added_by: int = None, is_regex: bool = False) -> bool:
    pool = await get_pool()
    try:
        await pool.execute("""
            INSERT INTO banned_words (word, added_by, is_regex) VALUES ($1, $2, $3)
        """, word.lower(), added_by, is_regex)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def remove_banned_word(word: str) -> bool:
    pool = await get_pool()
    result = await pool.execute("DELETE FROM banned_words WHERE word = $1", word.lower())
    return result == "DELETE 1"


async def get_banned_words() -> List[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM banned_words ORDER BY created_at DESC")


async def get_banned_words_list() -> List[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT word FROM banned_words WHERE is_regex = FALSE")
    return [r["word"] for r in rows]


# ─────────────────────────── MESSAGES ───────────────────────────

async def log_message(group_id: int, user_id: int, message_id: int,
                       message_type: str = "text") -> int:
    pool = await get_pool()
    try:
        row = await pool.fetchrow("""
            INSERT INTO messages (group_id, user_id, message_id, message_type)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, group_id, user_id, message_id, message_type)
        return row["id"] if row else 0
    except Exception:
        # Duplicate yoki boshqa xato — o'tkazib yuboramiz
        return 0


async def get_user_message_ids(group_id: int, user_id: int) -> list[int]:
    """Foydalanuvchining guruhda yozgan barcha xabar ID larini qaytaradi."""
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT message_id FROM messages
        WHERE group_id = $1 AND user_id = $2 AND was_deleted = FALSE
        ORDER BY id DESC
    """, group_id, user_id)
    return [r["message_id"] for r in rows]


async def mark_message_deleted(group_id: int, message_id: int, reason: str):
    pool = await get_pool()
    await pool.execute("""
        UPDATE messages SET was_deleted = TRUE, delete_reason = $3
        WHERE group_id = $1 AND message_id = $2
    """, group_id, message_id, reason)


async def count_messages_today() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT COUNT(*) as cnt FROM messages
        WHERE created_at >= CURRENT_DATE
    """)
    return row["cnt"]


async def count_deleted_today() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT COUNT(*) as cnt FROM messages
        WHERE was_deleted = TRUE AND created_at >= CURRENT_DATE
    """)
    return row["cnt"]


# ─────────────────────────── ADMIN ACTIONS ───────────────────────────

async def log_admin_action(admin_id: int, action_type: str,
                            target_user_id: int = None, group_id: int = None,
                            details: dict = None):
    pool = await get_pool()
    import json
    await pool.execute("""
        INSERT INTO admin_actions (admin_id, action_type, target_user_id, group_id, details)
        VALUES ($1, $2, $3, $4, $5)
    """, admin_id, action_type, target_user_id, group_id,
        json.dumps(details or {}))


async def get_admin_actions(limit: int = 50, offset: int = 0) -> List[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("""
        SELECT aa.*, u.username as admin_username, u.first_name as admin_first_name,
               tu.username as target_username
        FROM admin_actions aa
        LEFT JOIN users u ON u.telegram_id = aa.admin_id
        LEFT JOIN users tu ON tu.id = aa.target_user_id
        ORDER BY aa.created_at DESC
        LIMIT $1 OFFSET $2
    """, limit, offset)


# ─────────────────────────── MUTED USERS ───────────────────────────

async def mute_user(user_id: int, group_id: int, muted_by: int,
                    muted_until, reason: str = None):
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO muted_users (user_id, group_id, muted_by, muted_until, reason)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, group_id) DO UPDATE SET
            muted_until = EXCLUDED.muted_until,
            reason = EXCLUDED.reason,
            muted_by = EXCLUDED.muted_by
    """, user_id, group_id, muted_by, muted_until, reason)


async def unmute_user(user_id: int, group_id: int):
    pool = await get_pool()
    await pool.execute("""
        DELETE FROM muted_users WHERE user_id = $1 AND group_id = $2
    """, user_id, group_id)


# ─────────────────────────── BROADCASTS ───────────────────────────

async def create_broadcast(message_text: str, sent_by: int, target: str = "all",
                            media_file_id: str = None, media_type: str = None) -> int:
    pool = await get_pool()
    row = await pool.fetchrow("""
        INSERT INTO broadcasts (message_text, sent_by, target, media_file_id, media_type)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, message_text, sent_by, target, media_file_id, media_type)
    return row["id"]


async def update_broadcast_stats(broadcast_id: int, success: int, fail: int):
    pool = await get_pool()
    await pool.execute("""
        UPDATE broadcasts SET
            success_count = $2::integer,
            fail_count = $3::integer,
            recipients_count = $2::integer + $3::integer,
            status = 'done',
            finished_at = NOW()
        WHERE id = $1::integer
    """, broadcast_id, success, fail)


async def get_broadcasts(limit: int = 20) -> List[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("""
        SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT $1
    """, limit)


# ─────────────────────────── SETTINGS ───────────────────────────

async def get_setting(key: str) -> Optional[str]:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT value FROM bot_settings WHERE key = $1", key)
    return row["value"] if row else None


async def set_setting(key: str, value: str):
    pool = await get_pool()
    await pool.execute("""
        INSERT INTO bot_settings (key, value) VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
    """, key, value)


# ─────────────────────────── SCHEDULED POSTS ───────────────────────────

async def create_scheduled_post(
    title: str, content: str, media_file_id: str, media_type: str,
    send_times: list, target_groups: list, created_by: int
) -> int:
    import json
    pool = await get_pool()
    row = await pool.fetchrow("""
        INSERT INTO scheduled_posts
            (title, content, media_file_id, media_type, send_times, target_groups, created_by)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
        RETURNING id
    """, title, content, media_file_id, media_type,
        json.dumps(send_times), json.dumps(target_groups), created_by)
    return row["id"]


async def get_all_scheduled_posts() -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM scheduled_posts ORDER BY created_at DESC"
    )


async def get_scheduled_post(post_id: int):
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM scheduled_posts WHERE id = $1", post_id
    )


async def get_active_scheduled_posts() -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM scheduled_posts WHERE is_active = TRUE"
    )


async def toggle_scheduled_post(post_id: int) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow("""
        UPDATE scheduled_posts
        SET is_active = NOT is_active, updated_at = NOW()
        WHERE id = $1
        RETURNING is_active
    """, post_id)
    return row["is_active"] if row else False


async def update_scheduled_post_content(
    post_id: int, title: str, content: str,
    media_file_id: str = None, media_type: str = None
):
    pool = await get_pool()
    await pool.execute("""
        UPDATE scheduled_posts
        SET title=$2, content=$3, media_file_id=$4, media_type=$5, updated_at=NOW()
        WHERE id=$1
    """, post_id, title, content, media_file_id, media_type)


async def delete_scheduled_post(post_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM scheduled_posts WHERE id = $1", post_id)


async def count_scheduled_posts() -> int:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM scheduled_posts")
    return row["cnt"]


# ─────────────────────────── BANNED IMAGES ──────────────────────────

async def add_banned_image(phash: str, added_by: int, note: str = "",
                           segment_hashes: str = "") -> bool:
    """pHash + segment_hashes ni saqlaydi."""
    pool = await get_pool()
    try:
        await pool.execute(
            "INSERT INTO banned_images (phash, added_by, note, segment_hashes) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (phash) DO NOTHING",
            phash, added_by, note, segment_hashes
        )
        return True
    except Exception:
        return False


async def get_all_banned_images_full() -> list[dict]:
    """pHash + segment_hashes bilan barcha taqiqlangan rasmlar."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT phash, segment_hashes FROM banned_images ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


async def get_all_banned_image_hashes() -> list[str]:
    """Barcha taqiqlangan pHash larni qaytaradi."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT phash FROM banned_images ORDER BY created_at DESC")
    return [r["phash"] for r in rows]



async def get_banned_images_list() -> list[dict]:
    """Admin panel uchun to'liq ro'yxat (oxirgi 50 ta)."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, phash, note, added_by, created_at FROM banned_images ORDER BY created_at DESC LIMIT 50"
    )
    return [dict(r) for r in rows]


async def delete_banned_image_by_id(image_id: int) -> bool:
    pool = await get_pool()
    result = await pool.execute("DELETE FROM banned_images WHERE id = $1", image_id)
    return result != "DELETE 0"


# ─────────────────────────── STATS ───────────────────────────

async def get_stats_overview() -> dict:
    pool = await get_pool()
    users = await pool.fetchrow("SELECT COUNT(*) as total, SUM(CASE WHEN is_banned THEN 1 ELSE 0 END) as banned FROM users")
    groups = await pool.fetchrow("SELECT COUNT(*) as total FROM groups WHERE is_active = TRUE")
    msgs = await pool.fetchrow("SELECT COUNT(*) as total, SUM(CASE WHEN was_deleted THEN 1 ELSE 0 END) as deleted FROM messages WHERE created_at >= CURRENT_DATE")
    actions = await pool.fetchrow("SELECT COUNT(*) as total FROM admin_actions WHERE created_at >= CURRENT_DATE")

    return {
        "total_users": users["total"],
        "banned_users": users["banned"],
        "total_groups": groups["total"],
        "messages_today": msgs["total"],
        "deleted_today": msgs["deleted"],
        "admin_actions_today": actions["total"],
    }


# ─────────────────────────── BANNED OCR TEXTS ────────────────

async def get_banned_ocr_texts() -> list:
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM banned_ocr_texts ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def add_banned_ocr_text(text: str, added_by: int = None) -> bool:
    pool = await get_pool()
    try:
        await pool.execute(
            "INSERT INTO banned_ocr_texts(text, added_by) VALUES($1, $2)",
            text.strip().lower(), added_by
        )
        return True
    except Exception:
        return False


async def remove_banned_ocr_text(text_id: int) -> bool:
    pool = await get_pool()
    result = await pool.execute("DELETE FROM banned_ocr_texts WHERE id=$1", text_id)
    return result == "DELETE 1"


async def get_banned_ocr_texts_list() -> list[str]:
    """Faqat matn ro'yxati — moderatsiya uchun tez yuklash."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT text FROM banned_ocr_texts")
    return [r['text'] for r in rows]


# ──────────────────────── CLEANUP ───────────────────────────

async def delete_user_messages_log(group_id: int, user_id: int) -> int:
    """
    Foydalanuvchi banned bo'lganda DB dagi xabar loglarini tozalaydi.
    Musor to'planmasin!
    Returns: o'chirilgan yozuvlar soni
    """
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM messages WHERE group_id = $1 AND user_id = $2",
        group_id, user_id
    )
    # result format: 'DELETE 5'
    try:
        return int(result.split()[1])
    except Exception:
        return 0
