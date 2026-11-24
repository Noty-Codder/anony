# IstkharClone - maintenance mode (owner only; applies to main bot and clones)

from pyrogram import filters, types

from IstkharClone import app, config, lang
from IstkharClone.core.context import registry


@app.on_message(filters.command(["maintenance"]) & filters.user(config.OWNER_ID))
@lang.language()
async def _maintenance(_, m: types.Message):
    if registry.current().is_clone:
        return
    db = registry.main.db
    arg = m.command[1].lower() if len(m.command) > 1 else ""
    if arg not in ("on", "off"):
        return await m.reply_text(
            m.lang["maintenance_usage"].format("ON" if db.maintenance else "OFF")
        )
    await db.set_maintenance(arg == "on")
    await m.reply_text(m.lang["maintenance_on"] if arg == "on" else m.lang["maintenance_off"])
