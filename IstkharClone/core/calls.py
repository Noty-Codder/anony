# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


from ntgcalls import (ConnectionNotFound, TelegramServerError,
                      RTMPStreamingUnsupported, ConnectionError,
                      TransportParseException)
from pyrogram.errors import (ChatSendMediaForbidden, ChatSendPhotosForbidden,
                             MessageIdInvalid)
from pyrogram.types import InputMediaPhoto, Message
from pytgcalls import PyTgCalls, exceptions, types
from pytgcalls.pytgcalls_session import PyTgCallsSession

from IstkharClone import (app, config, db, lang, logger,
                          queue, thumb, userbot, yt)
from IstkharClone.core.context import registry
from IstkharClone.helpers import Media, Track, buttons
from IstkharClone.helpers import _audio


class TgCall(PyTgCalls):
    """Call engine of ONE bot (main or clone).

    ``self.ctx`` is the BotContext that owns it; assistants may be shared with
    the main bot (``ctx.shared_assistants``) in which case ownership of a chat
    is tracked by ``registry`` so two bots never drive the same chat.
    """

    def __init__(self):
        self.clients = []
        self.ctx = None

    # ------------------------------------------------------------ controls
    async def pause(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=True)
        try:
            return await client.pause(chat_id)
        except (ConnectionNotFound, exceptions.NotInCallError):
            await self.stop(chat_id)

    async def resume(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=False)
        try:
            return await client.resume(chat_id)
        except (ConnectionNotFound, exceptions.NotInCallError):
            await self.stop(chat_id)

    async def stop(self, chat_id: int) -> None:
        client = await db.get_assistant(chat_id)
        queue.clear(chat_id)
        await db.remove_call(chat_id)
        await db.set_loop(chat_id, 0)
        registry.release(chat_id, self.ctx)

        try:
            await client.leave_call(chat_id, close=False)
        except Exception:
            pass

    # ------------------------------------------------------------ helpers
    async def _thumb(self, chat_id: int, media: Media | Track) -> str | None:
        if not config.THUMB_GEN or not await db.get_thumb_on(chat_id):
            return None
        if isinstance(media, Track):
            return await thumb.generate(media)
        return config.DEFAULT_THUMB

    async def _fx_line(self, chat_id: int) -> str:
        preset, volume, speed = await _audio.chat_fx(chat_id)
        bits = []
        if preset != "normal":
            bits.append(f"EQ: {_audio.EQ_PRESETS[preset][0]}")
        if volume != _audio.DEF_VOL:
            bits.append(f"Vol: {volume}%")
        if abs(speed - 1.0) > 0.01:
            bits.append(f"Speed: {speed:g}x")
        return ("\n<b>" + " | ".join(bits) + "</b>") if bits else ""

    async def _say(self, message: Message | None, chat_id: int, text: str) -> None:
        """Edit ``message`` or, when there is none, send a fresh message."""
        try:
            if message:
                await message.edit_text(text)
            else:
                await app.send_message(chat_id=chat_id, text=text)
        except Exception:
            pass

    # ------------------------------------------------------------ playing
    async def play_media(
        self,
        chat_id: int,
        message: Message | None,
        media: Media | Track,
        seek_time: int = 0,
    ) -> None:
        client = await db.get_assistant(chat_id)
        _lang = await lang.get_lang(chat_id)
        _thumb = await self._thumb(chat_id, media)

        if not media.file_path:
            await self._say(message, chat_id, _lang["error_no_file"].format(config.SUPPORT_CHAT))
            return await self.play_next(chat_id)

        speed = await db.get_speed(chat_id)
        play_path = await _audio.render(chat_id, media.file_path, bool(media.video))
        ss = int(seek_time / speed) if play_path != media.file_path else int(seek_time)

        stream = types.MediaStream(
            media_path=play_path,
            audio_parameters=types.AudioQuality.HIGH,
            video_parameters=types.VideoQuality.HD_720p,
            audio_flags=types.MediaStream.Flags.REQUIRED,
            video_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.IGNORE
            ),
            ffmpeg_parameters=f"-ss {ss}" if ss > 1 else None,
        )
        try:
            await client.play(
                chat_id=chat_id,
                stream=stream,
                config=types.GroupCallConfig(auto_start=False),
            )
            registry.claim(chat_id, self.ctx)
            if not seek_time:
                media.time = 1
                await db.add_call(chat_id)
                queue.seen(chat_id, media.id)
                text = _lang["play_media"].format(
                    media.url,
                    media.title,
                    media.duration,
                    media.user,
                ) + await self._fx_line(chat_id)
                keyboard = buttons.controls(chat_id)
                if not message:
                    return
                try:
                    if _thumb:
                        await message.edit_media(
                            media=InputMediaPhoto(
                                media=_thumb,
                                caption=text,
                            ),
                            reply_markup=keyboard,
                        )
                    else:
                        await message.edit_text(text, reply_markup=keyboard)
                except (ChatSendMediaForbidden, ChatSendPhotosForbidden, MessageIdInvalid):
                    if _thumb:
                        sent = await app.send_photo(
                            chat_id=chat_id,
                            photo=_thumb,
                            caption=text,
                            reply_markup=keyboard,
                        )
                    else:
                        sent = await app.send_message(
                            chat_id=chat_id,
                            text=text,
                            reply_markup=keyboard,
                        )
                    media.message_id = sent.id
                for mid in {message.id, media.message_id}:
                    await db.track_msg(chat_id, mid, "play")
        except FileNotFoundError:
            await self._say(message, chat_id, _lang["error_no_file"].format(config.SUPPORT_CHAT))
            await self.play_next(chat_id)
        except exceptions.NoActiveGroupCall:
            await self.stop(chat_id)
            await self._say(message, chat_id, _lang["error_no_call"])
        except exceptions.NoAudioSourceFound:
            await self._say(message, chat_id, _lang["error_no_audio"])
            await self.play_next(chat_id)
        except (ConnectionError, ConnectionNotFound, TelegramServerError,
                TransportParseException, TimeoutError):
            await self.stop(chat_id)
            await self._say(message, chat_id, _lang["error_tg_server"])
        except RTMPStreamingUnsupported:
            await self.stop(chat_id)
            await self._say(message, chat_id, _lang["error_rtmp"])

    async def refresh(self, chat_id: int) -> bool:
        """Re-apply EQ / volume / speed to the running stream, keeping the
        current position (song does not restart from 0)."""
        media = queue.get_current(chat_id)
        if not media or not await db.get_call(chat_id):
            return False
        pos = max(int(media.time), 2)
        paused = not await db.playing(chat_id)
        await self.play_media(chat_id, None, media, seek_time=pos)
        if paused:
            await self.pause(chat_id)
        # show the new EQ / volume / speed on the player card
        try:
            _lang = await lang.get_lang(chat_id)
            text = _lang["play_media"].format(
                media.url, media.title, media.duration, media.user
            ) + await self._fx_line(chat_id)
            keyboard = buttons.controls(chat_id)
            try:
                await app.edit_message_caption(
                    chat_id, media.message_id, text, reply_markup=keyboard
                )
            except Exception:
                await app.edit_message_text(
                    chat_id, media.message_id, text, reply_markup=keyboard
                )
        except Exception:
            pass
        return True

    async def replay(self, chat_id: int) -> None:
        if not await db.get_call(chat_id):
            return

        media = queue.get_current(chat_id)
        _lang = await lang.get_lang(chat_id)
        msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
        media.message_id = msg.id
        await self.play_media(chat_id, msg, media)

    async def _autoplay(self, chat_id: int, previous: Media | Track | None):
        """Next related track when the queue ran dry and autoplay is on."""
        if not previous or not isinstance(previous, Track):
            return None
        if not await db.get_autoplay(chat_id):
            return None
        track = await yt.related(previous, set(queue.history[chat_id]))
        if track:
            track.user = "Autoplay"
            queue.add(chat_id, track)
        return track

    async def play_next(self, chat_id: int) -> None:
        if loop := await db.get_loop(chat_id):
            await db.set_loop(chat_id, loop - 1)
            return await self.replay(chat_id)

        previous = queue.get_current(chat_id)
        media = queue.get_next(chat_id)
        if not media:
            media = await self._autoplay(chat_id, previous)
            if not media:
                return await self.stop(chat_id)
            media = queue.get_current(chat_id)

        try:
            if media.message_id:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=media.message_id,
                    revoke=True,
                )
                media.message_id = 0
        except Exception:
            pass

        _lang = await lang.get_lang(chat_id)
        msg = await app.send_message(chat_id=chat_id, text=_lang["play_next"])
        if not media.file_path:
            media.file_path = await yt.download(media.id, video=media.video)
            if not media.file_path:
                await self.play_next(chat_id)
                return await msg.edit_text(
                    _lang["error_no_file"].format(config.SUPPORT_CHAT)
                )

        media.message_id = msg.id
        await self.play_media(chat_id, msg, media)

    async def ping(self) -> float:
        pings = [client.ping for client in self.clients]
        return round(sum(pings) / len(pings), 2) if pings else 0.0

    # ------------------------------------------------------------ updates
    async def decorators(self, client: PyTgCalls, default=None) -> None:
        owner = default or self.ctx

        @client.on_update()
        async def update_handler(_, update: types.Update) -> None:
            # whichever bot streams in this chat handles the update
            ctx = registry.owner(update.chat_id) or owner
            from IstkharClone.core.context import _current

            token = _current.set(ctx)
            try:
                engine = ctx.anon
                if isinstance(update, types.StreamEnded):
                    if update.stream_type == types.StreamEnded.Type.AUDIO:
                        await engine.play_next(update.chat_id)
                elif isinstance(update, types.ChatUpdate):
                    if update.status in [
                        types.ChatUpdate.Status.KICKED,
                        types.ChatUpdate.Status.LEFT_GROUP,
                        types.ChatUpdate.Status.CLOSED_VOICE_CHAT,
                    ]:
                        await engine.stop(update.chat_id)
            finally:
                _current.reset(token)

    async def boot(self) -> None:
        PyTgCallsSession.notice_displayed = True
        for ub in userbot.clients:
            client = PyTgCalls(ub)
            await client.start()
            self.clients.append(client)
            await self.decorators(client)
        logger.info("PyTgCalls client(s) started.")

    async def boot_own(self, ub) -> None:
        """Start an own PyTgCalls for a clone assistant (clone has its session)."""
        PyTgCallsSession.notice_displayed = True
        client = PyTgCalls(ub)
        await client.start()
        self.clients.append(client)
        await self.decorators(client, self.ctx)

    async def shutdown_own(self) -> None:
        for chat_id in list(self.ctx.db.active_calls):
            try:
                client = await self.ctx.db.get_assistant(chat_id)
                await client.leave_call(chat_id, close=False)
            except Exception:
                pass
        self.clients.clear()
