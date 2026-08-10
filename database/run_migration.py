"""DB migratsiya skripti — .env kredensiallaridan foydalanadi."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run_migration():
    from bot.config import settings
    import asyncpg

    print(f"DB ga ulanmoqda: {settings.get_db_dsn()[:40]}...")
    conn = await asyncpg.connect(dsn=settings.get_db_dsn())

    try:
        # banned_ocr_texts jadvalini yaratish
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_ocr_texts (
                id BIGSERIAL PRIMARY KEY,
                text TEXT UNIQUE NOT NULL,
                added_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("✅ banned_ocr_texts jadvali yaratildi (yoki allaqachon bor)")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_banned_ocr_texts_text
            ON banned_ocr_texts(text)
        """)
        print("✅ Indeks yaratildi")

        # Tekshirish
        count = await conn.fetchval("SELECT COUNT(*) FROM banned_ocr_texts")
        print(f"✅ Jadval ishlayapti. Hozir {count} ta yozuv.")

    finally:
        await conn.close()
        print("Tayyor!")

if __name__ == "__main__":
    asyncio.run(run_migration())
