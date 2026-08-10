"""
OCR (Optical Character Recognition) — rasmdagi matnni o'qish.

Ishlatish: pytesseract + Pillow
VPS da o'rnatish:
    sudo apt install tesseract-ocr tesseract-ocr-uzb tesseract-ocr-rus
    pip install pytesseract

Qo'llab-quvvatlanadigan tillar: o'zbek, rus, ingliz
"""
import asyncio
import re
from io import BytesIO
from loguru import logger

# Taqiqlangan OCR matnlar cache (DB dan yuklanadi)
_ocr_banned: list[str] = []
_ocr_loaded: bool = False

# pytesseract mavjudligini tekshirish
def is_ocr_available() -> bool:
    try:
        import pytesseract  # noqa
        from PIL import Image  # noqa
        return True
    except ImportError:
        return False


def _check_tesseract() -> bool:
    """Tesseract binary mavjudligini tekshiradi."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


async def refresh_ocr_cache():
    """DB dan taqiqlangan OCR matnlarni qayta yuklaydi."""
    global _ocr_banned, _ocr_loaded
    try:
        from database import queries
        _ocr_banned = await queries.get_banned_ocr_texts_list()
        _ocr_loaded = True
        logger.info(f"OCR cache yangilandi: {len(_ocr_banned)} ta taqiqlangan matn")
    except Exception as e:
        logger.warning(f"OCR cache yuklanmadi: {e}")
        _ocr_loaded = True  # xato bo'lsa ham True — cheksiz retry oldini olish


async def get_ocr_banned() -> list[str]:
    """Taqiqlangan OCR matnlar ro'yxatini qaytaradi (cache orqali)."""
    global _ocr_loaded
    if not _ocr_loaded:
        await refresh_ocr_cache()
    return _ocr_banned


def _extract_text_sync(image_bytes: bytes) -> str:
    """Rasmdan matnni sinxron o'qiydi (executor da ishlatiladi)."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        # Bir nechta til: o'zbek (lotin), rus (kiril), ingliz
        # +osd — avtomatik yo'nalish aniqlash
        config = "--oem 3 --psm 6"
        text = pytesseract.image_to_string(img, lang="uzb+rus+eng", config=config)
        return text.strip()
    except Exception as e:
        logger.debug(f"OCR xato: {e}")
        return ""


async def extract_text_from_image(image_bytes: bytes) -> str:
    """Rasmdan matnni async o'qiydi."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_text_sync, image_bytes)


def normalize(text: str) -> str:
    """Matnni solishtirish uchun normallashtiradi."""
    # Kichik harfga o'tkazish, ortiqcha bo'shliqlarni olib tashlash
    text = text.lower()
    # Bir nechta bo'sh joyni biriga almashtirish
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def check_ocr_banned(image_bytes: bytes) -> tuple[bool, str]:
    """
    Rasmdagi matnni o'qib, taqiqlangan so'zlar bilan solishtiradi.

    Returns:
        (True, "topilgan_matn") — taqiqlangan so'z topildi
        (False, "")            — topilmadi
    """
    if not is_ocr_available():
        return False, ""

    if not _check_tesseract():
        logger.warning("Tesseract topilmadi! sudo apt install tesseract-ocr")
        return False, ""

    banned_list = await get_ocr_banned()
    if not banned_list:
        return False, ""

    # Rasmdan matn o'qish
    raw_text = await extract_text_from_image(image_bytes)
    if not raw_text:
        return False, ""

    text_norm = normalize(raw_text)
    logger.debug(f"OCR o'qildi ({len(raw_text)} belgi): {raw_text[:100]!r}")

    # Taqiqlangan matnlarni tekshirish
    for banned in banned_list:
        banned_norm = normalize(banned)
        if banned_norm in text_norm:
            logger.info(f"OCR BANNED: '{banned}' topildi rasmdagi matnda")
            return True, banned

    return False, ""
