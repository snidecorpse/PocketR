"""
PocketR Pico Edition V2 pet core.

Headless tamagotchi engine for the Pico LCD app.
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


SAVE_VERSION = 2
ROOM_MAIN = "MAIN"
ROOM_ARCADE = "ARCADE"
ROOM_BATHROOM = "BATHROOM"
ROOM_BEDROOM = "BEDROOM"
ACTIVITY_NONE = "NONE"
ACTIVITY_HEART_CATCH = "HEART_CATCH"

AGE_ACCEL = 60.0
MAX_OFFLINE_SECONDS = 7 * 24 * 60 * 60
CATCHUP_STEP_SECONDS = 300.0
MAX_STAT = 100.0
MIN_STAT = 0.0

ROOMS = {
    ROOM_MAIN: {"name": "Main", "neighbors": (ROOM_ARCADE, ROOM_BATHROOM, ROOM_BEDROOM)},
    ROOM_ARCADE: {"name": "Arcade", "neighbors": (ROOM_MAIN,)},
    ROOM_BATHROOM: {"name": "Bathroom", "neighbors": (ROOM_MAIN,)},
    ROOM_BEDROOM: {"name": "Bedroom", "neighbors": (ROOM_MAIN,)},
}

ROOM_GRAPH = {
    ROOM_MAIN: (ROOM_ARCADE, ROOM_BATHROOM, ROOM_BEDROOM),
    ROOM_ARCADE: (ROOM_MAIN,),
    ROOM_BATHROOM: (ROOM_MAIN,),
    ROOM_BEDROOM: (ROOM_MAIN,),
}

BASE_DRAINS_PER_HOUR = {
    "hunger": 5.6,
    "hygiene": 3.8,
    "fun": 3.0,
    "love": 2.6,
}

MOVE_COSTS = {
    "hunger": -1.2,
    "hygiene": -0.6,
}

TALK_PAIRS = (
    ("You: Hey, I am here with you.", "Him: I feel better when you stay close."),
    ("You: I missed you a little today.", "Him: Then come spend a little time with me."),
    ("You: Are you doing okay?", "Him: Better now that you checked on me."),
    ("You: I wanted to talk to you.", "Him: I always like hearing your voice."),
    ("You: You mean a lot to me.", "Him: That makes my whole day softer."),
    ("You: Come here for a second.", "Him: Okay. I am right here."),
    ("You: I was thinking about you.", "Him: Then I already feel loved."),
    ("You: Let us just stay like this.", "Him: I would like that a lot."),
)

DEFAULT_STATE = {
    "version": SAVE_VERSION,
    "room": ROOM_MAIN,
    "alive": True,
    "death_reason": "",
    "age_seconds": 0.0,
    "last_epoch": 0.0,
    "wellness": 100.0,
    "fun": 74.0,
    "hunger": 78.0,
    "hygiene": 76.0,
    "love": 82.0,
    "talk_index": 0,
    "feed_count": 0,
    "talk_count": 0,
    "clean_count": 0,
    "love_count": 0,
    "arcade_sessions": 0,
    "heart_catch_best": 0,
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


def _safe_epoch_time():
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


def _is_v2_state(raw):
    required = (
        "version",
        "room",
        "alive",
        "death_reason",
        "age_seconds",
        "last_epoch",
        "wellness",
        "fun",
        "hunger",
        "hygiene",
        "love",
        "talk_index",
        "feed_count",
        "talk_count",
        "clean_count",
        "love_count",
        "arcade_sessions",
        "heart_catch_best",
        "last_message",
    )
    if not isinstance(raw, dict):
        return False
    if int(raw.get("version", -1)) != SAVE_VERSION:
        return False
    for key in required:
        if key not in raw:
            return False
    return True


def _merge_state(raw):
    state = _copy_default_state()
    for key in state:
        if key in raw:
            state[key] = raw[key]
    state["version"] = SAVE_VERSION
    return state


def _deficit(value, threshold):
    if value >= threshold:
        return 0.0
    return clamp((threshold - value) / threshold, 0.0, 1.0)


def _day_label(age_seconds):
    days = int(float(age_seconds) // 86400.0) + 1
    if days < 1:
        days = 1
    return "D%d" % days


def heart_catch_reward(score):
    try:
        score = int(score)
    except Exception:
        score = 0
    if score < 0:
        score = 0
    fun_gain = min(22, 6 + score)
    love_gain = min(6, score // 4)
    hunger_loss = min(8, 2 + score // 3)
    hygiene_loss = min(6, 1 + score // 4)
    return {
        "fun_gain": int(fun_gain),
        "love_gain": int(love_gain),
        "hunger_loss": int(hunger_loss),
        "hygiene_loss": int(hygiene_loss),
    }


class PocketRPet:
    def __init__(self, save_path="pocketr_pet_save.json", now_fn=None):
        self.save_path = save_path
        self.now_fn = now_fn
        self.state = _copy_default_state()
        self._runtime_activity = ACTIVITY_NONE

    def _resolve_now(self, now=None):
        direct = _valid_epoch(now)
        if direct is not None:
            return direct
        if self.now_fn is not None:
            try:
                return _valid_epoch(self.now_fn())
            except Exception:
                pass
        return _safe_epoch_time()

    def _set_message(self, text):
        self.state["last_message"] = str(text)

    def _boost(self, effects):
        for key in effects:
            if key in self.state:
                self.state[key] = clamp(float(self.state[key]) + float(effects[key]), MIN_STAT, MAX_STAT)

    def _set_runtime_activity(self, activity):
        self._runtime_activity = str(activity or ACTIVITY_NONE)

    def _clear_runtime_activity(self):
        self._runtime_activity = ACTIVITY_NONE

    def _activity_multiplier(self):
        hunger_mult = 1.0
        hygiene_mult = 1.0
        fun_mult = 1.0
        love_mult = 1.0

        if self.state["room"] == ROOM_ARCADE:
            hunger_mult *= 1.25
            hygiene_mult *= 1.20

        if self._runtime_activity == ACTIVITY_HEART_CATCH:
            hunger_mult *= 1.45
            hygiene_mult *= 1.35
            love_mult *= 1.10

        return {
            "hunger": hunger_mult,
            "hygiene": hygiene_mult,
            "fun": fun_mult,
            "love": love_mult,
        }

    def _finalize_death(self):
        if not self.state["alive"]:
            return
        lowest = {
            "fun": float(self.state["fun"]),
            "hunger": float(self.state["hunger"]),
            "hygiene": float(self.state["hygiene"]),
            "love": float(self.state["love"]),
        }
        reason = min(lowest, key=lowest.get)
        self.state["alive"] = False
        self.state["death_reason"] = reason
        self._set_message("GAME OVER. You did not take care of him.")

    def _advance_chunk(self, dt):
        if not self.state["alive"]:
            return
        if dt <= 0.0:
            return

        mult = self._activity_multiplier()
        self.state["age_seconds"] = float(self.state["age_seconds"]) + (dt * AGE_ACCEL)

        hunger_drop = BASE_DRAINS_PER_HOUR["hunger"] * mult["hunger"] * (dt / 3600.0)
        hygiene_drop = BASE_DRAINS_PER_HOUR["hygiene"] * mult["hygiene"] * (dt / 3600.0)
        fun_drop = BASE_DRAINS_PER_HOUR["fun"] * mult["fun"] * (dt / 3600.0)
        love_drop = BASE_DRAINS_PER_HOUR["love"] * mult["love"] * (dt / 3600.0)

        self.state["hunger"] = clamp(float(self.state["hunger"]) - hunger_drop, MIN_STAT, MAX_STAT)
        self.state["hygiene"] = clamp(float(self.state["hygiene"]) - hygiene_drop, MIN_STAT, MAX_STAT)
        self.state["fun"] = clamp(float(self.state["fun"]) - fun_drop, MIN_STAT, MAX_STAT)
        self.state["love"] = clamp(float(self.state["love"]) - love_drop, MIN_STAT, MAX_STAT)

        stress = 0.0
        stress += 0.30 * _deficit(float(self.state["hunger"]), 35.0)
        stress += 0.27 * _deficit(float(self.state["hygiene"]), 30.0)
        stress += 0.18 * _deficit(float(self.state["fun"]), 28.0)
        stress += 0.25 * _deficit(float(self.state["love"]), 28.0)

        wellness_loss_hour = 0.0
        if stress > 0.12:
            wellness_loss_hour += (stress - 0.12) * 8.0

        critical_count = 0
        for stat_name in ("fun", "hunger", "hygiene", "love"):
            if float(self.state[stat_name]) < 15.0:
                critical_count += 1
                wellness_loss_hour += 3.0
        if critical_count >= 2:
            wellness_loss_hour += 2.0

        wellness_regen_hour = 0.0
        if (
            float(self.state["fun"]) > 65.0
            and float(self.state["hunger"]) > 65.0
            and float(self.state["hygiene"]) > 65.0
            and float(self.state["love"]) > 65.0
        ):
            wellness_regen_hour = 0.50
        elif (
            float(self.state["fun"]) > 50.0
            and float(self.state["hunger"]) > 50.0
            and float(self.state["hygiene"]) > 50.0
            and float(self.state["love"]) > 50.0
        ):
            wellness_regen_hour = 0.15

        new_wellness = float(self.state["wellness"]) + ((wellness_regen_hour - wellness_loss_hour) * (dt / 3600.0))
        self.state["wellness"] = clamp(new_wellness, MIN_STAT, MAX_STAT)

        if float(self.state["wellness"]) <= 0.0:
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

    def new_game(self, now=None):
        self.state = _copy_default_state()
        epoch_now = self._resolve_now(now)
        if epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        self._clear_runtime_activity()
        return self.snapshot()

    def load(self, now=None):
        raw = _read_json(self.save_path)
        if not _is_v2_state(raw):
            return self.new_game(now=now)

        self.state = _merge_state(raw)
        self._clear_runtime_activity()

        epoch_now = self._resolve_now(now)
        last_epoch = _valid_epoch(self.state.get("last_epoch"))
        if epoch_now is not None and last_epoch is not None and epoch_now >= last_epoch:
            delta = epoch_now - last_epoch
            if delta > MAX_OFFLINE_SECONDS:
                delta = MAX_OFFLINE_SECONDS
            if delta > 0.0:
                self._advance(delta)
            self.state["last_epoch"] = epoch_now
        elif epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        return self.snapshot()

    def save(self, now=None):
        epoch_now = self._resolve_now(now)
        if epoch_now is not None:
            self.state["last_epoch"] = epoch_now
        self.state["version"] = SAVE_VERSION
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

    def go_room(self, room, now=None):
        self.tick(now=now)
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        room = str(room or "").upper()
        current = self.state["room"]
        if room not in ROOMS:
            return self._result(False, "That room does not exist.")
        if room == current:
            return self._result(True, "He is already there.")
        if room not in ROOM_GRAPH.get(current, ()):
            return self._result(False, "You cannot go there from here.")

        self.state["room"] = room
        self._boost(MOVE_COSTS)
        self._set_message("He moved to the %s." % ROOMS[room]["name"])
        self.save(now=now)
        return self._result(True, self.state["last_message"])

    def feed(self, now=None):
        self.tick(now=now)
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        hunger_now = float(self.state["hunger"])
        if hunger_now <= 65.0:
            self._boost({"hunger": 20, "love": 1, "hygiene": -1})
            message = "He ate happily."
        elif hunger_now <= 85.0:
            self._boost({"hunger": 10, "hygiene": -1})
            message = "Quick snack done."
        else:
            self._boost({"hunger": 2, "hygiene": -3, "fun": -1})
            message = "He is already full."

        self.state["feed_count"] = int(self.state["feed_count"]) + 1
        self._set_message(message)
        self.save(now=now)
        return self._result(True, message)

    def interact(self, now=None):
        self.tick(now=now)
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        room = self.state["room"]
        if room == ROOM_MAIN:
            idx = int(self.state["talk_index"]) % len(TALK_PAIRS)
            pair = TALK_PAIRS[idx]
            self.state["talk_index"] = int(self.state["talk_index"]) + 1
            self.state["talk_count"] = int(self.state["talk_count"]) + 1
            self._boost({"love": 4, "fun": 1})
            self._set_message(pair[1])
            self.save(now=now)
            return self._result(True, pair[1], lines=[pair[0], pair[1]])

        if room == ROOM_BATHROOM:
            self.state["clean_count"] = int(self.state["clean_count"]) + 1
            self._boost({"hygiene": 24, "love": 1, "fun": -1})
            lines = ["You helped him get cleaned up.", "He feels fresh again."]
            self._set_message(lines[-1])
            self.save(now=now)
            return self._result(True, lines[-1], lines=lines)

        if room == ROOM_BEDROOM:
            self.state["love_count"] = int(self.state["love_count"]) + 1
            self._boost({"love": 8, "fun": 2})
            lines = ["You got close with him for a while.", "He feels extra loved."]
            self._set_message(lines[-1])
            self.save(now=now)
            return self._result(True, lines[-1], lines=lines)

        if room == ROOM_ARCADE:
            return self._result(True, "Arcade menu ready.", open_menu="ARCADE")

        return self._result(False, "Nothing happens.")

    def apply_arcade_result(self, game_name, score, now=None):
        self.tick(now=now)
        if not self.state["alive"]:
            return self._result(False, "He is gone. Restart to try again.")

        if str(game_name or "").upper() != ACTIVITY_HEART_CATCH:
            return self._result(False, "Unknown arcade game.")

        reward = heart_catch_reward(score)
        self._boost({
            "fun": reward["fun_gain"],
            "love": reward["love_gain"],
            "hunger": -reward["hunger_loss"],
            "hygiene": -reward["hygiene_loss"],
        })
        self.state["arcade_sessions"] = int(self.state["arcade_sessions"]) + 1
        best = int(self.state["heart_catch_best"])
        score = int(score)
        if score > best:
            self.state["heart_catch_best"] = score
        message = "Heart Catcher score %d. Fun +%d Love +%d." % (
            score,
            reward["fun_gain"],
            reward["love_gain"],
        )
        self._set_message(message)
        self.save(now=now)
        result = self._result(True, message)
        result["reward"] = reward
        return result

    def snapshot(self):
        return {
            "room": self.state["room"],
            "alive": bool(self.state["alive"]),
            "death_reason": self.state["death_reason"],
            "age_seconds": float(self.state["age_seconds"]),
            "day_label": _day_label(self.state["age_seconds"]),
            "wellness": round(float(self.state["wellness"]), 2),
            "fun": round(float(self.state["fun"]), 1),
            "hunger": round(float(self.state["hunger"]), 1),
            "hygiene": round(float(self.state["hygiene"]), 1),
            "love": round(float(self.state["love"]), 1),
            "talk_index": int(self.state["talk_index"]),
            "feed_count": int(self.state["feed_count"]),
            "talk_count": int(self.state["talk_count"]),
            "clean_count": int(self.state["clean_count"]),
            "love_count": int(self.state["love_count"]),
            "arcade_sessions": int(self.state["arcade_sessions"]),
            "heart_catch_best": int(self.state["heart_catch_best"]),
            "last_message": self.state["last_message"],
        }

    def restart(self, now=None):
        self.new_game(now=now)
        self.save(now=now)
        return self.snapshot()

    def _result(self, ok, message, lines=None, open_menu=None):
        out = {
            "ok": bool(ok),
            "message": str(message),
            "lines": list(lines or []),
            "state": self.snapshot(),
        }
        if open_menu is not None:
            out["open_menu"] = str(open_menu)
        return out
