"""
PocketR Pico Edition V1

Single-file Micropython-safe pet engine for the PocketR tamagotchi core.

Usage example:

    pet = PocketRPet()
    pet.load()
    pet.tick()
    print(pet.snapshot())
    print(pet.move("RIGHT"))
    print(pet.do_action("Cuddle"))
    pet.save()
"""

try:
    import ujson as json
except ImportError:
    import json

try:
    import utime as _time
except ImportError:
    import time as _time

import os


VERSION = 1
MAX_STAT = 100.0
MIN_STAT = 0.0
AGE_ACCEL = 60.0  # 1 real minute = 1 pet hour
MAX_OFFLINE_SECONDS = 7 * 24 * 60 * 60
CATCHUP_STEP_SECONDS = 300.0
MOVE_LOAD_SECONDS = 10 * 60.0
MOVE_LOAD_BONUS = 0.15
ARCADE_ROOM_BONUS = 0.18

ROOM_HALL = "HALL"
ROOM_BEDROOM = "BEDROOM"
ROOM_LIVING = "LIVING"
ROOM_BATHROOM = "BATHROOM"
ROOM_ARCADE = "ARCADE"

ROOMS = {
    ROOM_HALL: {
        "neighbors": {
            "LEFT": ROOM_ARCADE,
            "RIGHT": ROOM_BEDROOM,
            "UP": ROOM_BATHROOM,
            "DOWN": ROOM_LIVING,
        },
        "actions": ["Check In", "Stretch"],
    },
    ROOM_BEDROOM: {
        "neighbors": {"LEFT": ROOM_HALL},
        "actions": ["Cuddle", "Give Hug", "Sleep"],
    },
    ROOM_LIVING: {
        "neighbors": {"UP": ROOM_HALL},
        "actions": [
            "Watch TV",
            "Lounge",
            "Light Snack",
            "Balanced Meal",
            "Sweet Treat",
            "Talk",
        ],
    },
    ROOM_BATHROOM: {
        "neighbors": {"DOWN": ROOM_HALL},
        "actions": ["Use Toilet", "Shower", "Night Routine", "Change Clothes"],
    },
    ROOM_ARCADE: {
        "neighbors": {"RIGHT": ROOM_HALL},
        "actions": ["Arcade Session"],
    },
}

BASE_DRAINS_PER_HOUR = {
    "hunger": 6.25,
    "energy": 5.25,
    "hygiene": 3.00,
    "social": 2.50,
    "fun": 2.75,
    "bladder": 5.75,
}

MOVE_COSTS = {
    "energy": -0.8,
    "hunger": -0.4,
    "bladder": -0.5,
}

ACTION_WINDOWS = {
    "Check In": (0.05, 5 * 60.0),
    "Stretch": (0.05, 5 * 60.0),
    "Cuddle": (0.22, 12 * 60.0),
    "Give Hug": (0.22, 12 * 60.0),
    "Sleep": (0.0, 0.0),
    "Watch TV": (0.12, 8 * 60.0),
    "Lounge": (0.05, 5 * 60.0),
    "Light Snack": (0.12, 8 * 60.0),
    "Balanced Meal": (0.12, 8 * 60.0),
    "Sweet Treat": (0.12, 8 * 60.0),
    "Talk": (0.05, 5 * 60.0),
    "Use Toilet": (0.12, 8 * 60.0),
    "Shower": (0.12, 10 * 60.0),
    "Night Routine": (0.22, 12 * 60.0),
    "Change Clothes": (0.12, 10 * 60.0),
    "Arcade Session": (0.40, 20 * 60.0),
}

ACTION_EFFECTS = {
    "Check In": {"social": 3, "mood": 2, "fun": 1},
    "Stretch": {"energy": 2, "mood": 1, "fun": 1},
    "Cuddle": {"social": 8, "mood": 6, "energy": -2, "fun": 3},
    "Give Hug": {"social": 7, "mood": 5, "fun": 2, "energy": -1},
    "Sleep": {"energy": 14, "mood": 4, "hunger": -3, "bladder": -5},
    "Watch TV": {"fun": 7, "social": 1, "energy": -2, "hunger": -1},
    "Lounge": {"energy": 6, "mood": 3, "fun": 2, "bladder": -2},
    "Light Snack": {"hunger": 8, "mood": 1, "bladder": -1},
    "Balanced Meal": {"hunger": 16, "energy": 3, "mood": 2, "bladder": -3},
    "Sweet Treat": {"hunger": 6, "fun": 7, "mood": 5, "energy": -2, "hygiene": -2},
    "Talk": {"social": 4, "fun": 2, "mood": 2},
    "Use Toilet": {"bladder": 38, "hygiene": -3, "mood": 1},
    "Shower": {"hygiene": 34, "mood": 5, "energy": -3},
    "Night Routine": {"hygiene": 18, "energy": 11, "mood": 7, "social": 2, "bladder": -6, "hunger": -3},
    "Change Clothes": {"mood": 5, "hygiene": 2, "social": 1},
    "Arcade Session": {"fun": 9, "mood": 6, "energy": -4, "hunger": -2, "bladder": -2},
}

ACTION_MESSAGES = {
    "Check In": "You checked in on him. He feels noticed.",
    "Stretch": "Tiny stretch break done. He loosened up.",
    "Cuddle": "Cuddle time helped him feel safe and close.",
    "Give Hug": "Big hug delivered. He brightened up right away.",
    "Sleep": "He got some rest and recovered a bit.",
    "Watch TV": "Cozy TV time together lifted his mood.",
    "Lounge": "He relaxed for a while and settled down.",
    "Light Snack": "Light snack shared. He feels a little better.",
    "Balanced Meal": "Balanced meal done. He looks recharged.",
    "Sweet Treat": "Sweet treat time. He is extra playful now.",
    "Talk": "You spent a little time talking with him.",
    "Use Toilet": "Bathroom break handled. He feels relieved.",
    "Shower": "Shower done. He feels fresh and clean.",
    "Night Routine": "Night routine complete. He feels calmer.",
    "Change Clothes": "Outfit change done. He feels refreshed.",
    "Arcade Session": "Arcade time was fun, but it tired him out.",
}

TALK_PAIRS = [
    ("You: I missed you today.", "Him: I missed you too. Stay with me a bit."),
    ("You: How are you holding up?", "Him: Better now that you checked on me."),
    ("You: I wanted to spend time with you.", "Him: That means a lot to me."),
    ("You: You are doing okay.", "Him: I needed to hear that from you."),
    ("You: Come here for a minute.", "Him: I am here. I like this."),
    ("You: I have been thinking about you.", "Him: Then today already feels better."),
]

DEFAULT_STATE = {
    "version": VERSION,
    "room": ROOM_HALL,
    "alive": True,
    "death_reason": "",
    "age_seconds": 0.0,
    "sim_clock": 0.0,
    "last_epoch": 0.0,
    "health": 96.0,
    "hunger": 82.0,
    "energy": 86.0,
    "hygiene": 78.0,
    "social": 72.0,
    "fun": 72.0,
    "bladder": 68.0,
    "mood": 84.0,
    "move_load_until_clock": 0.0,
    "action_load_bonus": 0.0,
    "action_load_until_clock": 0.0,
    "talk_index": 0,
    "hugs_given": 0,
    "cuddles_shared": 0,
    "talk_sessions": 0,
    "arcade_sessions": 0,
    "snacks_given": 0,
    "last_message": "He is ready.",
}


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _copy_default_state():
    out = {}
    for key in DEFAULT_STATE:
        out[key] = DEFAULT_STATE[key]
    return out


def _valid_epoch(value):
    if value is None:
        return None
    try:
        value = float(value)
    except Exception:
        return None
    if value < 946684800.0:
        return None
    return value


def _safe_time_time():
    try:
        return _valid_epoch(_time.time())
    except Exception:
        return None


def _ensure_parent_dir(path):
    if not path:
        return
    norm = path.replace("\\", "/")
    if "/" not in norm:
        return
    parts = norm.split("/")
    if parts and parts[0] == "":
        current = "/"
        parts = parts[1:-1]
    else:
        current = ""
        parts = parts[:-1]
    for part in parts:
        if not part:
            continue
        if current in ("", "/"):
            current = (current + part) if current != "/" else ("/" + part)
        else:
            current = current + "/" + part
        try:
            os.mkdir(current)
        except OSError:
            pass


def _read_json(path):
    try:
        with open(path, "r") as handle:
            raw = handle.read()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _write_json(path, data):
    text = json.dumps(data)
    _ensure_parent_dir(path)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as handle:
            handle.write(text)
        try:
            if hasattr(os, "replace"):
                os.replace(tmp_path, path)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass
                os.rename(tmp_path, path)
        except Exception:
            with open(path, "w") as handle:
                handle.write(text)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return True
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        try:
            with open(path, "w") as handle:
                handle.write(text)
            return True
        except Exception:
            return False


def _merge_state(raw):
    state = _copy_default_state()
    if not isinstance(raw, dict):
        return state
    for key in state:
        if key in raw:
            state[key] = raw[key]
    try:
        state["version"] = int(raw.get("version", VERSION))
    except Exception:
        state["version"] = VERSION
    return state


def _age_label(age_seconds):
    total = int(max(0.0, float(age_seconds)))
    if total < 60:
        return "%ds" % total
    minutes = total // 60
    if minutes < 60:
        return "%dm" % minutes
    hours = minutes // 60
    rem_minutes = minutes % 60
    if hours < 24:
        return "%dh %dm" % (hours, rem_minutes)
    days = hours // 24
    rem_hours = hours % 24
    return "%dd %dh" % (days, rem_hours)


def _mood_word(state):
    if float(state["hygiene"]) < 24.0:
        return "Dirty"
    if float(state["energy"]) < 24.0:
        return "Tired"
    if float(state["social"]) < 30.0 or float(state["fun"]) < 30.0:
        return "Misses You"
    if float(state["mood"]) >= 72.0:
        return "Happy"
    if float(state["mood"]) >= 44.0:
        return "Okay"
    return "Sad"


class PocketRPet:
    def __init__(self, save_path="pocketr_pet_save.json", now_fn=None):
        self.save_path = save_path
        self.now_fn = now_fn
        self.state = _copy_default_state()

    def _resolve_now(self, now=None):
        direct = _valid_epoch(now)
        if direct is not None:
            return direct
        if self.now_fn is not None:
            try:
                return _valid_epoch(self.now_fn())
            except Exception:
                pass
        return _safe_time_time()

    def _set_last_message(self, text):
        self.state["last_message"] = str(text)

    def _boost(self, effects):
        for key in effects:
            if key not in self.state:
                continue
            self.state[key] = clamp(
                float(self.state[key]) + float(effects[key]),
                MIN_STAT,
                MAX_STAT,
            )

    def _set_move_window(self):
        self.state["move_load_until_clock"] = float(self.state["sim_clock"]) + MOVE_LOAD_SECONDS

    def _set_action_window(self, action):
        bonus, seconds = ACTION_WINDOWS.get(action, (0.0, 0.0))
        self.state["action_load_bonus"] = float(bonus)
        self.state["action_load_until_clock"] = float(self.state["sim_clock"]) + float(seconds)

    def _activity_load(self):
        clock = float(self.state["sim_clock"])
        load = 1.0
        if self.state["room"] == ROOM_ARCADE:
            load += ARCADE_ROOM_BONUS
        if clock < float(self.state["move_load_until_clock"]):
            load += MOVE_LOAD_BONUS
        if clock < float(self.state["action_load_until_clock"]):
            load += float(self.state["action_load_bonus"])
        return max(1.0, load)

    def _finalize_death(self):
        if not self.state["alive"]:
            return
        lowest = {
            "hunger": float(self.state["hunger"]),
            "energy": float(self.state["energy"]),
            "hygiene": float(self.state["hygiene"]),
            "social": float(self.state["social"]),
            "fun": float(self.state["fun"]),
            "bladder": float(self.state["bladder"]),
        }
        reason = min(lowest, key=lowest.get)
        self.state["alive"] = False
        self.state["death_reason"] = reason
        self._set_last_message("GAME OVER. You did not take care of him. Cause: low %s." % reason)

    def _advance_chunk(self, dt):
        if not self.state["alive"]:
            return
        if dt <= 0.0:
            return

        self.state["sim_clock"] = float(self.state["sim_clock"]) + dt
        self.state["age_seconds"] = float(self.state["age_seconds"]) + (dt * AGE_ACCEL)

        load_delta = self._activity_load() - 1.0

        hunger_drop = BASE_DRAINS_PER_HOUR["hunger"] * (1.0 + 0.62 * load_delta) * (dt / 3600.0)
        energy_drop = BASE_DRAINS_PER_HOUR["energy"] * (1.0 + 0.95 * load_delta) * (dt / 3600.0)
        hygiene_drop = BASE_DRAINS_PER_HOUR["hygiene"] * (1.0 + 0.40 * load_delta) * (dt / 3600.0)
        social_drop = BASE_DRAINS_PER_HOUR["social"] * (1.0 + 0.10 * load_delta) * (dt / 3600.0)
        fun_drop = BASE_DRAINS_PER_HOUR["fun"] * (1.0 + 0.18 * load_delta) * (dt / 3600.0)
        bladder_drop = BASE_DRAINS_PER_HOUR["bladder"] * (1.0 + 0.74 * load_delta) * (dt / 3600.0)

        self.state["hunger"] = clamp(float(self.state["hunger"]) - hunger_drop, MIN_STAT, MAX_STAT)
        self.state["energy"] = clamp(float(self.state["energy"]) - energy_drop, MIN_STAT, MAX_STAT)
        self.state["hygiene"] = clamp(float(self.state["hygiene"]) - hygiene_drop, MIN_STAT, MAX_STAT)
        self.state["social"] = clamp(float(self.state["social"]) - social_drop, MIN_STAT, MAX_STAT)
        self.state["fun"] = clamp(float(self.state["fun"]) - fun_drop, MIN_STAT, MAX_STAT)
        self.state["bladder"] = clamp(float(self.state["bladder"]) - bladder_drop, MIN_STAT, MAX_STAT)

        def deficit(value, threshold):
            if value >= threshold:
                return 0.0
            return clamp((threshold - value) / threshold, 0.0, 1.0)

        stress = 0.0
        stress += 0.26 * deficit(float(self.state["hunger"]), 30.0)
        stress += 0.24 * deficit(float(self.state["energy"]), 28.0)
        stress += 0.18 * deficit(float(self.state["hygiene"]), 26.0)
        stress += 0.22 * deficit(float(self.state["bladder"]), 24.0)
        stress += 0.05 * deficit(float(self.state["social"]), 22.0)
        stress += 0.05 * deficit(float(self.state["fun"]), 22.0)
        stress += 0.08 * deficit(float(self.state["energy"]), 36.0) * clamp(load_delta, 0.0, 2.0)

        critical_count = 0
        for stat_name in ("hunger", "energy", "hygiene", "bladder"):
            if float(self.state[stat_name]) < 15.0:
                critical_count += 1

        hp_loss_hour = 0.0
        if stress > 0.15:
            hp_loss_hour += (stress - 0.15) * 5.6
        if critical_count >= 2:
            hp_loss_hour += (critical_count - 1) * 2.8
        if critical_count >= 3:
            hp_loss_hour += 2.2
        if critical_count >= 4:
            hp_loss_hour += 1.2
        if load_delta > 0.0 and float(self.state["energy"]) < 35.0:
            hp_loss_hour += clamp(load_delta, 0.0, 1.8) * deficit(float(self.state["energy"]), 35.0) * 1.8

        hp_regen_hour = 0.0
        core_min = min(
            float(self.state["hunger"]),
            float(self.state["energy"]),
            float(self.state["hygiene"]),
            float(self.state["bladder"]),
        )
        if core_min > 62.0 and float(self.state["mood"]) > 65.0:
            hp_regen_hour = 0.75
        elif core_min > 48.0 and float(self.state["mood"]) > 52.0:
            hp_regen_hour = 0.22

        health_now = float(self.state["health"]) + ((hp_regen_hour - hp_loss_hour) * (dt / 3600.0))
        self.state["health"] = clamp(health_now, MIN_STAT, MAX_STAT)

        mood_target = (
            float(self.state["health"]) * 0.28
            + float(self.state["fun"]) * 0.20
            + float(self.state["social"]) * 0.17
            + float(self.state["energy"]) * 0.12
            + float(self.state["hunger"]) * 0.09
            + float(self.state["hygiene"]) * 0.07
            + float(self.state["bladder"]) * 0.07
        )
        mood_lerp = clamp(dt / 1800.0, 0.0, 1.0)
        self.state["mood"] = clamp(
            float(self.state["mood"]) + ((mood_target - float(self.state["mood"])) * mood_lerp),
            MIN_STAT,
            MAX_STAT,
        )

        if float(self.state["health"]) <= 0.0:
            self._finalize_death()

    def _advance(self, elapsed_s):
        if elapsed_s is None:
            return
        try:
            remaining = float(elapsed_s)
        except Exception:
            return
        if remaining <= 0.0:
            return
        while remaining > 0.0 and self.state["alive"]:
            step = remaining if remaining < CATCHUP_STEP_SECONDS else CATCHUP_STEP_SECONDS
            self._advance_chunk(step)
            remaining -= step

    def _sync_to_now(self, now=None):
        epoch_now = self._resolve_now(now)
        last_epoch = _valid_epoch(self.state.get("last_epoch"))
        if epoch_now is None:
            return None
        if last_epoch is not None and epoch_now >= last_epoch:
            delta = epoch_now - last_epoch
            if delta > 0.0:
                self._advance(delta)
        self.state["last_epoch"] = epoch_now
        return epoch_now

    def _save_result(self):
        return self.save()

    def new_game(self, now=None):
        self.state = _copy_default_state()
        epoch_now = self._resolve_now(now)
        if epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        return self.snapshot()

    def load(self, now=None):
        raw = _read_json(self.save_path)
        if raw is None:
            return self.new_game(now=now)

        self.state = _merge_state(raw)
        changed = False
        epoch_now = self._resolve_now(now)
        last_epoch = _valid_epoch(self.state.get("last_epoch"))
        if epoch_now is not None and last_epoch is not None and epoch_now >= last_epoch:
            delta = epoch_now - last_epoch
            if delta > MAX_OFFLINE_SECONDS:
                delta = MAX_OFFLINE_SECONDS
            if delta > 0.0:
                self._advance(delta)
                changed = True
            self.state["last_epoch"] = epoch_now
        elif epoch_now is not None and last_epoch is None:
            self.state["last_epoch"] = epoch_now

        if changed:
            self.save(now=epoch_now)
        return self.snapshot()

    def save(self, now=None):
        epoch_now = self._resolve_now(now)
        if epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        self.state["version"] = VERSION
        return _write_json(self.save_path, self.state)

    def tick(self, elapsed_s=None, now=None):
        epoch_now = self._resolve_now(now)
        if elapsed_s is None:
            last_epoch = _valid_epoch(self.state.get("last_epoch"))
            if epoch_now is not None and last_epoch is not None and epoch_now >= last_epoch:
                elapsed_s = epoch_now - last_epoch
            else:
                elapsed_s = 0.0
        self._advance(elapsed_s)
        if epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        return self.snapshot()

    def available_actions(self):
        if not self.state["alive"]:
            return []
        room = self.state["room"]
        info = ROOMS.get(room, ROOMS[ROOM_HALL])
        return list(info["actions"])

    def _result(self, ok, message, lines=None):
        if lines is None:
            lines = []
        return {
            "ok": bool(ok),
            "message": str(message),
            "lines": list(lines),
            "state": self.snapshot(),
        }

    def move(self, direction):
        self._sync_to_now()
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        direction = str(direction or "").upper()
        room = self.state["room"]
        info = ROOMS.get(room, ROOMS[ROOM_HALL])
        next_room = info["neighbors"].get(direction)
        if not next_room:
            self._set_last_message("No room in that direction.")
            self._save_result()
            return self._result(False, "No room in that direction.")

        self.state["room"] = next_room
        self._boost(MOVE_COSTS)
        self._set_move_window()
        self._set_last_message("He moved into the %s." % next_room.title())
        if float(self.state["health"]) <= 0.0:
            self._finalize_death()
        self._save_result()
        return self._result(True, self.state["last_message"])

    def do_action(self, action):
        self._sync_to_now()
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        action = str(action or "")
        if action not in self.available_actions():
            return self._result(False, "That action is not available here.")

        effects = ACTION_EFFECTS.get(action, {})
        self._boost(effects)
        self._set_action_window(action)

        if action == "Cuddle":
            self.state["cuddles_shared"] = int(self.state["cuddles_shared"]) + 1
        elif action == "Give Hug":
            self.state["hugs_given"] = int(self.state["hugs_given"]) + 1
        elif action in ("Light Snack", "Balanced Meal", "Sweet Treat"):
            self.state["snacks_given"] = int(self.state["snacks_given"]) + 1
        elif action == "Talk":
            self.state["talk_sessions"] = int(self.state["talk_sessions"]) + 1
        elif action == "Arcade Session":
            self.state["arcade_sessions"] = int(self.state["arcade_sessions"]) + 1

        if action == "Talk":
            idx = int(self.state["talk_index"]) % len(TALK_PAIRS)
            self.state["talk_index"] = int(self.state["talk_index"]) + 1
            pair = TALK_PAIRS[idx]
            self._set_last_message(pair[1])
            self._save_result()
            return self._result(True, pair[1], lines=[pair[0], pair[1]])

        self._set_last_message(ACTION_MESSAGES.get(action, "He responded to that action."))
        if float(self.state["health"]) <= 0.0:
            self._finalize_death()
        self._save_result()
        return self._result(True, self.state["last_message"])

    def snapshot(self):
        out = {
            "room": self.state["room"],
            "alive": bool(self.state["alive"]),
            "death_reason": self.state["death_reason"],
            "age_seconds": float(self.state["age_seconds"]),
            "age_label": _age_label(self.state["age_seconds"]),
            "health": round(float(self.state["health"]), 2),
            "hunger": round(float(self.state["hunger"]), 2),
            "energy": round(float(self.state["energy"]), 2),
            "hygiene": round(float(self.state["hygiene"]), 2),
            "social": round(float(self.state["social"]), 2),
            "fun": round(float(self.state["fun"]), 2),
            "bladder": round(float(self.state["bladder"]), 2),
            "mood": round(float(self.state["mood"]), 2),
            "mood_word": _mood_word(self.state),
            "available_actions": self.available_actions(),
            "hugs_given": int(self.state["hugs_given"]),
            "cuddles_shared": int(self.state["cuddles_shared"]),
            "talk_sessions": int(self.state["talk_sessions"]),
            "arcade_sessions": int(self.state["arcade_sessions"]),
            "snacks_given": int(self.state["snacks_given"]),
            "last_message": self.state["last_message"],
            "activity_load": round(self._activity_load(), 3),
        }
        return out

    def restart(self, now=None):
        self.new_game(now=now)
        self.save(now=now)
        return self.snapshot()