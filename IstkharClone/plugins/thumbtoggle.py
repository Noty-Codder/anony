# IstkharClone - thumbnail on / off per chat

from pyrogram import filters, types

from IstkharClone import app, db, lang
from IstkharClone.helpers import admin_check


@app.on_message(filters.command(["thumb", "nothumb", "thumbnail"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def _thumb(_, m: types.Message):
    arg = m.command[1].lower() if len(m.command) > 1 else ""
    if m.command[0] == "nothumb":
        new = False
    elif arg in ("on", "enable"):
        new = True
    elif arg in ("off", "disable"):
        new = False
    else:
        new = not await db.get_thumb_on(m.chat.id)
    await db.set_thumb_on(m.chat.id, new)
    await m.reply_text(m.lang["thumb_on"] if new else m.lang["thumb_off"])
