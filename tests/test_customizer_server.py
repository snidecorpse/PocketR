from __future__ import annotations

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

import customizer_server


def png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (240, 240)) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        img = Image.new("RGB", size, color)
        img.save(tmp_path, format="PNG")
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


class CustomizerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="pocketr_customizer_test_"))
        self.project_root = self.tmp_dir / "PocketR"
        self.project_root.mkdir(parents=True, exist_ok=True)

        (self.project_root / "customizer_web").mkdir(parents=True, exist_ok=True)
        (self.project_root / "customizer_web" / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")

        asset_root = self.project_root / "game" / "assets" / "pet_game"
        for room in customizer_server.ROOM_SLUGS:
            room_dir = asset_root / "rooms" / room
            room_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (240, 240), (30, 30, 30)).save(room_dir / "base.png", format="PNG")

        for group in customizer_server.ANIM_GROUPS:
            gdir = asset_root / "Sprites" / group
            gdir.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (112, 112), (200, 0, 0, 255)).save(gdir / "frame_000.png", format="PNG")

        for name in customizer_server.SINGLE_SPRITE_FILES:
            Image.new("RGBA", (112, 112), (0, 200, 0, 255)).save(asset_root / name, format="PNG")

        (asset_root / "dialogue.json").write_text(
            """
            {
              "greeting": [{"player": "hello", "pet": "hi", "social": 2, "fun": 1},],
              "feelings": [{"player": "how are you", "pet": "okay"},],
            }
            """.strip(),
            encoding="utf-8",
        )

        self.state = customizer_server.CustomizerState(self.project_root)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _stage_bg(self, room: str, color: tuple[int, int, int]) -> None:
        up = customizer_server.UploadedFile(
            field="file",
            filename=f"{room}.png",
            content_type="image/png",
            data=png_bytes(color),
        )
        self.state.stage_background({"room": room}, {"file": [up]})

    def test_meta_and_current_payload(self) -> None:
        meta = self.state.meta_payload()
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["meta"]["rooms"], customizer_server.ROOM_SLUGS)

        current = self.state.current_payload()
        self.assertTrue(current["ok"])
        self.assertFalse(current["draft"]["has_changes"])
        self.assertIn("feelings", current["dialogue"]["template"])

    def test_background_upload_rejects_bad_extension(self) -> None:
        up = customizer_server.UploadedFile(
            field="file",
            filename="bad.txt",
            content_type="text/plain",
            data=b"bad",
        )
        with self.assertRaises(customizer_server.ApiError) as ctx:
            self.state.stage_background({"room": "hub"}, {"file": [up]})
        self.assertIn("Background must be", str(ctx.exception))

    def test_dialogue_stage_preserves_category_order(self) -> None:
        payload = {
            "dialogue": {
                "zeta": [{"player": "A", "pet": "B", "social": 1, "fun": 2}],
                "alpha": [{"player": "C", "pet": "D"}],
            }
        }
        out = self.state.stage_dialogue(payload)
        self.assertTrue(out["ok"])

        current = self.state.current_payload()
        keys = list(current["dialogue"]["data"].keys())
        self.assertEqual(keys, ["zeta", "alpha"])

    def test_apply_creates_snapshot_and_writes_override(self) -> None:
        self._stage_bg("hub", (200, 20, 20))
        result = self.state.apply_draft()
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("snapshot_id"))

        applied = self.project_root / ".pocketr" / "pet" / "overrides" / "pet_game" / "rooms" / "hub" / "base.png"
        self.assertTrue(applied.is_file())

        snaps = self.state.list_snapshots()
        self.assertTrue(snaps["ok"])
        self.assertGreaterEqual(len(snaps["snapshots"]), 1)

    def test_restore_reverts_previous_override(self) -> None:
        self._stage_bg("hub", (200, 10, 10))
        first = self.state.apply_draft()
        first_snapshot_id = str(first["snapshot_id"])

        self._stage_bg("hub", (10, 200, 10))
        self.state.apply_draft()

        self.state.restore_snapshot(first_snapshot_id)

        applied = self.project_root / ".pocketr" / "pet" / "overrides" / "pet_game" / "rooms" / "hub" / "base.png"
        self.assertTrue(applied.is_file())
        with Image.open(applied) as img:
            r, g, _b = img.convert("RGB").getpixel((8, 8))
        self.assertGreater(r, g)

    def test_snapshot_download_zip_contains_pocketr_structure(self) -> None:
        self._stage_bg("hub", (123, 55, 220))
        applied = self.state.apply_draft()
        sid = str(applied["snapshot_id"])

        filename, payload = self.state.snapshot_zip_payload(sid)
        self.assertTrue(filename.endswith(".zip"))
        self.assertGreater(len(payload), 0)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = Path(tmp.name)
            zip_path.write_bytes(payload)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
            self.assertIn("INSTALL_ON_PI.txt", names)
            self.assertIn(".pocketr/pet/overrides/pet_game/rooms/hub/base.png", names)
        finally:
            try:
                zip_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
