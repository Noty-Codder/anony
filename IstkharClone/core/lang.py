# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import json
from functools import wraps
from pathlib import Path

from pyrogram import errors

from IstkharClone import app, config, db, logger
from IstkharClone.core.context import registry
from IstkharClone.ui import fancy

lang_codes = {
    "ar": "العربية",
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "hi": "हिन्दी",
    "ja": "日本語",
    "my": "မြန်မာဘာသာ",
    "pa": "ਪੰਜਾਬੀ",
    "pt": "Português",
    "ru": "Русский",
    "tr": "Türkçe",
    "zh": "中文"
}


class Language:
    """
    Language class for managing multilingual support using JSON language files.
    """

    def __init__(self):
        self.lang_codes = lang_codes
        self.lang_dir = Path("IstkharClone/locales")
        self.languages = self.load_files()

    def load_files(self):
        languages = {}
        lang_files = {file.stem: file for file in self.lang_dir.glob("*.json")}
        for lang_code, lang_file in lang_files.items():
            with open(lang_file, "r", encoding="utf-8") as file:
                languages[lang_code] = json.load(file)

        # every language falls back to English for keys it does not have yet
        base = languages.get("en", {})
        for code in list(languages):
            languages[code] = {**base, **languages[code]}
        if config.UI_FONT and "en" in languages:
            languages["en"] = {
                k: (fancy(v) if isinstance(v, str) else v)
                for k, v in languages["en"].items()
            }
        logger.info(f"Loaded languages: {', '.join(languages.keys())}")
        return languages

    async def get_lang(self, chat_id: int) -> dict:
        lang_code = await db.get_lang(chat_id)
        return self.languages[lang_code]

    def get_languages(self) -> dict:
        files = {f.stem for f in self.lang_dir.glob("*.json")}
        return {code: self.lang_codes[code] for code in sorted(files)}

    def language(self):
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                fallen = next(
                    (
                        arg
                        for arg in args
                        if hasattr(arg, "chat") or hasattr(arg, "message")
                    ),
                    None,
                )

                if not fallen.from_user:
                    return

                if hasattr(fallen, "chat"):
                    chat = fallen.chat
                elif hasattr(fallen, "message"):
                    chat = fallen.message.chat

                if not chat: return

                if chat.id in db.blacklisted:
                    logger.info(f"Chat {chat.id} is blacklisted, leaving...")
                    return await chat.leave()

                uid = fallen.from_user.id
                main = registry.main
                if uid in main.db.bans or uid in db.bans:
                    return                      # (g)banned user: ignored
                if (
                    main.db.maintenance
                    and uid != config.OWNER_ID
                    and uid not in app.sudoers
                ):
                    text = self.languages.get(config.LANG_CODE, {}).get("maintenance_msg")
                    try:
                        if hasattr(fallen, "reply_text"):
                            return await fallen.reply_text(text)
                        return await fallen.answer(text, show_alert=True)
                    except Exception:
                        return

                lang_code = await db.get_lang(chat.id)
                lang_dict = self.languages[lang_code]

                setattr(fallen, "lang", lang_dict)
                try:
                    return await func(*args, **kwargs)
                except (errors.FloodWait, errors.SlowmodeWait):
                    return
                except (
                    errors.ChannelInvalid, errors.ChannelPrivate,
                    errors.MessageIdInvalid, errors.MessageNotModified,
                ):
                    return
                except (
                    errors.Forbidden, errors.exceptions.Forbidden,
                    errors.ChatWriteForbidden, errors.exceptions.ChatWriteForbidden,
                ):
                    return

            return wrapper

        return decorator
