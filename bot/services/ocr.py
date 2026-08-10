"""
OCR (Optical Character Recognition) — rasmdagi matnni o'qish.

Optimallashtirilgan: 1 ta PSM, semaphore (max 2 parallel), timeout.
VPS da o'rnatish:
    sudo apt install tesseract-ocr tesseract-ocr-uzb tesseract-ocr-rus tesseract-ocr-eng
    pip install pytesseract
"""
import asyncio
import re
from io import BytesIO
from loguru import logger

# Taqiqlangan OCR matnlar cache
_ocr_banned: list[str] = []
_ocr_loaded: bool = False

# Tesseract mavjudligi — bir marta tekshiriladi
_tesseract_ok: bool | None = None

# Bir vaqtda maksimal 2 ta OCR jarayoni (server tiqilmasin)
_ocr_semaphore = asyncio.Semaphore(2)

# OCR timeout (soniya) — bu vaqtdan ko'p kutilmaydi
_OCR_TIMEOUT = 10.0


def is_ocr_available() -> bool:
    try:
        import pytesseract  # noqa
        from PIL import Image  # noqa
        return True
    except ImportError:
        return False


def _check_tesseract() -> bool:
    global _tesseract_ok
    if _tesseract_ok is not None:
        return _tesseract_ok
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _tesseract_ok = True
    except Exception:
        _tesseract_ok = False
        logger.warning("Tesseract topilmadi! sudo apt install tesseract-ocr")
    return _tesseract_ok


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
        _ocr_loaded = True


async def get_ocr_banned() -> list[str]:
    global _ocr_loaded
    if not _ocr_loaded:
        await refresh_ocr_cache()
    return _ocr_banned


# ── Rasm preprocessing ────────────────────────────────────────

def _preprocess_image(img):
    """Grayscale + kontrast — OCR aniqligini oshiradi."""
    from PIL import ImageEnhance

    img = img.convert("L")  # Grayscale

    # Kichik rasmlarni kattalashtirish
    w, h = img.size
    if w < 800:
        scale = 800 / w
        from PIL import Image
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Kontrast oshirish
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return img


def _extract_text_sync(image_bytes: bytes) -> str:
    """
    Rasmdan matnni sinxron o'qiydi.
    Faqat 1 ta PSM mode — server yukini kamaytiradi.
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = _preprocess_image(img)

        # PSM 11: Sparse text — reklama postlaridagi turli joylardagi matnni topadi
        config = "--oem 3 --psm 11"
        text = pytesseract.image_to_string(img, lang="uzb+rus+eng", config=config)
        return text.strip()

    except Exception as e:
        logger.debug(f"OCR xato: {e}")
        return ""


# ── Normalizatsiya ────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _digits_only(text: str) -> str:
    """Faqat raqamlar — telefon raqamlar uchun."""
    return re.sub(r"\D", "", text)


def _alphanum_only(text: str) -> str:
    """Faqat harf+raqam — URL/domain uchun."""
    return re.sub(r"[^a-z0-9\u0400-\u04ff]", "", text.lower())


# ── Asosiy tekshiruv ──────────────────────────────────────────

async def check_ocr_banned(image_bytes: bytes) -> tuple[bool, str]:
    """
    Rasmdagi matnni o'qib, taqiqlangan so'zlar bilan solishtiradi.
    Semaphore orqali server yukini cheklaydi (max 2 parallel).
    Timeout: 10 soniya.
    """
    if not is_ocr_available() or not _check_tesseract():
        return False, ""

    banned_list = await get_ocr_banned()
    if not banned_list:
        return False, ""

    # Semaphore: bir vaqtda max 2 ta OCR
    async with _ocr_semaphore:
        try:
            loop = asyncio.get_event_loop()
            raw_text = await asyncio.wait_for(
                loop.run_in_executor(None, _extract_text_sync, image_bytes),
                timeout=_OCR_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("OCR timeout (10s) — rasm o'tkazib yuborildi")
            return False, ""
        except Exception as e:
            logger.debug(f"OCR executor xato: {e}")
            return False, ""

    if not raw_text:
        return False, ""

    logger.info(f"OCR natija ({len(raw_text)} belgi): {raw_text[:150]!r}")

    text_norm    = _normalize(raw_text)
    text_digits  = _digits_only(raw_text)
    text_alphnum = _alphanum_only(raw_text)

    for banned in banned_list:
        banned_norm    = _normalize(banned)
        banned_digits  = _digits_only(banned)
        banned_alphnum = _alphanum_only(banned)

        # 1. To'liq matn ichida
        if banned_norm and banned_norm in text_norm:
            logger.info(f"OCR BANNED (text): '{banned}'")
            return True, banned

        # 2. Telefon raqam (faqat raqamlar)
        if len(banned_digits) >= 7 and banned_digits in text_digits:
            logger.info(f"OCR BANNED (digits): '{banned}'")
            return True, banned

        # 3. URL/domain (harf+raqam)
        if len(banned_alphnum) >= 4 and banned_alphnum in text_alphnum:
            logger.info(f"OCR BANNED (alphanum): '{banned}'")
            return True, banned

    return False, ""
