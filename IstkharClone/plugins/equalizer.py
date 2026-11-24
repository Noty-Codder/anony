# IstkharClone - equalizer presets + volume panel

from pyrogram import filters, types

from IstkharClone import anon, app, db, lang
from IstkharClone.helpers import buttons, can_manage_vc
from IstkharClone.helpers import _audio

_busy: set[int] = set()


async def _panel(chat_id: int, _lang: dict):
    preset, volume = await db.get_eq(chat_id)
    text = _lang["eq_panel"].format(_audio.EQ_PRESETS[preset][0], volume)
    return text, buttons.eq_markup(_lang, chat_id, preset, volume)


async def _vol_panel(chat_id: int, _lang: dict):
    _, volume = await db.get_eq(chat_id)
    return _lang["vol_panel"].format(volume), buttons.volume_markup(_lang, chat_id, volume)


@app.on_message(filters.command(["eq", "equalizer"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _eq(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])
    text, markup = await _panel(m.chat.id, m.lang)
    await m.reply_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^eq ") & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _eq_cb(_, q: types.CallbackQuery):
    parts = q.data.split()
    action, chat_id = parts[1], int(parts[2])
    arg = parts[3] if len(parts) > 3 else None

    if action == "panel":
        text, markup = await _panel(chat_id, q.lang)
        await q.answer()
        return await q.edit_message_text(text, reply_markup=markup)
    if action == "volp":
        text, markup = await _vol_panel(chat_id, q.lang)
        await q.answer()
        return await q.edit_message_text(text, reply_markup=markup)

    if chat_id in _busy:
        return await q.answer(q.lang["fx_busy"], show_alert=True)

    if action == "set":
        if arg not in _audio.EQ_PRESETS:
            return await q.answer()
        await db.set_eq(chat_id, preset=arg)
    elif action == "vol":
        _, volume = await db.get_eq(chat_id)
        if arg == "reset":
            await db.set_eq(chat_id, preset="normal", volume=_audio.DEF_VOL)
        else:
            await db.set_eq(chat_id, volume=_audio.next_volume(volume, arg))
    else:
        return await q.answer()

    await q.answer(q.lang["fx_applying"])
    _busy.add(chat_id)
    try:
        if await db.get_call(chat_id):
            await anon.refresh(chat_id)
    finally:
        _busy.discard(chat_id)

    text, markup = (
        await _vol_panel(chat_id, q.lang) if action == "vol" else await _panel(chat_id, q.lang)
    )
    try:
        await q.edit_message_text(text, reply_markup=markup)
    except Exception:
        pass
