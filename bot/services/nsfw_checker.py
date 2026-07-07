"""
NSFW kontent tekshiruvi — ikki model parallel:
  1. nudenet   — aniq a'zo aniqlash (haqiqiy fotolar uchun yaxshi)
  2. opennsfw2 — umumiy NSFW ball  (kartun/anime uchun yaxshi)
Ikkalasidan biri flag qilsa -> bloklash.
"""
import asyncio
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from loguru import logger

NUDENET_EXPOSED_THRESHOLD = 0.45
NUDENET_COVERED_THRESHOLD = 0.85
OPENNSFW2_THRESHOLD       = 0.75

NSFW_EXPOSED = {
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
NSFW_COVERED = {
    "FEMALE_GENITALIA_COVERED",
    "FEMALE_BREAST_COVERED",
}

_nudenet_detector = None
_nudenet_available = None
_opennsfw2_available = None


def _check_nudenet() -> bool:
    global _nudenet_available
    if _nudenet_available is None:
        try:
            import nudenet  # noqa
            _nudenet_available = True
        except ImportError:
            _nudenet_available = False
            logger.warning("nudenet yoq -- pip install nudenet")
    return _nudenet_available


def _check_opennsfw2() -> bool:
    global _opennsfw2_available
    if _opennsfw2_available is None:
        try:
            import opennsfw2  # noqa
            _opennsfw2_available = True
        except ImportError:
            _opennsfw2_available = False
            logger.warning("opennsfw2 yoq -- pip install opennsfw2")
    return _opennsfw2_available


def is_nsfw_available() -> bool:
    return _check_nudenet() or _check_opennsfw2()


def _to_jpg_bytes(file_bytes: bytes, ext: str) -> bytes:
    if ext.lower() in ("jpg", "jpeg"):
        return file_bytes
    try:
        from PIL import Image
        img = Image.open(BytesIO(file_bytes)).convert("RGB")
        out = BytesIO()
        img.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception as e:
        logger.debug(f"Rasm konvertatsiya ({ext}->jpg): {e}")
        return file_bytes


def _ffmpeg_first_frame(video_bytes: bytes, ext: str = "webm"):
    """ffmpeg orqali video/animatsiyaning birinchi kadrini qaytaradi."""
    tmp_vid = None
    tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(video_bytes)
            tmp_vid = f.name
        tmp_out = tmp_vid + ".jpg"
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_vid, "-vframes", "1", "-q:v", "2", tmp_out],
            capture_output=True, timeout=10,
        )
        if res.returncode == 0 and Path(tmp_out).exists():
            data = Path(tmp_out).read_bytes()
            return data
        return None
    except FileNotFoundError:
        logger.debug("ffmpeg topilmadi -- video kadr ajratilmadi")
        return None
    except Exception as e:
        logger.debug(f"ffmpeg xato: {e}")
        return None
    finally:
        if tmp_vid:
            Path(tmp_vid).unlink(missing_ok=True)
        if tmp_out:
            Path(tmp_out).unlink(missing_ok=True)


def _nudenet_check(jpg_bytes: bytes) -> bool:
    global _nudenet_detector
    if _nudenet_detector is None:
        from nudenet import NudeDetector
        logger.info("NudeDetector yuklanmoqda...")
        _nudenet_detector = NudeDetector()
        logger.info("NudeDetector tayyor")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(jpg_bytes)
        tmp = f.name
    try:
        results = _nudenet_detector.detect(tmp)
        for det in results:
            cls = det.get("class", "")
            score = det.get("score", 0.0)
            if cls in NSFW_EXPOSED and score >= NUDENET_EXPOSED_THRESHOLD:
                logger.info(f"nudenet EXPOSED: {cls} {score:.2f}")
                return True
            if cls in NSFW_COVERED and score >= NUDENET_COVERED_THRESHOLD:
                logger.info(f"nudenet COVERED (high): {cls} {score:.2f}")
                return True
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)


def _opennsfw2_check(jpg_bytes: bytes) -> bool:
    try:
        import opennsfw2 as n2
        from PIL import Image
        img = Image.open(BytesIO(jpg_bytes)).convert("RGB")
        score = n2.predict_pil_image(img)
        if score >= OPENNSFW2_THRESHOLD:
            logger.info(f"opennsfw2 NSFW: {score:.2f}")
            return True
        return False
    except Exception as e:
        logger.debug(f"opennsfw2 xato: {e}")
        return False


async def is_nsfw(file_bytes: bytes, ext: str = "jpg") -> bool:
    """
    True  -> 18+ kontent (ochirish kerak)
    False -> toza yoki tekshirib bolmadi
    """
    if not file_bytes:
        return False

    loop = asyncio.get_event_loop()

    if ext.lower() in ("webm", "mp4", "tgs"):
        frame = await loop.run_in_executor(None, _ffmpeg_first_frame, file_bytes, ext)
        if not frame:
            return False
        file_bytes = frame
        ext = "jpg"

    jpg = await loop.run_in_executor(None, _to_jpg_bytes, file_bytes, ext)
    if not jpg:
        return False

    tasks = []
    if _check_nudenet():
        tasks.append(loop.run_in_executor(None, _nudenet_check, jpg))
    if _check_opennsfw2():
        tasks.append(loop.run_in_executor(None, _opennsfw2_check, jpg))

    if not tasks:
        return False

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r is True:
                return True
        return False
    except Exception as e:
        logger.error(f"is_nsfw xato: {e}")
        return False
