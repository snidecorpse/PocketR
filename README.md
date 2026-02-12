# PocketR

PocketR is a Raspberry Pi handheld UI/OS shell for a 240x240 LCD HAT.  
It boots into a game-style launcher, runs app modules from `game/apps/`, and supports safe shutdown/update flows on-device.

This README is the full project map for development, deployment, customization, and debugging.

## 1) What This Project Does

PocketR provides:
- A stable hardware launcher (`app.py`) for ST7789 + GPIO inputs.
- A modular OS shell (`game/main.py`) with app selection and transitions.
- Built-in apps:
  - Pet Game (`game/apps/pet_game.py`)
  - Gallery (`game/apps/blank.py`)
  - Settings (`game/apps/settings.py`)
  - Updater (`game/apps/updater.py`)
- Shared UI helpers (`game/ui_common.py`) and image assets (`game/assets/`).
- Linux deployment scripts (`deploy/`) for autoboot and update integration.

## 2) Hardware + Runtime Model

### Display/Input
- Display driver: `ST7789.py`
- Resolution: `240 x 240`
- Inputs:
  - Joystick directions: `UP`, `DOWN`, `LEFT`, `RIGHT`
  - Joystick center press: `PRESS`
  - Buttons: `K1`, `K2`, `K3`

### Core Input Semantics
`app.py` emits edge events:
- press edge: `K1`, `K2`, `K3`, `PRESS`, `UP`, etc.
- release edge: `K1_UP`, `K2_UP`, `K3_UP`, etc.

Held-state checks are available through `ctx.inputs.is_down("KEY")`.

### Safe Shutdown
- Global behavior in launcher + game shell: hold `K3` for ~3 seconds.
- Triggers `ctx.request_poweroff()`.
- On desktop runner, poweroff is simulated by exiting.

## 3) Repository Layout

```text
PocketR/
  app.py                     # Stable Pi launcher/engine (hardware loop)
  desktop_run.py             # Desktop simulator (keyboard + pygame)
  config.py                  # Driver configuration helpers
  ST7789.py                  # LCD HAT driver
  requirements.txt
  .pocketr/                  # Local runtime data (desktop); Pi uses /root/.pocketr/
    settings.json
    pet/state.json
    update/last_update.json

  game/
    main.py                  # PocketR OS shell: intro/home/app routing
    ui_common.py             # Shared rendering/UI utilities
    apps/
      pet_game.py            # Tamagotchi-style simulation
      blank.py               # Gallery app (slide/grid)
      settings.py            # Settings/help/debug/shutdown panels
      updater.py             # Update app UI + process control
    scripts/
      update_repo.sh         # Git pull helper invoked by updater app
    assets/
      ui/                    # Intro, icon tiles, non-pet app bg
      blank_gallery/         # Gallery images
      pet_game/              # Pet sprites + editable dialogue JSON

  deploy/
    *.service.in
    *.sh
    README_DEPLOY.md
```

## 4) Launcher and Engine (`app.py`)

`app.py` is intentionally stable so systemd startup does not break when game logic changes.

Responsibilities:
- Initialize ST7789 display + backlight.
- Read GPIO button/joystick edges each frame.
- Build a `Ctx` object passed to game modules.
- Load and hot-apply settings from persistent `settings.json` (default path: `/root/.pocketr/settings.json`):
  - `brightness`
  - `target_fps`
- Run the game module loop via `game.main` (`init/update/render`).
- Enforce global hold-to-shutdown.

### Context object (`Ctx`)
Important fields/methods used by apps:
- `ctx.disp` display object
- `ctx.inputs` edge + held input helper
- `ctx.font_s`, `ctx.font_m`, `ctx.font_l`
- `ctx.base_dir`, `ctx.game_dir`, `ctx.data_dir`
- `ctx.user` persistent app/session state dictionary
- `ctx.asset(*parts)` absolute path to `game/assets/...`
- `ctx.data_path(*parts)` absolute path to persistent runtime files
- `ctx.show(img)` draw image to LCD
- `ctx.request_poweroff()` shutdown helper

## 5) OS Shell (`game/main.py`)

Modes:
- `INTRO`
- `INTRO_OUT`
- `HOME`
- `APP`

Behavior:
- Displays intro image + animated square glow ring during loading.
- Fades into a 2x2 app selector grid.
- Opens selected app on `K1` or joystick `PRESS`.
- Returns from app when app module `update()` returns `True`.
- Applies global K3 hold progress overlay.

### Menu map
`MENU_MODULES`:
- `0 -> game.apps.pet_game`
- `1 -> game.apps.blank`
- `2 -> game.apps.settings`
- `3 -> game.apps.updater`

## 6) App Details

## 6.1) Pet Game (`game/apps/pet_game.py`)

Current implementation is a room-based tamagotchi simulation.

### Core mechanics
- Joystick held directions move the pet sprite continuously.
- Crossing room boundaries transitions to connected rooms.
- Stats decay over time using weighted risk logic.
- Health can recover when care stats stay high.
- If health reaches zero, pet dies and restart prompt appears.

### Tracked stats (0..100)
- `health`
- `hunger`
- `energy`
- `hygiene`
- `social`
- `fun`
- `bladder`
- `mood`

### Decay/health model
Each frame, the simulation:
1. Applies base stat decay rates.
2. Adds movement and pose modifiers.
3. Computes penalties for critical low stats.
4. Applies stacked penalty if multiple vitals are low at once.
5. Applies health recovery when core needs are healthy.
6. Smoothly updates mood using weighted stat targets.
7. Triggers death state at `health <= 0`.

### Rooms and transitions
Configured graph:
- Main Hall (`HUB`): central junction
- Right from Hall: Bedroom
- Down from Hall: Living Room
- Up from Hall: Bathroom
- Left from Hall: Arcade

Note: this mapping uses left for Arcade so all four directions are uniquely mapped.

### Room actions
- Hall: `Check In`, `Stretch`, `Save & Quit`
- Bedroom: `Cuddle`, `Give Hug`, `Sleep`
- Living Room: `Watch TV`, `Lounge`, `Talk`, `Open Gallery`
- Arcade: `Brick Breaker`, `Memory Match`, `Runner Dash`
- Bathroom: `Use Toilet`, `Shower`

### Arcade mini-games
- Brick Breaker now has progressive levels (`L1` to `L3`) with increasing brick density/speed.
- Mini-game play area renders on a full black gameplay canvas (not semi-opaque over room art).

### Talk system
- Dialogue is loaded from `game/assets/pet_game/dialogue.json`.
- JSON keys are categories (for example `greeting`, `feelings`, `plans`, `jokes`).
- Values are arrays of conversation entries:
  - `player` text
  - `pet` text
  - optional stat effects (`social`, `fun`)

### Sprites
Loaded from `game/assets/pet_game/`:
- `idle.png`
- `walk1.png`
- `walk2.png`
- `sleep.png`
- `shower.png`
- `toilet.png`

These are placeholder art; replace with your own sprite sheets/assets as needed.

### Controls in pet game
- Move: joystick directions (held)
- Open action panel: `B1` or joystick `PRESS`
- Confirm panel item: `B1`
- `B2` short: quick supportive interaction (or close panel)
- `B2` long (~1.2s): reopen tutorial slides
- `B3` short: quick care action
- Global `B3` hold still performs OS shutdown

## 6.2) Gallery (`game/apps/blank.py`)

Gallery modes:
- `SLIDE` mode
- `GRID` mode

Features:
- Auto scan images from `game/assets/blank_gallery/`
- Slide animation timing from Settings
- Auto-scroll timing from Settings
- Optional filename overlay support
- Updated panel/card UI to match current launcher style

Controls vary slightly by mode:
- `B2` exits (or leaves focus mode in grid)
- Joystick moves selection
- `B1`/`PRESS` confirms/focuses depending on mode

## 6.3) Settings (`game/apps/settings.py`)

Settings sections:
- `Controls & Help`
- `Brightness`
- `Shutdown`
- `Show FPS`
- `Pet Game Settings`
- `Gallery Settings`
- `Target FPS`
- `Source`
- `Debug`

### Persistence
Settings are saved to:
- `/root/.pocketr/settings.json` (Pi default)
- `./.pocketr/settings.json` fallback on desktop/dev machines

### Gallery settings keys
- `gallery_mode`: `SLIDE` or `GRID`
- `gallery_auto_scroll`: bool
- `gallery_auto_seconds`: float
- `gallery_swipe_seconds`: float
- `gallery_show_filename`: bool

### Rendering details
- Rows are rendered inside panel cards.
- Small inline bars display values for brightness/fps and gallery timings.

## 6.4) Updater (`game/apps/updater.py`)

Purpose:
- Launch update script.
- Show progress/log tail.
- Reboot after successful update.

Flow:
1. User confirms update.
2. App discovers repo root candidates (including `/root/PocketR`).
3. Runs `game/scripts/update_repo.sh` with selected repo path.
4. Captures output to `/tmp/pocketr_update.log`.
5. On success, triggers reboot attempts.

UI intentionally avoids long path dumps to keep small-screen readability.

## 7) Shared UI (`game/ui_common.py`)

Contains reusable helpers for:
- App background loading/fallback generation.
- Text wrapping.
- Overlay panel rendering.
- Progress bars and interpolation helpers.
- Intro/home visual effects support.

`game/assets/ui/app_bg.png` is the base background for non-pet apps.

## 8) Assets and Customization

## 8.1) Replace app icons
Icons used on launcher grid:
- `game/assets/ui/icon_1.png`
- `game/assets/ui/icon_2.png`
- `game/assets/ui/icon_3.png`
- `game/assets/ui/icon_4.png`

## 8.2) Replace intro art
- `game/assets/ui/intro.png`

## 8.3) Replace non-pet background
- `game/assets/ui/app_bg.png`

## 8.4) Gallery content
Drop images into:
- `game/assets/blank_gallery/`

## 8.5) Pet assets
- Sprite placeholders in `game/assets/pet_game/`
- Dialogue categories in `game/assets/pet_game/dialogue.json`

## 9) Running the Project

## 9.1) Raspberry Pi runtime
Main entrypoint:
```bash
python3 app.py
```

For service/autoboot setup, use scripts in `deploy/`.

## 9.2) Desktop simulation
```bash
python3 desktop_run.py
```
Optional flags:
```bash
python3 desktop_run.py --scale 3 --fps 30
```

Desktop control mapping:
- arrows or WASD -> joystick directions
- Enter/Space -> `PRESS`
- `1` -> `K1`
- `2` -> `K2`
- `3` -> `K3`
- `R` hot reloads game modules
- `Esc`/`Q` quits

## 10) Deployment Notes (`deploy/`)

`deploy/` contains scripts/service templates for:
- enabling/disabling autoboot
- splash/update service hooks
- poweroff backlight integration
- optional USB update support

Read:
- `deploy/README_DEPLOY.md`

## 11) Update Script (`game/scripts/update_repo.sh`)

Script behavior:
- Accepts repo path arg or `POCKETR_REPO` env.
- Falls back to common PocketR paths.
- Normalizes path and walks upward to find git root.
- Runs:
  - `git pull --rebase --autostash`
- Outputs status for updater UI log tail.

Updater app behavior:
- Uses `settings.json` source mode:
  - `AUTO`: discover candidate repos automatically.
  - `PRESET`: start from selected preset path, then fallback chain.
- Execution order:
  1. direct `git -C <repo> pull --rebase --autostash`
  2. `game/scripts/update_repo.sh` fallback for the same repo
  3. next candidate path in chain
- Persists attempt history in `/root/.pocketr/update/last_update.json`.

## 12) Configuration File Reference (`/root/.pocketr/settings.json`)

Typical file:
```json
{
  "brightness": 60,
  "target_fps": 15,
  "show_fps": false,
  "gallery_mode": "SLIDE",
  "gallery_auto_scroll": true,
  "gallery_auto_seconds": 3.2,
  "gallery_swipe_seconds": 0.22,
  "gallery_show_filename": true,
  "updater_source_mode": "AUTO",
  "updater_source_value": "/root/PocketR",
  "pet_game": {
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
    "show_tutorial_next_open": false
  }
}
```

If missing, defaults are rebuilt in Settings app.

## 13) Development Workflow

Recommended loop:
1. Edit files under `game/` for app/UI gameplay changes.
2. Run desktop simulation for fast iteration.
3. Validate on Pi for true LCD/input behavior.
4. Persist settings/asset changes as needed.

For quick syntax validation:
```bash
python3 -m py_compile app.py game/main.py game/apps/*.py game/ui_common.py
```

## 14) Troubleshooting

## Issue: updater says path is not a git repo
- Ensure install path is a real clone (not copied zip folder).
- Verify `.git/` exists in target PocketR directory.
- Confirm updater candidates include actual deployment path (typically `/root/PocketR`).

## Issue: text clipping on 240x240
- Keep labels short.
- Use wrapped text blocks in panels.
- Avoid exposing long filesystem paths in UI.

## Issue: controls not responding
- Check GPIO pin mapping in ST7789/HAT wiring.
- Confirm `ACTIVE_HIGH` behavior in `app.py` matches hardware.

## Issue: splash or launcher art missing
- Confirm files exist in `game/assets/ui/` and are readable.
- App will fallback to generated visuals where possible.

## 15) Roadmap Hooks

Natural next expansion points:
- Replace placeholder pet sprites with animated frames/sheets.
- Add mini-games launched from Arcade panel.
- Extend `dialogue.json` with deeper branching and stat effects.
- Persist long-term pet state to disk (optional save file).
- Add richer pet AI scheduling (day/night personality behavior).

## 16) Safety Notes

- Prefer software shutdown (`K3` hold or shutdown action) before power cut.
- Do not cut power during update/pull/reboot cycle.
- Keep a known-good branch/tag for quick rollback in field deployments.

---
If you want, next pass can include a dedicated `PET_GAME_DESIGN.md` with full data schema for actions, dialogue, balance tuning, and sprite state machine details.
