# IstkharClone - shuffle / remove from queue

from pyrogram import filters, types

from IstkharClone import app, db, lang, queue
from IstkharClone.helpers import can_manage_vc


@app.on_message(filters.command(["shuffle"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _shuffle(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])
    n = queue.shuffle(m.chat.id)
    if not n:
        return await m.reply_text(m.lang["shuffle_few"])
    await m.reply_text(m.lang["shuffle_done"].format(n, m.from_user.mention))


@app.on_message(filters.command(["remove", "rmqueue"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _remove(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply_text(m.lang["remove_usage"])
    item = queue.remove_at(m.chat.id, int(m.command[1]) - 1)
    if not item:
        return await m.reply_text(m.lang["remove_bad"])
    await m.reply_text(m.lang["remove_done"].format(item.title, m.from_user.mention))
