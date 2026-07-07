"""Bot entry point."""
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import settings
from database.connection import create_pool, close_pool
from bot.middlewares.moderation import BotMiddleware
from bot.handlers import admin_handler, group_commands, group_moderation, rag_handler
from bot.handlers import scheduled_posts
from bot.services.moderation import refresh_banned_words_cache
from bot.services.scheduler import scheduler_loop


async def on_startup(bot: Bot):
    logger.info("Bot ishga tushmoqda...")
    await create_pool()
    await refresh_banned_words_cache()
    info = await bot.get_me()
    logger.info(f"Bot ishga tushdi: @{info.username}")
    # Kunlik scheduler
    asyncio.create_task(scheduler_loop(bot))
    logger.info("Scheduler ishga tushdi")


async def on_shutdown(bot: Bot):
    logger.info("Bot to'xtatilmoqda...")
    await close_pool()


async def main():
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Middleware — outer: handler topilmasa ham har qanday xabar uchun ishlaydi
    dp.message.outer_middleware(BotMiddleware())

    # Routerlar — tartib muhim
    dp.include_router(admin_handler.router)       # PM — admin buyruqlari
    dp.include_router(scheduled_posts.router)     # PM — rejalashtirilgan xabarlar
    dp.include_router(group_commands.router)      # Guruh — /ban /mute va h.k.
    dp.include_router(rag_handler.router)         # Hujjat yuklash + AI javob
    dp.include_router(group_moderation.router)    # Avtomatik moderatsiya (oxirida)

    logger.info("Polling boshlandi...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
