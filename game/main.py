# -*- coding: utf-8 -*-
"""
Your real game lives here.

This file is a minimal example that renders a screen and reacts to inputs.
Replace it with your actual game logic + assets.

Required by the launcher:
- render(ctx) -> PIL.Image (240x240)

Optional:
- init(ctx)
- update(ctx, dt, ev)

Inputs in ev:
- "UP","DOWN","LEFT","RIGHT","PRESS","K1","K2","K3" when pressed
- "<NAME>_UP" when released (e.g. "PRESS_UP")
"""
import time
from PIL import Image, ImageDraw

ROOMS = ["GAME", "BED", "LIVING", "BATH"]
ROOM_BG = {
    "GAME": (18, 18, 32),
    "BED": (20, 16, 24),
    "LIVING": (16, 24, 18),
    "BATH": (20, 24, 28),
}

def init(ctx):
    ctx.user["room"] = "LIVING"
    ctx.user["msg"] = "Game folder loaded ✅"
    ctx.user["msg_until"] = time.time() + 2.0

def update(ctx, dt, ev):
    if "UP" in ev: ctx.user["room"] = "GAME"
    if "DOWN" in ev: ctx.user["room"] = "LIVING"
    if "LEFT" in ev: ctx.user["room"] = "BED"
    if "RIGHT" in ev: ctx.user["room"] = "BATH"

    if "PRESS" in ev:
        ctx.user["msg"] = "PRESS!"
        ctx.user["msg_until"] = time.time() + 1.0

    if "K1" in ev:
        ctx.user["msg"] = "K1"
        ctx.user["msg_until"] = time.time() + 1.0
    if "K2" in ev:
        ctx.user["msg"] = "K2"
        ctx.user["msg_until"] = time.time() + 1.0
    if "K3" in ev:
        ctx.user["msg"] = "K3"
        ctx.user["msg_until"] = time.time() + 1.0

def render(ctx):
    room = ctx.user.get("room", "LIVING")
    img = Image.new("RGB", (ctx.disp.width, ctx.disp.height), ROOM_BG[room])
    draw = ImageDraw.Draw(img)

    # top bar
    draw.rectangle((0, 0, ctx.disp.width, 36), fill=(0, 0, 0))
    draw.text((8, 8), f"ROOM: {room}", font=ctx.font_m, fill=(255,255,255))

    # boot/shutdown hold overlay info from launcher
    if ctx.user.get("shutdown_holding"):
        remain = max(0.0, 10.0 - float(ctx.user.get("shutdown_hold_seconds", 0.0)))
        msg = f"HOLD OFF IN {remain:0.0f}"
        draw.rectangle((0, ctx.disp.height-30, ctx.disp.width, ctx.disp.height), fill=(0,0,0))
        draw.text((8, ctx.disp.height-22), msg, font=ctx.font_m, fill=(255,255,255))
    else:
        draw.rectangle((0, ctx.disp.height-30, ctx.disp.width, ctx.disp.height), fill=(0,0,0))
        draw.text((8, ctx.disp.height-22), "K1/K2/K3 + D-PAD. Hold PRESS 10s to power off.",
                  font=ctx.font_s, fill=(255,255,255))

    # message bubble
    if time.time() < float(ctx.user.get("msg_until", 0.0)):
        draw.rounded_rectangle((20, 90, 220, 130), radius=12, fill=(0,0,0), outline=(255,255,255), width=2)
        draw.text((32, 102), str(ctx.user.get("msg","")), font=ctx.font_m, fill=(255,255,255))

    return img
