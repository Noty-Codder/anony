"""Per-bot execution context.

Every bot (the main one and each clone) owns its own database, queue, call
engine, download folder and assistant list.  Code in the rest of the project
keeps writing ``from IstkharClone import app, db, queue, anon, userbot`` --
those names are *proxies* that resolve to the context of the bot that is
currently handling the update.  That is what keeps clone data from merging
with the main bot (or with another clone).
"""

from __future__ import annotations

import contextvars
import os
from typing import Any, Optional

_current: contextvars.ContextVar[Optional["BotContext"]] = contextvars.ContextVar(
    "istkhar_ctx", default=None
)


class BotContext:
    """Everything that belongs to exactly one bot."""

    def __init__(
        self,
        *,
        key: str,
        client: Any = None,
        db: Any = None,
        queue: Any = None,
        anon: Any = None,
        userbot: Any = None,
        is_clone: bool = False,
        owner_id: int = 0,
        shared_assistants: bool = False,
    ):
        self.key = key                      # "main" or "c<bot_id>"
        self.app = client
        self.db = db
        self.queue = queue
        self.anon = anon
        self.userbot = userbot
        self.is_clone = is_clone
        self.owner_id = owner_id
        self.shared_assistants = shared_assistants
        self.custom: dict = {}              # clone customisation (start img, links ...)
        self.download_dir = os.path.join("downloads", key)
        os.makedirs(self.download_dir, exist_ok=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BotContext {self.key}>"

    # context-manager sugar:  with ctx.use(): ...
    def use(self):
        return _Use(self)


class _Use:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.token = None

    def __enter__(self):
        self.token = _current.set(self.ctx)
        return self.ctx

    def __exit__(self, *exc):
        _current.reset(self.token)
        return False


class Registry:
    """All live contexts + a tiny lock so two bots never drive the same
    assistant in the same chat."""

    def __init__(self):
        self.main: Optional[BotContext] = None
        self.clones: dict[int, BotContext] = {}
        self._owner: dict[int, BotContext] = {}

    # ---- lookup
    def all(self) -> list[BotContext]:
        out = [self.main] if self.main else []
        out.extend(self.clones.values())
        return out

    def current(self) -> BotContext:
        ctx = _current.get()
        return ctx if ctx is not None else self.main

    # ---- chat ownership (only matters for contexts sharing assistants)
    def owner(self, chat_id: int) -> Optional[BotContext]:
        return self._owner.get(chat_id)

    def claim(self, chat_id: int, ctx: BotContext) -> None:
        if ctx.shared_assistants:
            self._owner[chat_id] = ctx

    def release(self, chat_id: int, ctx: Optional[BotContext] = None) -> None:
        cur = self._owner.get(chat_id)
        if cur is not None and (ctx is None or cur is ctx):
            self._owner.pop(chat_id, None)

    def is_busy_for(self, chat_id: int, ctx: BotContext) -> bool:
        """True when *another* bot already streams in this chat through the
        same shared assistant pool."""
        if not ctx.shared_assistants:
            return False
        cur = self._owner.get(chat_id)
        return cur is not None and cur is not ctx


registry = Registry()


def current() -> BotContext:
    return registry.current()


def bind(callback, ctx: BotContext):
    """Wrap a handler callback so it always runs inside ``ctx``."""
    from functools import wraps

    @wraps(callback)
    async def wrapper(*args, **kwargs):
        token = _current.set(ctx)
        try:
            return await callback(*args, **kwargs)
        finally:
            _current.reset(token)

    return wrapper


class Proxy:
    """Attribute proxy to ``current().<attr>``."""

    __slots__ = ("_istk_attr",)

    def __init__(self, attr: str):
        object.__setattr__(self, "_istk_attr", attr)

    def _istk_target(self):
        return getattr(registry.current(), object.__getattribute__(self, "_istk_attr"))

    def __getattr__(self, name):
        return getattr(self._istk_target(), name)

    def __setattr__(self, name, value):
        setattr(self._istk_target(), name, value)

    def __bool__(self):
        return self._istk_target() is not None

    def __repr__(self):  # pragma: no cover
        return f"<Proxy {object.__getattribute__(self, '_istk_attr')} -> {self._istk_target()!r}>"
