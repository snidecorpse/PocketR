# GAME folder update (OS shell)

Changes included in this update:

- Intro splash stays longer (~3.5s) before going to the home screen.
- Home screen: 2x2 icon grid with the earlier panel sizing (no bottom instruction bar).
- Controls:
  - D-pad: move selection
  - **K1: confirm / open**
  - **K2: back** (inside menus)
  - **Hold K3: shutdown** (~3s)

Menus:
1. Menu 1 (top-left): Game (placeholder room navigation)
2. Menu 2 (top-right): Blank (reserved)
3. Menu 3 (bottom-left): Settings/Debug info
4. Menu 4 (bottom-right): Update (runs `git pull` via `game/scripts/update_repo.sh`, then reboots)

## Note about center-press shutdown
Your `app.py` still has a global **PRESS-hold 10s** shutdown in the engine loop.
If you want *only* K3 to shutdown, change that block in `app.py` to watch K3 instead of PRESS.
