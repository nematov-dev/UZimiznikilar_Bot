"""
Rasm barmoq izi (pHash + segment hashes) — taqiqlangan rasmlarni aniqlash.

Qanday ishlaydi:
  1. pHash — butun rasmning hash (bir xil rasm, siqilgan, o'lcham o'zgargan)
  2. Segment hash — rasm 9 bo'lakka (3x3) bo'linadi, har birining hash
     - Kesib yuborilgan rasm: ba'zi bo'laklar mos keladi
     - Screenshotda atrofida boshqa rasm: ichki bo'laklar mos keladi
  => Ikkalasidan biri mos kelsa — taqiqlangan rasm sifatida aniqlanadi
"""
import asyncio
import json
from io import BytesIO
from loguru import logger

PHASH_THRESHOLD = 15       # Butun rasm uchun Hamming masofasi (oshirildi: siqilgan/rangi o'zgargan/o'lcham o'zgargan uchun)
SEGMENT_THRESHOLD = 10     # Segment uchun — kesib yuborilgan qismlarni topish uchun yumshoqroq
MIN_SEGMENT_MATCHES = 2    # Kamida shu qancha segment mos kelsa → topilgan


def _check_imagehash() -> bool:
    try:
        import imagehash  # noqa
        return True
    except ImportError:
        return False


def is_imagehash_available() -> bool:
    return _check_imagehash()


# ── Butun rasm pHash ──────────────────────────────────────────

def compute_phash(image_bytes: bytes) -> str | None:
    try:
        import imagehash
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        return str(imagehash.phash(img))
    except Exception as e:
        logger.debug(f"pHash xato: {e}")
        return None


def phash_distance(hash1: str, hash2: str) -> int:
    try:
        import imagehash
        return imagehash.hex_to_hash(hash1) - imagehash.hex_to_hash(hash2)
    except Exception:
        return 64


# ── Segment hashes (3x3 grid) ─────────────────────────────────

def compute_segment_hashes(image_bytes: bytes, grid: int = 4) -> list[str]:
    """
    Rasmni grid x grid bo'lakka bo'lib, har birining pHash ni qaytaradi.
    Kesilgan yoki atrofiga narsa qo'shilgan rasmlarni aniqlash uchun ishlatiladi.
    grid=4 → 16 ta segment (avval 3x3=9 edi) — mayda kesimlarni ham topadi.
    """
    try:
        import imagehash
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        # Eng kichik o'lchamni tekshirish
        if w < grid * 8 or h < grid * 8:
            return []

        hashes = []
        for row in range(grid):
            for col in range(grid):
                x1 = col * w // grid
                y1 = row * h // grid
                x2 = (col + 1) * w // grid
                y2 = (row + 1) * h // grid
                seg = img.crop((x1, y1, x2, y2))
                hashes.append(str(imagehash.phash(seg)))
        return hashes
    except Exception as e:
        logger.debug(f"Segment hash xato: {e}")
        return []


def segment_hashes_to_str(hashes: list[str]) -> str:
    """Saqlash uchun JSON ga aylantirish."""
    return json.dumps(hashes)


def segment_hashes_from_str(s: str) -> list[str]:
    """DB dan o'qish uchun."""
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def check_segment_match(
    incoming_hashes: list[str],
    banned_hashes: list[str],
    threshold: int = SEGMENT_THRESHOLD,
    min_matches: int = MIN_SEGMENT_MATCHES,
) -> bool:
    """
    Kelayotgan rasm segmentlari taqiqlangan rasm segmentlariga mos keladimi?
    min_matches ta segment mos kelsa → True.
    """
    if not incoming_hashes or not banned_hashes:
        return False
    matches = 0
    for inc in incoming_hashes:
        for ban in banned_hashes:
            if phash_distance(inc, ban) <= threshold:
                matches += 1
                if matches >= min_matches:
                    return True
    return False


# ── Bir vaqtda hisoblash (pHash + segments) ───────────────────

def compute_all_hashes(image_bytes: bytes) -> tuple[str | None, list[str]]:
    """pHash va segment hashlarni bir vaqtda hisoblaydi."""
    phash = compute_phash(image_bytes)
    segments = compute_segment_hashes(image_bytes)
    return phash, segments


# ── Async wrappers ────────────────────────────────────────────

async def compute_phash_async(image_bytes: bytes) -> str | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_phash, image_bytes)


async def compute_all_hashes_async(image_bytes: bytes) -> tuple[str | None, list[str]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_all_hashes, image_bytes)
