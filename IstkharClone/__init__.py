# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
#
# IstkharClone: AnonXMusic core + clone system, per-clone databases and the
# premium UI.


import time
import asyncio
import logging
from logging.handlers import RotatingFileHandler

logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s: %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("log.txt", maxBytes=10485760, backupCount=5),
        logging.StreamHandler(),
    ],
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("ntgcalls").setLevel(logging.CRITICAL)
logging.getLogger("pymongo").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pytgcalls").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


__version__ = "4.0.0"

from config import Config

config = Config()
config.check()
tasks = []
boot = time.time()

# --- per-bot proxies -------------------------------------------------------
# app / db / queue / anon / userbot always point at the bot that is handling
# the current update (main bot or one of the clones).
from IstkharClone.core.context import BotContext, Proxy, registry

app = Proxy("app")
db = Proxy("db")
queue = Proxy("queue")
anon = Proxy("anon")
userbot = Proxy("userbot")

from IstkharClone.ui import install_button_patch
install_button_patch()

from IstkharClone.core.bot import Bot
_app = Bot()

from IstkharClone.core.dir import ensure_dirs
ensure_dirs()

from IstkharClone.core.userbot import Userbot
_userbot = Userbot()

from IstkharClone.core.mongo import MongoDB
_db = MongoDB(dbname=config.DB_NAME)

from IstkharClone.core.lang import Language
lang = Language()

from IstkharClone.core.telegram import Telegram
from IstkharClone.core.youtube import YouTube
tg = Telegram()
yt = YouTube()

from IstkharClone.helpers import Queue, Thumbnail
_queue = Queue()
thumb = Thumbnail()

from IstkharClone.core.calls import TgCall
_anon = TgCall()

_main = BotContext(
    key="main",
    client=_app,
    db=_db,
    queue=_queue,
    anon=_anon,
    userbot=_userbot,
    owner_id=config.OWNER_ID,
)
_anon.ctx = _main
registry.main = _main


async def stop() -> None:
    logger.info("Stopping...")
    for task in tasks:
        task.cancel()
        try:
            await task
        except (asyncio.exceptions.CancelledError, Exception):
            pass

    from IstkharClone.core.clones import clones
    await clones.stop_all()

    await _app.exit()
    await _userbot.exit()
    await _db.close()
    await thumb.close()

    logger.info("Stopped.\n")
