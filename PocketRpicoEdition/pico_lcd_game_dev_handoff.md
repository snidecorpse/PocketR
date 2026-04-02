# Pico-LCD-1.44 + Pico 2 W Game Dev Handoff

This document is the **hardware handoff** for the Pico 2 W + Waveshare **Pico-LCD-1.44** setup.

The goal is simple:

- get the **screen working**
- get the **4 buttons working**
- lock the display orientation to **`0x08`**
- give game developers a tiny, reusable platform layer
- let game developers focus on **game logic**, not SPI pins, LCD init, or button scanning

---

## 1) Hardware summary

Display module: **Waveshare Pico-LCD-1.44**

Important hardware details:

- controller: **ST7735S**
- resolution: **128 x 128**
- interface: **SPI**
- color mode used: **RGB565**

Pin mapping used on Pico / Pico 2 / Pico 2 W:

- `DIN` -> `GP11`
- `CLK` -> `GP10`
- `CS` -> `GP9`
- `DC` -> `GP8`
- `RST` -> `GP12`
- `BL` -> `GP13`
- `KEY0` -> `GP15`
- `KEY1` -> `GP17`
- `KEY2` -> `GP2`
- `KEY3` -> `GP3`

Buttons are **active low**:
- pressed = pin reads `0`
- released = pin reads `1`

---

## 2) Recommended project structure

Use this structure on the Pico:

```text
/display.py
/buttons.py
/platform_hw.py
/main.py
/game.py
```

### Responsibility split

- `display.py`
  - owns LCD init
  - owns SPI
  - owns drawing buffer
  - exposes simple drawing helpers

- `buttons.py`
  - owns key pin setup
  - owns polling
  - exposes `pressed`, `just_pressed`, `just_released`

- `platform_hw.py`
  - combines display + buttons
  - gives game code a single clean interface

- `game.py`
  - game logic only

- `main.py`
  - startup entry point

---

## 3) Display orientation

For this setup, lock orientation to:

```python
self.write_cmd(0x36)
self.write_data(b'\x08')
```

That is the orientation baseline for development.

Do **not** let each game change this unless there is a real reason.
Keep a single known orientation so asset placement and button mapping stay consistent.

---

## 4) Drop-in `display.py`

This is a reusable MicroPython display driver for the LCD.

```python
from machine import Pin, SPI
import time
import framebuf


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
RED = rgb565(255, 0, 0)
GREEN = rgb565(0, 255, 0)
BLUE = rgb565(0, 0, 255)
YELLOW = rgb565(255, 255, 0)
CYAN = rgb565(0, 255, 255)
GRAY = rgb565(80, 80, 80)


class PicoLCD144(framebuf.FrameBuffer):
    WIDTH = 128
    HEIGHT = 128

    # visible area offset for this panel
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
            miso=None
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
        self.write_cmd(0x01)  # SWRESET
        time.sleep_ms(150)

        self.write_cmd(0x11)  # SLPOUT
        time.sleep_ms(150)

        self.write_cmd(0x3A)  # COLMOD
        self.write_data(b'\x05')  # RGB565
        time.sleep_ms(10)

        self.write_cmd(0x36)  # MADCTL
        self.write_data(b'\x08')  # fixed orientation for project

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

        self.write_cmd(0x21)  # INVON
        self.write_cmd(0x13)  # NORON
        time.sleep_ms(10)

        self.write_cmd(0x29)  # DISPON
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

    def clear(self, color=BLACK):
        self.fill(color)

    def backlight(self, on=True):
        self.bl.value(1 if on else 0)
```

---

## 5) Drop-in `buttons.py`

This module gives developers a clean input layer.

```python
from machine import Pin


class Buttons:
    def __init__(self):
        self.key0 = Pin(15, Pin.IN, Pin.PULL_UP)
        self.key1 = Pin(17, Pin.IN, Pin.PULL_UP)
        self.key2 = Pin(2, Pin.IN, Pin.PULL_UP)
        self.key3 = Pin(3, Pin.IN, Pin.PULL_UP)

        self.current = [False, False, False, False]
        self.previous = [False, False, False, False]

    def read_raw(self):
        return [
            self.key0.value() == 0,
            self.key1.value() == 0,
            self.key2.value() == 0,
            self.key3.value() == 0,
        ]

    def update(self):
        self.previous = self.current[:]
        self.current = self.read_raw()

    def pressed(self, index):
        return self.current[index]

    def just_pressed(self, index):
        return self.current[index] and not self.previous[index]

    def just_released(self, index):
        return (not self.current[index]) and self.previous[index]

    def any_pressed(self):
        return (
            self.current[0] or
            self.current[1] or
            self.current[2] or
            self.current[3]
        )

    def get_pressed_list(self):
        out = []
        for i in range(4):
            if self.current[i]:
                out.append(i)
        return out
```

---

## 6) Drop-in `platform_hw.py`

This is the layer game developers should import.

```python
import time
from display import PicoLCD144, BLACK, WHITE, GREEN, RED, YELLOW, CYAN
from buttons import Buttons


class PlatformHW:
    def __init__(self):
        self.lcd = PicoLCD144()
        self.buttons = Buttons()

    def update_inputs(self):
        self.buttons.update()

    def begin_frame(self, color=BLACK):
        self.lcd.clear(color)

    def end_frame(self):
        self.lcd.show()

    def draw_debug_buttons(self):
        labels = ["K0", "K1", "K2", "K3"]
        box_y = 104
        box_w = 29
        box_h = 20
        gap = 3

        for i in range(4):
            x = 2 + i * (box_w + gap)

            if self.buttons.pressed(i):
                fill = GREEN
                text = BLACK
            else:
                fill = RED
                text = WHITE

            self.lcd.fill_rect(x, box_y, box_w, box_h, fill)
            self.lcd.rect(x, y=box_y, w=box_w, h=box_h, c=WHITE)
            self.lcd.text(labels[i], x + 7, box_y + 6, text)

    def splash(self):
        self.begin_frame()
        self.lcd.text("PICO LCD READY", 8, 20, YELLOW)
        self.lcd.text("BUTTONS READY", 12, 40, CYAN)
        self.lcd.text("ORIENTATION 0x08", 4, 60, WHITE)
        self.end_frame()
        time.sleep_ms(800)
```

### If keyword arguments cause issues in your MicroPython build

Replace this line:

```python
self.lcd.rect(x, y=box_y, w=box_w, h=box_h, c=WHITE)
```

with:

```python
self.lcd.rect(x, box_y, box_w, box_h, WHITE)
```

That version is safer.

---

## 7) Drop-in `main.py`

This is a clean hardware test and starter loop.

```python
import time
from platform_hw import PlatformHW
from display import BLACK, WHITE, YELLOW, CYAN, GREEN


hw = PlatformHW()
hw.splash()

while True:
    hw.update_inputs()

    hw.begin_frame(BLACK)
    hw.lcd.text("GAME PLATFORM TEST", 2, 10, WHITE)
    hw.lcd.text("PRESS ANY KEY", 16, 28, YELLOW)

    if hw.buttons.just_pressed(0):
        hw.lcd.text("KEY0 OK", 34, 52, GREEN)
    elif hw.buttons.just_pressed(1):
        hw.lcd.text("KEY1 OK", 34, 52, GREEN)
    elif hw.buttons.just_pressed(2):
        hw.lcd.text("KEY2 OK", 34, 52, GREEN)
    elif hw.buttons.just_pressed(3):
        hw.lcd.text("KEY3 OK", 34, 52, GREEN)
    else:
        hw.lcd.text("WAITING...", 30, 52, CYAN)

    hw.draw_debug_buttons()
    hw.end_frame()

    time.sleep_ms(40)
```

---

## 8) What game developers should use

Game developers should **not** deal with:

- SPI pins
- LCD reset sequence
- MADCTL
- ST7735S commands
- direct GPIO key reads

Game developers should only use:

```python
hw.update_inputs()
hw.buttons.pressed(0)
hw.buttons.just_pressed(1)
hw.begin_frame()
hw.lcd.text(...)
hw.lcd.fill_rect(...)
hw.end_frame()
```

That is the contract.

---

## 9) Minimal game-facing API contract

Developers building games should rely on this behavior:

### Input
- `hw.buttons.pressed(i)`  
  returns `True` while button is held

- `hw.buttons.just_pressed(i)`  
  returns `True` for one update only when button is newly pressed

- `hw.buttons.just_released(i)`  
  returns `True` for one update only when button is released

### Drawing
- `hw.begin_frame(color)`
- draw to `hw.lcd`
- `hw.end_frame()`

### Button indexes
Use this consistent mapping everywhere:

- `0` -> KEY0 -> GP15
- `1` -> KEY1 -> GP17
- `2` -> KEY2 -> GP2
- `3` -> KEY3 -> GP3

If the design team wants semantic names, define:

```python
BTN_A = 0
BTN_B = 1
BTN_X = 2
BTN_Y = 3
```

or

```python
BTN_UP = 0
BTN_DOWN = 1
BTN_LEFT = 2
BTN_RIGHT = 3
```

Do that once and keep it consistent per game.

---

## 10) Example game stub for devs

This is what game code should look like.

```python
from display import WHITE, BLACK, GREEN


class Game:
    def __init__(self, hw):
        self.hw = hw
        self.x = 60
        self.y = 60

    def update(self):
        if self.hw.buttons.just_pressed(0):
            self.x -= 5
        if self.hw.buttons.just_pressed(1):
            self.x += 5
        if self.hw.buttons.just_pressed(2):
            self.y -= 5
        if self.hw.buttons.just_pressed(3):
            self.y += 5

        if self.x < 0:
            self.x = 0
        if self.x > 118:
            self.x = 118
        if self.y < 0:
            self.y = 0
        if self.y > 118:
            self.y = 118

    def draw(self):
        self.hw.begin_frame(BLACK)
        self.hw.lcd.text("GAME TEST", 30, 10, WHITE)
        self.hw.lcd.fill_rect(self.x, self.y, 10, 10, GREEN)
        self.hw.end_frame()
```

And the app runner:

```python
import time
from platform_hw import PlatformHW
from game import Game

hw = PlatformHW()
game = Game(hw)

while True:
    hw.update_inputs()
    game.update()
    game.draw()
    time.sleep_ms(40)
```

---

## 11) Rules for the dev team

### Rule 1
Do not reinitialize the display inside game code.

### Rule 2
Do not access raw key pins from game code.

### Rule 3
Do not change the orientation from `0x08` unless the whole project agrees.

### Rule 4
Keep a single update loop:
- poll input
- update game state
- draw frame
- sleep a little

### Rule 5
Prefer `just_pressed()` for menu navigation and one-shot actions.

### Rule 6
Prefer `pressed()` for held movement if smooth hold behavior is wanted.

---

## 12) Quick test checklist

Before handing hardware to game developers, verify:

- screen turns on
- text appears
- orientation is correct with `0x08`
- all 4 buttons register
- `KEY0`
- `KEY1`
- `KEY2`
- `KEY3`
- screen updates without crashing
- main loop runs continuously

---

## 13) Fast troubleshooting

### Black screen
Check:
- board orientation on header
- `BL` backlight pin
- SPI pins
- power

### White or strange screen
Check:
- display init sequence
- SPI speed
- wrong controller assumptions

### Buttons not responding
Check:
- buttons are active low
- using `Pin.PULL_UP`
- reading `pin.value() == 0` for pressed

### Screen works but game flickers
Check:
- drawing whole frame once
- calling `show()` once per frame
- avoiding extra `show()` calls in helper functions

---

## 14) Final handoff summary

The foundation layer is:

- `display.py` for LCD setup and drawing
- `buttons.py` for key input
- `platform_hw.py` for unified hardware access

The game team should build only on top of that.

They should treat the hardware layer as stable and use it like a small engine.

That keeps development clean and avoids each game re-solving:
- LCD init
- orientation
- button reads
- frame rendering basics
