"""Auto-delete worker.

* player cards  -> deleted 24 hours after they were sent
* broadcasts    -> deleted 48 hours after they were sent

Every message is deleted by the SAME bot that sent it (main bot or the clone),
and the list lives in that bot's own database, so it survives restarts and
clone data never mixes.
"""

import asyncio

from IstkharClone import logger
from IstkharClone.core.context import registry

TTL = {"play": 24 * 3600, "bcast": 48 * 3600}
CHECK_EVERY = 600  # seconds


async def _sweep(ctx) -> int:
    done = 0
    with ctx.use():
        for kind, ttl in TTL.items():
            for doc in await ctx.db.expired_msgs(kind, ttl):
                try:
                    await ctx.app.delete_messages(doc["chat_id"], doc["message_id"])
                except Exception:
                    pass  # already deleted / no rights / chat gone -> just forget it
                await ctx.db.forget_msg(doc["_id"])
                done += 1
                await asyncio.sleep(0.3)
    return done


async def run() -> None:
    await asyncio.sleep(30)
    while True:
        for ctx in list(registry.all()):
            try:
                await _sweep(ctx)
            except Exception as ex:
                logger.warning(f"cleaner [{getattr(ctx, 'key', '?')}]: {ex}")
        await asyncio.sleep(CHECK_EVERY)
