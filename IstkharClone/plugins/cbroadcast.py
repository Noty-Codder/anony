# IstkharClone - broadcast of a CLONE owner (only reaches this clone's chats)

import asyncio

from pyrogram import errors, filters, types

from IstkharClone import app, config, db, lang
from IstkharClone.core.context import registry

_locks: dict[str, asyncio.Lock] = {}


@app.on_message(filters.command(["cbroadcast", "cgcast"]) & ~app.bl_users)
@lang.language()
async def _cbroadcast(_, m: types.Message):
    ctx = registry.current()
    if not ctx.is_clone:
        return
    if m.from_user.id not in (ctx.owner_id, config.OWNER_ID):
        return await m.reply_text(m.lang["clone_only_owner"])
    if not m.reply_to_message:
        return await m.reply_text(m.lang["gcast_usage"])
    lock = _locks.setdefault(ctx.key, asyncio.Lock())
    if lock.locked():
        return await m.reply_text(m.lang["gcast_active"])

    msg = m.reply_to_message
    copy = "-copy" in m.command
    groups = set() if "-nochat" in m.command else set(await db.get_chats())
    users = set(await db.get_users()) if "-user" in m.command else set()
    sent = await m.reply_text(m.lang["gcast_start"])
    count = ucount = 0
    async with lock:
        for chat in list(groups | users):
            try:
                out = await (msg.copy(chat, reply_markup=msg.reply_markup) if copy else msg.forward(chat))
                await db.track_msg(chat, out.id, "bcast")
                if chat in groups:
                    count += 1
                else:
                    ucount += 1
                await asyncio.sleep(0.2)
            except errors.FloodWait as fw:
                await asyncio.sleep(fw.value + 5)
            except Exception:
                continue
    await sent.edit_text(m.lang["gcast_end"].format(count, ucount))
