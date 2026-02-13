# PocketR Pet Game Instructions

This document is the focused gameplay guide for the Pet Game app.

## 1) Goal
Keep him healthy and happy by balancing needs, interacting in rooms, talking, and using actions regularly. If health reaches zero, the game enters a game-over screen and waits for restart.

## 2) Controls
- Move: joystick directions (hold).
- Open actions: `B1` or joystick `PRESS`.
- Confirm selection: `B1`.
- `B2` short: quick supportive interaction.
- `B2` long (~1.2s): reopen tutorial slides.
- `B3` short: quick care action.
- Exit game: in Hall actions, choose `Save & Quit`.
- Restart after death: `B1` or joystick `PRESS`.

## 3) Rooms and Actions
Room map:
- Hall center
- Bedroom to the right
- Bathroom up
- Living room down
- Arcade left

Hall:
- `Check In`
- `Stretch`
- `Take Picture` (saves photo to Gallery path)
- `Save & Quit`

Bedroom:
- `Cuddle`
- `Give Hug`
- `Sleep`

Living:
- `Watch TV`
- `Lounge`
- `Talk` (opens category menu, then typewriter dialogue)
- `Open Gallery` (app jump)

Bathroom:
- `Use Toilet`
- `Shower`
- `Night Routine`
- `Change Clothes`

Arcade:
- `Brick Breaker`
- `Memory Match`
- `Runner Dash`

## 4) Dialogue System
Talk actions are queue-based:
- Line 1: `You: ...`
- Line 2: `Him: ...`

Typewriter behavior:
- While typing: `B1`/`PRESS` completes current line immediately.
- Next `B1`/`PRESS` advances to next line.
- Talk menu order follows the key order in `game/assets/pet_game/dialogue.json` (or persistent override).

## 5) Stats and Simulation Algorithm
Core stats:
- `HP`, `HNG`, `ENG`, `HYG`, `SOC`, `FUN`, `BLD`, `MOOD`

Simulation model:
1. Age increases continuously using accelerated time (`1 real minute = 1 pet hour`).
2. Base per-hour drains are applied to hunger, energy, hygiene, social, fun, bladder.
3. Moving increases some drains.
4. Sleep pose modifies drain/regen behavior.
5. A stress score is computed from deficits below thresholds.
6. HP loss starts when stress passes a threshold and compounds with multiple critical vitals.
7. HP regen applies when core needs are healthy.
8. Mood lerps toward a weighted target from health + needs.
9. If HP reaches `0`, pet dies and game-over screen is shown.

Decay tuning:
- Current build is slightly faster than before (`DECAY_TUNE_MULT = 1.12`).

## 6) Death and Restart
When HP reaches zero:
- Full red `GAME OVER` screen appears.
- Message warns that he was not taken care of.
- Shows cause (lowest critical stat).
- Restart prompt: `B1 / PRESS`.

## 7) Sprite and Animation System
Animation folders are read from `game/assets/pet_game/Sprites/`:
- `Walking`, `IdleHappy`, `IdleSad`, `Talking`, `HugCuddle`, `Sleeping`, `Shower`, `Changing`, `Gaming`

Pipeline:
1. Each animation category uses a fixed slot (`walk 56x96`, `talk 64x96`, `sleep 96x64`, etc.).
2. Runtime computes one canonical set scale from max alpha bounds across frames in that folder.
3. Every frame in that set uses the same scale (prevents tiny-to-big drift).
4. `sleeping` uses center Y anchor; upright states use bottom Y anchor.
5. `Sprite Scale` in settings applies one uniform global multiplier (`0.85..1.20`) to all animation slots.
6. Left-facing states are mirrored automatically based on movement/facing.

Idle sad special rule:
- First loop runs full sequence once.
- Later loops run from frame 5 onward.

## 8) Minigames
Brick Breaker:
- Multi-level progression (`L1` to `L3`), denser/faster as level rises.

Memory Match:
- 2x3 card grid, match all pairs.

Runner Dash:
- Auto-run obstacle dodge with jump input.

Exit any minigame:
- `B2`

## 9) Authoring Specs for Room Art
Room asset dimensions:
- Full canvas: `240x240`
- Top HUD reserved: `y=0..73`
- Play frame: `x=6..233`, `y=74..233`
- Sprite clip region: `x=8..231`, `y=76..231`

Room file contract:
- runtime is base-only: `base.png` (or `Base.png`) is used for room art
- `obj_*.png` files are ignored by renderer
- optional `fg.png` can occlude foreground

## 10) Persistence
Primary runtime save location:
- `/root/.pocketr/pet/state.json` (Pi target)

Dialogue override location:
- `/root/.pocketr/pet/dialogue.json`

These keep runtime state separate from repo content.
