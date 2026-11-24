# IstkharClone - clone system (/clone, /delclone, /myclone + sudo tools)

import asyncio
import os
import re

from pyrogram import enums, errors, filters, types

from IstkharClone import app, config, lang, logger
from IstkharClone.core.clones import clones
from IstkharClone.core.context import registry
from IstkharClone.helpers import buttons
from IstkharClone.ui import tg_link

PENDING: dict[int, str] = {}
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
OWNER = config.OWNER_ID


def _ref(link: str):
    link = str(link or "").strip()
    if link.startswith("@"):
        return link[1:]
    m = re.match(r"https?://t\.me/([A-Za-z0-9_]{4,})/?$", link)
    return m.group(1) if m else None   # private invite links cannot be checked


async def _joined(user_id: int) -> bool:
    if not config.CLONE_FSUB or user_id == OWNER or user_id in app.sudoers:
        return True
    main = registry.main.app
    for link in (config.FSUB_CHANNEL, config.FSUB_GROUP):
        ref = _ref(link)
        if not ref:
            continue
        try:
            member = await main.get_chat_member(ref, user_id)
            if member.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
                return False
        except errors.UserNotParticipant:
            return False
        except Exception:
            continue    # bot not admin there -> never block the user
    return True


def _fsub_markup(_lang: dict):
    return types.InlineKeyboardMarkup([
        [
            types.InlineKeyboardButton(_lang["channel"], url=tg_link(config.FSUB_CHANNEL)),
            types.InlineKeyboardButton(_lang["support"], url=tg_link(config.FSUB_GROUP)),
        ],
        [types.InlineKeyboardButton(_lang["clone_verify"], callback_data="clone_verify")],
    ])


async def _do_clone(reply, user: types.User, token: str, _lang: dict):
    """``reply`` is an async callable(text, **kw) -> Message (send or edit)."""
    if not TOKEN_RE.match(token):
        return await reply(_lang["clone_invalid"])

    if await clones.count() >= config.CLONE_LIMIT and user.id != OWNER:
        return await reply(_lang["clone_limit"].format(config.CLONE_LIMIT))

    if user.id != OWNER and user.id not in app.sudoers and await clones.by_owner(user.id):
        return await reply(_lang["clone_already_user"])

    if await clones.get(int(token.split(":")[0])):
        return await reply(_lang["clone_already_bot"])

    status = await reply(_lang["clone_starting"])
    try:
        ctx = await clones.create(token, user.id, user.first_name)
    except (errors.AccessTokenExpired, errors.AccessTokenInvalid):
        return await status.edit_text(_lang["clone_invalid"])
    except Exception as ex:
        logger.exception("clone failed")
        return await status.edit_text(_lang["clone_error"].format(str(ex)[:200]))

    await status.edit_text(
        _lang["clone_done"].format(ctx.app.username),
        reply_markup=types.InlineKeyboardMarkup([[
            types.InlineKeyboardButton(
                f"@{ctx.app.username}", url=f"https://t.me/{ctx.app.username}"
            )
        ]]),
    )
    if config.CLONE_LOGGER:
        try:
            await registry.main.app.send_message(
                config.CLONE_LOGGER,
                _lang["clone_log"].format(
                    ctx.app.mention, ctx.app.username, ctx.app.id, user.mention, user.id
                ),
            )
        except Exception:
            pass


@app.on_message(filters.command("clone") & ~app.bl_users)
@lang.language()
async def _clone(_, m: types.Message):
    token = m.command[1].strip() if len(m.command) > 1 else None
    if not token:
        return await m.reply_text(m.lang["clone_usage"])

    if m.chat.type != enums.ChatType.PRIVATE:
        # never leave a bot token lying around in a group
        try:
            await m.delete()
        except Exception:
            pass
        return await m.reply_text(m.lang["clone_pm_only"])

    if not await _joined(m.from_user.id):
        PENDING[m.from_user.id] = token
        return await m.reply_text(m.lang["clone_fsub"], reply_markup=_fsub_markup(m.lang))

    await _do_clone(m.reply_text, m.from_user, token, m.lang)
    try:
        await m.delete()
    except Exception:
        pass


@app.on_callback_query(filters.regex("^clone_verify$"))
@lang.language()
async def _clone_verify(_, q: types.CallbackQuery):
    token = PENDING.get(q.from_user.id)
    if not token:
        return await q.answer(q.lang["clone_usage_short"], show_alert=True)
    if not await _joined(q.from_user.id):
        return await q.answer(q.lang["clone_not_joined"], show_alert=True)
    PENDING.pop(q.from_user.id, None)
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass
    await _do_clone(q.message.reply_text, q.from_user, token, q.lang)


@app.on_message(filters.command(["delclone", "rmclone", "delbot", "rmbot", "deleteclone", "removeclone"]))
@lang.language()
async def _delclone(_, m: types.Message):
    mine = await clones.by_owner(m.from_user.id)
    if len(m.command) > 1:
        doc = await clones.find(" ".join(m.command[1:]))
    elif len(mine) == 1:
        doc = mine[0]
    else:
        return await m.reply_text(m.lang["clone_del_usage"])

    if not doc:
        return await m.reply_text(m.lang["clone_not_found"])
    if m.from_user.id not in (doc["owner_id"], OWNER) and m.from_user.id not in app.sudoers:
        return await m.reply_text(m.lang["clone_not_owner"])
    sent = await m.reply_text(m.lang["clone_removing"])
    await clones.drop(doc["bot_id"], reason=f"removed by {m.from_user.id}")
    await sent.edit_text(m.lang["clone_removed"].format(doc.get("username")))


@app.on_message(filters.command(["myclone", "myclones", "mybot", "mybots"]))
@lang.language()
async def _myclone(_, m: types.Message):
    mine = await clones.by_owner(m.from_user.id)
    if not mine:
        return await m.reply_text(m.lang["clone_none"])
    text = m.lang["clone_mine"]
    for i, d in enumerate(mine, 1):
        live = d["bot_id"] in registry.clones
        text += f"\n{i}. @{d.get('username')} · <code>{d['bot_id']}</code> · {'🟢' if live else '🔴'}"
    await m.reply_text(text)


# ---------------------------------------------------------------- sudo tools
@app.on_message(filters.command(["clones", "cloned"]) & app.sudoers)
@lang.language()
async def _clones(_, m: types.Message):
    docs = await clones.all_docs()
    if not docs:
        return await m.reply_text(m.lang["clone_none_total"])
    lines = []
    for i, d in enumerate(docs, 1):
        live = "🟢" if d["bot_id"] in registry.clones else "🔴"
        lines.append(
            f"{i}. {live} @{d.get('username')} | {d['bot_id']} | owner {d['owner_id']} | {d.get('created', '-')}"
        )
    text = "\n".join(lines)
    if len(text) < 3500:
        return await m.reply_text(m.lang["clone_total"].format(len(docs)) + "\n\n<pre>" + text + "</pre>")
    with open("clones.txt", "w") as f:
        f.write(text)
    await m.reply_document("clones.txt", caption=m.lang["clone_total"].format(len(docs)))
    os.remove("clones.txt")


@app.on_message(filters.command(["totalclones", "totalbots"]) & app.sudoers)
@lang.language()
async def _total(_, m: types.Message):
    await m.reply_text(
        m.lang["clone_count"].format(await clones.count(), len(registry.clones))
    )


@app.on_message(filters.command(["cinfo"]) & app.sudoers)
@lang.language()
async def _cinfo(_, m: types.Message):
    if len(m.command) < 2:
        return await m.reply_text(m.lang["clone_del_usage"])
    d = await clones.find(" ".join(m.command[1:]))
    if not d:
        return await m.reply_text(m.lang["clone_not_found"])
    ctx = registry.clones.get(d["bot_id"])
    served = len(await ctx.db.get_chats()) if ctx else 0
    users = len(await ctx.db.get_users()) if ctx else 0
    await m.reply_text(m.lang["clone_info"].format(
        d.get("name"), d.get("username"), d["bot_id"], d["owner_id"],
        d.get("created", "-"), "🟢" if ctx else "🔴",
        "own" if ctx and not ctx.shared_assistants else "shared",
        served, users, len(ctx.db.active_calls) if ctx else 0,
    ))


@app.on_message(filters.command(["cinactive"]) & app.sudoers)
@lang.language()
async def _cinactive(_, m: types.Message):
    docs = [d for d in await clones.all_docs() if d["bot_id"] not in registry.clones]
    if not docs:
        return await m.reply_text(m.lang["clone_all_live"])
    await m.reply_text(m.lang["clone_inactive"].format(len(docs)) + "\n" + "\n".join(
        f"• @{d.get('username')} <code>{d['bot_id']}</code>" for d in docs[:60]))


@app.on_message(filters.command(["delcinactive"]) & filters.user(OWNER))
@lang.language()
async def _delcinactive(_, m: types.Message):
    docs = [d for d in await clones.all_docs() if d["bot_id"] not in registry.clones]
    for d in docs:
        await clones.drop(d["bot_id"], reason="inactive clean-up")
    await m.reply_text(m.lang["clone_cleaned"].format(len(docs)))


@app.on_message(filters.command(["delallclone", "delallclones"]) & filters.user(OWNER))
@lang.language()
async def _delall(_, m: types.Message):
    docs = await clones.all_docs()
    sent = await m.reply_text(m.lang["clone_removing"])
    for d in docs:
        await clones.drop(d["bot_id"], reason="delallclone")
    await sent.edit_text(m.lang["clone_cleaned"].format(len(docs)))
