# IstkharClone - clone owner customisation (runs inside every clone)

import random
import re
from functools import wraps

from pyrogram import Client, filters, types

from IstkharClone import app, config, lang, logger
from IstkharClone.core.clones import clones
from IstkharClone.core.context import registry
from IstkharClone.ui import tg_link


def clone_owner(func):
    """Only inside a clone, only for its owner (or the main owner)."""

    @wraps(func)
    async def wrapper(client, m: types.Message, *a, **kw):
        ctx = registry.current()
        if not ctx.is_clone:
            return
        uid = m.from_user.id if m.from_user else 0
        if uid not in (ctx.owner_id, config.OWNER_ID):
            return await m.reply_text(m.lang["clone_only_owner"])
        return await func(client, m, *a, **kw)

    return wrapper


async def _save(ctx):
    await clones.update(ctx.app.id, custom=ctx.custom)


def _link(value: str):
    value = value.strip()
    if re.match(r"^(https?://t\.me/|t\.me/|@)[A-Za-z0-9_+/]{4,}$", value):
        return tg_link(value)
    return None


@app.on_message(filters.command(["setsupport", "setchannel"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _set_link(_, m: types.Message):
    ctx = registry.current()
    if len(m.command) < 2:
        return await m.reply_text(m.lang["clonecfg_link_usage"].format(m.command[0]))
    link = _link(m.command[1])
    if not link:
        return await m.reply_text(m.lang["clonecfg_link_bad"])
    key = "support" if m.command[0] == "setsupport" else "channel"
    ctx.custom[key] = link
    await _save(ctx)
    await m.reply_text(m.lang["clonecfg_saved"])


@app.on_message(filters.command(["setstartimg"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _set_start_img(_, m: types.Message):
    ctx = registry.current()
    src = m.reply_to_message
    if src and src.photo:
        ctx.custom["start_img"] = src.photo.file_id
    elif len(m.command) > 1 and m.command[1].startswith("http"):
        ctx.custom["start_img"] = m.command[1]
    elif len(m.command) > 1 and m.command[1].lower() == "reset":
        ctx.custom.pop("start_img", None)
    else:
        return await m.reply_text(m.lang["clonecfg_img_usage"])
    await _save(ctx)
    await m.reply_text(m.lang["clonecfg_saved"])


@app.on_message(filters.command(["setplaytext", "addplaytext"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _set_play_text(_, m: types.Message):
    ctx = registry.current()
    if len(m.command) < 2:
        return await m.reply_text(m.lang["clonecfg_text_usage"])
    text = m.text.split(None, 1)[1]
    if text.lower() == "reset":
        ctx.custom.pop("play_text", None)
    else:
        items = ctx.custom.setdefault("play_text", [])
        if text not in items:
            items.append(text)
    await _save(ctx)
    await m.reply_text(m.lang["clonecfg_saved"])


@app.on_message(filters.command(["setstreamtext"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _set_stream_text(_, m: types.Message):
    ctx = registry.current()
    if len(m.command) < 2:
        return await m.reply_text(m.lang["clonecfg_stream_usage"])
    text = m.text.split(None, 1)[1]
    if text.lower() == "reset":
        ctx.custom.pop("stream_text", None)
    else:
        ctx.custom["stream_text"] = text
    await _save(ctx)
    await m.reply_text(m.lang["clonecfg_saved"])


@app.on_message(filters.command(["botinfo"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _botinfo(_, m: types.Message):
    ctx = registry.current()
    await m.reply_text(m.lang["clonecfg_info"].format(
        app.name, app.username, app.id, ctx.owner_id,
        ctx.custom.get("support", config.SUPPORT_CHAT),
        ctx.custom.get("channel", config.SUPPORT_CHANNEL),
        "own" if not ctx.shared_assistants else "shared",
        len(await ctx.db.get_chats()), len(await ctx.db.get_users()),
    ))


@app.on_message(filters.command(["logger", "setlogger"]) & ~app.bl_users)
@lang.language()
@clone_owner
async def _clone_logger(_, m: types.Message):
    ctx = registry.current()
    if len(m.command) < 2 or m.command[1] not in ("on", "off"):
        return await m.reply_text(m.lang["logger_usage"].format(m.command[0]))
    ctx.custom["log"] = m.command[1] == "on"
    await _save(ctx)
    await m.reply_text(m.lang["logger_on"] if ctx.custom["log"] else m.lang["logger_off"])


# ---- own assistant ---------------------------------------------------------
@app.on_message(filters.command(["setstring", "setassistant"]) & filters.private & ~app.bl_users)
@lang.language()
@clone_owner
async def _set_string(_, m: types.Message):
    ctx = registry.current()
    if len(m.command) < 2:
        return await m.reply_text(m.lang["clonecfg_string_usage"])
    session = m.command[1].strip()
    try:
        await m.delete()          # never keep a session string in the chat
    except Exception:
        pass
    sent = await m.reply_text(m.lang["clonecfg_string_wait"])
    # validate with a throw-away client first
    probe = Client(
        name=f"probe_{ctx.key}", api_id=config.API_ID, api_hash=config.API_HASH,
        session_string=session, in_memory=True, no_updates=True,
    )
    try:
        await probe.start()
        await probe.stop()
    except Exception as ex:
        return await sent.edit_text(m.lang["clonecfg_string_bad"].format(type(ex).__name__))
    doc = await clones.get(ctx.app.id)
    await clones.update(ctx.app.id, session=session)
    doc["session"] = session
    await sent.edit_text(m.lang["clonecfg_string_ok"])
    # restart this clone with the new assistant
    import asyncio
    asyncio.create_task(_restart(doc))


@app.on_message(filters.command(["delstring", "delassistant"]) & filters.private & ~app.bl_users)
@lang.language()
@clone_owner
async def _del_string(_, m: types.Message):
    ctx = registry.current()
    doc = await clones.get(ctx.app.id)
    await clones.col.update_one({"bot_id": ctx.app.id}, {"$unset": {"session": ""}})
    doc.pop("session", None)
    await m.reply_text(m.lang["clonecfg_string_removed"])
    import asyncio
    asyncio.create_task(_restart(doc))


async def _restart(doc):
    import asyncio
    await asyncio.sleep(2)
    await clones.stop_one(doc["bot_id"])
    await clones.start_one(doc)
