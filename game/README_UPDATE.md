# Pocket-R GAME folder update (v3)

Changes in this drop:

- Longer **animated** intro splash (fade-in + loading dots).
- HOME confirm supports **K1** *and* joystick **PRESS**.
- New **Settings** UI with proper bars/sliders:
  - Brightness (applies immediately)
  - Target FPS + Show FPS toggle
  - Repo Path selector (for the updater)
  - Debug page (scrollable)
- Revamped **Updater** UI (reads Repo Path from Settings).

## Notes about the updater

If you originally installed Pocket-R by copying a zip, your install folder will **not** be a git repo (no `.git/`), so `git pull` will fail.

To enable in-device updates, install Pocket-R as a git clone, or point **Repo Path** in Settings to the folder that *is* a git clone.
