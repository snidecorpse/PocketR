from machine import Pin, SPI
import time
import framebuf

try:
    import urandom as random
except ImportError:
    import random

from pocketr_pet import (
    ACTIVITY_HEART_CATCH,
    ACTIVITY_NONE,
    ROOM_ARCADE,
    ROOM_BATHROOM,
    ROOM_BEDROOM,
    ROOM_MAIN,
    PocketRPet,
    heart_catch_reward,
)


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
RED = rgb565(255, 86, 86)
CORAL = rgb565(255, 112, 112)
PINK = rgb565(255, 138, 214)
GOLD = rgb565(255, 204, 90)
AQUA = rgb565(100, 235, 235)
TEAL = rgb565(42, 124, 124)
BLUE = rgb565(70, 128, 255)
NAVY = rgb565(28, 36, 76)
SKY = rgb565(146, 214, 255)
PURPLE = rgb565(86, 56, 140)
LAVENDER = rgb565(182, 154, 255)
PLUM = rgb565(98, 60, 124)
GREEN = rgb565(92, 212, 110)
MINT = rgb565(170, 245, 200)
GRAY = rgb565(86, 86, 96)
MID = rgb565(48, 48, 58)
DARK = rgb565(22, 20, 28)
BROWN = rgb565(118, 80, 54)
TAN = rgb565(196, 148, 112)
CREAM = rgb565(244, 226, 208)
HAIR = rgb565(25, 22, 32)
SKIN = rgb565(248, 208, 170)
SHIRT = rgb565(82, 116, 224)
PANTS = rgb565(42, 56, 110)
SHOES = rgb565(240, 240, 250)
PLANT = rgb565(72, 170, 86)
ARC_NEON = rgb565(255, 64, 185)

STAT_COLORS = {
    "FUN": PINK,
    "HNG": GOLD,
    "HYG": AQUA,
    "LOVE": CORAL,
}

ROOM_NAMES = {
    ROOM_MAIN: "MAIN",
    ROOM_ARCADE: "ARCADE",
    ROOM_BATHROOM: "BATH",
    ROOM_BEDROOM: "BED",
}

K4_HOLD_MS = 450
DIALOGUE_LINE_MS = 1600
FLASH_MS = 1600
AUTOSAVE_MS = 15000
FRAME_MS = 40


PET_PALETTE = {
    "H": HAIR,
    "K": SKIN,
    "B": SHIRT,
    "P": PANTS,
    "S": SHOES,
    "L": SKY,
    "M": CORAL,
    "C": PINK,
}

PET_SPRITES = {
    "idle": (
        "................",
        "......HHHH......",
        ".....HHHHHH.....",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKHKKHKKH...",
        "...HKKKKKKKKH...",
        "...HKKLMMLKKH...",
        "...HHKKKKKKHH...",
        "....HHBBBBHH....",
        "...HBBBBBBBBH...",
        "...HBBLBBLBBH...",
        "...HBBBBBBBBH...",
        "...HHBBPPBBHH...",
        "....HPP..PPH....",
        "...SSS....SSS...",
    ),
    "talk": (
        "................",
        "......HHHH......",
        ".....HHHHHH.....",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKHKKHKKH...",
        "...HKKKKKKKKH...",
        "...HKKLMMMKKH...",
        "...HHKKKKKKHH...",
        "....HHBBBBHH....",
        "...HBBBBBBBBH...",
        "..HBBB LBBLBBH..".replace(" ", "B"),
        "..HBBBBBBBBBBH..".replace(" ", "B"),
        "...HHBBPPBBHH...",
        "...HPPP..PPPH...",
        "..SSS......SSS..",
    ),
    "feed": (
        "................",
        "......HHHH......",
        ".....HHHHHH.....",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKHKKHKKH...",
        "...HKKKKKKKKH...",
        "...HKKLMMLKKH...",
        "...HHKKKKKKHH...",
        "....HHBBBBHH....",
        "...HBBBBBBBBH...",
        "..HBBBLLLLBBH...",
        "..HBBBBBBBBBH...",
        "...HHBBPPBBHH...",
        "...HPP....PPH...",
        "..SSS......SSS..",
    ),
    "clean": (
        "....C.......C...",
        "......HHHH......",
        "...C.HHHHHH...C.",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKHKKHKKH...",
        "...HKKKKKKKKH...",
        "..CHKKLMMLKKHC..",
        "...HHKKKKKKHH...",
        "....HHBBBBHH....",
        "...HBBBBBBBBH...",
        "...HBBLBBLBBH...",
        "...HBBBBBBBBH...",
        "...HHBBPPBBHH...",
        "....HPP..PPH....",
        "...SSS....SSS...",
    ),
    "love": (
        ".....MM..MM.....",
        "....MMMMMMMM....",
        "....MMMMMMMM....",
        ".....MMMMMM.....",
        "......MMMM......",
        "......HHHH......",
        ".....HHHHHH.....",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKLMMLKKH...",
        "...HHKKKKKKHH...",
        "...HBBBBBBBBH...",
        "...HBBLBBLBBH...",
        "...HHBBPPBBHH...",
        "....HPP..PPH....",
        "...SSS....SSS...",
    ),
    "arcade": (
        "................",
        "......HHHH......",
        ".....HHHHHH.....",
        "....HHHKKHHH....",
        "...HHKKKKKKHH...",
        "...HKKHKKHKKH...",
        "...HKKKKKKKKH...",
        "...HKKLMMLKKH...",
        "...HHKKKKKKHH...",
        "....HHBBBBHH....",
        "...HBBBBBBBBH...",
        "...HBBBBBBBBH...",
        "...HBBPPPPBBH...",
        "...HHBP..PBHH...",
        "....SS....SS....",
        "...PP......PP...",
    ),
}


class LCD_1in44(framebuf.FrameBuffer):
    WIDTH = 128
    HEIGHT = 128
    XSTART = 2
    YSTART = 1

    def __init__(self):
        self.cs = Pin(9, Pin.OUT, value=1)
        self.dc = Pin(8, Pin.OUT, value=1)
        self.rst = Pin(12, Pin.OUT, value=1)
        self.bl = Pin(13, Pin.OUT, value=1)
        self.spi = SPI(
            1,
            baudrate=20_000_000,
            polarity=0,
            phase=0,
            sck=Pin(10),
            mosi=Pin(11),
            miso=None,
        )
        self.buffer = bytearray(self.WIDTH * self.HEIGHT * 2)
        super().__init__(self.buffer, self.WIDTH, self.HEIGHT, framebuf.RGB565)
        self.reset()
        self.init_display()
        self.bl.value(1)
        self.fill(BLACK)
        self.show()

    def write_cmd(self, cmd):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)

    def write_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(data)
        self.cs.value(1)

    def reset(self):
        self.rst.value(1)
        time.sleep_ms(50)
        self.rst.value(0)
        time.sleep_ms(50)
        self.rst.value(1)
        time.sleep_ms(150)

    def init_display(self):
        self.write_cmd(0x01)
        time.sleep_ms(150)
        self.write_cmd(0x11)
        time.sleep_ms(150)
        self.write_cmd(0x3A)
        self.write_data(b"\x05")
        time.sleep_ms(10)
        self.write_cmd(0x36)
        self.write_data(b"\x08")
        self.write_cmd(0xB1)
        self.write_data(b"\x01\x2C\x2D")
        self.write_cmd(0xB2)
        self.write_data(b"\x01\x2C\x2D")
        self.write_cmd(0xB3)
        self.write_data(b"\x01\x2C\x2D\x01\x2C\x2D")
        self.write_cmd(0xB4)
        self.write_data(b"\x07")
        self.write_cmd(0xC0)
        self.write_data(b"\xA2\x02\x84")
        self.write_cmd(0xC1)
        self.write_data(b"\xC5")
        self.write_cmd(0xC2)
        self.write_data(b"\x0A\x00")
        self.write_cmd(0xC3)
        self.write_data(b"\x8A\x2A")
        self.write_cmd(0xC4)
        self.write_data(b"\x8A\xEE")
        self.write_cmd(0xC5)
        self.write_data(b"\x0E")
        self.write_cmd(0x21)
        self.write_cmd(0x13)
        time.sleep_ms(10)
        self.write_cmd(0x29)
        time.sleep_ms(100)

    def set_window(self, x0, y0, x1, y1):
        x0 += self.XSTART
        x1 += self.XSTART
        y0 += self.YSTART
        y1 += self.YSTART
        self.write_cmd(0x2A)
        self.write_data(bytes([0x00, x0, 0x00, x1]))
        self.write_cmd(0x2B)
        self.write_data(bytes([0x00, y0, 0x00, y1]))
        self.write_cmd(0x2C)

    def show(self):
        self.set_window(0, 0, self.WIDTH - 1, self.HEIGHT - 1)
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(self.buffer)
        self.cs.value(1)


class Buttons:
    def __init__(self):
        self.pins = [
            Pin(15, Pin.IN, Pin.PULL_UP),  # K1
            Pin(17, Pin.IN, Pin.PULL_UP),  # K2
            Pin(2, Pin.IN, Pin.PULL_UP),   # K3
            Pin(3, Pin.IN, Pin.PULL_UP),   # K4
        ]
        self.current = [False, False, False, False]
        self.previous = [False, False, False, False]

    def update(self):
        self.previous = self.current[:]
        self.current = []
        for pin in self.pins:
            self.current.append(pin.value() == 0)

    def pressed(self, index):
        return self.current[index]

    def just_pressed(self, index):
        return self.current[index] and (not self.previous[index])

    def just_released(self, index):
        return (not self.current[index]) and self.previous[index]


def ticks_ms():
    return time.ticks_ms()


def ticks_diff(a, b):
    return time.ticks_diff(a, b)


def ticks_add(a, b):
    return time.ticks_add(a, b)


def text_x(text):
    return len(str(text)) * 8


def center_text(fb, text, y, color):
    x = (128 - text_x(text)) // 2
    if x < 0:
        x = 0
    fb.text(str(text), x, y, color)


def wrap_text(text, width=15, max_lines=2):
    words = str(text or "").split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        test = word if not current else current + " " + word
        if len(test) <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if words and len(lines) == max_lines:
        rebuilt = " ".join(lines)
        if len(rebuilt) < len(str(text)):
            tail = lines[-1]
            if len(tail) >= width:
                tail = tail[: width - 1]
            lines[-1] = tail + "…"
    return lines


def fill_round_rect(fb, x, y, w, h, color):
    fb.fill_rect(x + 1, y, w - 2, h, color)
    fb.fill_rect(x, y + 1, w, h - 2, color)


def draw_round_rect(fb, x, y, w, h, color):
    fb.rect(x + 1, y, w - 2, h, color)
    fb.rect(x, y + 1, w, h - 2, color)
    fb.pixel(x + 1, y + 1, color)
    fb.pixel(x + w - 2, y + 1, color)
    fb.pixel(x + 1, y + h - 2, color)
    fb.pixel(x + w - 2, y + h - 2, color)


def draw_panel(fb, x, y, w, h, fill, border):
    fill_round_rect(fb, x, y, w, h, fill)
    draw_round_rect(fb, x, y, w, h, border)


def draw_pixel_sprite(fb, sprite_key, x, y, scale=2):
    sprite = PET_SPRITES.get(sprite_key, PET_SPRITES["idle"])
    row_idx = 0
    for row in sprite:
        col_idx = 0
        for ch in row:
            color = PET_PALETTE.get(ch)
            if color is not None:
                fb.fill_rect(x + (col_idx * scale), y + (row_idx * scale), scale, scale, color)
            col_idx += 1
        row_idx += 1


def draw_heart_glyph(fb, x, y, color):
    fb.pixel(x + 1, y, color)
    fb.pixel(x + 2, y, color)
    fb.pixel(x + 4, y, color)
    fb.pixel(x + 5, y, color)
    fb.fill_rect(x, y + 1, 7, 2, color)
    fb.fill_rect(x + 1, y + 3, 5, 1, color)
    fb.fill_rect(x + 2, y + 4, 3, 1, color)
    fb.pixel(x + 3, y + 5, color)


def draw_room_background(fb, room):
    play_y = 36
    play_h = 58
    if room == ROOM_MAIN:
        fb.fill_rect(0, play_y, 128, play_h, rgb565(78, 56, 48))
        fb.fill_rect(0, 80, 128, 14, rgb565(98, 74, 58))
        fb.fill_rect(10, 44, 22, 22, SKY)
        fb.rect(9, 43, 24, 24, CREAM)
        fb.fill_rect(18, 70, 6, 12, BROWN)
        fb.fill_rect(14, 64, 14, 8, PLANT)
        fb.rect(92, 48, 24, 16, CREAM)
        fb.fill_rect(96, 52, 16, 8, TAN)
    elif room == ROOM_ARCADE:
        fb.fill_rect(0, play_y, 128, play_h, rgb565(30, 16, 48))
        fb.fill_rect(0, 80, 128, 14, rgb565(18, 10, 34))
        fb.fill_rect(10, 44, 18, 34, NAVY)
        fb.rect(10, 44, 18, 34, ARC_NEON)
        fb.fill_rect(36, 48, 22, 28, MID)
        fb.rect(36, 48, 22, 28, PURPLE)
        fb.fill_rect(40, 52, 14, 10, BLUE)
        fb.fill_rect(88, 46, 26, 18, PLUM)
        fb.rect(88, 46, 26, 18, LAVENDER)
        draw_heart_glyph(fb, 96, 52, GOLD)
    elif room == ROOM_BATHROOM:
        fb.fill_rect(0, play_y, 128, play_h, rgb565(46, 96, 100))
        for xx in range(0, 128, 16):
            fb.vline(xx, play_y, play_h, TEAL)
        for yy in range(play_y, play_y + play_h, 14):
            fb.hline(0, yy, 128, TEAL)
        fb.fill_rect(88, 52, 24, 18, CREAM)
        fb.rect(88, 52, 24, 18, AQUA)
        fb.fill_rect(94, 70, 12, 10, WHITE)
        fb.fill_rect(18, 62, 18, 12, WHITE)
        fb.rect(18, 62, 18, 12, SKY)
        fb.fill_rect(14, 74, 26, 4, TEAL)
    else:
        fb.fill_rect(0, play_y, 128, play_h, rgb565(70, 56, 90))
        fb.fill_rect(0, 80, 128, 14, rgb565(90, 74, 112))
        fb.fill_rect(14, 58, 38, 18, TAN)
        fb.rect(14, 58, 38, 18, CREAM)
        fb.fill_rect(18, 52, 30, 8, LAVENDER)
        fb.fill_rect(92, 46, 18, 22, SKY)
        fb.rect(92, 46, 18, 22, WHITE)


def draw_stat_card(fb, x, y, label, value, fill_color):
    draw_panel(fb, x, y, 60, 10, MID, WHITE)
    inner_w = int((58 * max(0, min(100, value))) / 100)
    if inner_w > 0:
        fb.fill_rect(x + 1, y + 1, inner_w, 8, fill_color)
    txt_color = BLACK if value >= 30 else WHITE
    fb.text(label, x + 2, y + 1, txt_color)


class HeartCatcher:
    def __init__(self):
        self.reset()

    def reset(self):
        self.catcher_x = 55
        self.catcher_y = 108
        self.catcher_w = 18
        self.score = 0
        self.elapsed_ms = 0
        self.spawn_accum = 0
        self.hearts = []
        self.done = False

    def start(self):
        self.reset()

    def _progress(self):
        p = self.elapsed_ms / 20000.0
        if p < 0.0:
            return 0.0
        if p > 1.0:
            return 1.0
        return p

    def _spawn_interval_ms(self):
        return int(650 - (290 * self._progress()))

    def _fall_speed(self):
        return 50.0 + (50.0 * self._progress())

    def _spawn_heart(self):
        x = random.randint(8, 116)
        self.hearts.append({"x": x, "y": 38.0})

    def update(self, buttons, dt_ms):
        if self.done:
            return
        if buttons.pressed(0):
            self.catcher_x -= 5
        if buttons.pressed(1):
            self.catcher_x += 5
        if self.catcher_x < 4:
            self.catcher_x = 4
        if self.catcher_x > 106:
            self.catcher_x = 106

        self.elapsed_ms += dt_ms
        self.spawn_accum += dt_ms
        interval = self._spawn_interval_ms()
        while self.spawn_accum >= interval:
            self.spawn_accum -= interval
            self._spawn_heart()
            interval = self._spawn_interval_ms()

        speed = self._fall_speed()
        survivors = []
        for heart in self.hearts:
            heart["y"] += speed * (dt_ms / 1000.0)
            hx = int(heart["x"])
            hy = int(heart["y"])
            if hy + 6 >= self.catcher_y and hy <= self.catcher_y + 8 and hx + 6 >= self.catcher_x and hx <= self.catcher_x + self.catcher_w:
                self.score += 1
                continue
            if hy > 118:
                continue
            survivors.append(heart)
        self.hearts = survivors

        if self.elapsed_ms >= 20000:
            self.done = True

    def draw(self, fb):
        fb.fill_rect(0, 36, 128, 58, rgb565(18, 10, 34))
        fb.fill_rect(0, 94, 128, 24, rgb565(32, 18, 50))
        fb.text("T%02d" % max(0, (20000 - self.elapsed_ms + 999) // 1000), 4, 38, WHITE)
        fb.text("S%02d" % self.score, 88, 38, GOLD)
        fb.fill_rect(self.catcher_x, self.catcher_y, self.catcher_w, 4, CORAL)
        fb.fill_rect(self.catcher_x + 3, self.catcher_y - 3, self.catcher_w - 6, 3, PINK)
        for heart in self.hearts:
            draw_heart_glyph(fb, int(heart["x"]), int(heart["y"]), PINK)


class PocketRPicoApp:
    MODE_WORLD = 0
    MODE_DIALOGUE = 1
    MODE_ROOM_PICK = 2
    MODE_ARCADE_MENU = 3
    MODE_HEART_CATCH_READY = 4
    MODE_HEART_CATCH_PLAY = 5
    MODE_HEART_CATCH_RESULT = 6
    MODE_GAME_OVER = 7

    def __init__(self):
        self.lcd = LCD_1in44()
        self.buttons = Buttons()
        self.pet = PocketRPet()
        self.pet.load()
        self.mode = self.MODE_GAME_OVER if not self.pet.snapshot()["alive"] else self.MODE_WORLD
        self.dialogue_lines = []
        self.dialogue_index = 0
        self.dialogue_deadline_ms = 0
        self.room_pick_selection = 0
        self.arcade_menu_selection = 0
        self.k4_hold_started_ms = 0
        self.k4_hold_consumed = False
        self.heart_state = HeartCatcher()
        self.pending_heart_score = 0
        self.pending_heart_reward = heart_catch_reward(0)
        self.flash_message = ""
        self.flash_until_ms = 0
        self.last_frame_ms = ticks_ms()
        self.last_save_ms = self.last_frame_ms
        self.pose_name = "idle"
        self.pose_until_ms = 0

    def set_flash(self, text, ms=FLASH_MS):
        self.flash_message = str(text)
        self.flash_until_ms = ticks_add(ticks_ms(), ms)

    def active_message(self):
        now = ticks_ms()
        if ticks_diff(self.flash_until_ms, now) > 0:
            return self.flash_message
        return self.pet.snapshot()["last_message"]

    def set_pose(self, name, ms=1200):
        self.pose_name = str(name)
        self.pose_until_ms = ticks_add(ticks_ms(), ms)

    def current_pose(self, snap):
        if self.mode in (self.MODE_HEART_CATCH_READY, self.MODE_HEART_CATCH_PLAY, self.MODE_HEART_CATCH_RESULT):
            return "arcade"
        if self.mode == self.MODE_DIALOGUE and snap["room"] == ROOM_MAIN:
            return "talk"
        if ticks_diff(self.pose_until_ms, ticks_ms()) > 0:
            return self.pose_name
        if snap["room"] == ROOM_ARCADE:
            return "arcade"
        return "idle"

    def set_dialogue(self, lines):
        self.dialogue_lines = list(lines or [])
        if not self.dialogue_lines:
            self.mode = self.MODE_WORLD
            return
        self.dialogue_index = 0
        self.dialogue_deadline_ms = ticks_add(ticks_ms(), DIALOGUE_LINE_MS)
        self.mode = self.MODE_DIALOGUE

    def close_dialogue(self):
        self.dialogue_lines = []
        self.dialogue_index = 0
        self.dialogue_deadline_ms = 0
        snap = self.pet.snapshot()
        self.mode = self.MODE_GAME_OVER if not snap["alive"] else self.MODE_WORLD

    def open_arcade_menu(self):
        self.arcade_menu_selection = 0
        self.mode = self.MODE_ARCADE_MENU

    def start_room_picker(self):
        self.room_pick_selection = 0
        self.mode = self.MODE_ROOM_PICK

    def start_heart_ready(self):
        self.heart_state.reset()
        self.pending_heart_score = 0
        self.pending_heart_reward = heart_catch_reward(0)
        self.mode = self.MODE_HEART_CATCH_READY

    def finish_heart_round(self):
        self.pending_heart_score = int(self.heart_state.score)
        self.pending_heart_reward = heart_catch_reward(self.pending_heart_score)
        self.mode = self.MODE_HEART_CATCH_RESULT

    def handle_world_inputs(self, now_ms):
        snap = self.pet.snapshot()
        room = snap["room"]

        if self.buttons.just_pressed(2):
            result = self.pet.feed()
            self.set_pose("feed", 1100)
            self.set_flash(result["message"])
            return

        if room == ROOM_MAIN:
            if self.buttons.just_pressed(0):
                result = self.pet.go_room(ROOM_ARCADE)
                self.set_flash(result["message"])
                return
            if self.buttons.just_pressed(1):
                result = self.pet.go_room(ROOM_BATHROOM)
                self.set_flash(result["message"])
                return

            if self.buttons.just_pressed(3):
                self.k4_hold_started_ms = now_ms
                self.k4_hold_consumed = False

            if self.buttons.pressed(3) and self.k4_hold_started_ms and (not self.k4_hold_consumed):
                if ticks_diff(now_ms, self.k4_hold_started_ms) >= K4_HOLD_MS:
                    self.k4_hold_consumed = True
                    self.start_room_picker()
                    self.set_flash("Bedroom?", 800)
                    return

            if self.buttons.just_released(3):
                if self.k4_hold_consumed:
                    self.k4_hold_started_ms = 0
                    self.k4_hold_consumed = False
                    return
                self.k4_hold_started_ms = 0
                result = self.pet.interact()
                self.set_pose("talk", 1800)
                self.set_dialogue(result.get("lines") or [result["message"]])
                return

        else:
            self.k4_hold_started_ms = 0
            self.k4_hold_consumed = False
            if room == ROOM_ARCADE and self.buttons.just_pressed(1):
                result = self.pet.go_room(ROOM_MAIN)
                self.set_flash(result["message"])
                return
            if room == ROOM_BATHROOM and self.buttons.just_pressed(0):
                result = self.pet.go_room(ROOM_MAIN)
                self.set_flash(result["message"])
                return
            if room == ROOM_BEDROOM and self.buttons.just_pressed(0):
                result = self.pet.go_room(ROOM_MAIN)
                self.set_flash(result["message"])
                return

            if self.buttons.just_pressed(3):
                result = self.pet.interact()
                if result.get("open_menu") == "ARCADE":
                    self.open_arcade_menu()
                    return
                if room == ROOM_BATHROOM:
                    self.set_pose("clean", 1400)
                elif room == ROOM_BEDROOM:
                    self.set_pose("love", 1400)
                self.set_flash(result["message"])

    def handle_dialogue_inputs(self, now_ms):
        if self.buttons.just_pressed(2):
            self.close_dialogue()
            return
        if self.buttons.just_pressed(3):
            if self.dialogue_index < len(self.dialogue_lines) - 1:
                self.dialogue_index += 1
                self.dialogue_deadline_ms = ticks_add(now_ms, DIALOGUE_LINE_MS)
            else:
                self.close_dialogue()
            return
        if ticks_diff(now_ms, self.dialogue_deadline_ms) >= 0:
            if self.dialogue_index < len(self.dialogue_lines) - 1:
                self.dialogue_index += 1
                self.dialogue_deadline_ms = ticks_add(now_ms, DIALOGUE_LINE_MS)
            else:
                self.close_dialogue()

    def handle_room_pick_inputs(self):
        if self.buttons.just_pressed(0) or self.buttons.just_pressed(1):
            self.room_pick_selection = 1 - self.room_pick_selection
            return
        if self.buttons.just_pressed(2):
            self.mode = self.MODE_WORLD
            return
        if self.buttons.just_pressed(3):
            if self.room_pick_selection == 0:
                result = self.pet.go_room(ROOM_BEDROOM)
                self.set_flash(result["message"])
            self.mode = self.MODE_WORLD

    def handle_arcade_menu_inputs(self):
        if self.buttons.just_pressed(0):
            self.arcade_menu_selection = (self.arcade_menu_selection - 1) % 2
            return
        if self.buttons.just_pressed(1):
            self.arcade_menu_selection = (self.arcade_menu_selection + 1) % 2
            return
        if self.buttons.just_pressed(2):
            self.mode = self.MODE_WORLD
            return
        if self.buttons.just_pressed(3):
            if self.arcade_menu_selection == 0:
                self.start_heart_ready()
            else:
                self.mode = self.MODE_WORLD

    def handle_heart_ready_inputs(self):
        if self.buttons.just_pressed(2):
            self.mode = self.MODE_ARCADE_MENU
            return
        if self.buttons.just_pressed(3):
            self.heart_state.start()
            self.mode = self.MODE_HEART_CATCH_PLAY

    def handle_heart_play_inputs(self, dt_ms):
        self.heart_state.update(self.buttons, dt_ms)
        if self.buttons.just_pressed(2):
            self.finish_heart_round()
            return
        if self.heart_state.done:
            self.finish_heart_round()

    def handle_heart_result_inputs(self):
        if self.buttons.just_pressed(2):
            self.mode = self.MODE_WORLD
            return
        if self.buttons.just_pressed(3):
            result = self.pet.apply_arcade_result(ACTIVITY_HEART_CATCH, self.pending_heart_score)
            self.set_flash(result["message"], 1800)
            self.mode = self.MODE_WORLD

    def handle_game_over_inputs(self):
        if self.buttons.just_pressed(3):
            self.pet.restart()
            self.mode = self.MODE_WORLD
            self.set_flash("New pet started.", 1200)

    def autosave_if_needed(self, now_ms):
        if ticks_diff(now_ms, self.last_save_ms) >= AUTOSAVE_MS:
            self.pet.save()
            self.last_save_ms = now_ms

    def draw_room_strip(self, fb, snap):
        room = snap["room"]
        strip_color = BROWN
        if room == ROOM_ARCADE:
            strip_color = PURPLE
        elif room == ROOM_BATHROOM:
            strip_color = TEAL
        elif room == ROOM_BEDROOM:
            strip_color = PLUM
        fb.fill_rect(0, 28, 128, 8, strip_color)
        center_text(fb, ROOM_NAMES.get(room, room), 28, WHITE)
        fb.text(snap["day_label"], 96, 28, GOLD)

    def draw_hud(self, fb, snap):
        fb.fill_rect(0, 0, 128, 28, DARK)
        draw_stat_card(fb, 4, 4, "FUN", snap["fun"], STAT_COLORS["FUN"])
        draw_stat_card(fb, 64, 4, "HNG", snap["hunger"], STAT_COLORS["HNG"])
        draw_stat_card(fb, 4, 16, "HYG", snap["hygiene"], STAT_COLORS["HYG"])
        draw_stat_card(fb, 64, 16, "LOVE", snap["love"], STAT_COLORS["LOVE"])

    def draw_message_panel(self, fb, text, border=WHITE):
        draw_panel(fb, 2, 94, 124, 24, MID, border)
        lines = wrap_text(text, 15, 2)
        if len(lines) == 1:
            center_text(fb, lines[0], 102, WHITE)
        else:
            center_text(fb, lines[0], 98, WHITE)
            center_text(fb, lines[1], 106, WHITE)

    def draw_footer(self, fb):
        fb.fill_rect(0, 118, 128, 10, BLACK)
        hint = "K1< K2> K3F K4I"
        if self.mode == self.MODE_ROOM_PICK:
            hint = "K1/2 K3X K4OK"
        elif self.mode == self.MODE_ARCADE_MENU:
            hint = "K1/2 K3X K4OK"
        elif self.mode == self.MODE_HEART_CATCH_READY:
            hint = "K3X  K4GO"
        elif self.mode == self.MODE_HEART_CATCH_PLAY:
            hint = "K1< K2> K3X"
        elif self.mode == self.MODE_HEART_CATCH_RESULT:
            hint = "K3BK K4GET"
        elif self.mode == self.MODE_DIALOGUE:
            hint = "K3X  K4NXT"
        elif self.mode == self.MODE_GAME_OVER:
            hint = "K4 RESTART"
        center_text(fb, hint, 119, GRAY)

    def draw_menu_box(self, fb, title, options, selection):
        draw_panel(fb, 18, 42, 92, 44, rgb565(24, 18, 30), WHITE)
        center_text(fb, title, 46, GOLD)
        base_y = 58
        idx = 0
        for option in options:
            y = base_y + (idx * 10)
            if idx == selection:
                fb.fill_rect(26, y - 1, 76, 9, BLUE)
            center_text(fb, option, y, WHITE if idx != selection else BLACK)
            idx += 1

    def draw_world(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        pose = self.current_pose(snap)
        draw_pixel_sprite(fb, pose, 48, 46, 2)
        self.draw_message_panel(fb, self.active_message(), GOLD)

    def draw_dialogue(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        draw_pixel_sprite(fb, "talk", 48, 46, 2)
        current = self.dialogue_lines[self.dialogue_index] if self.dialogue_lines else ""
        self.draw_message_panel(fb, current, SKY)

    def draw_room_pick(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        draw_pixel_sprite(fb, "idle", 48, 46, 2)
        self.draw_menu_box(fb, "ROOM", ("BEDROOM", "CANCEL"), self.room_pick_selection)
        self.draw_message_panel(fb, "Hold K4 from Main to open this.", SKY)

    def draw_arcade_menu(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        draw_pixel_sprite(fb, "arcade", 48, 46, 2)
        self.draw_menu_box(fb, "ARCADE", ("HEART", "BACK"), self.arcade_menu_selection)
        self.draw_message_panel(fb, "Pick a game.", PINK)

    def draw_heart_ready(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        draw_pixel_sprite(fb, "arcade", 48, 46, 2)
        draw_panel(fb, 20, 46, 88, 32, rgb565(18, 10, 34), PINK)
        center_text(fb, "HEART", 52, WHITE)
        center_text(fb, "CATCHER", 60, WHITE)
        self.draw_message_panel(fb, "K4 start. K3 back.", PINK)

    def draw_heart_play(self, fb, snap):
        self.draw_room_strip(fb, snap)
        self.heart_state.draw(fb)
        self.draw_message_panel(fb, "Catch hearts for FUN and LOVE.", PINK)

    def draw_heart_result(self, fb, snap):
        draw_room_background(fb, snap["room"])
        self.draw_room_strip(fb, snap)
        draw_pixel_sprite(fb, "arcade", 48, 46, 2)
        draw_panel(fb, 12, 44, 104, 38, rgb565(24, 14, 38), WHITE)
        center_text(fb, "SCORE %d" % self.pending_heart_score, 48, GOLD)
        center_text(fb, "BEST %d" % max(self.pending_heart_score, snap["heart_catch_best"]), 58, WHITE)
        center_text(
            fb,
            "F+%d L+%d" % (self.pending_heart_reward["fun_gain"], self.pending_heart_reward["love_gain"]),
            68,
            PINK,
        )
        self.draw_message_panel(fb, "K4 take reward. K3 skip.", PINK)

    def draw_game_over(self, fb, snap):
        fb.fill(RED)
        center_text(fb, "GAME", 24, WHITE)
        center_text(fb, "OVER", 36, WHITE)
        center_text(fb, "YOU DIDN'T", 58, WHITE)
        center_text(fb, "TAKE CARE", 68, WHITE)
        center_text(fb, "OF HIM", 78, WHITE)
        if snap["death_reason"]:
            center_text(fb, "LOW " + snap["death_reason"].upper(), 96, BLACK)
        center_text(fb, "K4 RESTART", 112, WHITE)

    def draw(self, snap):
        self.lcd.fill(BLACK)
        self.draw_hud(self.lcd, snap)

        if self.mode == self.MODE_DIALOGUE:
            self.draw_dialogue(self.lcd, snap)
        elif self.mode == self.MODE_ROOM_PICK:
            self.draw_room_pick(self.lcd, snap)
        elif self.mode == self.MODE_ARCADE_MENU:
            self.draw_arcade_menu(self.lcd, snap)
        elif self.mode == self.MODE_HEART_CATCH_READY:
            self.draw_heart_ready(self.lcd, snap)
        elif self.mode == self.MODE_HEART_CATCH_PLAY:
            self.draw_heart_play(self.lcd, snap)
        elif self.mode == self.MODE_HEART_CATCH_RESULT:
            self.draw_heart_result(self.lcd, snap)
        elif self.mode == self.MODE_GAME_OVER:
            self.draw_game_over(self.lcd, snap)
        else:
            self.draw_world(self.lcd, snap)

        self.draw_footer(self.lcd)
        self.lcd.show()

    def run(self):
        self.set_flash("PocketR Pico V2", 1000)
        while True:
            now_ms = ticks_ms()
            dt_ms = ticks_diff(now_ms, self.last_frame_ms)
            if dt_ms < 0:
                dt_ms = 0
            self.last_frame_ms = now_ms

            self.buttons.update()
            if self.mode == self.MODE_HEART_CATCH_PLAY:
                self.pet._set_runtime_activity(ACTIVITY_HEART_CATCH)
            else:
                self.pet._set_runtime_activity(ACTIVITY_NONE)

            self.pet.tick(elapsed_s=dt_ms / 1000.0)
            snap = self.pet.snapshot()
            if (not snap["alive"]) and self.mode != self.MODE_GAME_OVER:
                self.mode = self.MODE_GAME_OVER

            if self.mode == self.MODE_WORLD:
                self.handle_world_inputs(now_ms)
            elif self.mode == self.MODE_DIALOGUE:
                self.handle_dialogue_inputs(now_ms)
            elif self.mode == self.MODE_ROOM_PICK:
                self.handle_room_pick_inputs()
            elif self.mode == self.MODE_ARCADE_MENU:
                self.handle_arcade_menu_inputs()
            elif self.mode == self.MODE_HEART_CATCH_READY:
                self.handle_heart_ready_inputs()
            elif self.mode == self.MODE_HEART_CATCH_PLAY:
                self.handle_heart_play_inputs(dt_ms)
            elif self.mode == self.MODE_HEART_CATCH_RESULT:
                self.handle_heart_result_inputs()
            elif self.mode == self.MODE_GAME_OVER:
                self.handle_game_over_inputs()

            self.autosave_if_needed(now_ms)
            self.draw(self.pet.snapshot())
            time.sleep_ms(FRAME_MS)


def main():
    app = PocketRPicoApp()
    app.run()


if __name__ == "__main__":
    main()
