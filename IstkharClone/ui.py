"""Premium UI kit shared by the main bot and every clone.

* ``fancy``       small-caps font that leaves HTML, {placeholders}, links,
                  /commands and @mentions untouched
* ``wrap_quote``  blockquote card around any text / caption
* ``install_button_patch``  every inline button gets a random colour
                  (blue / green / red) and the small-caps font
* ``premium``     optional Telegram-Premium custom emoji
"""

from __future__ import annotations

import inspect
import random
import re
from typing import Any, Optional

from IstkharClone import config

# ------------------------------------------------------------------ font
_MAP = {
    "a": "ᴧ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "є", "f": "ғ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "η",
    "o": "σ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}
_TABLE = str.maketrans({**_MAP, **{k.upper(): v for k, v in _MAP.items()}})

# pieces of a string that must never be converted
_KEEP = re.compile(
    r"(<code>.*?</code>|<pre>.*?</pre>|<[^>]+>|&[#\w]+;|\{[^{}]*\}"
    r"|(?:https?|tg)://\S+|(?<![\w/])/[A-Za-z0-9_]+(?:@\w+)?|@\w+)",
    re.S,
)


def fancy(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    out, last = [], 0
    for m in _KEEP.finditer(text):
        out.append(text[last:m.start()].translate(_TABLE))
        out.append(m.group(0))
        last = m.end()
    out.append(text[last:].translate(_TABLE))
    return "".join(out)


# ------------------------------------------------------------------ quote
_HAS_QUOTE = re.compile(r"<\s*blockquote", re.I)


def has_quote(text: Any) -> bool:
    return isinstance(text, str) and bool(_HAS_QUOTE.search(text))


def wrap_quote(text: Any, expandable: bool = False) -> Any:
    """Wrap ``text`` in a blockquote unless it already contains one."""
    if not isinstance(text, str):
        return text
    body = text.strip()
    if not body or has_quote(body):
        return text
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>{body}</{tag}>"


def quote(text: Any, expandable: bool = False) -> str:
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>{text}</{tag}>"


# ------------------------------------------------------------------ premium emoji
PREMIUM_IDS = {
    "✨": "6172312314423808834", "🎵": "5409025823388741707",
    "🎧": "6082387600599944892", "🤖": "5355051922862653659",
    "👋": "5246815495713207687", "💖": "6170455814810112778",
    "📚": "5260512129240276089", "❓": "5188540541922480562",
    "🛠": "5462921117423384478", "🔎": "5429571366384842791",
    "🌀": "5373310679241466020", "⌛": "5891211339170326418",
}
_TAG = re.compile(r"<tg-emoji[^>]*>.*?</tg-emoji>", re.S)


def premium(text: str) -> str:
    """Swap a few emoji for premium custom emoji when PREMIUM_EMOJI is on."""
    if not config.PREMIUM_EMOJI or not isinstance(text, str):
        return text
    parts, last, out = list(_TAG.finditer(text)), 0, []
    spans = [(m.start(), m.end()) for m in parts]

    def inside(pos):
        return any(a <= pos < b for a, b in spans)

    for i, ch in enumerate(text):
        if ch in PREMIUM_IDS and not inside(i):
            out.append(f'<tg-emoji emoji-id="{PREMIUM_IDS[ch]}">{ch}</tg-emoji>')
        else:
            out.append(ch)
    return "".join(out)


# ------------------------------------------------------------------ buttons
_installed = False


def _styles():
    from pyrogram import enums

    names = ("PRIMARY", "SUCCESS", "DANGER")
    return [getattr(enums.ButtonStyle, n) for n in names if hasattr(enums.ButtonStyle, n)]


def random_style():
    try:
        pool = _styles()
        return random.choice(pool) if pool else None
    except Exception:
        return None


def install_button_patch() -> None:
    """Give every InlineKeyboardButton a random colour + small-caps text."""
    global _installed
    if _installed:
        return
    _installed = True

    from pyrogram import enums
    from pyrogram.types import InlineKeyboardButton as IKB

    try:
        params = set(inspect.signature(IKB.__init__).parameters)
    except (TypeError, ValueError):  # pragma: no cover
        params = set()
    has_style = "style" in params and hasattr(enums, "ButtonStyle")
    has_icon = "icon_custom_emoji_id" in params
    original = IKB.__init__

    def patched(self, *args, **kwargs):
        # text may come positionally
        if args and isinstance(args[0], str) and config.UI_FONT:
            args = (fancy(args[0]),) + tuple(args[1:])
        elif isinstance(kwargs.get("text"), str) and config.UI_FONT:
            kwargs["text"] = fancy(kwargs["text"])

        if has_style and config.UI_COLORS:
            style = kwargs.get("style")
            if style is None:
                kwargs["style"] = random_style()
            elif not isinstance(style, enums.ButtonStyle):
                name = str(getattr(style, "value", style)).upper()
                kwargs["style"] = getattr(enums.ButtonStyle, name, random_style())
        elif "style" in kwargs and not has_style:
            kwargs.pop("style")

        icon = kwargs.get("icon_custom_emoji_id")
        if icon is not None:
            if has_icon and config.BUTTON_ICONS:
                kwargs["icon_custom_emoji_id"] = str(icon)
            else:
                kwargs.pop("icon_custom_emoji_id", None)
        original(self, *args, **kwargs)

    IKB.__init__ = patched


def tg_link(val: Optional[str], fallback: Optional[str] = None) -> str:
    """'@chat', 'chat', 't.me/chat' or a full url -> https url."""
    fb = fallback or config.SUPPORT_CHAT
    if not val or str(val).strip().lower() in ("", "none"):
        return fb
    val = str(val).strip()
    if " " in val:
        return fb
    if val.startswith(("https://", "http://", "tg://")):
        return val
    if val.startswith("t.me/"):
        return "https://" + val
    return f"https://t.me/{val.lstrip('@')}"


def pick(value: str) -> str:
    """Several space separated links -> one random link."""
    items = [v for v in str(value or "").split() if v]
    return random.choice(items) if items else ""
