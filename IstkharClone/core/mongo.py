# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


from random import randint
from time import time

from pymongo import AsyncMongoClient

from IstkharClone import config, logger, userbot


class MongoDB:
    def __init__(self, dbname: str = "IstkharClone", mongo: AsyncMongoClient | None = None):
        """
        Initialize the MongoDB connection.

        Every bot (main + each clone) gets its *own* database inside the same
        cluster, so clone data never merges with the main bot or another clone.
        """
        self.owns_client = mongo is None
        self.mongo = mongo or AsyncMongoClient(config.MONGO_URL, serverSelectionTimeoutMS=12500)
        self.dbname = dbname
        self.db = self.mongo[dbname]

        self.admin_list = {}
        self.active_calls = {}
        self.admin_play = []
        self.blacklisted = []
        self.cmd_delete = []
        self.loop = {}
        self.notified = []
        self.cache = self.db.cache
        self.logger = True          # play logger is ON by default

        self.assistant = {}
        self.assistantdb = self.db.assistant

        self.auth = {}
        self.authdb = self.db.auth

        self.chats = []
        self.chatsdb = self.db.chats

        self.lang = {}
        self.langdb = self.db.lang

        self.users = []
        self.usersdb = self.db.users

        # premium per-chat settings (autoplay, thumbnail, equalizer, ...)
        self.settingsdb = self.db.settings
        # messages that must be auto-deleted later (player cards, broadcasts)
        self.trackdb = self.db.tracked_messages
        self._settings: dict[int, dict] = {}

        # bans: in the main DB these are global (gban), in a clone DB they only
        # apply to that clone
        self.bans: set[int] = set()
        self.maintenance = False

    async def connect(self) -> None:
        """Check if we can connect to the database.

        Raises:
            SystemExit: If the connection to the database fails.
        """
        try:
            start = time()
            await self.mongo.admin.command("ping")
            logger.info(f"Database connection successful. ({time() - start:.2f}s)")
            await self.load_cache()
        except Exception as e:
            raise SystemExit(f"Database connection failed: {type(e).__name__}") from e

    async def close(self) -> None:
        """Close the connection to the database."""
        if not self.owns_client:
            return
        await self.mongo.close()
        logger.info("Database connection closed.")

    async def connect_clone(self) -> None:
        """Light start-up for a clone database (client is shared)."""
        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(True)
        await self.get_logger()
        await self.load_bans()

    # CACHE
    async def get_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_call(self, chat_id: int) -> None:
        self.active_calls[chat_id] = 1

    async def remove_call(self, chat_id: int) -> None:
        self.active_calls.pop(chat_id, None)

    async def playing(self, chat_id: int, paused: bool = None) -> bool | None:
        if paused is not None:
            self.active_calls[chat_id] = int(not paused)
        return bool(self.active_calls.get(chat_id, 0))

    async def get_admins(self, chat_id: int, reload: bool = False) -> list[int]:
        from IstkharClone.helpers._admins import reload_admins

        if chat_id not in self.admin_list or reload:
            self.admin_list[chat_id] = await reload_admins(chat_id)
        return self.admin_list[chat_id]

    async def get_loop(self, chat_id: int) -> int:
        return self.loop.get(chat_id, 0)

    async def set_loop(self, chat_id: int, count: int) -> None:
        self.loop[chat_id] = count

    # AUTH METHODS
    async def _get_auth(self, chat_id: int) -> set[int]:
        if chat_id not in self.auth:
            doc = await self.authdb.find_one({"_id": chat_id}) or {}
            self.auth[chat_id] = set(doc.get("user_ids", []))
        return self.auth[chat_id]

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._get_auth(chat_id)

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id not in users:
            users.add(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$addToSet": {"user_ids": user_id}}, upsert=True
            )

    async def rm_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id in users:
            users.discard(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$pull": {"user_ids": user_id}}
            )

    # ASSISTANT METHODS
    async def set_assistant(self, chat_id: int) -> int:
        num = randint(1, len(userbot.clients))
        await self.assistantdb.update_one(
            {"_id": chat_id},
            {"$set": {"num": num}},
            upsert=True,
        )
        self.assistant[chat_id] = num
        return num

    async def get_assistant(self, chat_id: int):
        from IstkharClone import anon

        if chat_id not in self.assistant:
            doc = await self.assistantdb.find_one({"_id": chat_id})
            num = doc["num"] if doc else None

            if not num or num > len(anon.clients):
                num = await self.set_assistant(chat_id)
            self.assistant[chat_id] = num

        return anon.clients[self.assistant[chat_id] - 1]

    async def get_client(self, chat_id: int):
        if chat_id not in self.assistant:
            await self.get_assistant(chat_id)

        num = self.assistant[chat_id]
        if num > len(userbot.clients):
            num = await self.set_assistant(chat_id)
            self.assistant[chat_id] = num

        return userbot.clients[num - 1]

    # BLACKLIST METHODS
    async def add_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.append(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"},
                {"$addToSet": {"chat_ids": chat_id}},
                upsert=True,
            )
        await self.cache.update_one(
            {"_id": "bl_users"},
            {"$addToSet": {"user_ids": chat_id}},
            upsert=True,
        )

    async def del_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.remove(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"},
                {"$pull": {"chat_ids": chat_id}},
            )
        await self.cache.update_one(
            {"_id": "bl_users"},
            {"$pull": {"user_ids": chat_id}},
        )

    async def get_blacklisted(self, chat: bool = False) -> list[int]:
        if chat:
            if not self.blacklisted:
                doc = await self.cache.find_one({"_id": "bl_chats"})
                self.blacklisted.extend(doc.get("chat_ids", []) if doc else [])
            return self.blacklisted
        doc = await self.cache.find_one({"_id": "bl_users"})
        return doc.get("user_ids", []) if doc else []

    # CHAT METHODS
    async def is_chat(self, chat_id: int) -> bool:
        return chat_id in self.chats

    async def add_chat(self, chat_id: int) -> None:
        if not await self.is_chat(chat_id):
            self.chats.append(chat_id)
            await self.chatsdb.insert_one({"_id": chat_id})

    async def rm_chat(self, chat_id: int) -> None:
        if await self.is_chat(chat_id):
            self.chats.remove(chat_id)
            await self.chatsdb.delete_one({"_id": chat_id})

    async def get_chats(self) -> list:
        if not self.chats:
            self.chats.extend([chat["_id"] async for chat in self.chatsdb.find()])
        return self.chats

    # COMMAND DELETE
    async def get_cmd_delete(self, chat_id: int) -> bool:
        if chat_id not in self.cmd_delete:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("cmd_delete"):
                self.cmd_delete.append(chat_id)
        return chat_id in self.cmd_delete

    async def set_cmd_delete(self, chat_id: int, delete: bool = False) -> None:
        if delete:
            self.cmd_delete.append(chat_id)
        else:
            self.cmd_delete.remove(chat_id)
        await self.chatsdb.update_one(
            {"_id": chat_id},
            {"$set": {"cmd_delete": delete}},
            upsert=True,
        )

    # LANGUAGE METHODS
    async def set_lang(self, chat_id: int, lang_code: str):
        await self.langdb.update_one(
            {"_id": chat_id},
            {"$set": {"lang": lang_code}},
            upsert=True,
        )
        self.lang[chat_id] = lang_code

    async def get_lang(self, chat_id: int) -> str:
        if chat_id not in self.lang:
            doc = await self.langdb.find_one({"_id": chat_id})
            self.lang[chat_id] = doc["lang"] if doc else config.LANG_CODE
        return self.lang[chat_id]

    # LOGGER METHODS
    async def is_logger(self) -> bool:
        return self.logger

    async def get_logger(self) -> bool:
        doc = await self.cache.find_one({"_id": "logger"})
        if doc:
            self.logger = doc["status"]
        return self.logger

    async def set_logger(self, status: bool) -> None:
        self.logger = status
        await self.cache.update_one(
            {"_id": "logger"},
            {"$set": {"status": status}},
            upsert=True,
        )

    # PLAY MODE METHODS
    async def get_play_mode(self, chat_id: int) -> bool:
        if chat_id not in self.admin_play:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("admin_play"):
                self.admin_play.append(chat_id)
        return chat_id in self.admin_play

    async def set_play_mode(self, chat_id: int, remove: bool = False) -> None:
        if remove and chat_id in self.admin_play:
            self.admin_play.remove(chat_id)
        else:
            self.admin_play.append(chat_id)
        await self.chatsdb.update_one(
            {"_id": chat_id},
            {"$set": {"admin_play": not remove}},
            upsert=True,
        )

    # SUDO METHODS
    async def add_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$pull": {"user_ids": user_id}}
        )

    async def get_sudoers(self) -> list[int]:
        doc = await self.cache.find_one({"_id": "sudoers"})
        return doc.get("user_ids", []) if doc else []

    # USER METHODS
    async def is_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def add_user(self, user_id: int) -> None:
        if not await self.is_user(user_id):
            self.users.append(user_id)
            await self.usersdb.insert_one({"_id": user_id})

    async def rm_user(self, user_id: int) -> None:
        if await self.is_user(user_id):
            self.users.remove(user_id)
            await self.usersdb.delete_one({"_id": user_id})

    async def get_users(self) -> list:
        if not self.users:
            self.users.extend([user["_id"] async for user in self.usersdb.find()])
        return self.users


    # PER-CHAT SETTINGS (autoplay, thumbnail, equalizer, speed ...)
    async def get_setting(self, chat_id: int, key: str, default=None):
        if chat_id not in self._settings:
            doc = await self.settingsdb.find_one({"_id": chat_id}) or {}
            doc.pop("_id", None)
            self._settings[chat_id] = doc
        return self._settings[chat_id].get(key, default)

    async def set_setting(self, chat_id: int, key: str, value) -> None:
        await self.get_setting(chat_id, key)
        self._settings[chat_id][key] = value
        await self.settingsdb.update_one(
            {"_id": chat_id}, {"$set": {key: value}}, upsert=True
        )

    def cached(self, chat_id: int, key: str, default=None):
        """Sync read of an already loaded per-chat setting (for keyboards)."""
        return self._settings.get(chat_id, {}).get(key, default)

    async def get_autoplay(self, chat_id: int) -> bool:
        return bool(await self.get_setting(chat_id, "autoplay", False))

    async def set_autoplay(self, chat_id: int, on: bool) -> None:
        await self.set_setting(chat_id, "autoplay", bool(on))

    async def get_thumb_on(self, chat_id: int) -> bool:
        return bool(await self.get_setting(chat_id, "thumb", True))

    async def set_thumb_on(self, chat_id: int, on: bool) -> None:
        await self.set_setting(chat_id, "thumb", bool(on))

    async def get_eq(self, chat_id: int) -> tuple[str, int]:
        return (
            await self.get_setting(chat_id, "eq", "normal"),
            int(await self.get_setting(chat_id, "volume", 100)),
        )

    async def set_eq(self, chat_id: int, preset: str | None = None, volume: int | None = None) -> None:
        if preset is not None:
            await self.set_setting(chat_id, "eq", preset)
        if volume is not None:
            await self.set_setting(chat_id, "volume", int(volume))

    async def get_speed(self, chat_id: int) -> float:
        return float(await self.get_setting(chat_id, "speed", 1.0))

    async def set_speed(self, chat_id: int, speed: float) -> None:
        await self.set_setting(chat_id, "speed", float(speed))

    # BANS (gban in main DB, clone-gban in a clone DB) + MAINTENANCE
    async def load_bans(self) -> None:
        doc = await self.cache.find_one({"_id": "bans"})
        self.bans = set(doc.get("user_ids", [])) if doc else set()
        doc = await self.cache.find_one({"_id": "maintenance"})
        self.maintenance = bool(doc and doc.get("status"))

    async def add_ban(self, user_id: int) -> None:
        self.bans.add(user_id)
        await self.cache.update_one(
            {"_id": "bans"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_ban(self, user_id: int) -> None:
        self.bans.discard(user_id)
        await self.cache.update_one({"_id": "bans"}, {"$pull": {"user_ids": user_id}})

    # AUTO-DELETE TRACKING (player cards 24h, broadcasts 48h)
    async def track_msg(self, chat_id: int, message_id: int, kind: str = "play") -> None:
        if not chat_id or not message_id:
            return
        try:
            await self.trackdb.update_one(
                {"chat_id": int(chat_id), "message_id": int(message_id)},
                {"$set": {"kind": kind, "ts": int(time())}},
                upsert=True,
            )
        except Exception as ex:
            logger.warning(f"track_msg failed: {ex}")

    async def expired_msgs(self, kind: str, ttl: int, limit: int = 300) -> list[dict]:
        cutoff = int(time()) - ttl
        return await self.trackdb.find(
            {"kind": kind, "ts": {"$lt": cutoff}}
        ).to_list(length=limit)

    async def forget_msg(self, doc_id) -> None:
        await self.trackdb.delete_one({"_id": doc_id})

    async def set_maintenance(self, status: bool) -> None:
        self.maintenance = status
        await self.cache.update_one(
            {"_id": "maintenance"}, {"$set": {"status": status}}, upsert=True
        )

    async def migrate_coll(self) -> None:
        logger.info("Migrating users and chats from old collections...")

        users, musers, mchats = [], [], []
        seen_chats, seen_users = set(), set()
        users.extend([user async for user in self.usersdb.find()])
        users.extend([user async for user in self.db.tgusersdb.find()])

        for user in users:
            _id = user.get("_id")
            if isinstance(_id, int):
                user_id = _id
            else:
                user_id = int(user.get("user_id"))

            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            musers.append({"_id": user_id})

        await self.usersdb.drop()
        await self.db.tgusersdb.drop()
        if musers:
            await self.usersdb.insert_many(musers)

        async for chat in self.chatsdb.find():
            _id = chat.get("_id")
            if isinstance(_id, int):
                chat_id = _id
            else:
                chat_id = int(chat.get("chat_id"))

            if chat_id in seen_chats:
                continue
            seen_chats.add(chat_id)
            mchats.append({"_id": chat_id})

        await self.chatsdb.drop()
        if mchats:
            await self.chatsdb.insert_many(mchats)

        await self.cache.insert_one({"_id": "migrated"})
        logger.info("Migration completed successfully.")

    async def load_cache(self) -> None:
        doc = await self.cache.find_one({"_id": "migrated"})
        if not doc:
            await self.migrate_coll()

        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(True)
        await self.load_bans()
        logger.info("Database cache loaded.")
