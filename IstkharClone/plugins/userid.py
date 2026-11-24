# IstkharClone - /id

from pyrogram import filters, types

from IstkharClone import app, lang
from IstkharClone.helpers import utils


@app.on_message(filters.command(["id"]) & ~app.bl_users)
@lang.language()
async def _id(_, m: types.Message):
    target = m.reply_to_message.from_user if m.reply_to_message and m.reply_to_message.from_user else m.from_user
    text = m.lang["id_user"].format(target.id)
    if m.chat.type.name != "PRIVATE":
        text += m.lang["id_chat"].format(m.chat.id)
    text += m.lang["id_msg"].format(m.id)
    await m.reply_text(text)
