"""Clone manager.

Every clone is a full bot of its own:
  * its own Mongo database (``<DB_NAME>_c<bot_id>``) -> data never merges
  * its own queue, call engine, download folder and settings
  * its own assistant (session string) or, when none is set, the shared pool
    of the main bot (a chat is then served by one bot at a time)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Optional

from pyrogram import enums
from pyrogram.errors import (AccessTokenExpired, AccessTokenInvalid, FloodWait)
from pyrogram.types import BotCommand

from IstkharClone import config, logger
from IstkharClone.core.client import CloneClient
from IstkharClone.core.context import BotContext, bind, registry

# plugins whose handlers are shared with clones
CLONE_PLUGINS = {
    "play", "pause", "resume", "skip", "stop", "seek", "loop", "queue",
    "speed", "shuffle", "autoplay", "equalizer", "callbacks", "start",
    "ping", "auth", "language", "stats", "iquery", "misc", "userid",
    "clone", "clonecfg", "thumbtoggle", "cbroadcast", "gban",
}

BOT_COMMANDS = [
    ("clone", "Clone your own music bot"),
    ("start", "Start the music bot"),
    ("help", "Help menu and all commands"),
    ("play", "Play a song in the voice chat"),
    ("vplay", "Play a video in the voice chat"),
    ("pause", "Pause the stream"),
    ("resume", "Resume the stream"),
    ("skip", "Skip to the next track"),
    ("stop", "Stop the stream and clear the queue"),
    ("queue", "Show the queue"),
    ("shuffle", "Shuffle the queue"),
    ("speed", "Change playback speed"),
    ("eq", "Equalizer and volume"),
    ("autoplay", "Toggle autoplay"),
    ("ping", "Ping and system stats"),
    ("settings", "Chat settings"),
]


class CloneManager:
    def __init__(self):
        self.guard_task: Optional[asyncio.Task] = None
        self._fails: dict[int, int] = {}
        self._starting: set[int] = set()

    # ------------------------------------------------------------ storage
    @property
    def col(self):
        return registry.main.db.db.clones

    async def count(self) -> int:
        return await self.col.count_documents({})

    async def get(self, bot_id: int) -> Optional[dict]:
        return await self.col.find_one({"bot_id": int(bot_id)})

    async def find(self, query: str) -> Optional[dict]:
        query = str(query).strip().lstrip("@")
        return await self.col.find_one(
            {"$or": [{"token": query}, {"username": query}] + (
                [{"bot_id": int(query)}] if query.isdigit() else []
            )}
        )

    async def by_owner(self, user_id: int) -> list[dict]:
        return [d async for d in self.col.find({"owner_id": int(user_id)})]

    async def all_docs(self) -> list[dict]:
        return [d async for d in self.col.find({})]

    async def update(self, bot_id: int, **fields) -> None:
        await self.col.update_one({"bot_id": int(bot_id)}, {"$set": fields})

    # ------------------------------------------------------------ runtime
    def attach_handlers(self, client: CloneClient, ctx: BotContext) -> int:
        main_app = registry.main.app
        n = 0
        for plugin, handler, group in list(main_app.handler_log):
            if plugin not in CLONE_PLUGINS:
                continue
            flt = getattr(handler, "filters", None)
            try:
                new = type(handler)(bind(handler.callback, ctx), flt)
                client.add_handler(new, group)
                n += 1
            except Exception as ex:  # pragma: no cover
                logger.warning("handler copy failed (%s): %s", plugin, ex)
        return n

    async def _build(self, doc: dict) -> BotContext:
        from IstkharClone.core.calls import TgCall
        from IstkharClone.core.mongo import MongoDB
        from IstkharClone.helpers import Queue

        main = registry.main
        bot_id = int(doc["bot_id"])
        key = f"c{bot_id}"
        client = CloneClient(bot_id, doc["token"], int(doc["owner_id"]), main.app)
        db = MongoDB(dbname=f"{config.DB_NAME}_{key}", mongo=main.db.mongo)
        ctx = BotContext(
            key=key,
            client=client,
            db=db,
            queue=Queue(),
            anon=TgCall(),
            is_clone=True,
            owner_id=int(doc["owner_id"]),
            shared_assistants=True,
        )
        ctx.anon.ctx = ctx
        ctx.doc = doc
        ctx.custom = dict(doc.get("custom") or {})
        # until an own assistant is attached the main pool is used
        ctx.userbot = main.userbot
        ctx.anon.clients = main.anon.clients
        return ctx

    async def _attach_assistant(self, ctx: BotContext, session: str) -> bool:
        from IstkharClone.core.userbot import CloneAssistants

        ua = CloneAssistants(ctx.key)
        try:
            await asyncio.wait_for(ua.boot(session), timeout=config.ASSISTANT_START_TIMEOUT)
            ctx.anon.clients = []
            await ctx.anon.boot_own(ua.clients[0])
        except Exception as ex:
            logger.warning("Assistant of clone %s failed (%s); using shared assistants.", ctx.key, ex)
            await ua.exit()
            ctx.anon.clients = registry.main.anon.clients
            return False
        ctx.userbot = ua
        ctx.shared_assistants = False
        return True

    async def start_one(self, doc: dict, *, announce: bool = False, retry: bool = True) -> bool:
        bot_id = int(doc["bot_id"])
        if bot_id in registry.clones or bot_id in self._starting:
            return True
        self._starting.add(bot_id)
        ctx = None
        try:
            ctx = await self._build(doc)
            await ctx.db.connect_clone()
            self.attach_handlers(ctx.app, ctx)
            with ctx.use():
                await asyncio.wait_for(ctx.app.start(), timeout=config.CLONE_START_TIMEOUT)
                ctx.app.finish_boot()
                if doc.get("session"):
                    with_session = await self._attach_assistant(ctx, doc["session"])
                    if not with_session:
                        ctx.shared_assistants = True
            registry.clones[bot_id] = ctx
            logger.info("Clone @%s started (%s).", ctx.app.username, ctx.key)
            if announce and config.CLONE_LOGGER:
                try:
                    await registry.main.app.send_message(
                        config.CLONE_LOGGER,
                        f"<b>✅ Clone started</b>\n@{ctx.app.username}",
                    )
                except Exception:
                    pass
            return True
        except FloodWait as ex:
            await self._cleanup(ctx)
            if retry:
                wait = max(5, int(getattr(ex, "value", 30)) + 6)
                logger.warning("Clone %s rate limited, retry in %ss", bot_id, wait)
                asyncio.create_task(self._delayed(doc, wait))
            return False
        except (AccessTokenExpired, AccessTokenInvalid):
            await self._cleanup(ctx)
            await self.drop(bot_id, reason="invalid token")
            return False
        except asyncio.TimeoutError:
            await self._cleanup(ctx)
            logger.error("Clone %s start timed out.", bot_id)
            return False
        except Exception:
            await self._cleanup(ctx)
            logger.exception("Clone %s failed to start.", bot_id)
            return False
        finally:
            self._starting.discard(bot_id)

    async def _delayed(self, doc, wait):
        await asyncio.sleep(wait)
        await self.start_one(doc, announce=True, retry=False)

    async def _cleanup(self, ctx: Optional[BotContext]) -> None:
        if ctx is None:
            return
        try:
            if ctx.app.is_connected:
                await ctx.app.stop()
        except Exception:
            pass
        if isinstance(getattr(ctx, "userbot", None), object) and hasattr(ctx.userbot, "exit") and ctx.userbot is not registry.main.userbot:
            try:
                await ctx.userbot.exit()
            except Exception:
                pass

    async def start_all(self) -> None:
        docs = await self.all_docs()
        if not docs:
            return
        logger.info("Starting %s clone(s)...", len(docs))
        sem = asyncio.Semaphore(config.CLONE_START_CONCURRENCY)

        async def run(d):
            async with sem:
                await self.start_one(d)

        await asyncio.gather(*(run(d) for d in docs), return_exceptions=True)
        logger.info("%s/%s clone(s) running.", len(registry.clones), len(docs))
        if not self.guard_task:
            self.guard_task = asyncio.create_task(self.guard())

    async def stop_one(self, bot_id: int) -> None:
        ctx = registry.clones.pop(int(bot_id), None)
        if not ctx:
            return
        try:
            with ctx.use():
                await ctx.anon.shutdown_own() if not ctx.shared_assistants else None
        except Exception:
            pass
        for chat_id in list(ctx.db.active_calls):
            registry.release(chat_id, ctx)
        try:
            await ctx.app.stop()
        except Exception:
            pass
        if ctx.userbot is not registry.main.userbot:
            try:
                await ctx.userbot.exit()
            except Exception:
                pass

    async def stop_all(self) -> None:
        if self.guard_task:
            self.guard_task.cancel()
            self.guard_task = None
        for bot_id in list(registry.clones):
            await self.stop_one(bot_id)

    # ------------------------------------------------------------ create / remove
    async def create(self, token: str, owner_id: int, owner_name: str = "") -> BotContext:
        """Validate ``token``, start the clone, save it.  Raises on failure."""
        bot_id = int(token.split(":")[0])
        doc = {
            "bot_id": bot_id,
            "token": token,
            "owner_id": int(owner_id),
            "owner_name": owner_name,
            "created": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            "support": config.SUPPORT_CHAT,
            "channel": config.SUPPORT_CHANNEL,
            "custom": {},
        }
        ok = await self.start_one(doc, retry=False)
        if not ok:
            raise RuntimeError("Could not start the bot with this token.")
        ctx = registry.clones[bot_id]
        doc.update(username=ctx.app.username, name=ctx.app.name)
        ctx.doc = doc
        await self.col.replace_one({"bot_id": bot_id}, doc, upsert=True)
        try:
            await ctx.app.set_bot_commands([BotCommand(c, d) for c, d in BOT_COMMANDS])
        except Exception:
            pass
        return ctx

    async def drop(self, bot_id: int, reason: str = "") -> Optional[dict]:
        """Stop the clone, delete it and its database."""
        bot_id = int(bot_id)
        doc = await self.get(bot_id)
        await self.stop_one(bot_id)
        await self.col.delete_one({"bot_id": bot_id})
        try:
            await registry.main.db.mongo.drop_database(f"{config.DB_NAME}_c{bot_id}")
        except Exception:
            pass
        import shutil
        shutil.rmtree(f"downloads/c{bot_id}", ignore_errors=True)
        if doc and config.CLONE_LOGGER:
            try:
                await registry.main.app.send_message(
                    config.CLONE_LOGGER,
                    f"<b>🧹 Clone removed</b>\n@{doc.get('username')} "
                    f"(<code>{bot_id}</code>)" + (f"\nReason: {reason}" if reason else ""),
                )
            except Exception:
                pass
        return doc

    # ------------------------------------------------------------ guard
    async def guard(self, every: int = 300) -> None:
        """Every 5 min: a clone whose token was revoked is removed.  Network
        hiccups never remove a clone (3 strikes of AccessToken errors needed)."""
        while True:
            await asyncio.sleep(every)
            for bot_id, ctx in list(registry.clones.items()):
                try:
                    await asyncio.wait_for(ctx.app.get_me(), timeout=20)
                    self._fails.pop(bot_id, None)
                except (AccessTokenExpired, AccessTokenInvalid):
                    self._fails[bot_id] = self._fails.get(bot_id, 0) + 1
                    if self._fails[bot_id] >= 3:
                        await self.drop(bot_id, reason="bot token revoked / bot deleted")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass


clones = CloneManager()
