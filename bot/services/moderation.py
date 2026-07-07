"""Link va taqiqlangan so'z tekshiruvi."""
import re
from typing import List
from database import queries

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

_cache: List[str] = []
_cache_loaded: bool = False


async def refresh_banned_words_cache():
    global _cache, _cache_loaded
    try:
        _cache = await queries.get_banned_words_list()
        _cache_loaded = True
    except Exception:
        pass


def contains_link(text: str) -> bool:
    return bool(URL_PATTERN.search(text))


def contains_banned_word(text: str) -> tuple[bool, str]:
    """Matn ichida taqiqlangan so'z bor-yo'qligini tekshiradi (substring)."""
    t = text.lower()
    for word in _cache:
        if word and word in t:
            return True, word
    return False, ""


async def check_message(text: str) -> dict:
    if not _cache_loaded:
        await refresh_banned_words_cache()

    has_link = contains_link(text)
    has_bad, bad_word = contains_banned_word(text)

    return {
        "has_link": has_link,
        "has_profanity": has_bad,
        "profane_word": bad_word,
        "should_delete": has_link or has_bad,
    }
