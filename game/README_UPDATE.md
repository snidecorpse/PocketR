# Game folder update: Main OS (Intro + Home)

This update contains the Pocket-R **Main OS** layer:

- Intro splash image: `assets/ui/intro.png` (replace with your own)
- Home screen: 2x2 icon grid, D-pad navigation, PRESS to open
- **Hold K3** to shutdown (3 seconds). This is implemented inside `game/main.py`.

## Note about shutdown
Your launcher `app.py` still shuts down on **PRESS** (center) hold at the engine level.
If you want shutdown to be **K3 only**, you must change the launcher to watch K3
instead of PRESS.

Minimal change needed in `app.py`:
- In `run_engine(...)`, replace the `"PRESS"` / `"PRESS_UP"` hold-tracking with `"K3"` / `"K3_UP"`
- Set `SHUTDOWN_HOLD_SECONDS` to your desired value (e.g. 3.0)

This game update works even if you don't change `app.py`, but then BOTH will work:
- PRESS hold -> shutdown (engine)
- K3 hold -> shutdown (game)
