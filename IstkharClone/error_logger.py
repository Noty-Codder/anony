"""Central error reporting.

Unhandled handler exceptions, background-task failures and ERROR/CRITICAL log
records are sent (de-duplicated, rate limited) to ``ERROR_LOGGER_ID``.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
import traceback

from IstkharClone import config
from IstkharClone.core.context import registry

_IGNORED = {
    "FloodWait", "SlowmodeWait", "MessageNotModified", "MessageIdInvalid",
    "QueryIdInvalid", "ChatWriteForbidden", "ChannelPrivate", "ChannelInvalid",
    "UserIsBlocked", "InputUserDeactivated", "PeerIdInvalid", "MessageDeleteForbidden",
    "CancelledError", "StopPropagation", "ContinuePropagation",
}
_seen: dict[str, float] = {}
_window: list[float] = []


def _allowed(sig: str) -> bool:
    now = time.time()
    if now - _seen.get(sig, 0) < 60:
        return False
    _window[:] = [t for t in _window if now - t < 60]
    if len(_window) >= 15:
        return False
    _seen[sig] = now
    _window.append(now)
    if len(_seen) > 500:
        _seen.clear()
    return True


async def report(exc: BaseException, where: str = "", bot: str = "", update=None) -> None:
    chat = config.ERROR_LOGGER_ID
    main = registry.main
    if not chat or not main or not getattr(main, "app", None):
        return
    if type(exc).__name__ in _IGNORED:
        return
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    sig = f"{type(exc).__name__}:{tb[-200:]}"
    if not _allowed(sig):
        return
    extra = ""
    if update is not None:
        try:
            who = getattr(getattr(update, "from_user", None), "id", "-")
            cid = getattr(getattr(update, "chat", None) or getattr(getattr(update, "message", None), "chat", None), "id", "-")
            extra = f"\n<b>User:</b> <code>{who}</code> | <b>Chat:</b> <code>{cid}</code>"
        except Exception:
            pass
    text = (
        f"<b>⚠️ Error</b> · <code>{html.escape(bot or 'main')}</code>\n"
        f"<b>Where:</b> <code>{html.escape(where or '-')}</code>{extra}\n"
        f"<b>Type:</b> <code>{html.escape(type(exc).__name__)}</code>\n"
        f"<pre>{html.escape(tb[-2800:])}</pre>"
    )
    try:
        await main.app.send_message(chat, text, quote_wrap=False)
    except Exception:
        pass


class _LogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR or not record.exc_info:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(report(record.exc_info[1], record.name))


def install(loop: asyncio.AbstractEventLoop) -> None:
    logging.getLogger().addHandler(_LogHandler(level=logging.ERROR))

    def _handler(_loop, context):
        exc = context.get("exception")
        if exc is not None:
            _loop.create_task(report(exc, "asyncio: " + str(context.get("message", ""))))

    loop.set_exception_handler(_handler)
