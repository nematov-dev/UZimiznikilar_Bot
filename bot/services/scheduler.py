"""Kunlik rejalashtirilgan xabarlarni avtomatik yuborish."""
import asyncio
import json
from datetime import datetime, date
from typing import Dict, Set
from loguru import logger
from aiogram import Bot

# {post_id: {"YYYY-MM-DD:HH:MM", ...}}  — bugun yuborilgan vaqtlar
_sent_log: Dict[int, Set[str]] = {}
_last_reset: date = None


async def scheduler_loop(bot: Bot):
    """Main background loop — har daqiqada bir marta ishlaydi."""
    global _last_reset
    logger.info("📅 Scheduler ishga tushdi")

    while True:
        try:
            now = datetime.now()
            today = now.date()
            current_time = now.strftime("%H:%M")

            # Har kun yarim tungida log ni tozalab ketish
            if _last_reset != today:
                _sent_log.clear()
                _last_reset = today
                logger.info(f"Scheduler: kunlik reset — {today}")

            from database import queries
            posts = await queries.get_active_scheduled_posts()

            for post in posts:
                pid = post["id"]
                times = _parse_json(post["send_times"])

                if current_time not in times:
                    continue

                key = f"{today}:{current_time}"
                already_sent = _sent_log.get(pid, set())
                if key in already_sent:
                    continue  # Bu daqiqada allaqachon yuborilgan

                already_sent.add(key)
                _sent_log[pid] = already_sent

                asyncio.create_task(_send_post(bot, post))

        except Exception as e:
            logger.error(f"Scheduler loop xato: {e}")

        # Keyingi daqiqaning boshiga qadar kutish
        now = datetime.now()
        sleep_sec = 60 - now.second
        await asyncio.sleep(sleep_sec)


async def _send_post(bot: Bot, post):
    """Bitta postni barcha target guruhlarga yuboradi."""
    post_id = post["id"]
    title = post["title"]
    content = post["content"] or ""
    media_file_id = post["media_file_id"]
    media_type = post["media_type"]
    groups = _parse_json(post["target_groups"])

    logger.info(f"📤 Post '{title}' (id={post_id}) → {len(groups)} guruh")

    success = fail = 0
    for group_id in groups:
        try:
            if media_type == "photo":
                await bot.send_photo(group_id, media_file_id, caption=content, parse_mode="HTML")
            elif media_type == "video":
                await bot.send_video(group_id, media_file_id, caption=content, parse_mode="HTML")
            else:
                await bot.send_message(group_id, content, parse_mode="HTML")
            success += 1
        except Exception as e:
            logger.warning(f"Post {post_id} → {group_id} xato: {e}")
            fail += 1
        await asyncio.sleep(0.05)

    logger.info(f"Post '{title}': ✅{success} ❌{fail}")


def _parse_json(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []
