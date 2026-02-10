from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Tuple

from PIL import Image, ImageDraw


@dataclass
class PetState:
    """Placeholder for your real Pocket-R pet game."""
    room: str = "LIVING"   # GAME / BATH / LIVING / BED
    msg: str = ""
    msg_until: float = 0.0


ROOM_INFO: Dict[str, Tuple[str, str]] = {
    "GAME": ("Game Area", "Play mini-games"),
    "BATH": ("Bathroom", "Clean up"),
    "LIVING": ("Living Room", "Messages / cuddle"),
    "BED": ("Bedroom", "Sleep"),
}


def init(ctx):
    ctx.user.setdefault("pet_game", PetState().__dict__)


def _st(ctx) -> PetState:
    return PetState(**ctx.user.get("pet_game", {}))


def _save(ctx, st: PetState) -> None:
    ctx.user["pet_game"] = st.__dict__


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    """Return True to go back to the OS home."""
    st = _st(ctx)
    now = time.time()

    if "K2" in ev:
        _save(ctx, st)
        return True

    # Room navigation (matches your earlier mapping):
    #   Right=Bathroom, Down=Living, Left=Bedroom, Up=Game
    if "UP" in ev:
        st.room = "GAME"
    if "RIGHT" in ev:
        st.room = "BATH"
    if "DOWN" in ev:
        st.room = "LIVING"
    if "LEFT" in ev:
        st.room = "BED"

    # Interact (use joystick center PRESS, K1 also works as a convenience)
    if "PRESS" in ev or "K1" in ev:
        if st.room == "GAME":
            st.msg = "You played a game!"
        elif st.room == "BATH":
            st.msg = "All clean!"
        elif st.room == "LIVING":
            st.msg = "You checked messages."
        elif st.room == "BED":
            st.msg = "Good night... zzz"
        st.msg_until = now + 1.7

    if st.msg and now >= st.msg_until:
        st.msg = ""

    _save(ctx, st)
    return False


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    st = _st(ctx)

    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)

    title, subtitle = ROOM_INFO.get(st.room, ("Unknown", ""))

    d.text((12, 12), title, font=ctx.font_l, fill=(255, 255, 255))
    d.text((12, 46), subtitle, font=ctx.font_m, fill=(200, 200, 200))

    # Simple "pet" placeholder box
    box = [12, 78, w - 12, h - 54]
    d.rectangle(box, outline=(140, 140, 140), width=2)
    d.text((18, 92), "[Pet sprite goes here]", font=ctx.font_m, fill=(180, 180, 180))

    # Room chooser hint (no permanent footer; just tiny corner text)
    d.text((12, h - 38), "D-pad: switch rooms", font=ctx.font_s, fill=(160, 160, 160))
    d.text((12, h - 22), "PRESS/K1: action   K2: back", font=ctx.font_s, fill=(160, 160, 160))

    if st.msg:
        d.rectangle([12, h - 90, w - 12, h - 58], fill=(0, 0, 0))
        d.rectangle([12, h - 90, w - 12, h - 58], outline=(255, 255, 255), width=2)
        d.text((18, h - 84), st.msg, font=ctx.font_m, fill=(255, 255, 255))

    return img
