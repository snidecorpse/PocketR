# PocketR Customizer Web App

This root-level tool provides a desktop-first web editor for user-facing PocketR content.

It lets you customize:
- Room backgrounds (`hub`, `bedroom`, `living`, `bathroom`, `arcade`)
- Sprite animation folders (`Walking`, `IdleHappy`, `IdleSad`, `Talking`, `HugCuddle`, `Sleeping`, `Shower`, `Changing`, `Gaming`)
- Single fallback sprites (`idle.png`, `walk1.png`, `walk2.png`, `sleep.png`, `shower.png`, `toilet.png`)
- Dialogue categories/lines (`player`, `pet`, optional `social`, `fun`)

It does **not** expose gameplay/debug tuning controls.

## Run

From project root:

```bash
python3 customizer_server.py
```

Optional:

```bash
python3 customizer_server.py --host 127.0.0.1 --port 8765
```

Then open:

- [http://127.0.0.1:8765](http://127.0.0.1:8765)

## Data Paths (Desktop)

- Draft workspace: `/Users/rahil/Desktop/Projects/PocketR/.pocketr/customizer/draft/`
- Snapshots: `/Users/rahil/Desktop/Projects/PocketR/.pocketr/customizer/snapshots/<timestamp>/`
- Applied visual overrides: `/Users/rahil/Desktop/Projects/PocketR/.pocketr/pet/overrides/pet_game/`
- Applied dialogue override: `/Users/rahil/Desktop/Projects/PocketR/.pocketr/pet/dialogue.json`

## API

- `GET /api/meta`
- `GET /api/current`
- `POST /api/draft/background` (multipart)
- `POST /api/draft/sprite` (multipart)
- `POST /api/draft/dialogue` (json)
- `POST /api/draft/discard`
- `POST /api/validate`
- `POST /api/apply`
- `GET /api/snapshots`
- `GET /api/snapshot_download?snapshot_id=<id>` (downloads install-ready zip)
- `POST /api/restore` (json)
- `GET /api/preview_asset?...`

## Snapshot Transfer To Pi

1. Select a snapshot in the web UI.
2. Click **Download Snapshot** to get `pocketr_snapshot_<id>.zip`.
3. Copy the zip to your Pi PocketR repo root.
4. Unzip in place:

```bash
unzip pocketr_snapshot_*.zip -d .
```

This restores `.pocketr/pet/overrides/pet_game/...` and `.pocketr/pet/dialogue.json`.

## Runtime Override Policy

`game/apps/pet_game.py` now resolves visual assets with override-first behavior:

1. `.pocketr/pet/overrides/pet_game/...` (user override)
2. `game/assets/pet_game/...` (bundled fallback)

Dialogue already follows persistent override-first behavior via `.pocketr/pet/dialogue.json`.
