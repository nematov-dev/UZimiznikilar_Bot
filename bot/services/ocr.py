"""
OCR — rasmdagi matnni o'qish (pytesseract).

MUHIM: pytesseract timeout parametri orqali tesseract jarayoni o'ldiriladi.
asyncio.wait_for ISHLATILMAYDI — u faqat Python ni to'xtatadi,
tesseract subprocess zombie bo'lib qoladi.
"""
import asyncio
import re
from io import BytesIO
from loguru import logger

# Cache
_ocr_banned: list[str] = []
_ocr_loaded: bool = False
_tesseract_ok: bool | None = None

# Bir vaqtda MAX 1 ta OCR (server yukini kamaytirish)
_ocr_semaphore = asyncio.Semaphore(1)

# Tesseract timeout — JARAYONNI O'LDIRADI (zombie bo'lmaydi)
_TESSERACT_TIMEOUT = 8  # soniya


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
        logger.warning("Tesseract topilmadi!")
    return _tesseract_ok


async def refresh_ocr_cache():
    global _ocr_banned, _ocr_loaded
    try:
        from database import queries
        _ocr_banned = await queries.get_banned_ocr_texts_list()
        _ocr_loaded = True
        logger.info(f"OCR cache: {len(_ocr_banned)} ta taqiqlangan matn")
    except Exception as e:
        logger.warning(f"OCR cache yuklanmadi: {e}")
        _ocr_loaded = True


async def get_ocr_banned() -> list[str]:
    global _ocr_loaded
    if not _ocr_loaded:
        await refresh_ocr_cache()
    return _ocr_banned


# ── Preprocessing (yengil) ────────────────────────────────────

def _preprocess(img):
    """Grayscale + kontrast + DPI belgilash — OCR aniqligini oshiradi."""
    from PIL import Image, ImageEnhance

    img = img.convert("L")

    # Kichraytirish — 1000px max (kichik yozuvlarni yaxshi o'qish uchun)
    w, h = img.size
    max_side = 1000
    if w > max_side or h > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    img = ImageEnhance.Contrast(img).enhance(1.8)

    # DPI belgilash — "Estimating resolution" xatosi oldini oladi
    img.info["dpi"] = (300, 300)
    return img


def _extract_text_sync(image_bytes: bytes) -> str:
    """
    Rasmdan matn o'qish.
    --dpi 300: Tesseract resolution xatosini oldini oladi.
    timeout: jarayonni o'ldiradi (zombie bo'lmaydi).
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = _preprocess(img)

        # --dpi 300: "Estimating resolution" xatosini bartaraf etadi
        # --psm 3: Auto page segmentation (universal rejim)
        text = pytesseract.image_to_string(
            img,
            lang="uzb+rus+eng",
            config="--oem 3 --psm 3 --dpi 300",
            timeout=_TESSERACT_TIMEOUT,
        )
        return text.strip()

    except RuntimeError as e:
        err_str = str(e)
        # pytesseract timeout
        if "timeout" in err_str.lower():
            logger.warning(f"OCR timeout ({_TESSERACT_TIMEOUT}s)")
            return ""
        # Tesseract stderr warning (masalan "Estimating resolution")
        # — bu xato emas, matn bor bo'lishi mumkin
        logger.debug(f"OCR runtime: {err_str[:100]}")
        return ""
    except Exception as e:
        logger.debug(f"OCR xato: {e}")
        return ""


# ── Normalizatsiya ────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()

def _digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)

def _alphanum_only(text: str) -> str:
    return re.sub(r"[^a-z0-9\u0400-\u04ff]", "", text.lower())


# ── Asosiy tekshiruv ──────────────────────────────────────────

async def check_ocr_banned(image_bytes: bytes) -> tuple[bool, str]:
    """
    Rasmdagi matnni o'qib, taqiqlangan so'zlar bilan solishtiradi.
    MAX 1 ta parallel OCR. Tesseract timeout orqali zombie oldini oladi.
    """
    if not is_ocr_available() or not _check_tesseract():
        return False, ""

    banned_list = await get_ocr_banned()
    if not banned_list:
        return False, ""

    # Katta rasmlarni OCR qilmaymiz (2MB dan katta)
    if len(image_bytes) > 2 * 1024 * 1024:
        return False, ""

    # Max 1 ta parallel OCR — server tiqilmasin
    try:
        async with asyncio.timeout(15):  # umumiy kutish limiti
            async with _ocr_semaphore:
                loop = asyncio.get_event_loop()
                raw_text = await loop.run_in_executor(
                    None, _extract_text_sync, image_bytes
                )
    except TimeoutError:
        logger.warning("OCR semaphore timeout — o'tkazib yuborildi")
        return False, ""
    except Exception as e:
        logger.debug(f"OCR xato: {e}")
        return False, ""

    if not raw_text:
        return False, ""

    logger.info(f"OCR ({len(raw_text)} belgi): {raw_text[:100]!r}")

    text_norm = _normalize(raw_text)
    text_digits = _digits_only(raw_text)
    text_alphnum = _alphanum_only(raw_text)

    for banned in banned_list:
        b_norm = _normalize(banned)
        b_digits = _digits_only(banned)
        b_alphnum = _alphanum_only(banned)

        if b_norm and b_norm in text_norm:
            logger.info(f"OCR BANNED: '{banned}'")
            return True, banned

        if len(b_digits) >= 7 and b_digits in text_digits:
            logger.info(f"OCR BANNED (digits): '{banned}'")
            return True, banned

        if len(b_alphnum) >= 4 and b_alphnum in text_alphnum:
            logger.info(f"OCR BANNED (alphanum): '{banned}'")
            return True, banned

    return False, ""
