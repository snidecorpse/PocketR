Perfect question — this is exactly where you *lock the architecture* so future-you doesn’t accidentally break boot at 3am 😄
Below is a **fully fleshed-out `game/README_GAME.md`** you can drop in as-is.

You don’t need to change anything else.

---

```md
# Pocket-R Game Module Guide

This folder (`game/`) contains **ALL real game logic, assets, and behavior**.

The rest of the repository (especially `app.py` and `deploy/`) is considered
**system-critical boot infrastructure** and should be treated as stable.

If Pocket-R boots, but your game crashes → the launcher will catch it and
display an error screen instead of breaking autoboot.

---

## 🚦 Golden Rule (DO NOT BREAK BOOT)
**Never change `app.py` to add game logic.**

- `app.py` is a **stable launcher / engine**
- Your game lives entirely inside `game/`
- systemd always runs `python3 app.py`
- If `game/` is broken, Pocket-R still boots safely

Think of `app.py` like firmware and `game/` like a cartridge.

---

## 📁 Required Folder Structure
```

game/
**init**.py
main.py              # REQUIRED entry point
assets/
sprites/
ui/
fonts/
sounds/

````

You may add subfolders freely **inside `game/`**.

---

## 🎮 Game Contract (MANDATORY)
Your `game/main.py` **must** define:

```python
def render(ctx) -> PIL.Image.Image
````

That’s it.
Everything else is optional.

If `render()` is missing, the launcher will crash the game and show an error screen.

---

## 🔁 Optional Lifecycle Hooks

You *may* also define:

```python
def init(ctx):          # runs once at boot
def update(ctx, dt, ev) # runs every frame before render
```

### Call Order

```
init(ctx)        # once
loop:
  update(ctx, dt, ev)
  render(ctx)
```

---

## 🧠 The `ctx` Object (Your Interface to the System)

You **must only interact with hardware via `ctx`**.

### Available Fields

```python
ctx.disp        # ST7789 display object (DO NOT re-init or exit it)
ctx.inputs      # input edge tracker
ctx.font_s      # small font
ctx.font_m      # medium font
ctx.font_l      # large font

ctx.base_dir    # absolute path to repo root
ctx.game_dir    # absolute path to ./game
ctx.user        # persistent dict for game state
```

### Persistent Game State

Use `ctx.user` to store:

* stats (hunger, happiness, etc.)
* current room
* timers
* flags

Example:

```python
ctx.user["hunger"] = 50
ctx.user["room"] = "BED"
```

This dict persists across frames.

---

## 🖼 Assets (Sprites, Images, Fonts)

All assets **must live inside `game/assets/`**.

Use the helper:

```python
path = ctx.asset("sprites", "pet_idle.png")
```

⚠️ **Never use relative paths** like `"../"` or `"./"`
systemd does NOT guarantee the working directory.

---

## 🎛 Inputs (Buttons & Joystick)

### Event Dictionary (`ev`)

Passed into `update(ctx, dt, ev)`.

Keys appear **only on edges** (not held continuously):

```
"UP", "DOWN", "LEFT", "RIGHT"
"PRESS"          # joystick center
"K1", "K2", "K3"

"PRESS_UP", "K1_UP", etc.
```

Example:

```python
if "LEFT" in ev:
    ctx.user["room"] = "BED"
```

### Held State

If you need to check whether something is currently held:

```python
ctx.inputs.is_down("PRESS")
```

---

## ⏱ Timing

* `dt` = seconds since last frame (clamped)
* Do NOT assume fixed FPS
* All animations should be time-based, not frame-based

Bad ❌:

```python
x += 1
```

Good ✅:

```python
x += speed * dt
```

---

## 🔌 Power Management (IMPORTANT)

### Shutdown Gesture (GLOBAL)

* Holding **joystick PRESS for 10 seconds** triggers a **real Linux shutdown**
* This is handled by the launcher
* **Do NOT re-implement shutdown logic in the game**

You *may* show UI feedback using:

```python
ctx.user["shutdown_holding"]          # bool
ctx.user["shutdown_hold_seconds"]     # float
```

Example:

```python
if ctx.user["shutdown_holding"]:
    remaining = 10 - ctx.user["shutdown_hold_seconds"]
```

### Manual Shutdown (Advanced)

If your game runs its **own loop** (see below), you must call:

```python
ctx.request_poweroff()
```

---

## 🔄 Two Allowed Game Models

### 1️⃣ Engine-Driven Mode (RECOMMENDED)

You provide:

* `update(ctx, dt, ev)`
* `render(ctx)`

Launcher handles:

* FPS pacing
* input polling
* shutdown gesture
* display output

This is safest.

---

### 2️⃣ Custom Loop Mode (ADVANCED)

If `game/main.py` defines:

```python
def run(ctx):
    ...
```

Then:

* Launcher hands over control completely
* YOU must:

  * call `ctx.request_poweroff()` yourself
  * manage frame pacing
  * call `ctx.show(img)` manually

Only do this if you *really* need it.

---

## 🧯 Crash Behavior (Fail-Safe)

If your game throws an exception:

* Launcher catches it
* LCD shows **GAME CRASH**
* Error is logged to:

```bash
journalctl -u pocketr.service
```

This prevents boot loops and SD corruption.

---

## 🚫 Forbidden Actions (DO NOT DO THESE)

❌ Re-initialize the display
❌ Call `disp.Init()` or `disp.module_exit()`
❌ Call `os.system("shutdown")` directly
❌ Block the main loop for long periods
❌ Use infinite loops inside `update()`
❌ Modify GPIO pin modes directly

All of these can:

* break autoboot
* cause black screens
* corrupt SD card

---

## 🧪 Testing on the Pi

```bash
cd ~/pocketr
git pull
sudo systemctl restart pocketr.service
journalctl -u pocketr.service -n 200 --no-pager
```

---

