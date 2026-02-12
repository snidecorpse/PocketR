# Pocket-R Desktop Runner

This lets you run the **same** `./game/main.py` UI loop on a laptop, so you can iterate fast without pushing to the Pi.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements_desktop.txt
```

## Run

From your project root (same folder that contains `game/`):

```bash
python desktop_run.py
```

## Controls
- Arrow keys / WASD: D-pad
- Enter / Space: PRESS
- 1: K1 (confirm)
- 2: K2 (back)
- 3: K3 (hold ~3s triggers shutdown -> exits runner)

## Dev
- Press **R** to hot reload the `game` Python modules.
- ESC or Q to quit.
