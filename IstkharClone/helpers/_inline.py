# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
#
# IstkharClone: premium keyboards (random colours + small-caps are applied
# globally by ui.install_button_patch).


from pyrogram import types

from IstkharClone import app, config, db, lang
from IstkharClone.core.context import registry
from IstkharClone.core.lang import lang_codes
from IstkharClone.helpers import _audio
from IstkharClone.ui import tg_link


def _custom(key: str, default: str) -> str:
    ctx = registry.current()
    return tg_link(ctx.custom.get(key), default) if ctx.is_clone else default


class Inline:
    def __init__(self):
        self.ikm = types.InlineKeyboardMarkup
        self.ikb = types.InlineKeyboardButton

    # ------------------------------------------------------------ player
    def cancel_dl(self, text) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, callback_data=f"cancel_dl")]])

    def controls(
        self,
        chat_id: int,
        status: str = None,
        timer: str = None,
        remove: bool = False,
    ) -> types.InlineKeyboardMarkup:
        keyboard = []
        if status:
            keyboard.append(
                [self.ikb(text=status, callback_data=f"controls status {chat_id}")]
            )
        elif timer:
            keyboard.append(
                [self.ikb(text=timer, callback_data=f"controls status {chat_id}")]
            )

        if not remove:
            auto = db.cached(chat_id, "autoplay", False)
            keyboard.append(
                [
                    self.ikb(text="▷", callback_data=f"controls resume {chat_id}"),
                    self.ikb(text="II", callback_data=f"controls pause {chat_id}"),
                    self.ikb(text="⥁", callback_data=f"controls replay {chat_id}"),
                    self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                    self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
                ]
            )
            keyboard.append(
                [
                    self.ikb(text="⏪ 15s", callback_data=f"controls seekb {chat_id}"),
                    self.ikb(text="❄️ EQ", callback_data=f"controls eq {chat_id}"),
                    self.ikb(text="15s ⏩", callback_data=f"controls seekf {chat_id}"),
                ]
            )
            keyboard.append(
                [
                    self.ikb(
                        text=f"Autoplay: {'ON' if auto else 'OFF'}",
                        callback_data=f"controls auto {chat_id}",
                    ),
                    self.ikb(text="🔀", callback_data=f"controls shuffle {chat_id}"),
                ]
            )
        return self.ikm(keyboard)

    # ------------------------------------------------------------ audio fx
    def eq_markup(self, _lang: dict, chat_id: int, current: str, volume: int):
        rows, row = [], []
        for key, (name, _f) in _audio.EQ_PRESETS.items():
            label = f"✅ {name}" if key == current else name
            row.append(self.ikb(text=label, callback_data=f"eq set {chat_id} {key}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([self.ikb(text=f"🔊 Volume · {volume}%", callback_data=f"eq volp {chat_id}")])
        rows.append([self.ikb(text=_lang["close"], callback_data="close")])
        return self.ikm(rows)

    def volume_markup(self, _lang: dict, chat_id: int, volume: int):
        return self.ikm(
            [
                [
                    self.ikb(text="Vol −25", callback_data=f"eq vol {chat_id} down"),
                    self.ikb(text="Vol +25", callback_data=f"eq vol {chat_id} up"),
                ],
                [self.ikb(text=f"Boost +100 · {volume}%", callback_data=f"eq vol {chat_id} boost")],
                [self.ikb(text="Reset · Normal · 100%", callback_data=f"eq vol {chat_id} reset")],
                [self.ikb(text=_lang["back"], callback_data=f"eq panel {chat_id}")],
                [self.ikb(text=_lang["close"], callback_data="close")],
            ]
        )

    def speed_markup(self, chat_id: int, current: float, close_text: str):
        row = [
            self.ikb(
                text=f"✅ {s:g}x" if abs(s - current) < 0.01 else f"{s:g}x",
                callback_data=f"speed {chat_id} {s}",
            )
            for s in _audio.SPEEDS
        ]
        return self.ikm([row[:3], row[3:], [self.ikb(text=close_text, callback_data="close")]])

    # ------------------------------------------------------------ help
    def help_markup(
        self, _lang: dict, back: bool = False
    ) -> types.InlineKeyboardMarkup:
        if back:
            rows = [
                [
                    self.ikb(text=_lang["back"], callback_data="help back"),
                    self.ikb(text=_lang["close"], callback_data="help close"),
                ]
            ]
        else:
            cbs = ["admins", "auth", "blist", "lang", "ping", "play", "queue",
                   "stats", "sudo", "fx", "clone"]
            buttons = [
                self.ikb(text=_lang[f"help_{i}"], callback_data=f"help {cb}")
                for i, cb in enumerate(cbs)
            ]
            rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
            rows.append([self.ikb(text=_lang["close"], callback_data="help close")])

        return self.ikm(rows)

    def lang_markup(self, _lang: str) -> types.InlineKeyboardMarkup:
        langs = lang.get_languages()

        buttons = [
            self.ikb(
                text=f"{name} ({code}) {'✔️' if code == _lang else ''}",
                callback_data=f"lang_change {code}",
            )
            for code, name in langs.items()
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        return self.ikm(rows)

    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, url=_custom("support", config.SUPPORT_CHAT))]])

    def play_queued(
        self, chat_id: int, item_id: str, _text: str
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text, callback_data=f"controls force {chat_id} {item_id}"
                    )
                ]
            ]
        )

    def queue_markup(
        self, chat_id: int, _text: str, playing: bool
    ) -> types.InlineKeyboardMarkup:
        _action = "pause" if playing else "resume"
        return self.ikm(
            [[self.ikb(text=_text, callback_data=f"controls {_action} {chat_id} q")]]
        )

    def settings_markup(
        self, lang: dict, admin_only: bool, cmd_delete: bool, language: str,
        chat_id: int, thumb: bool = True, autoplay: bool = False,
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=lang["play_mode"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=admin_only, callback_data="settings play"),
                ],
                [
                    self.ikb(
                        text=lang["cmd_delete"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=cmd_delete, callback_data="settings delete"),
                ],
                [
                    self.ikb(text=lang["thumb"] + " ➜", callback_data="settings"),
                    self.ikb(text=thumb, callback_data="settings thumb"),
                ],
                [
                    self.ikb(text="Autoplay ➜", callback_data="settings"),
                    self.ikb(text=autoplay, callback_data="settings auto"),
                ],
                [
                    self.ikb(
                        text=lang["language"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=lang_codes[language], callback_data="language"),
                ],
            ]
        )

    # ------------------------------------------------------------ start
    def start_key(
        self, lang: dict, private: bool = False
    ) -> types.InlineKeyboardMarkup:
        rows = [
            [
                self.ikb(
                    text=lang["add_me"],
                    url=f"https://t.me/{app.username}?startgroup=true",
                )
            ],
            [
                self.ikb(text=lang["help"], callback_data="help"),
                self.ikb(text=lang["clone_btn"], callback_data="clone_info"),
            ],
            [
                self.ikb(text=lang["support"], url=_custom("support", config.SUPPORT_CHAT)),
                self.ikb(text=lang["channel"], url=_custom("channel", config.SUPPORT_CHANNEL)),
            ],
        ]
        if private:
            rows += [
                [
                    self.ikb(
                        text=lang["source"],
                        url="https://github.com/AnonymousX1025/AnonXMusic",
                    )
                ]
            ]
        else:
            rows += [[self.ikb(text=lang["language"], callback_data="language")]]
        return self.ikm(rows)

    def clone_info_markup(self, lang: dict) -> types.InlineKeyboardMarkup:
        main = registry.main.app
        return self.ikm(
            [
                [self.ikb(text=lang["clone_btn_go"], url=f"https://t.me/{main.username}?start=clone")],
                [self.ikb(text=lang["back"], callback_data="start_back")],
            ]
        )

    def close(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, callback_data="close")]])

    def yt_key(self, link: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(text="❐", copy_text=link),
                    self.ikb(text="Youtube", url=link),
                ],
            ]
        )
