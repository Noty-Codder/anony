from os import getenv

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "False") -> bool:
    return str(getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int = 0) -> int:
    try:
        return int(str(getenv(name, default)).strip() or default)
    except ValueError:
        return default


class Config:
    def __init__(self):
        self.API_ID = _int("API_ID")
        self.API_HASH = getenv("API_HASH")

        self.BOT_TOKEN = getenv("BOT_TOKEN")
        self.MONGO_URL = getenv("MONGO_URL") or getenv("MONGO_DB_URI")
        # main bot database name; every clone gets "<DB_NAME>_c<bot_id>"
        self.DB_NAME = getenv("DB_NAME", "IstkharClone")

        self.LOGGER_ID = _int("LOGGER_ID")
        self.OWNER_ID = _int("OWNER_ID")
        self.OWNER_USERNAME = getenv("OWNER_USERNAME", "")

        self.DURATION_LIMIT = _int("DURATION_LIMIT", 60) * 60
        self.QUEUE_LIMIT = _int("QUEUE_LIMIT", 20)
        self.PLAYLIST_LIMIT = _int("PLAYLIST_LIMIT", 20)

        self.SESSION1 = getenv("SESSION") or getenv("STRING_SESSION")
        self.SESSION2 = getenv("SESSION2")
        self.SESSION3 = getenv("SESSION3")

        self.SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/fallenx")
        self.SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/DevilsHeavenMF")

        self.AUTO_LEAVE: bool = _bool("AUTO_LEAVE")
        self.AUTO_END: bool = _bool("AUTO_END")

        self.THUMB_GEN: bool = _bool("THUMB_GEN", "True")
        self.VIDEO_PLAY: bool = _bool("VIDEO_PLAY", "True")

        self.LANG_CODE = getenv("LANG_CODE", "en")

        self.COOKIES_URL = [
            url for url in getenv("COOKIES_URL", "").split(" ")
            if url and "batbin.me" in url
        ]
        self.DEFAULT_THUMB = getenv("DEFAULT_THUMB", "https://te.legra.ph/file/3e40a408286d4eda24191.jpg")
        self.PING_IMG = getenv("PING_IMG", "https://files.catbox.moe/haagg2.png")
        # several images can be given, separated by a space; one is picked at random
        self.START_IMG = getenv("START_IMG", "https://files.catbox.moe/zvziwk.jpg")
        self.HELP_IMG = getenv("HELP_IMG", "") or self.START_IMG
        self.STATS_IMG = getenv("STATS_IMG", "") or self.PING_IMG

        # ---------------- clone system ----------------
        self.CLONE_LIMIT = _int("CLONE_LIMIT", 500)
        self.CLONE_START_CONCURRENCY = max(1, _int("CLONE_START_CONCURRENCY", 6))
        self.CLONE_START_TIMEOUT = max(15, _int("CLONE_START_TIMEOUT", 45))
        self.ASSISTANT_START_TIMEOUT = max(10, _int("ASSISTANT_START_TIMEOUT", 30))
        self.CLONE_LOGGER = _int("CLONE_LOGGER") or self.LOGGER_ID
        # force-join before a user may clone (channel / group links)
        self.CLONE_FSUB: bool = _bool("CLONE_FSUB", "True")
        self.FSUB_CHANNEL = getenv("FSUB_CHANNEL") or self.SUPPORT_CHANNEL
        self.FSUB_GROUP = getenv("FSUB_GROUP") or self.SUPPORT_CHAT
        self.BOT_LINK = getenv("BOT_LINK", "")

        # ---------------- UI ----------------
        # random blue/green/red button colours + blockquote cards + small-caps font
        self.UI_COLORS: bool = _bool("UI_COLORS", "True")
        self.UI_BLOCKQUOTE: bool = _bool("UI_BLOCKQUOTE", "True")
        self.UI_FONT: bool = _bool("UI_FONT", "True")
        # Telegram-Premium custom emoji in texts/buttons (needs a bot that may use them)
        self.PREMIUM_EMOJI: bool = _bool("PREMIUM_EMOJI")
        self.BUTTON_ICONS: bool = _bool("BUTTON_ICONS")

        # ---------------- misc ----------------
        # every unhandled error / traceback is reported here (optional)
        self.ERROR_LOGGER_ID = _int("ERROR_LOGGER_ID")
        self.SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", "")
        self.HEROKU_APP_NAME = getenv("HEROKU_APP_NAME")
        self.HEROKU_API_KEY = getenv("HEROKU_API_KEY")

    def check(self):
        missing = [
            var
            for var in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "LOGGER_ID", "OWNER_ID", "SESSION1"]
            if not getattr(self, var)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
