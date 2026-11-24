# IstkharClone - playback speed (0.5x - 2x), keeps the song position

from pyrogram import filters, types

from IstkharClone import anon, app, db, lang, queue
from IstkharClone.helpers import buttons, can_manage_vc
from IstkharClone.helpers import _audio

_busy: set[int] = set()


async def apply_speed(chat_id: int, speed: float) -> bool:
    await db.set_speed(chat_id, speed)
    return await anon.refresh(chat_id)


@app.on_message(filters.command(["speed"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _speed(_, m: types.Message):
    chat_id = m.chat.id
    if not await db.get_call(chat_id):
        return await m.reply_text(m.lang["not_playing"])
    if len(m.command) > 1:
        try:
            speed = float(m.command[1].lower().rstrip("x"))
        except ValueError:
            return await m.reply_text(m.lang["speed_usage"])
        if not 0.5 <= speed <= 2.0:
            return await m.reply_text(m.lang["speed_usage"])
        if chat_id in _busy:
            return await m.reply_text(m.lang["fx_busy"])
        _busy.add(chat_id)
        sent = await m.reply_text(m.lang["fx_applying"])
        try:
            await apply_speed(chat_id, speed)
        finally:
            _busy.discard(chat_id)
        return await sent.edit_text(m.lang["speed_set"].format(f"{speed:g}", m.from_user.mention))
    cur = await db.get_speed(chat_id)
    await m.reply_text(
        m.lang["speed_panel"].format(f"{cur:g}"),
        reply_markup=buttons.speed_markup(chat_id, cur, m.lang["close"]),
    )


@app.on_callback_query(filters.regex(r"^speed ") & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _speed_cb(_, q: types.CallbackQuery):
    _, chat_id, value = q.data.split()
    chat_id, speed = int(chat_id), float(value)
    if not await db.get_call(chat_id):
        return await q.answer(q.lang["not_playing"], show_alert=True)
    if chat_id in _busy:
        return await q.answer(q.lang["fx_busy"], show_alert=True)
    await q.answer(q.lang["fx_applying"])
    _busy.add(chat_id)
    try:
        await apply_speed(chat_id, speed)
    finally:
        _busy.discard(chat_id)
    try:
        await q.edit_message_text(
            q.lang["speed_panel"].format(f"{speed:g}"),
            reply_markup=buttons.speed_markup(chat_id, speed, q.lang["close"]),
        )
    except Exception:
        pass
