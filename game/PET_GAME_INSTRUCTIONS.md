# PocketR Pet Game Instructions

This document is the focused gameplay guide for the Pet Game app.

## 1) Goal
Keep him healthy and happy by balancing needs, interacting in rooms, talking, and using actions regularly. If health reaches zero, the game enters a game-over screen and waits for restart.

## 2) Controls
- Move: joystick directions (hold).
- Open actions: `B1` or joystick `PRESS`.
- Confirm selection: `B1`.
- `B2` short: quick supportive interaction.
- `B2` long (~1.6s): save + exit pet game.
  - Hold overlay appears with progress; release cancels.
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
- `Eat Snack` (opens 3-choice snack menu with cooldown)
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
- `Micro Snake`
- `Heart Catch`
- `Reflex Tap`

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
3. Activity-load scaling increases drains:
   - walking > idle
   - arcade room > non-arcade rooms
   - mini-games apply strongest ongoing drain
4. Sleep pose modifies drain/regen behavior.
5. A stress score is computed from deficits below thresholds.
6. HP loss starts at a stricter stress threshold and compounds harder with multiple critical vitals.
7. HP regen applies only when core needs and mood are healthy.
8. Mood lerps toward a weighted target from health + needs.
9. If HP reaches `0`, pet dies and game-over screen is shown.

Decay tuning:
- Current build is slightly faster than before (`DECAY_TUNE_MULT = 1.25`).

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
1. Runtime picks a single scale reference from `IdleHappy` (fallback `Walking`).
2. Target apparent body height is `92px` on a shared `112x112` sprite canvas.
3. One shared scale factor is applied to all animation folders.
4. `sleeping` uses center Y anchor; upright states use bottom Y anchor.
5. `Sprite Scale` in settings applies one uniform global multiplier (`0.85..1.20`) after shared normalization.
6. Left-facing states are mirrored automatically based on movement/facing.
7. X-position is clamped from active frame width to reduce side cutoffs.

Idle sad special rule:
- First loop runs full sequence once.
- Later loops run from frame 5 onward.

## 8) Minigames
Brick Breaker:
- Clear-all progression (`L1` to `L5`) with proper level gating.
- `LEVEL UP` flash appears briefly on transitions.

Memory Match:
- 2x3 card grid, match all pairs.

Runner Dash:
- Auto-run obstacle dodge with jump input.

Micro Snake:
- 14x14 grid.
- Directional input updates heading (reverse-direction blocked).
- Win at 25 food; collision with wall/body ends run.

Heart Catch:
- Move basket left/right.
- Catch hearts, avoid bombs.
- 3 lives, 35-second round.

Reflex Tap:
- Moving marker crosses a hit lane.
- Press `B1`/`PRESS` to score timing hits.
- 10 rounds with streak-based points.

Exit any minigame:
- `B2`

Snack submenu (`Living -> Eat Snack`):
- `Light Snack`: `hunger +8`, `mood +1`, `bladder -1`
- `Balanced Meal`: `hunger +16`, `energy +3`, `mood +2`, `bladder -3`
- `Sweet Treat`: `hunger +6`, `fun +7`, `mood +5`, `energy -2`, `hygiene -2`
- Cooldown: `45s`

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
