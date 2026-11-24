# IstkharClone - global ban (main sudoers) / clone ban (clone owner)

from pyrogram import filters, types

from IstkharClone import app, config, db, lang
from IstkharClone.core.context import registry
from IstkharClone.helpers import utils


@app.on_message(filters.command(["gban", "ungban"]) & app.sudoers)
@lang.language()
async def _gban(_, m: types.Message):
    """Global: affects the main bot AND every clone."""
    ctx = registry.current()
    if ctx.is_clone:
        return                      # global bans are managed from the main bot
    user = await utils.extract_user(m)
    if not user:
        return await m.reply_text(m.lang["user_not_found"])
    main_db = registry.main.db
    if m.command[0] == "gban":
        if user.id in app.sudoers or user.id == config.OWNER_ID:
            return await m.reply_text(m.lang["gban_sudo"])
        if user.id in main_db.bans:
            return await m.reply_text(m.lang["gban_already"].format(user.mention))
        await main_db.add_ban(user.id)
        return await m.reply_text(m.lang["gban_added"].format(user.mention))
    if user.id not in main_db.bans:
        return await m.reply_text(m.lang["gban_not"].format(user.mention))
    await main_db.del_ban(user.id)
    await m.reply_text(m.lang["gban_removed"].format(user.mention))


@app.on_message(filters.command(["gbanned", "gbanlist"]) & app.sudoers)
@lang.language()
async def _gbanned(_, m: types.Message):
    bans = registry.main.db.bans
    if not bans:
        return await m.reply_text(m.lang["gban_empty"])
    text = m.lang["gban_list"].format(len(bans))
    for i, uid in enumerate(list(bans)[:60], 1):
        text += f"\n{i}. <a href=tg://user?id={uid}>{uid}</a>"
    await m.reply_text(text)


@app.on_message(filters.command(["cgban", "uncgban"]) & ~app.bl_users)
@lang.language()
async def _cgban(_, m: types.Message):
    """Clone-level ban: only affects THIS clone."""
    ctx = registry.current()
    if not ctx.is_clone:
        return
    if m.from_user.id not in (ctx.owner_id, config.OWNER_ID):
        return await m.reply_text(m.lang["clone_only_owner"])
    user = await utils.extract_user(m)
    if not user:
        return await m.reply_text(m.lang["user_not_found"])
    if user.id in (ctx.owner_id, config.OWNER_ID):
        return await m.reply_text(m.lang["gban_sudo"])
    if m.command[0] == "cgban":
        await db.add_ban(user.id)
        return await m.reply_text(m.lang["gban_added"].format(user.mention))
    await db.del_ban(user.id)
    await m.reply_text(m.lang["gban_removed"].format(user.mention))
