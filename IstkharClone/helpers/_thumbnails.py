# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
#
# IstkharClone: premium "now playing" card (glass panel, colour glow taken
# from the song art, progress bar with knob, player controls).

import asyncio
import colorsys
import os
import random

import aiohttp
from PIL import (Image, ImageChops, ImageDraw, ImageEnhance,
                 ImageFilter, ImageFont, ImageOps)

from IstkharClone import config
from IstkharClone.helpers import Track

W, H = 1280, 720
BRAND = "IstkharClone"
FONT_B = "IstkharClone/helpers/Raleway-Bold.ttf"
FONT_L = "IstkharClone/helpers/Inter-Light.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _accent(img: Image.Image) -> tuple[int, int, int]:
    """Vivid colour taken from the art (random neon if the art is grey)."""
    small = img.convert("RGB").resize((48, 48))
    best, score = None, -1.0
    for r, g, b in small.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        sc = s * v
        if sc > score:
            best, score = (h, s, v), sc
    if not best or score < 0.25:
        h, s, v = random.random(), 0.85, 1.0
    else:
        h, s, v = best
        s, v = max(s, 0.65), max(v, 0.95)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _glow(size, box, radius, color, blur=45, alpha=190) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _fit_text(draw, text, font_path, max_w, start, min_size=36, lines=2):
    """Biggest font (<= start) that fits ``text`` in ``lines`` lines; adds "…" if cut."""
    def wrap(f):
        words, out, cur = text.split(), [], ""
        for w in words:
            t = f"{cur} {w}".strip()
            if draw.textlength(t, font=f) <= max_w:
                cur = t
            else:
                if cur:
                    out.append(cur)
                cur = w
        if cur:
            out.append(cur)
        return out

    for size in range(start, min_size - 1, -2):
        f = _font(font_path, size)
        out = wrap(f)
        if len(out) <= lines:
            return f, out
    f = _font(font_path, min_size)
    out = wrap(f)[:lines]
    last = out[-1]
    while last and draw.textlength(last + "…", font=f) > max_w:
        last = last[:-1]
    out[-1] = last.rstrip() + "…"
    return f, out


def _icons(draw, cx, cy, color, white):
    # previous
    draw.polygon([(cx - 150, cy), (cx - 118, cy - 20), (cx - 118, cy + 20)], fill=white)
    draw.polygon([(cx - 118, cy), (cx - 86, cy - 20), (cx - 86, cy + 20)], fill=white)
    # play / pause button
    draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=color)
    draw.rounded_rectangle((cx - 13, cy - 16, cx - 4, cy + 16), radius=3, fill=(15, 15, 20))
    draw.rounded_rectangle((cx + 4, cy - 16, cx + 13, cy + 16), radius=3, fill=(15, 15, 20))
    # next
    draw.polygon([(cx + 86, cy - 20), (cx + 118, cy), (cx + 86, cy + 20)], fill=white)
    draw.polygon([(cx + 118, cy - 20), (cx + 150, cy), (cx + 118, cy + 20)], fill=white)


def render(temp: str, output: str, song: Track) -> str:
    art = Image.open(temp).convert("RGB")
    color = _accent(art)
    white = (255, 255, 255)
    soft = (205, 208, 220)

    # ---------- background: blurred art + colour wash + vignette
    bg = ImageOps.fit(art, (W, H), method=Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(38))
    bg = ImageEnhance.Brightness(bg).enhance(0.38)
    bg = ImageEnhance.Color(bg).enhance(1.25).convert("RGBA")

    wash = Image.new("RGBA", (W, H), color + (0,))
    grad = Image.linear_gradient("L").rotate(90).resize((W, H))      # left -> right
    wash.putalpha(grad.point(lambda p: int(p * 0.22)))
    bg = Image.alpha_composite(bg, wash)

    vignette = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vignette).ellipse((-260, -200, W + 260, H + 200), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(ImageChops.invert(vignette).point(lambda p: int(p * 0.65)))
    bg = Image.alpha_composite(bg, dark)

    # ---------- album art with colour glow
    box = (80, 130, 80 + 460, 130 + 460)
    bg = Image.alpha_composite(bg, _glow((W, H), box, 46, color, 50, 170))
    cover = _rounded(ImageOps.fit(art, (460, 460), method=Image.LANCZOS), 40)
    bg.alpha_composite(cover, (80, 130))
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(box, radius=40, outline=white + (70,), width=2)
    bg = Image.alpha_composite(bg, ring)

    # ---------- glass panel
    panel = (590, 90, 1210, 630)
    glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glass).rounded_rectangle(panel, radius=44, fill=(255, 255, 255, 26),
                                            outline=(255, 255, 255, 60), width=2)
    bg = Image.alpha_composite(bg, glass)
    draw = ImageDraw.Draw(bg)

    px = panel[0] + 44
    inner_w = panel[2] - panel[0] - 88

    # "now playing" pill
    pill_font = _font(FONT_B, 20)
    label = "NOW PLAYING"
    pw = int(draw.textlength(label, font=pill_font)) + 52
    draw.rounded_rectangle((px, 128, px + pw, 168), radius=20, fill=color)
    draw.ellipse((px + 14, 142, px + 26, 154), fill=(15, 15, 20))
    draw.text((px + 36, 148), label, font=pill_font, fill=(15, 15, 20), anchor="lm")

    # brand
    bf = _font(FONT_B, 22)
    draw.text((panel[2] - 44, 148), BRAND, font=bf, fill=soft, anchor="rm")

    # title (max 2 lines, auto size)
    title = (song.title or "Unknown").strip()
    tf, lines = _fit_text(draw, title, FONT_B, inner_w, 56)
    y = 205
    for line in lines:
        draw.text((px, y), line, font=tf, fill=white)
        y += int(tf.size * 1.22)

    # artist | views
    meta = song.channel_name or "Unknown artist"
    if song.view_count:
        meta += f"  •  {song.view_count}"
    mf = _font(FONT_L, 28)
    draw.text((px, y + 8), meta[:48], font=mf, fill=soft)

    # progress bar
    bar_y = 436
    x0, x1 = px, px + inner_w
    draw.rounded_rectangle((x0, bar_y - 5, x1, bar_y + 5), radius=5, fill=(78, 80, 96))
    knob = x0 + int(inner_w * 0.045)
    draw.rounded_rectangle((x0, bar_y - 5, knob, bar_y + 5), radius=5, fill=color)
    draw.ellipse((knob - 13, bar_y - 13, knob + 13, bar_y + 13), fill=white)
    draw.ellipse((knob - 6, bar_y - 6, knob + 6, bar_y + 6), fill=color)

    tfnt = _font(FONT_L, 24)
    draw.text((x0, bar_y + 26), "0:01", font=tfnt, fill=soft)
    draw.text((x1, bar_y + 26), str(song.duration or "--:--"), font=tfnt, fill=soft, anchor="ra")

    # controls
    _icons(draw, (x0 + x1) // 2, 545, color, white)

    bg.convert("RGB").save(output, quality=95)
    return output


class Thumbnail:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    async def save_thumb(self, output_path: str, url: str) -> str:
        async with self.session.get(url) as resp:
            with open(output_path, "wb") as f:
                f.write(await resp.read())
        return output_path

    async def generate(self, song: Track, size=(1280, 720)) -> str:
        try:
            temp = f"cache/temp_{song.id}.jpg"
            output = f"cache/{song.id}_v2.png"
            if os.path.exists(output):
                return output

            await self.save_thumb(temp, song.thumbnail)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, render, temp, output, song)
            try:
                os.remove(temp)
            except Exception:
                pass
            return output
        except Exception:
            return config.DEFAULT_THUMB
