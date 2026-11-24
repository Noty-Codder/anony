"""Equalizer / volume / speed engine.

Instead of relying on the live stream to understand filter options, the
current file is rendered once through ffmpeg with the chosen preset and played
from there (the song continues from the same timestamp, no restart from 0).
Rendered files are cached in ``cache/fx`` by (file, filter) hash.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

from IstkharClone import db, logger

FX_DIR = Path("cache/fx")

# key -> (label, ffmpeg audio filter)
EQ_PRESETS: dict[str, tuple[str, str]] = {
    "normal":    ("Normal", ""),
    "clear":     ("Clear Audio", "highpass=f=60,equalizer=f=1000:t=q:w=1:g=3,equalizer=f=3500:t=q:w=1:g=4,dynaudnorm=f=200"),
    "dj":        ("DJ Bass", "bass=g=12:f=70:w=0.6,treble=g=4,acompressor=ratio=3,dynaudnorm=f=150"),
    "bass":      ("Bass Boost", "bass=g=9:f=90:w=0.5"),
    "deep":      ("Deep Bass", "bass=g=15:f=55:w=0.7,lowpass=f=12000"),
    "8d":        ("8D Audio", "apulsator=hz=0.09,stereotools=mlev=0.05,bass=g=4"),
    "lofi":      ("Lo-Fi", "highpass=f=200,lowpass=f=3500,acompressor=ratio=4,aecho=0.8:0.85:60:0.25"),
    "vocal":     ("Vocal", "highpass=f=120,equalizer=f=2500:t=q:w=2:g=6,dynaudnorm=f=200"),
    "treble":    ("Treble", "treble=g=10:f=4000"),
    "soft":      ("Soft", "volume=0.8,lowpass=f=8000"),
    "party":     ("Party", "bass=g=8,treble=g=6,extrastereo=m=2.0,dynaudnorm=f=150"),
    "nightcore": ("Nightcore", "asetrate=48000*1.25,aresample=48000,atempo=1.0"),
    "slowed":    ("Slowed + Reverb", "asetrate=48000*0.85,aresample=48000,aecho=0.8:0.88:60:0.4"),
}

SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
MIN_VOL, DEF_VOL, MAX_VOL = 0, 100, 500


def clamp_volume(v: int) -> int:
    return max(MIN_VOL, min(MAX_VOL, int(v)))


def next_volume(cur: int, action: str) -> int:
    if action == "up":
        return clamp_volume(cur + 25)
    if action == "down":
        return clamp_volume(cur - 25)
    if action == "boost":
        return clamp_volume(cur + 100)
    return DEF_VOL


def _atempo(speed: float) -> str:
    # one atempo handles 0.5-2.0; chain for anything outside that
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def build_filter(preset: str, volume: int, speed: float) -> str:
    parts = []
    eq = EQ_PRESETS.get(preset, EQ_PRESETS["normal"])[1]
    if eq:
        parts.append(eq)
    if abs(speed - 1.0) > 0.01:
        parts.append(_atempo(speed))
    if volume != DEF_VOL:
        parts.append(f"volume={volume / 100:.2f}")
        if volume > DEF_VOL:
            parts.append("alimiter=limit=0.95")
    return ",".join(parts)


async def chat_fx(chat_id: int) -> tuple[str, int, float]:
    preset, volume = await db.get_eq(chat_id)
    speed = await db.get_speed(chat_id)
    return preset, volume, speed


async def has_fx(chat_id: int) -> bool:
    preset, volume, speed = await chat_fx(chat_id)
    return bool(build_filter(preset, volume, speed))


async def render(chat_id: int, path: str, video: bool = False) -> str:
    """Return the path to play for ``chat_id`` (original path if no fx)."""
    if not path or path.startswith(("http://", "https://")):
        return path
    preset, volume, speed = await chat_fx(chat_id)
    chain = build_filter(preset, volume, speed)
    if not chain:
        return path
    if not os.path.exists(path):
        return path

    FX_DIR.mkdir(parents=True, exist_ok=True)
    ext = "mp4" if video else "webm"
    key = hashlib.sha1(f"{path}|{chain}|{video}|{speed}".encode()).hexdigest()[:20]
    out = FX_DIR / f"{key}.{ext}"
    if out.exists() and out.stat().st_size > 1024:
        return str(out)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path]
    if video:
        if abs(speed - 1.0) > 0.01:
            cmd += ["-filter:v", f"setpts=PTS/{speed:.4f}", "-c:v", "libx264",
                    "-preset", "ultrafast", "-crf", "28"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-af", chain, "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-vn", "-af", chain, "-c:a", "libopus", "-b:a", "160k"]
    cmd.append(str(out))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, err = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0 or not out.exists():
            logger.warning("fx render failed: %s", (err or b"").decode(errors="ignore")[-300:])
            return path
        return str(out)
    except Exception as ex:  # pragma: no cover
        logger.warning("fx render error: %s", ex)
        return path


def sweep(max_age: int = 6 * 3600) -> int:
    """Delete old rendered files."""
    n = 0
    if not FX_DIR.exists():
        return 0
    now = time.time()
    for f in FX_DIR.iterdir():
        try:
            if now - f.stat().st_mtime > max_age:
                f.unlink()
                n += 1
        except Exception:
            pass
    return n
