import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_game_cli import game

sheet = game.load_tool("contact_sheet")


class ContactSheets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def captures(self, count):
        from PIL import Image
        captures = []
        for index in range(count):
            directory = self.root / str(index)
            directory.mkdir()
            path = directory / "capture.png"
            Image.new("RGB", (360, 640), (index * 25, 40, 100)).save(path)
            captures.append({"scene": f"res://folder-{index}/Menu.tscn", "status": "success",
                             "artifacts": [str(path)], "findings": [], "summary": "Captured"})
        return captures

    def test_seven_scenes_make_two_pages_without_cropping(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow unavailable")
        captures = self.captures(7)
        captures[2] = {"scene": 'res://<script>alert("bad")</script>.tscn', "status": "failed",
                       "artifacts": [], "findings": [{"message": "Scene failed"}], "summary": "Failed"}
        output = sheet.export(captures, self.root)
        self.assertEqual(len(output["artifacts"]), 3)
        with Image.open(output["artifacts"][1]) as image:
            self.assertEqual(image.width, 992)
            # First thumbnail retains the source aspect ratio and distinct source color.
            self.assertEqual(image.getpixel((100, 100)), (0, 40, 100))
        with Image.open(output["artifacts"][2]) as image:
            self.assertEqual(image.width, 336)
        gallery = Path(output["artifacts"][0]).read_text()
        self.assertIn("&lt;script&gt;", gallery)
        self.assertNotIn('<script>alert', gallery)
        self.assertIn("folder-6/Menu.tscn", gallery)

    def test_missing_optional_pillow_keeps_html_gallery(self):
        captures = [{"scene": "res://missing.tscn", "status": "failed", "artifacts": [],
                     "findings": [{"message": "Missing scene"}], "summary": "Failed"}]
        with patch.object(sheet, "write_sheets", side_effect=ImportError("Pillow missing")):
            output = sheet.export(captures, self.root)
        self.assertEqual(output["png_grid"], "unavailable")
        self.assertTrue(Path(output["artifacts"][0]).is_file())


if __name__ == "__main__":
    unittest.main()
