"""Link va taqiqlangan so'z tekshiruvi."""
import re
from typing import List
from database import queries

# Haqiqiy URL larni bloklash (http, www, t.me, telegram.me va h.k.)
URL_PATTERN = re.compile(
    r"("
    r"https?://"                                              # http:// https://
    r"|www\."                                                 # www.
    r"|t\.me/"                                               # t.me/
    r"|telegram\.me/"                                        # telegram.me/
    r"|tg://"                                                # tg://
    r"|[a-zA-Z0-9][a-zA-Z0-9\-]{2,}\."                      # subdomain.
    r"(?:com|net|org|ru|uz|io|me|shop|online|site|gg|xyz|info|biz|co|tv|app)"
    r"(?:/|\s|$)"                                            # / yoki gap oxiri
    r")",
    re.IGNORECASE,
)

# @username ko'rinishidagi reklama — alohida tekshiriladi (faqat o'chirish, restrict emas)
USERNAME_PATTERN = re.compile(r"@[A-Za-z][A-Za-z0-9_]{3,31}")

_cache: List[str] = []
_cache_loaded: bool = False

_banned_names_cache: List[str] = []
_banned_names_loaded: bool = False


async def refresh_banned_words_cache():
    global _cache, _cache_loaded
    try:
        _cache = await queries.get_banned_words_list()
        _cache_loaded = True
    except Exception:
        pass


async def refresh_banned_names_cache():
    global _banned_names_cache, _banned_names_loaded
    try:
        _banned_names_cache = await queries.get_banned_names_list()
        _banned_names_loaded = True
    except Exception:
        pass


async def is_name_banned(first_name: str | None, last_name: str | None, username: str | None) -> tuple[bool, str]:
    """
    Foydalanuvchining ismi, familiyasi yoki username'i taqiqlangan niklar ro'yxatida borligini tekshiradi.
    @ bilan yozilgan bo'lsa - username'i aniq mos kelishi kerak.
    @ bo'lmasa - substring (ism ichida qatnashishi) tekshiriladi.
    """
    global _banned_names_loaded
    if not _banned_names_loaded:
        await refresh_banned_names_cache()

    first = (first_name or "").lower()
    last = (last_name or "").lower()
    uname = (username or "").lower()

    for banned in _banned_names_cache:
        banned_clean = banned.strip().lower()
        if not banned_clean:
            continue
        
        if banned_clean.startswith('@'):
            clean_banned_uname = banned_clean[1:]
            if uname == clean_banned_uname:
                return True, banned
        else:
            if banned_clean in first or banned_clean in last or banned_clean in uname:
                return True, banned

    return False, ""


def contains_link(text: str) -> bool:
    """Faqat haqiqiy URL larni tekshiradi (@username emas)."""
    return bool(URL_PATTERN.search(text))


def contains_username_ad(text: str) -> bool:
    """@username reklamani tekshiradi — faqat o'chirish (restrict emas)."""
    return bool(USERNAME_PATTERN.search(text))


# So'z chegarasi patternlari (lookbehind/lookahead [\w] — so'z harfi)
_WB_BEFORE = "(?<![\\w])"   # oldingi belgi so'z harfi bo'lmasa
_WB_AFTER  = "(?![\\w])"    # keyingi belgi so'z harfi bo'lmasa


def contains_banned_word(text: str) -> tuple[bool, str]:
    """
    Matn ichida taqiqlangan so'z bor-yo'qligini tekshiradi.
    Faqat ALOHIDA so'z sifatida: 'olma' qo'shilsa 'olmagin' topilmaydi,
    lekin 'olma mevasi' topiladi.
    """
    t = text.lower()
    for word in _cache:
        if not word:
            continue
        # So'z chegarasi: so'z harfidan oldin/keyin bo'lmasa — topildi
        pattern = _WB_BEFORE + re.escape(word) + _WB_AFTER
        if re.search(pattern, t):
            return True, word
    return False, ""


async def check_message(text: str) -> dict:
    if not _cache_loaded:
        await refresh_banned_words_cache()

    has_link = contains_link(text)
    has_username_ad = contains_username_ad(text)
    has_bad, bad_word = contains_banned_word(text)

    return {
        "has_link": has_link,
        "has_username_ad": has_username_ad,   # faqat o'chirish
        "has_profanity": has_bad,
        "profane_word": bad_word,
        "should_delete": has_link or has_username_ad or has_bad,
    }
