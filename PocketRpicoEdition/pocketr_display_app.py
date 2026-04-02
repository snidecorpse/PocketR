
from machine import Pin, SPI
import time
import framebuf

from pocketr_pet import PocketRPet, ROOMS


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
RED = rgb565(255, 0, 0)
GREEN = rgb565(0, 255, 0)
BLUE = rgb565(0, 90, 255)
YELLOW = rgb565(255, 255, 0)
CYAN = rgb565(0, 255, 255)
GRAY = rgb565(70, 70, 70)
DARK = rgb565(20, 20, 20)


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
        self.write_data(b'\x05')
        time.sleep_ms(10)

        # Locked orientation requested for project
        self.write_cmd(0x36)
        self.write_data(b'\x08')

        self.write_cmd(0xB1)
        self.write_data(b'\x01\x2C\x2D')

        self.write_cmd(0xB2)
        self.write_data(b'\x01\x2C\x2D')

        self.write_cmd(0xB3)
        self.write_data(b'\x01\x2C\x2D\x01\x2C\x2D')

        self.write_cmd(0xB4)
        self.write_data(b'\x07')

        self.write_cmd(0xC0)
        self.write_data(b'\xA2\x02\x84')

        self.write_cmd(0xC1)
        self.write_data(b'\xC5')

        self.write_cmd(0xC2)
        self.write_data(b'\x0A\x00')

        self.write_cmd(0xC3)
        self.write_data(b'\x8A\x2A')

        self.write_cmd(0xC4)
        self.write_data(b'\x8A\xEE')

        self.write_cmd(0xC5)
        self.write_data(b'\x0E')

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
            Pin(15, Pin.IN, Pin.PULL_UP),  # KEY0
            Pin(17, Pin.IN, Pin.PULL_UP),  # KEY1
            Pin(2, Pin.IN, Pin.PULL_UP),   # KEY2
            Pin(3, Pin.IN, Pin.PULL_UP),   # KEY3
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


def short_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def split_message(text, width=16):
    if text is None:
        return ["", ""]
    text = str(text).replace("\n", " ").strip()
    if len(text) <= width:
        return [text, ""]
    cut = text.rfind(" ", 0, width + 1)
    if cut <= 0:
        cut = width
    line1 = text[:cut].strip()
    line2 = text[cut:].strip()
    if len(line2) > width:
        line2 = line2[:width - 1] + "…"
    return [line1, line2]


class PocketRDisplayApp:
    MODE_ACTION = 0
    MODE_MOVE = 1

    def __init__(self):
        self.lcd = LCD_1in44()
        self.buttons = Buttons()
        self.pet = PocketRPet()
        self.pet.load()

        self.mode = self.MODE_ACTION
        self.selection = 0
        self.flash_text = ""
        self.flash_until = 0
        self.last_save_ms = time.ticks_ms()

    def set_flash(self, text, ms=2000):
        self.flash_text = str(text)
        self.flash_until = time.ticks_add(time.ticks_ms(), ms)

    def current_move_options(self):
        snap = self.pet.snapshot()
        room = snap["room"]
        info = ROOMS.get(room, {})
        neighbors = info.get("neighbors", {})
        options = []
        for direction in ("LEFT", "RIGHT", "UP", "DOWN"):
            if direction in neighbors:
                options.append((direction, neighbors[direction]))
        return options

    def current_action_options(self):
        return self.pet.available_actions()

    def current_options_count(self):
        if self.mode == self.MODE_ACTION:
            return len(self.current_action_options())
        return len(self.current_move_options())

    def clamp_selection(self):
        count = self.current_options_count()
        if count <= 0:
            self.selection = 0
            return
        if self.selection >= count:
            self.selection = count - 1
        if self.selection < 0:
            self.selection = 0

    def cycle_left(self):
        count = self.current_options_count()
        if count <= 0:
            return
        self.selection = (self.selection - 1) % count

    def cycle_right(self):
        count = self.current_options_count()
        if count <= 0:
            return
        self.selection = (self.selection + 1) % count

    def confirm(self):
        if self.mode == self.MODE_ACTION:
            actions = self.current_action_options()
            if not actions:
                self.set_flash("No actions here")
                return
            action = actions[self.selection]
            result = self.pet.do_action(action)
            self.set_flash(result["message"])
        else:
            moves = self.current_move_options()
            if not moves:
                self.set_flash("No room there")
                return
            direction, destination = moves[self.selection]
            result = self.pet.move(direction)
            self.set_flash(result["message"])
        self.clamp_selection()

    def update_inputs(self):
        self.buttons.update()

        if self.buttons.just_pressed(3):
            if self.mode == self.MODE_ACTION:
                self.mode = self.MODE_MOVE
            else:
                self.mode = self.MODE_ACTION
            self.selection = 0
            self.set_flash("MODE ACTION" if self.mode == self.MODE_ACTION else "MODE MOVE", 900)

        if self.buttons.just_pressed(0):
            self.cycle_left()

        if self.buttons.just_pressed(1):
            self.cycle_right()

        if self.buttons.just_pressed(2):
            self.confirm()

    def autosave_if_needed(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_save_ms) >= 15000:
            self.pet.save()
            self.last_save_ms = now

    def draw_button_box(self, x, label, pressed):
        fill = GREEN if pressed else GRAY
        text = BLACK if pressed else WHITE
        self.lcd.fill_rect(x, 104, 29, 22, fill)
        self.lcd.rect(x, 104, 29, 22, WHITE)
        self.lcd.text(label, x + 6, 111, text)

    def draw(self):
        snap = self.pet.tick()
        self.lcd.fill(DARK)

        # Top header
        self.lcd.fill_rect(0, 0, 128, 14, BLUE)
        room = str(snap["room"])
        room_x = 64 - (len(room) * 4)
        if room_x < 0:
            room_x = 0
        self.lcd.text(room, room_x, 3, WHITE)

        # Main stats
        self.lcd.text("Mood:" + str(snap["mood_word"]), 0, 18, YELLOW if snap["alive"] else RED)
        self.lcd.text("HP%02d H%02d E%02d" % (
            short_int(snap["health"]),
            short_int(snap["hunger"]),
            short_int(snap["energy"]),
        ), 0, 28, WHITE)
        self.lcd.text("Y%02d S%02d F%02d" % (
            short_int(snap["hygiene"]),
            short_int(snap["social"]),
            short_int(snap["fun"]),
        ), 0, 38, WHITE)
        self.lcd.text("B%02d M%02d %s" % (
            short_int(snap["bladder"]),
            short_int(snap["mood"]),
            str(snap["age_label"]),
        ), 0, 48, WHITE)

        # Current mode and selected thing
        if self.mode == self.MODE_ACTION:
            self.lcd.text("MODE: ACTION", 0, 62, CYAN)
            options = self.current_action_options()
            if options:
                selected = options[self.selection]
            else:
                selected = "-"
            line1, line2 = split_message(selected, 16)
            self.lcd.text(line1, 0, 72, GREEN)
            self.lcd.text(line2, 0, 82, GREEN)
        else:
            self.lcd.text("MODE: MOVE", 0, 62, CYAN)
            options = self.current_move_options()
            if options:
                direction, destination = options[self.selection]
                selected = direction + "->" + destination
            else:
                selected = "-"
            line1, line2 = split_message(selected, 16)
            self.lcd.text(line1, 0, 72, GREEN)
            self.lcd.text(line2, 0, 82, GREEN)

        # Message area
        if time.ticks_diff(self.flash_until, time.ticks_ms()) > 0:
            msg = self.flash_text
        else:
            msg = snap["last_message"]

        m1, m2 = split_message(msg, 16)
        self.lcd.text(m1, 0, 92, YELLOW if snap["alive"] else RED)

        # Button hint row
        self.draw_button_box(2, "<", self.buttons.pressed(0))
        self.draw_button_box(34, ">", self.buttons.pressed(1))
        self.draw_button_box(66, "OK", self.buttons.pressed(2))
        self.draw_button_box(98, "TAB", self.buttons.pressed(3))

        self.lcd.show()

    def run(self):
        self.set_flash("PocketR ready", 1200)
        while True:
            self.update_inputs()
            self.autosave_if_needed()
            self.draw()
            time.sleep_ms(80)


app = PocketRDisplayApp()
app.run()
