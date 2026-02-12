from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter

from ..persistence import ensure_data_dir, read_json, write_json_atomic
from ..ui_common import clamp, overlay_panel, wrap_text


ROOM_HUB = "HUB"
ROOM_BED = "BEDROOM"
ROOM_LIVING = "LIVING"
ROOM_ARCADE = "ARCADE"
ROOM_BATH = "BATHROOM"

MODE_ONBOARD_1 = "ONBOARD_1"
MODE_ONBOARD_2 = "ONBOARD_2"
MODE_PLAY = "PLAY"
PLAY_WORLD = "PLAY_WORLD"
PLAY_PANEL = "PLAY_PANEL"
PLAY_MINIGAME = "PLAY_MINIGAME"
BRICK_MAX_LEVELS = 3

STATE_REL_PATH = "pet/state.json"
DIALOGUE_REL_PATH = "pet/dialogue.json"

ONBOARD_WELCOME = "intro_welcome.png"
ONBOARD_CONTROLS = "intro_controls.png"

AGE_ACCEL = 60.0  # 1 real minute = 1 pet hour
K2_RECALL_SECONDS = 1.2
B3_SHORT_MAX_SECONDS = 0.85
PERSIST_SECONDS = 4.0


ROOMS: Dict[str, Dict] = {
    ROOM_HUB: {
        "name": "Main Hall",
        "slug": "hub",
        "neighbors": {"LEFT": ROOM_ARCADE, "RIGHT": ROOM_BED, "UP": ROOM_BATH, "DOWN": ROOM_LIVING},
        "actions": ["Check In", "Stretch", "Save & Quit"],
        "color": (42, 24, 20),
    },
    ROOM_BED: {
        "name": "Bedroom",
        "slug": "bedroom",
        "neighbors": {"LEFT": ROOM_HUB},
        "actions": ["Cuddle", "Give Hug", "Sleep"],
        "color": (54, 24, 40),
    },
    ROOM_LIVING: {
        "name": "Living Room",
        "slug": "living",
        "neighbors": {"UP": ROOM_HUB},
        "actions": ["Watch TV", "Lounge", "Talk", "Open Gallery"],
        "color": (24, 36, 44),
    },
    ROOM_ARCADE: {
        "name": "Arcade",
        "slug": "arcade",
        "neighbors": {"RIGHT": ROOM_HUB},
        "actions": ["Brick Breaker", "Memory Match", "Runner Dash"],
        "color": (26, 24, 50),
    },
    ROOM_BATH: {
        "name": "Bathroom",
        "slug": "bathroom",
        "neighbors": {"DOWN": ROOM_HUB},
        "actions": ["Use Toilet", "Shower"],
        "color": (18, 42, 46),
    },
}


ROOM_OBJECTS: Dict[str, List[str]] = {
    "hub": ["obj_sign.png"],
    "bedroom": ["obj_bed.png", "obj_pillow.png"],
    "living": ["obj_couch.png", "obj_tv.png", "obj_table.png"],
    "bathroom": ["obj_shower.png", "obj_toilet.png", "obj_sink.png"],
    "arcade": ["obj_cabinet.png", "obj_console.png"],
}


OBJECT_LAYOUT: Dict[str, Dict[str, Tuple[int, int, int, int, Tuple[int, int, int]]]] = {
    "hub": {
        "obj_sign.png": (88, 130, 64, 34, (180, 122, 92)),
    },
    "bedroom": {
        "obj_bed.png": (22, 134, 140, 66, (154, 84, 98)),
        "obj_pillow.png": (128, 112, 58, 34, (224, 190, 200)),
    },
    "living": {
        "obj_couch.png": (22, 150, 128, 56, (106, 86, 120)),
        "obj_tv.png": (152, 106, 62, 48, (86, 100, 126)),
        "obj_table.png": (128, 168, 84, 28, (162, 114, 86)),
    },
    "bathroom": {
        "obj_shower.png": (18, 92, 64, 116, (94, 148, 162)),
        "obj_toilet.png": (136, 142, 72, 56, (204, 210, 220)),
        "obj_sink.png": (94, 108, 46, 42, (186, 196, 210)),
    },
    "arcade": {
        "obj_cabinet.png": (24, 100, 64, 98, (132, 88, 170)),
        "obj_console.png": (116, 128, 102, 70, (90, 94, 146)),
    },
}


STAT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "health": (255, 116, 116),
    "hunger": (255, 192, 102),
    "energy": (148, 208, 255),
    "hygiene": (170, 240, 200),
    "social": (255, 164, 230),
    "fun": (186, 170, 255),
    "bladder": (214, 194, 136),
    "mood": (255, 230, 136),
}


SPRITE_FILES = {
    "idle": "idle.png",
    "walk1": "walk1.png",
    "walk2": "walk2.png",
    "sleep": "sleep.png",
    "shower": "shower.png",
    "toilet": "toilet.png",
}


@dataclass
class PetState:
    mode: str = MODE_ONBOARD_1
    seen_tutorial: bool = False

    room: str = ROOM_HUB
    x: float = 120.0
    y: float = 164.0

    health: float = 96.0
    hunger: float = 82.0
    energy: float = 86.0
    hygiene: float = 78.0
    social: float = 72.0
    fun: float = 72.0
    bladder: float = 68.0
    mood: float = 84.0

    alive: bool = True
    death_reason: str = ""
    age_seconds: float = 0.0

    panel_open: bool = False
    panel_kind: str = "ACTIONS"
    panel_sel: int = 0
    talk_index: int = 0
    play_submode: str = PLAY_WORLD
    minigame_name: str = ""
    minigame_state: Dict = field(default_factory=dict)

    msg: str = ""
    msg_until: float = 0.0

    walk_phase: float = 0.0
    pose: str = "idle"
    pose_until: float = 0.0
    blur_until: float = 0.0

    last_tick: float = 0.0
    last_persist: float = 0.0

    k2_hold_t0: float = 0.0
    k2_long_triggered: bool = False

    k3_hold_t0: float = 0.0
    k3_long_triggered: bool = False


def _state_fields() -> set:
    return set(PetState.__dataclass_fields__.keys())


def _st_from_dict(data: Dict) -> PetState:
    if not isinstance(data, dict):
        return PetState()
    fields = _state_fields()
    cleaned = {k: data[k] for k in fields if k in data}
    try:
        return PetState(**cleaned)
    except Exception:
        return PetState()


def _to_dict(st: PetState) -> Dict:
    return {k: getattr(st, k) for k in _state_fields()}


def _asset_path(ctx, name: str) -> str:
    return ctx.asset("pet_game", name)


def _data_dialogue_path(ctx) -> str:
    if hasattr(ctx, "data_path"):
        return ctx.data_path(DIALOGUE_REL_PATH)
    base = str(getattr(ctx, "base_dir", ".") or ".")
    return os.path.join(base, ".pocketr", DIALOGUE_REL_PATH)


def _persist_state(ctx, st: PetState, force: bool = False) -> None:
    now = time.time()
    if (not force) and (now - float(st.last_persist) < PERSIST_SECONDS):
        return
    st.last_persist = now
    try:
        write_json_atomic(ctx, STATE_REL_PATH, _to_dict(st))
    except Exception:
        pass


def _pet_defaults() -> Dict:
    return {
        "sim_speed": 1.0,
        "difficulty_profile": "normal",
        "decay_hunger_mult": 1.0,
        "decay_energy_mult": 1.0,
        "decay_hygiene_mult": 1.0,
        "decay_social_mult": 1.0,
        "decay_fun_mult": 1.0,
        "decay_bladder_mult": 1.0,
        "hp_loss_mult": 1.0,
        "hp_regen_mult": 1.0,
        "brick_speed_mult": 1.0,
        "memory_reveal_seconds": 1.1,
        "runner_speed_mult": 1.0,
        "show_tutorial_next_open": False,
    }


def _pet_cfg(ctx) -> Dict:
    prefs = ctx.user.get("_prefs", {}) if isinstance(ctx.user.get("_prefs"), dict) else {}
    pg = prefs.get("pet_game", {}) if isinstance(prefs.get("pet_game"), dict) else {}
    cfg = _pet_defaults()
    for k in cfg:
        if k in pg:
            cfg[k] = pg[k]

    try:
        cfg["sim_speed"] = float(clamp(float(cfg.get("sim_speed", 1.0)), 0.5, 2.0))
    except Exception:
        cfg["sim_speed"] = 1.0

    prof = str(cfg.get("difficulty_profile", "normal") or "normal").strip().lower()
    if prof not in ("easy", "normal", "hard", "custom"):
        prof = "normal"
    cfg["difficulty_profile"] = prof

    for k in (
        "decay_hunger_mult",
        "decay_energy_mult",
        "decay_hygiene_mult",
        "decay_social_mult",
        "decay_fun_mult",
        "decay_bladder_mult",
        "hp_loss_mult",
        "hp_regen_mult",
        "brick_speed_mult",
        "runner_speed_mult",
    ):
        try:
            cfg[k] = float(clamp(float(cfg.get(k, 1.0)), 0.5, 2.0))
        except Exception:
            cfg[k] = 1.0

    try:
        cfg["memory_reveal_seconds"] = float(clamp(float(cfg.get("memory_reveal_seconds", 1.1)), 0.3, 3.0))
    except Exception:
        cfg["memory_reveal_seconds"] = 1.1

    cfg["show_tutorial_next_open"] = bool(cfg.get("show_tutorial_next_open", False))
    return cfg


def _consume_tutorial_flag(ctx) -> bool:
    prefs = ctx.user.get("_prefs", {})
    if not isinstance(prefs, dict):
        return False
    pg = prefs.get("pet_game", {})
    if not isinstance(pg, dict):
        return False
    if not bool(pg.get("show_tutorial_next_open", False)):
        return False

    pg["show_tutorial_next_open"] = False
    prefs["pet_game"] = pg
    ctx.user["_prefs"] = prefs
    try:
        write_json_atomic(ctx, "settings.json", prefs)
    except Exception:
        pass
    return True


def _overlay_font(ctx):
    return getattr(ctx, "font_s", None)


def _meta_font(ctx):
    return getattr(ctx, "font_s", None)


def init(ctx):
    ensure_data_dir(ctx)
    now = time.time()
    cfg = _pet_cfg(ctx)

    raw = read_json(ctx, STATE_REL_PATH, {})
    st = _st_from_dict(raw)

    # First time only intro. After first completion, open straight into gameplay.
    force_tutorial = _consume_tutorial_flag(ctx) or bool(cfg.get("show_tutorial_next_open", False))
    st.mode = MODE_ONBOARD_1 if (force_tutorial or not st.seen_tutorial) else MODE_PLAY
    st.panel_open = False
    st.panel_kind = "ACTIONS"
    st.panel_sel = 0
    st.play_submode = PLAY_WORLD
    st.minigame_name = ""
    st.minigame_state = {}
    st.msg = ""
    st.msg_until = 0.0

    st.k2_hold_t0 = 0.0
    st.k2_long_triggered = False
    st.k3_hold_t0 = 0.0
    st.k3_long_triggered = False

    st.last_tick = now

    w, h = int(ctx.disp.width), int(ctx.disp.height)
    st.x = float(clamp(st.x, 12.0, float(w - 12)))
    st.y = float(clamp(st.y, 92.0, float(h - 14)))

    ctx.user["pet_game_v3"] = _to_dict(st)


def _st(ctx) -> PetState:
    raw = ctx.user.get("pet_game_v3", {})
    st = _st_from_dict(raw)
    if st.last_tick <= 0.0:
        st.last_tick = time.time()
    return st


def _save(ctx, st: PetState, force_persist: bool = False) -> None:
    ctx.user["pet_game_v3"] = _to_dict(st)
    _persist_state(ctx, st, force=force_persist)


def _placeholder_sprite(size: int, label: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (16, 14, 20, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, size - 2, size - 2], radius=max(5, size // 7), fill=(56, 38, 42, 255), outline=(255, 215, 205, 210), width=2)
    d.ellipse([size // 4, size // 6, size - size // 4, size - size // 3], fill=(255, 210, 175, 255), outline=(36, 18, 10, 220), width=2)
    d.text((6, size - 14), label.upper(), fill=(255, 244, 240, 230))
    return img


def _load_sprites(ctx, px: int) -> Dict[str, Image.Image]:
    mtags: List[str] = []
    for k, fname in SPRITE_FILES.items():
        p = _asset_path(ctx, fname)
        try:
            mtags.append(f"{k}:{int(os.path.getmtime(p))}")
        except Exception:
            mtags.append(f"{k}:0")

    key = f"{px}|" + "|".join(mtags)
    cache = ctx.user.get("_pet_sprite_cache", None)
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("data"), dict):
        return cache["data"]

    sprites: Dict[str, Image.Image] = {}
    for k, fname in SPRITE_FILES.items():
        p = _asset_path(ctx, fname)
        try:
            sp = Image.open(p).convert("RGBA")
            if sp.size != (px, px):
                sp = sp.resize((px, px))
            sprites[k] = sp
        except Exception:
            sprites[k] = _placeholder_sprite(px, k)

    ctx.user["_pet_sprite_cache"] = {"key": key, "data": sprites}
    return sprites


def _dialogue_data(ctx) -> Dict[str, List[Dict]]:
    data_path = _data_dialogue_path(ctx)
    fallback_path = _asset_path(ctx, "dialogue.json")

    try:
        data_mtime = int(os.path.getmtime(data_path))
    except Exception:
        data_mtime = -1

    try:
        fallback_mtime = int(os.path.getmtime(fallback_path))
    except Exception:
        fallback_mtime = -1

    key = f"{data_path}:{data_mtime}|{fallback_path}:{fallback_mtime}"
    cache = ctx.user.get("_pet_dialogue_cache", {})
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("data"), dict):
        return cache["data"]

    data: Dict[str, List[Dict]] = {}
    source = data_path if os.path.isfile(data_path) else fallback_path

    try:
        with open(source, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if not isinstance(v, list):
                    continue
                cleaned: List[Dict] = []
                for item in v:
                    if isinstance(item, dict):
                        cleaned.append(item)
                if cleaned:
                    data[str(k)] = cleaned
    except Exception:
        data = {}

    if not data:
        data = {
            "greeting": [{"player": "Hey buddy!", "pet": "Hey! Good to see you.", "social": 3, "fun": 2}],
            "feelings": [{"player": "How are you?", "pet": "Better when we hang out.", "social": 2, "fun": 1}],
        }

    ctx.user["_pet_dialogue_cache"] = {"key": key, "data": data}
    return data


def _set_pose(st: PetState, pose: str, seconds: float, now: float) -> None:
    st.pose = pose
    st.pose_until = now + max(0.0, float(seconds))


def _make_message(st: PetState, text: str, now: float, seconds: float = 2.4) -> None:
    st.msg = str(text)
    st.msg_until = now + max(0.8, float(seconds))


def _enter_room(st: PetState, room: str, side: str, w: int, h: int, now: float) -> None:
    st.room = room
    top_bound = 88.0
    bottom_bound = float(h - 12)

    if side == "LEFT":
        st.x = float(w - 14)
    elif side == "RIGHT":
        st.x = 14.0
    elif side == "UP":
        st.y = float(bottom_bound - 4)
    elif side == "DOWN":
        st.y = float(top_bound + 4)

    _make_message(st, f"Entered {ROOMS.get(room, {}).get('name', room)}", now, seconds=1.2)


def _apply_movement(ctx, st: PetState, dt: float, now: float) -> bool:
    if dt <= 0.0:
        return False

    if now < float(st.pose_until):
        return False

    mx = (1 if ctx.inputs.is_down("RIGHT") else 0) - (1 if ctx.inputs.is_down("LEFT") else 0)
    my = (1 if ctx.inputs.is_down("DOWN") else 0) - (1 if ctx.inputs.is_down("UP") else 0)

    if mx == 0 and my == 0:
        return False

    mlen = math.sqrt(float(mx * mx + my * my))
    if mlen > 0:
        mx = float(mx) / mlen
        my = float(my) / mlen

    speed = 84.0
    st.x += mx * speed * dt
    st.y += my * speed * dt
    st.walk_phase += dt * 8.0

    w, h = int(ctx.disp.width), int(ctx.disp.height)
    top_bound = 88.0
    bottom_bound = float(h - 12)
    edge = 12.0

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    neigh = room_info.get("neighbors", {})

    if st.x < -edge:
        nxt = neigh.get("LEFT")
        if nxt:
            _enter_room(st, str(nxt), "LEFT", w, h, now)
        else:
            st.x = 8.0
    elif st.x > float(w + edge):
        nxt = neigh.get("RIGHT")
        if nxt:
            _enter_room(st, str(nxt), "RIGHT", w, h, now)
        else:
            st.x = float(w - 8)

    if st.y < (top_bound - edge):
        nxt = neigh.get("UP")
        if nxt:
            _enter_room(st, str(nxt), "UP", w, h, now)
        else:
            st.y = top_bound + 2
    elif st.y > (bottom_bound + edge):
        nxt = neigh.get("DOWN")
        if nxt:
            _enter_room(st, str(nxt), "DOWN", w, h, now)
        else:
            st.y = bottom_bound - 2

    return True


def _base_drain_per_hour(cfg: Dict) -> Dict[str, float]:
    profile = str(cfg.get("difficulty_profile", "normal"))
    profile_decay = 1.0
    if profile == "easy":
        profile_decay = 0.85
    elif profile == "hard":
        profile_decay = 1.20

    return {
        "hunger": 5.0,
        "energy": 4.2,
        "hygiene": 2.4,
        "social": 2.0,
        "fun": 2.2,
        "bladder": 4.6,
        "profile_decay": profile_decay,
    }


def _apply_decay(st: PetState, dt: float, moving: bool, now: float, cfg: Dict) -> None:
    if not st.alive:
        return
    if dt <= 0.0:
        return

    st.age_seconds += dt * AGE_ACCEL

    profile = str(cfg.get("difficulty_profile", "normal") or "normal")
    drains = _base_drain_per_hour(cfg)
    profile_decay = float(drains.get("profile_decay", 1.0))
    mul = 1.35 if moving else 1.0

    hunger_drop = (drains["hunger"] * mul * profile_decay * float(cfg.get("decay_hunger_mult", 1.0))) * (dt / 3600.0)
    energy_drop = (drains["energy"] * mul * profile_decay * float(cfg.get("decay_energy_mult", 1.0))) * (dt / 3600.0)
    hygiene_drop = (drains["hygiene"] * profile_decay * float(cfg.get("decay_hygiene_mult", 1.0))) * (dt / 3600.0)
    social_drop = (drains["social"] * profile_decay * float(cfg.get("decay_social_mult", 1.0))) * (dt / 3600.0)
    fun_drop = (drains["fun"] * profile_decay * float(cfg.get("decay_fun_mult", 1.0))) * (dt / 3600.0)
    bladder_drop = (drains["bladder"] * mul * profile_decay * float(cfg.get("decay_bladder_mult", 1.0))) * (dt / 3600.0)

    sleeping = st.pose == "sleep" and now < st.pose_until
    if sleeping:
        energy_drop -= 7.5 * (dt / 3600.0)
        bladder_drop += 1.1 * (dt / 3600.0)
        hunger_drop += 0.8 * (dt / 3600.0)

    st.hunger = clamp(st.hunger - hunger_drop, 0.0, 100.0)
    st.energy = clamp(st.energy - energy_drop, 0.0, 100.0)
    st.hygiene = clamp(st.hygiene - hygiene_drop, 0.0, 100.0)
    st.social = clamp(st.social - social_drop, 0.0, 100.0)
    st.fun = clamp(st.fun - fun_drop, 0.0, 100.0)
    st.bladder = clamp(st.bladder - bladder_drop, 0.0, 100.0)

    def _def(v: float, thresh: float) -> float:
        if v >= thresh:
            return 0.0
        return clamp((thresh - v) / max(1e-6, thresh), 0.0, 1.0)

    stress = 0.0
    stress += 0.26 * _def(st.hunger, 30.0)
    stress += 0.24 * _def(st.energy, 28.0)
    stress += 0.18 * _def(st.hygiene, 26.0)
    stress += 0.22 * _def(st.bladder, 24.0)
    stress += 0.05 * _def(st.social, 22.0)
    stress += 0.05 * _def(st.fun, 22.0)

    critical_count = sum(1 for v in [st.hunger, st.energy, st.hygiene, st.bladder] if v < 15.0)

    hp_loss_hour = 0.0
    if stress > 0.18:
        hp_loss_hour += (stress - 0.18) * 4.2
    if critical_count >= 2:
        hp_loss_hour += (critical_count - 1) * 2.2
    if critical_count >= 3:
        hp_loss_hour += 1.5

    hp_regen_hour = 0.0
    core_min = min(st.hunger, st.energy, st.hygiene, st.bladder)
    if core_min > 55.0 and st.mood > 58.0:
        hp_regen_hour = 1.0
    elif core_min > 40.0:
        hp_regen_hour = 0.35

    profile_loss = 1.0
    profile_regen = 1.0
    if profile == "easy":
        profile_loss = 0.75
        profile_regen = 1.15
    elif profile == "hard":
        profile_loss = 1.25
        profile_regen = 0.90

    hp_loss_hour *= profile_loss * float(cfg.get("hp_loss_mult", 1.0))
    hp_regen_hour *= profile_regen * float(cfg.get("hp_regen_mult", 1.0))
    st.health = clamp(st.health + ((hp_regen_hour - hp_loss_hour) * (dt / 3600.0)), 0.0, 100.0)

    mood_target = (
        (st.health * 0.28)
        + (st.fun * 0.20)
        + (st.social * 0.17)
        + (st.energy * 0.12)
        + (st.hunger * 0.09)
        + (st.hygiene * 0.07)
        + (st.bladder * 0.07)
    )
    lerp = clamp(dt * 2.0, 0.0, 1.0)
    st.mood = clamp(st.mood + ((mood_target - st.mood) * lerp), 0.0, 100.0)

    if st.health <= 0.0:
        st.alive = False
        st.panel_open = False
        st.pose = "idle"
        lowest = {
            "hunger": st.hunger,
            "energy": st.energy,
            "hygiene": st.hygiene,
            "social": st.social,
            "fun": st.fun,
            "bladder": st.bladder,
        }
        reason = min(lowest, key=lowest.get)
        st.death_reason = reason
        _make_message(st, f"Your pet passed away from low {reason}. Press B1 to restart.", now, 8.0)


def _boost(st: PetState, **kwargs: float) -> None:
    for k, delta in kwargs.items():
        if not hasattr(st, k):
            continue
        cur = float(getattr(st, k))
        setattr(st, k, float(clamp(cur + float(delta), 0.0, 100.0)))


def _run_action(st: PetState, action: str, now: float) -> str:
    if action == "Check In":
        _boost(st, social=3, mood=2, fun=1)
        return "Quick check-in. Calm and steady."

    if action == "Stretch":
        _boost(st, energy=2, mood=1, fun=1)
        return "Short stretch done."

    if action == "Cuddle":
        _boost(st, social=8, mood=6, energy=-2, fun=3)
        return "Cuddle time. Feels safer."

    if action == "Give Hug":
        _boost(st, social=7, mood=5, fun=2, energy=-1)
        return "Big hug delivered."

    if action == "Sleep":
        _boost(st, energy=14, mood=4, hunger=-3, bladder=-5)
        _set_pose(st, "sleep", 2.8, now)
        return "Nap started. Energy rising."

    if action == "Watch TV":
        _boost(st, fun=7, social=1, energy=-2, hunger=-1)
        return "TV time. Mood up."

    if action == "Lounge":
        _boost(st, energy=6, mood=3, fun=2, bladder=-2)
        return "Lounge break complete."

    if action in ("Runner Dash", "Memory Match", "Brick Breaker"):
        return "Launching mini-game..."

    if action == "Use Toilet":
        _boost(st, bladder=38, hygiene=-3, mood=1)
        st.blur_until = now + 1.8
        _set_pose(st, "toilet", 1.8, now)
        return "Woah look away. Privacy moment."

    if action == "Shower":
        _boost(st, hygiene=34, mood=5, energy=-3)
        _set_pose(st, "shower", 1.9, now)
        return "Fresh and clean."

    return "Nothing happened."


def _panel_items(st: PetState, dialogue: Dict[str, List[Dict]]) -> List[str]:
    if st.panel_kind == "TALK":
        cats = sorted(list(dialogue.keys()))
        return cats or ["greeting"]

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    actions = room_info.get("actions", [])
    if isinstance(actions, list):
        return [str(a) for a in actions]
    return []


def _talk_once(st: PetState, dialogue: Dict[str, List[Dict]], category: str) -> str:
    entries = dialogue.get(category, [])
    if not entries:
        _boost(st, social=2, mood=1)
        return "You talked for a while."

    idx = st.talk_index % len(entries)
    st.talk_index += 1
    line = entries[idx]

    user_line = str(line.get("player", "Hi"))
    pet_line = str(line.get("pet", "Hey"))
    social_gain = float(line.get("social", 3))
    fun_gain = float(line.get("fun", 2))

    _boost(st, social=social_gain, fun=fun_gain, mood=2)
    return f"You: {user_line} | Pet: {pet_line}"


def _handle_short_long(st: PetState, now: float, ev: Dict[str, bool], inputs, key: str, hold_attr: str, long_attr: str, long_seconds: float) -> str:
    key_up = f"{key}_UP"

    if key in ev:
        setattr(st, hold_attr, now)
        setattr(st, long_attr, False)

    t0 = float(getattr(st, hold_attr, 0.0) or 0.0)
    long_triggered = bool(getattr(st, long_attr, False))
    if t0 > 0.0 and inputs.is_down(key) and (not long_triggered):
        if (now - t0) >= long_seconds:
            setattr(st, long_attr, True)
            return "LONG"

    if key_up in ev:
        t0 = float(getattr(st, hold_attr, 0.0) or 0.0)
        was_tracking = (t0 > 0.0) or bool(getattr(st, long_attr, False))
        if not was_tracking:
            setattr(st, hold_attr, 0.0)
            setattr(st, long_attr, False)
            return "NONE"
        was_long = bool(getattr(st, long_attr, False)) or (t0 > 0.0 and (now - t0) >= long_seconds)
        setattr(st, hold_attr, 0.0)
        setattr(st, long_attr, False)
        return "LONG" if was_long else "SHORT"

    return "NONE"


def _quick_support(st: PetState, now: float) -> None:
    lines = [
        "You gave a quick pep talk.",
        "A little encouragement helped.",
        "He smiles. That helped.",
        "Quick check-in: feeling better.",
    ]
    _boost(st, mood=1.5, social=1.0)
    _make_message(st, random.choice(lines), now, 1.5)


def _quick_care(st: PetState, now: float) -> None:
    if st.hunger < 50:
        _boost(st, hunger=4, mood=1)
        _make_message(st, "Quick snack delivered.", now, 1.6)
        return
    if st.energy < 50:
        _boost(st, energy=4, mood=1)
        _make_message(st, "Short rest helped.", now, 1.6)
        return
    if st.hygiene < 45:
        _boost(st, hygiene=5, mood=1)
        _make_message(st, "Quick tidy-up done.", now, 1.6)
        return
    if st.social < 45 or st.fun < 45:
        _boost(st, social=3, fun=3, mood=1)
        _make_message(st, "Quick play break.", now, 1.6)
        return

    _boost(st, mood=2, health=0.3)
    _make_message(st, "Quick care done.", now, 1.5)


def _brick_layout(w: int, level: int) -> List[Dict]:
    cols = 6
    rows = max(1, min(3, int(level)))
    gap_x = 4
    gap_y = 4
    bw = max(16, (w - 28 - ((cols - 1) * gap_x)) // cols)
    bh = 10
    start_x = 14
    start_y = 72
    bricks: List[Dict] = []

    for r in range(rows):
        x = start_x
        for _c in range(cols):
            hp = 2 if (rows >= 3 and r == 0) else 1
            bricks.append({
                "x": x,
                "y": start_y + (r * (bh + gap_y)),
                "w": bw,
                "h": bh,
                "alive": True,
                "hp": hp,
            })
            x += bw + gap_x
    return bricks


def _brick_reset_ball(mg: Dict, w: int, h: int, level: int) -> None:
    base_speed = float(mg.get("base_speed", 88.0))
    speed = base_speed * (1.0 + (max(1, int(level)) - 1) * 0.16)
    x_dir = -1.0 if random.random() < 0.5 else 1.0
    mg["paddle_x"] = float(w // 2)
    mg["ball_x"] = float(w // 2)
    mg["ball_y"] = float(h - 52)
    mg["ball_vx"] = speed * 0.88 * x_dir
    mg["ball_vy"] = -speed


def _start_minigame(ctx, st: PetState, name: str, cfg: Dict, now: float) -> None:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    st.play_submode = PLAY_MINIGAME
    st.minigame_name = str(name)
    st.panel_open = False
    st.panel_kind = "ACTIONS"
    st.panel_sel = 0

    if name == "Brick Breaker":
        speed = 88.0 * float(cfg.get("brick_speed_mult", 1.0))
        st.minigame_state = {
            "base_speed": speed,
            "level": 1,
            "max_levels": BRICK_MAX_LEVELS,
            "bricks": _brick_layout(w, 1),
            "score": 0.0,
            "elapsed": 0.0,
            "level_up_to": 0,
        }
        _brick_reset_ball(st.minigame_state, w, h, 1)
    elif name == "Memory Match":
        cards = [0, 1, 2, 0, 1, 2]
        random.shuffle(cards)
        st.minigame_state = {
            "cards": cards,
            "matched": [False] * 6,
            "revealed": [],
            "cursor": 0,
            "pending_until": 0.0,
            "moves": 0,
            "elapsed": 0.0,
        }
    else:  # Runner Dash
        st.minigame_state = {
            "player_y": float(h - 42),
            "vy": 0.0,
            "on_ground": True,
            "obstacles": [],
            "spawn_in": 0.9,
            "elapsed": 0.0,
            "score": 0.0,
        }

    if name == "Brick Breaker":
        _make_message(st, f"{name} started. Level 1/{BRICK_MAX_LEVELS}.", now, 1.8)
    else:
        _make_message(st, f"{name} started. B2 to exit.", now, 1.6)


def _finish_minigame(st: PetState, name: str, win: bool, score: float, now: float) -> None:
    # Reward loop: mood/fun-centric, minor fatigue/hunger cost.
    if win:
        _boost(st, fun=8.0, mood=6.0, energy=-2.5, hunger=-1.8, bladder=-1.2)
        _make_message(st, f"{name}: win! +fun +mood", now, 2.2)
    else:
        _boost(st, fun=3.0, mood=1.5, energy=-2.0, hunger=-1.2, bladder=-0.8)
        _make_message(st, f"{name}: done ({int(score)} pts).", now, 2.0)
    st.play_submode = PLAY_WORLD
    st.minigame_name = ""
    st.minigame_state = {}


def _update_brick_breaker(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict) -> Tuple[bool, bool, float]:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    paddle_w = 42
    paddle_h = 6
    paddle_y = h - 20
    paddle_speed = 120.0
    if ctx.inputs.is_down("LEFT"):
        mg["paddle_x"] = float(mg.get("paddle_x", w / 2)) - (paddle_speed * dt)
    if ctx.inputs.is_down("RIGHT"):
        mg["paddle_x"] = float(mg.get("paddle_x", w / 2)) + (paddle_speed * dt)
    mg["paddle_x"] = float(clamp(float(mg.get("paddle_x", w / 2)), 10 + paddle_w / 2, w - 10 - paddle_w / 2))

    mg["ball_x"] = float(mg.get("ball_x", w / 2)) + (float(mg.get("ball_vx", 80.0)) * dt)
    mg["ball_y"] = float(mg.get("ball_y", h / 2)) + (float(mg.get("ball_vy", -80.0)) * dt)
    mg["elapsed"] = float(mg.get("elapsed", 0.0)) + dt
    mg["score"] = float(mg.get("score", 0.0)) + (dt * 5.0)

    bx = float(mg.get("ball_x", w / 2))
    by = float(mg.get("ball_y", h / 2))
    bvx = float(mg.get("ball_vx", 80.0))
    bvy = float(mg.get("ball_vy", -80.0))

    if bx < 10:
        bx = 10
        bvx = abs(bvx)
    elif bx > w - 10:
        bx = w - 10
        bvx = -abs(bvx)
    if by < 64:
        by = 64
        bvy = abs(bvy)

    px0 = float(mg.get("paddle_x", w / 2)) - (paddle_w / 2)
    px1 = px0 + paddle_w
    if (paddle_y - 4) <= by <= (paddle_y + paddle_h) and px0 <= bx <= px1 and bvy > 0:
        bvy = -abs(bvy)
        offs = (bx - (px0 + paddle_w / 2)) / max(1.0, paddle_w / 2)
        bvx += offs * 38.0

    bricks = mg.get("bricks", [])
    alive_count = 0
    for b in bricks:
        if not b.get("alive", False):
            continue
        alive_count += 1
        bx0 = float(b.get("x", 0))
        by0 = float(b.get("y", 0))
        bw = float(b.get("w", 20))
        bh = float(b.get("h", 10))
        if (bx0 - 3) <= bx <= (bx0 + bw + 3) and (by0 - 3) <= by <= (by0 + bh + 3):
            hp = int(b.get("hp", 1))
            if hp > 1:
                b["hp"] = hp - 1
                mg["score"] = float(mg.get("score", 0.0)) + 4.0
            else:
                b["alive"] = False
                alive_count -= 1
                mg["score"] = float(mg.get("score", 0.0)) + 10.0
            bvy = -bvy
            break

    mg["ball_x"] = bx
    mg["ball_y"] = by
    mg["ball_vx"] = bvx
    mg["ball_vy"] = bvy

    if alive_count <= 0:
        level = int(mg.get("level", 1))
        max_levels = int(mg.get("max_levels", BRICK_MAX_LEVELS))
        if level < max_levels:
            level += 1
            mg["level"] = level
            mg["bricks"] = _brick_layout(w, level)
            mg["level_up_to"] = level
            mg["score"] = float(mg.get("score", 0.0)) + (16.0 * level)
            _brick_reset_ball(mg, w, h, level)
            return False, False, float(mg.get("score", 0.0))
        return True, True, float(mg.get("score", 0.0))
    if by > (h - 6):
        return True, False, float(mg.get("score", 0.0))
    return False, False, float(mg.get("score", 0.0))


def _update_memory_match(st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict, now: float) -> Tuple[bool, bool, float]:
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0
    mg["elapsed"] = float(mg.get("elapsed", 0.0)) + dt

    cards = list(mg.get("cards", []))
    if len(cards) != 6:
        return True, False, 0.0
    matched = list(mg.get("matched", [False] * 6))
    revealed = list(mg.get("revealed", []))
    cursor = int(mg.get("cursor", 0))
    pending_until = float(mg.get("pending_until", 0.0))

    if pending_until > 0.0 and now >= pending_until:
        revealed = []
        pending_until = 0.0

    if pending_until <= 0.0:
        c = cursor
        if "LEFT" in ev:
            c = c - 1 if (c % 3) > 0 else c + 2
        if "RIGHT" in ev:
            c = c + 1 if (c % 3) < 2 else c - 2
        if "UP" in ev:
            c = (c - 3) % 6
        if "DOWN" in ev:
            c = (c + 3) % 6
        cursor = c

        if ("K1" in ev) or ("PRESS" in ev):
            if (not matched[cursor]) and (cursor not in revealed):
                revealed.append(cursor)
                if len(revealed) == 2:
                    mg["moves"] = int(mg.get("moves", 0)) + 1
                    a, b = revealed[0], revealed[1]
                    if cards[a] == cards[b]:
                        matched[a] = True
                        matched[b] = True
                        revealed = []
                    else:
                        pending_until = now + float(cfg.get("memory_reveal_seconds", 1.1))

    mg["cursor"] = cursor
    mg["revealed"] = revealed
    mg["matched"] = matched
    mg["pending_until"] = pending_until

    if all(bool(x) for x in matched):
        moves = int(mg.get("moves", 0))
        score = max(5, 30 - (moves * 2))
        return True, True, float(score)
    return False, False, float(max(0, 20 - int(mg.get("moves", 0))))


def _update_runner_dash(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict) -> Tuple[bool, bool, float]:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    ground_y = h - 42
    player_x = 34
    player_w = 12
    player_h = 16
    grav = 330.0
    jump_v = -145.0

    if (("K1" in ev) or ("PRESS" in ev)) and bool(mg.get("on_ground", True)):
        mg["vy"] = jump_v
        mg["on_ground"] = False

    vy = float(mg.get("vy", 0.0)) + (grav * dt)
    py = float(mg.get("player_y", ground_y)) + (vy * dt)
    if py >= ground_y:
        py = float(ground_y)
        vy = 0.0
        mg["on_ground"] = True

    elapsed = float(mg.get("elapsed", 0.0)) + dt
    speed = (86.0 + min(42.0, elapsed * 3.4)) * float(cfg.get("runner_speed_mult", 1.0))
    obs = list(mg.get("obstacles", []))
    for o in obs:
        o["x"] = float(o.get("x", w)) - (speed * dt)
    obs = [o for o in obs if float(o.get("x", -20.0)) > -24.0]

    spawn_in = float(mg.get("spawn_in", 0.8)) - dt
    if spawn_in <= 0.0:
        oh = random.randint(10, 22)
        ow = random.randint(10, 18)
        obs.append({"x": float(w + 10), "w": float(ow), "h": float(oh)})
        spawn_in = random.uniform(0.85, 1.45)

    player_top = py - player_h
    collided = False
    for o in obs:
        ox = float(o.get("x", w))
        ow = float(o.get("w", 12))
        oh = float(o.get("h", 14))
        otop = ground_y - oh
        if (player_x < ox + ow) and (player_x + player_w > ox) and (player_top < ground_y) and ((py) > otop):
            collided = True
            break

    score = float(mg.get("score", 0.0)) + (dt * (8.0 + (speed * 0.03)))
    mg["player_y"] = py
    mg["vy"] = vy
    mg["obstacles"] = obs
    mg["spawn_in"] = spawn_in
    mg["elapsed"] = elapsed
    mg["score"] = score

    if collided:
        return True, False, score
    if elapsed >= 20.0:
        return True, True, score
    return False, False, score


def _update_minigame(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict, now: float) -> bool:
    if st.play_submode != PLAY_MINIGAME:
        return False
    name = str(st.minigame_name or "")
    if not name:
        st.play_submode = PLAY_WORLD
        st.minigame_state = {}
        return False

    if "K2" in ev:
        _finish_minigame(st, name, False, float(st.minigame_state.get("score", 0.0)) if isinstance(st.minigame_state, dict) else 0.0, now)
        return True

    if name == "Brick Breaker":
        done, win, score = _update_brick_breaker(ctx, st, dt, ev, cfg)
    elif name == "Memory Match":
        done, win, score = _update_memory_match(st, dt, ev, cfg, now)
    else:
        done, win, score = _update_runner_dash(ctx, st, dt, ev, cfg)

    if name == "Brick Breaker" and isinstance(st.minigame_state, dict):
        new_level = int(st.minigame_state.pop("level_up_to", 0) or 0)
        if new_level > 0:
            max_levels = int(st.minigame_state.get("max_levels", BRICK_MAX_LEVELS))
            _make_message(st, f"Brick Breaker Level {new_level}/{max_levels}", now, 1.4)

    if done:
        _finish_minigame(st, name, win, score, now)
        return True
    return True


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    st = _st(ctx)
    now = time.time()
    cfg = _pet_cfg(ctx)

    # Strict frame-based progression while app is active only.
    sim_dt = max(0.0, min(float(dt), 0.25)) * float(cfg.get("sim_speed", 1.0))
    st.last_tick = now

    if st.msg and now >= float(st.msg_until):
        st.msg = ""

    if now >= float(st.pose_until):
        st.pose = "idle"

    k2_evt = _handle_short_long(st, now, ev, ctx.inputs, "K2", "k2_hold_t0", "k2_long_triggered", K2_RECALL_SECONDS)
    b3_evt = _handle_short_long(st, now, ev, ctx.inputs, "K3", "k3_hold_t0", "k3_long_triggered", B3_SHORT_MAX_SECONDS)

    if k2_evt == "LONG":
        st.mode = MODE_ONBOARD_1
        st.panel_open = False
        st.panel_kind = "ACTIONS"
        st.panel_sel = 0
        st.play_submode = PLAY_WORLD
        st.minigame_name = ""
        st.minigame_state = {}
        _make_message(st, "Tutorial reopened.", now, 1.4)
        _save(ctx, st, force_persist=True)
        return False

    intro_confirm = ("K1" in ev) or ("PRESS" in ev)

    if st.mode == MODE_ONBOARD_1:
        if intro_confirm:
            st.mode = MODE_ONBOARD_2
        elif k2_evt == "SHORT":
            _save(ctx, st, force_persist=True)
            return True
        _save(ctx, st)
        return False

    if st.mode == MODE_ONBOARD_2:
        if intro_confirm:
            st.mode = MODE_PLAY
            st.seen_tutorial = True
            st.last_tick = now
            st.play_submode = PLAY_WORLD
            _make_message(st, "Welcome to PocketR pet life.", now, 1.8)
            _save(ctx, st, force_persist=True)
            return False
        elif k2_evt == "SHORT":
            _save(ctx, st, force_persist=True)
            return True
        _save(ctx, st)
        return False

    # MODE_PLAY
    if st.play_submode == PLAY_MINIGAME:
        _update_minigame(ctx, st, sim_dt, ev, cfg, now)
        _save(ctx, st)
        return False

    if k2_evt == "SHORT":
        if st.panel_open:
            st.panel_open = False
            st.panel_kind = "ACTIONS"
            st.panel_sel = 0
            st.play_submode = PLAY_WORLD
        else:
            _quick_support(st, now)

    # B3 short quick care action (global hold-B3 shutdown still handled by launcher).
    if b3_evt == "SHORT" and st.alive:
        _quick_care(st, now)

    opened_panel_now = False
    # B1 and joystick PRESS both open the actions panel.
    if (("PRESS" in ev) or ("K1" in ev)) and st.alive and (not st.panel_open) and st.play_submode == PLAY_WORLD:
        st.panel_open = True
        st.panel_kind = "ACTIONS"
        st.panel_sel = 0
        st.play_submode = PLAY_PANEL
        opened_panel_now = True

    if not st.alive:
        if "K1" in ev:
            keep_age = st.age_seconds
            st = PetState(mode=MODE_PLAY, seen_tutorial=True, age_seconds=keep_age, last_tick=now)
            st.play_submode = PLAY_WORLD
            _make_message(st, "A new buddy joined you.", now, 2.0)
            _save(ctx, st, force_persist=True)
            return False
        _save(ctx, st)
        return False

    moving = False
    if not st.panel_open and st.play_submode == PLAY_WORLD:
        moving = _apply_movement(ctx, st, sim_dt, now)

    _apply_decay(st, sim_dt, moving=moving, now=now, cfg=cfg)

    dialogue = _dialogue_data(ctx)

    if st.panel_open:
        items = _panel_items(st, dialogue)
        if items:
            st.panel_sel = int(clamp(float(st.panel_sel), 0.0, float(len(items) - 1)))

        if "UP" in ev and items:
            st.panel_sel = (st.panel_sel - 1) % len(items)
        if "DOWN" in ev and items:
            st.panel_sel = (st.panel_sel + 1) % len(items)

        # B1 confirm only.
        if ("K1" in ev) and items and (not opened_panel_now):
            chosen = items[st.panel_sel]

            if st.panel_kind == "ACTIONS" and chosen == "Talk":
                st.panel_kind = "TALK"
                st.panel_sel = 0
            elif st.panel_kind == "ACTIONS" and chosen == "Save & Quit":
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
                _save(ctx, st, force_persist=True)
                return True
            elif st.panel_kind == "ACTIONS" and chosen == "Open Gallery":
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
                _make_message(st, "Opening Gallery...", now, 1.2)
                ctx.user["_app_switch_to"] = 1
                _save(ctx, st, force_persist=True)
                return False
            elif st.panel_kind == "ACTIONS" and chosen in ("Brick Breaker", "Memory Match", "Runner Dash"):
                _start_minigame(ctx, st, chosen, cfg, now)
            elif st.panel_kind == "TALK":
                msg = _talk_once(st, dialogue, chosen)
                _make_message(st, msg, now, 3.0)
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
            else:
                msg = _run_action(st, chosen, now)
                _make_message(st, msg, now, 2.4)
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD

    _save(ctx, st)
    return False


def _room_base_fallback(size: Tuple[int, int], room: str) -> Image.Image:
    w, h = size
    base = Image.new("RGBA", (w, h), (12, 10, 10, 255))
    d = ImageDraw.Draw(base)

    room_info = ROOMS.get(room, ROOMS[ROOM_HUB])
    r, g, b = room_info.get("color", (32, 24, 24))

    for y in range(h):
        t = y / float(max(1, h - 1))
        rr = int(10 + (r * (0.45 + 0.55 * (1.0 - t))))
        gg = int(6 + (g * (0.42 + 0.58 * (1.0 - t))))
        bb = int(8 + (b * (0.40 + 0.60 * (1.0 - t))))
        d.line([0, y, w, y], fill=(rr, gg, bb, 255), width=1)

    d.rounded_rectangle([4, 82, w - 5, h - 5], radius=7, outline=(255, 220, 210, 80), width=2)
    name = room_info.get("name", room)
    d.text((8, 90), f"[{name} base placeholder]", fill=(245, 232, 226, 180))
    return base


def _object_fallback(size: Tuple[int, int], room_slug: str, fname: str) -> Image.Image:
    _w, _h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    cfg = OBJECT_LAYOUT.get(room_slug, {}).get(fname)
    if cfg:
        x, y, bw, bh, color = cfg
    else:
        x, y, bw, bh, color = (80, 120, 80, 40, (120, 88, 88))

    d.rounded_rectangle([x, y, x + bw, y + bh], radius=6, fill=(color[0], color[1], color[2], 180), outline=(255, 222, 210, 180), width=2)
    label = fname.replace("obj_", "").replace(".png", "")
    d.text((x + 6, y + max(4, (bh // 2) - 6)), label, fill=(255, 248, 240, 220))
    return layer


def _load_layered_room(ctx, room: str, size: Tuple[int, int]) -> Image.Image:
    w, h = size
    room_info = ROOMS.get(room, ROOMS[ROOM_HUB])
    slug = str(room_info.get("slug", "hub"))

    base_path = ctx.asset("pet_game", "rooms", slug, "base.png")
    obj_files = ROOM_OBJECTS.get(slug, [])
    obj_paths = [ctx.asset("pet_game", "rooms", slug, f) for f in obj_files]

    tags: List[str] = [f"{room}:{w}x{h}"]
    for p in [base_path] + obj_paths:
        try:
            tags.append(f"{p}:{int(os.path.getmtime(p))}")
        except Exception:
            tags.append(f"{p}:0")

    key = "|".join(tags)
    cache = ctx.user.get("_pet_room_cache", {})
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("img"), Image.Image):
        return cache["img"].copy()

    if os.path.isfile(base_path):
        try:
            base = Image.open(base_path).convert("RGBA")
            if base.size != (w, h):
                base = base.resize((w, h))
        except Exception:
            base = _room_base_fallback((w, h), room)
    else:
        base = _room_base_fallback((w, h), room)

    out = base.copy().convert("RGBA")

    for fname, p in zip(obj_files, obj_paths):
        if os.path.isfile(p):
            try:
                layer = Image.open(p).convert("RGBA")
                if layer.size != (w, h):
                    layer = layer.resize((w, h))
            except Exception:
                layer = _object_fallback((w, h), slug, fname)
        else:
            layer = _object_fallback((w, h), slug, fname)
        out = Image.alpha_composite(out, layer)

    ctx.user["_pet_room_cache"] = {"key": key, "img": out.copy()}
    return out.convert("RGB")


def _load_intro_slide(ctx, filename: str, fallback_title: str, size: Tuple[int, int]) -> Image.Image:
    path = _asset_path(ctx, filename)
    if os.path.isfile(path):
        try:
            img = Image.open(path).convert("RGB")
            if img.size != size:
                img = img.resize(size)
            return img
        except Exception:
            pass

    w, h = size
    img = Image.new("RGB", size, (14, 10, 12))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / float(max(1, h - 1))
        r = int(24 + (80 * (1.0 - t)))
        g = int(10 + (22 * (1.0 - t)))
        b = int(14 + (28 * (1.0 - t)))
        d.line([0, y, w, y], fill=(r, g, b), width=1)

    d.rounded_rectangle([12, 12, w - 13, h - 13], radius=8, outline=(255, 228, 214), width=2)
    d.text((20, 24), fallback_title, fill=(255, 246, 238), font=ctx.font_l)
    d.text((20, 70), f"[{filename} placeholder]", fill=(226, 210, 204), font=ctx.font_s)
    d.text((20, h - 26), "B1/PRESS next  B2 exit", fill=(226, 210, 204), font=ctx.font_s)
    return img


def _draw_stat_bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, label: str, value: float, color: Tuple[int, int, int], font) -> None:
    frac = clamp(float(value) / 100.0, 0.0, 1.0)
    d.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=(18, 14, 16, 220), outline=(255, 220, 210, 90), width=1)
    fill_w = int((w - 2) * frac)
    if fill_w > 0:
        d.rounded_rectangle([x + 1, y + 1, x + 1 + fill_w, y + h - 1], radius=3, fill=(color[0], color[1], color[2], 220))
    d.text((x + 3, y + 1), label, font=font, fill=(20, 14, 12))


def _draw_stats(ctx, img: Image.Image, st: PetState) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w, _h = img.size

    margin = 7
    gap = 4
    cols = 4
    bar_w = (w - (margin * 2) - (gap * (cols - 1))) // cols
    bar_h = 13

    row1 = [
        ("HP", st.health, "health"),
        ("HNG", st.hunger, "hunger"),
        ("ENG", st.energy, "energy"),
        ("HYG", st.hygiene, "hygiene"),
    ]
    row2 = [
        ("SOC", st.social, "social"),
        ("FUN", st.fun, "fun"),
        ("BLD", st.bladder, "bladder"),
        ("MOOD", st.mood, "mood"),
    ]

    for i, (label, value, key) in enumerate(row1):
        x = margin + i * (bar_w + gap)
        _draw_stat_bar(d, x, 6, bar_w, bar_h, label, value, STAT_COLORS[key], ctx.font_s)

    for i, (label, value, key) in enumerate(row2):
        x = margin + i * (bar_w + gap)
        _draw_stat_bar(d, x, 23, bar_w, bar_h, label, value, STAT_COLORS[key], ctx.font_s)


def _format_age(age_seconds: float) -> str:
    age = max(0, int(age_seconds))
    if age < 3600:
        m = age // 60
        s = age % 60
        return f"{m}m {s}s"
    if age < 86400:
        h = age // 3600
        m = (age % 3600) // 60
        return f"{h}h {m}m"
    if age < 30 * 86400:
        d = age // 86400
        h = (age % 86400) // 3600
        return f"{d}d {h}h"
    mo = age // (30 * 86400)
    d = (age % (30 * 86400)) // 86400
    return f"{mo}mo {d}d"


def _mood_word(st: PetState) -> str:
    if st.hygiene < 24:
        return "Dirty"
    if st.energy < 24:
        return "Tired"
    if st.social < 30 or st.fun < 30:
        return "Misses You"
    if st.mood >= 72:
        return "Happy"
    if st.mood >= 44:
        return "Okay"
    return "Sad"


def _draw_top_info(ctx, img: Image.Image, st: PetState) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w, _h = img.size
    mf = _meta_font(ctx)

    room_name = str(ROOMS.get(st.room, ROOMS[ROOM_HUB]).get("name", st.room))
    d.text((10, 40), room_name, font=mf, fill=(245, 234, 228, 230))

    age_text = _format_age(st.age_seconds)
    tw = int(d.textlength(age_text, font=mf))
    d.text((w - 10 - tw, 40), age_text, font=mf, fill=(232, 210, 202, 228))

    mood = _mood_word(st)
    bb = d.textbbox((0, 0), mood, font=mf)
    m_tw = int(bb[2] - bb[0])
    m_th = int(bb[3] - bb[1])
    pad_x = 9
    pad_y = 3
    bw = m_tw + (pad_x * 2)
    bh = m_th + (pad_y * 2)
    bx = (w - bw) // 2
    by = 37
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=(20, 14, 16, 170), outline=(255, 220, 210, 130), width=1)
    tx = bx + pad_x - bb[0]
    ty = by + pad_y - bb[1]
    d.text((tx, ty), mood, font=mf, fill=(248, 238, 232, 235))


def _sprite_for_state(st: PetState, sprites: Dict[str, Image.Image], moving: bool, now: float) -> Image.Image:
    if st.pose == "sleep" and now < st.pose_until:
        return sprites.get("sleep", sprites.get("idle"))
    if st.pose == "shower" and now < st.pose_until:
        return sprites.get("shower", sprites.get("idle"))
    if st.pose == "toilet" and now < st.pose_until:
        return sprites.get("toilet", sprites.get("idle"))

    if moving:
        frame = int(st.walk_phase) % 2
        if frame == 0:
            return sprites.get("walk1", sprites.get("idle"))
        return sprites.get("walk2", sprites.get("idle"))
    return sprites.get("idle")


def _draw_action_panel(ctx, img: Image.Image, st: PetState, dialogue: Dict[str, List[Dict]]) -> Image.Image:
    w, h = img.size
    rect = (8, h - 94, w - 9, h - 8)
    img = overlay_panel(img, rect, radius=6, fill=(8, 6, 10, 168), outline=(255, 220, 210, 105), width=1)
    d = ImageDraw.Draw(img)
    of = _overlay_font(ctx)

    x0, y0, x1, _y1 = rect
    title = "Talk" if st.panel_kind == "TALK" else "Actions"
    d.text((x0 + 10, y0 + 6), title, font=of, fill=(252, 240, 234))

    items = _panel_items(st, dialogue)
    if not items:
        d.text((x0 + 10, y0 + 28), "No options", font=of, fill=(240, 210, 198))
        return img

    vis = 3
    sel = int(clamp(float(st.panel_sel), 0.0, float(len(items) - 1)))
    start = max(0, min(sel - 1, max(0, len(items) - vis)))
    y = y0 + 30

    for idx in range(start, min(len(items), start + vis)):
        item = items[idx]
        selected = idx == sel
        if selected:
            d.rounded_rectangle([x0 + 8, y - 2, x1 - 8, y + 16], radius=4, fill=(245, 232, 225))
            fg = (24, 14, 12)
        else:
            fg = (236, 222, 215)

        name = str(item).replace("_", " ").title() if st.panel_kind == "TALK" else str(item)
        d.text((x0 + 12, y), name, font=of, fill=fg)
        y += 18

    hint = "B1 confirm"
    tw = int(d.textlength(hint, font=of))
    d.text((x1 - 10 - tw, y0 + 6), hint, font=of, fill=(225, 205, 197))
    return img


def _draw_top_center_text(ctx, img: Image.Image, text: str) -> None:
    if not text:
        return

    d = ImageDraw.Draw(img)
    of = _overlay_font(ctx)
    w, _h = img.size
    lines = wrap_text(d, text, of, max_width=w - 24)[:2]
    y = 58

    for line in lines:
        tw = int(d.textlength(line, font=of))
        x = (w - tw) // 2
        d.text((x + 1, y + 1), line, font=of, fill=(10, 8, 8, 220))
        d.text((x, y), line, font=of, fill=(248, 238, 232, 235))
        y += 15


def _draw_minigame_overlay(ctx, img: Image.Image, st: PetState) -> Image.Image:
    name = str(st.minigame_name or "")
    if not name:
        return img

    w, h = img.size
    rect = (8, 62, w - 9, h - 8)
    img = overlay_panel(img, rect, radius=8, fill=(0, 0, 0, 255), outline=(255, 220, 210, 110), width=2)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    d.text((x0 + 10, y0 + 8), name, font=ctx.font_m, fill=(250, 238, 232))
    d.text((x1 - 10 - int(d.textlength("B2 exit", font=ctx.font_s)), y0 + 12), "B2 exit", font=ctx.font_s, fill=(222, 208, 200))

    mg = st.minigame_state if isinstance(st.minigame_state, dict) else {}
    cx0, cy0 = x0 + 8, y0 + 30
    cx1, cy1 = x1 - 8, y1 - 8

    if name == "Brick Breaker":
        for b in list(mg.get("bricks", [])):
            if not b.get("alive", False):
                continue
            bx0 = int(b.get("x", 0))
            by0 = int(b.get("y", 0))
            bw = int(b.get("w", 18))
            bh = int(b.get("h", 10))
            hp = int(b.get("hp", 1))
            fill = (255, 176, 120) if hp <= 1 else (255, 132, 102)
            d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=2, fill=fill, outline=(255, 234, 214), width=1)

        paddle_x = int(mg.get("paddle_x", w // 2))
        paddle_y = h - 20
        d.rounded_rectangle([paddle_x - 21, paddle_y, paddle_x + 21, paddle_y + 6], radius=2, fill=(238, 226, 220))
        ball_x = int(mg.get("ball_x", w // 2))
        ball_y = int(mg.get("ball_y", h // 2))
        d.ellipse([ball_x - 3, ball_y - 3, ball_x + 3, ball_y + 3], fill=(255, 240, 232))
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 13), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))
        level = int(mg.get("level", 1))
        max_levels = int(mg.get("max_levels", BRICK_MAX_LEVELS))
        lvl = f"L{level}/{max_levels}"
        d.text((cx1 - 8 - int(d.textlength(lvl, font=ctx.font_s)), cy1 - 13), lvl, font=ctx.font_s, fill=(238, 228, 220))

    elif name == "Memory Match":
        cards = list(mg.get("cards", []))
        matched = list(mg.get("matched", [False] * 6))
        revealed = set(mg.get("revealed", []))
        cursor = int(mg.get("cursor", 0))
        cols, rows = 3, 2
        gw = cx1 - cx0
        gh = cy1 - cy0
        cw = max(20, (gw - 10) // cols)
        ch = max(20, (gh - 8) // rows)
        for i in range(min(6, len(cards))):
            r, c = divmod(i, cols)
            bx = cx0 + c * (cw + 3)
            by = cy0 + r * (ch + 4)
            is_open = bool(matched[i]) or (i in revealed)
            fill = (238, 228, 220) if is_open else (42, 36, 44)
            fg = (18, 12, 10) if is_open else (236, 220, 212)
            out = (255, 220, 210) if i == cursor else (150, 128, 120)
            d.rounded_rectangle([bx, by, bx + cw, by + ch], radius=4, fill=fill, outline=out, width=2 if i == cursor else 1)
            label = str(cards[i]) if is_open else "?"
            lw = int(d.textlength(label, font=ctx.font_m))
            d.text((bx + (cw - lw) // 2, by + (ch // 2) - 8), label, font=ctx.font_m, fill=fg)
        d.text((cx0, cy1 - 13), f"Moves {int(mg.get('moves', 0))}", font=ctx.font_s, fill=(238, 228, 220))

    else:  # Runner Dash
        ground = h - 42
        d.line([cx0, ground, cx1, ground], fill=(236, 224, 216), width=2)
        player_y = int(mg.get("player_y", ground))
        d.rounded_rectangle([34, player_y - 16, 46, player_y], radius=2, fill=(255, 214, 184), outline=(255, 242, 234), width=1)
        for o in list(mg.get("obstacles", [])):
            ox = int(o.get("x", w))
            ow = int(o.get("w", 12))
            oh = int(o.get("h", 14))
            d.rounded_rectangle([ox, ground - oh, ox + ow, ground], radius=2, fill=(232, 120, 120), outline=(255, 220, 220), width=1)
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 13), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))

    return img


def render(ctx) -> Image.Image:
    st = _st(ctx)
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    now = time.time()

    if st.mode == MODE_ONBOARD_1:
        img = _load_intro_slide(ctx, ONBOARD_WELCOME, "Welcome to Pocket R", (w, h))
        d = ImageDraw.Draw(img)
        hint = "B1/PRESS next   B2 exit"
        tw = int(d.textlength(hint, font=ctx.font_s))
        d.text((w - tw - 10, h - 18), hint, font=ctx.font_s, fill=(245, 232, 226))
        return img

    if st.mode == MODE_ONBOARD_2:
        img = _load_intro_slide(ctx, ONBOARD_CONTROLS, "Controls", (w, h))
        d = ImageDraw.Draw(img)
        hint = "B1/PRESS start   B2 exit"
        tw = int(d.textlength(hint, font=ctx.font_s))
        d.text((w - tw - 10, h - 18), hint, font=ctx.font_s, fill=(245, 232, 226))
        return img

    if st.play_submode == PLAY_MINIGAME:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        img = _draw_minigame_overlay(ctx, img, st)
        if st.msg:
            _draw_top_center_text(ctx, img, st.msg)
        return img

    img = _load_layered_room(ctx, st.room, (w, h)).convert("RGB")
    _draw_stats(ctx, img, st)
    _draw_top_info(ctx, img, st)

    sprite_px = max(34, min(60, w // 4))
    sprites = _load_sprites(ctx, sprite_px)

    moving = False
    if st.alive and not st.panel_open and now >= st.pose_until:
        moving = (
            ctx.inputs.is_down("LEFT")
            or ctx.inputs.is_down("RIGHT")
            or ctx.inputs.is_down("UP")
            or ctx.inputs.is_down("DOWN")
        )

    sprite = _sprite_for_state(st, sprites, moving=moving, now=now)
    if not st.alive:
        sprite = sprite.convert("RGBA")
        tint = Image.new("RGBA", sprite.size, (40, 40, 40, 170))
        sprite = Image.alpha_composite(sprite, tint)

    px = int(st.x - (sprite.width // 2))
    py = int(st.y - (sprite.height // 2))
    img.paste(sprite, (px, py), sprite)

    if st.pose == "toilet" and now < st.blur_until:
        img = img.filter(ImageFilter.GaussianBlur(2.2))
        d = ImageDraw.Draw(img)
        text = "Woah look away"
        tw = int(d.textlength(text, font=ctx.font_l))
        d.text(((w - tw) // 2, (h // 2) - 10), text, font=ctx.font_l, fill=(255, 245, 238))

    if st.msg:
        _draw_top_center_text(ctx, img, st.msg)

    if st.panel_open:
        img = _draw_action_panel(ctx, img, st, _dialogue_data(ctx))

    return img
