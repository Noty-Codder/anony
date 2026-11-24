# IstkharClone - autoplay: keep playing related songs when the queue ends

from pyrogram import filters, types

from IstkharClone import app, db, lang
from IstkharClone.helpers import can_manage_vc


@app.on_message(filters.command(["autoplay"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _autoplay(_, m: types.Message):
    cur = await db.get_autoplay(m.chat.id)
    arg = m.command[1].lower() if len(m.command) > 1 else ""
    if arg in ("on", "enable", "true"):
        new = True
    elif arg in ("off", "disable", "false"):
        new = False
    else:
        new = not cur
    await db.set_autoplay(m.chat.id, new)
    await m.reply_text(m.lang["autoplay_on"] if new else m.lang["autoplay_off"])
