"""Pyrogram client used by the main bot and every clone.

Adds the premium "blockquote card" look to everything the bot sends: text,
captions and edited media.  Messages that already contain a ``<blockquote``
(multi-quote screens) are left alone; pass ``quote_wrap=False`` to any call
to send raw text (broadcasts of user content, for example).
"""

from __future__ import annotations

import pyrogram
from pyrogram import enums

from IstkharClone import config
from IstkharClone.ui import wrap_quote


def _html_ok(parse_mode, default) -> bool:
    mode = parse_mode if parse_mode is not None else default
    if mode is None:
        return True
    name = getattr(mode, "name", str(mode)).upper()
    return name in ("HTML", "DEFAULT")


class IstkharClient(pyrogram.Client):
    def _q(self, args: tuple, kwargs: dict, name: str, pos: int):
        """Wrap argument ``name`` (keyword, or positional index ``pos``)."""
        if not kwargs.pop("quote_wrap", True) or not config.UI_BLOCKQUOTE:
            return args
        if kwargs.get("entities") or kwargs.get("caption_entities"):
            return args
        if not _html_ok(kwargs.get("parse_mode"), getattr(self, "parse_mode", None)):
            return args
        if name in kwargs:
            kwargs[name] = wrap_quote(kwargs[name])
        elif len(args) > pos:
            args = args[:pos] + (wrap_quote(args[pos]),) + args[pos + 1:]
        return args

    async def send_message(self, *args, **kwargs):
        args = self._q(args, kwargs, "text", 1)
        return await super().send_message(*args, **kwargs)

    async def edit_message_text(self, *args, **kwargs):
        args = self._q(args, kwargs, "text", 2)
        return await super().edit_message_text(*args, **kwargs)

    async def edit_message_caption(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().edit_message_caption(*args, **kwargs)

    async def send_photo(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().send_photo(*args, **kwargs)

    async def send_video(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().send_video(*args, **kwargs)

    async def send_animation(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().send_animation(*args, **kwargs)

    async def send_audio(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().send_audio(*args, **kwargs)

    async def send_document(self, *args, **kwargs):
        args = self._q(args, kwargs, "caption", 2)
        return await super().send_document(*args, **kwargs)

    async def edit_message_media(self, *args, **kwargs):
        raw = kwargs.pop("quote_wrap", True)
        media = kwargs.get("media") if "media" in kwargs else (args[2] if len(args) > 2 else None)
        if raw and config.UI_BLOCKQUOTE and media is not None:
            cap = getattr(media, "caption", None)
            if (
                isinstance(cap, str)
                and not getattr(media, "caption_entities", None)
                and _html_ok(getattr(media, "parse_mode", None), getattr(self, "parse_mode", None))
            ):
                media.caption = wrap_quote(cap)
        return await super().edit_message_media(*args, **kwargs)


class CloneClient(IstkharClient):
    """A clone bot.  Shares the global sudo / ban filters of the main bot."""

    def __init__(self, bot_id: int, token: str, owner_id: int, main_app):
        super().__init__(
            name=f"clone_{bot_id}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=token,
            parse_mode=enums.ParseMode.HTML,
            max_concurrent_transmissions=4,
            link_preview_options=pyrogram.types.LinkPreviewOptions(is_disabled=True),
            in_memory=True,
        )
        self.owner = owner_id
        self.logger = 0
        self.sudoers = main_app.sudoers
        self.bl_users = main_app.bl_users

    def finish_boot(self):
        self.id = self.me.id
        self.name = self.me.first_name
        self.username = self.me.username
        self.mention = self.me.mention
