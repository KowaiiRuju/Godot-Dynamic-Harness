import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_game_cli import ROOT, call, game

UI_PIPELINE_DIR = ROOT / "templates/core/tools/ui_pipeline"
if str(UI_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(UI_PIPELINE_DIR))

spec_bp = importlib.util.spec_from_file_location("bezel_profiler", UI_PIPELINE_DIR / "bezel_profiler.py")
bezel_profiler = importlib.util.module_from_spec(spec_bp)
spec_bp.loader.exec_module(bezel_profiler)

spec_md = importlib.util.spec_from_file_location("mockup_dissect", UI_PIPELINE_DIR / "mockup_dissect.py")
mockup_dissect = importlib.util.module_from_spec(spec_md)
spec_md.loader.exec_module(mockup_dissect)

spec_mg = importlib.util.spec_from_file_location("mockup_grade", UI_PIPELINE_DIR / "mockup_grade.py")
mockup_grade = importlib.util.module_from_spec(spec_mg)
spec_mg.loader.exec_module(mockup_grade)


class UIMockupPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gdh ui_pipeline ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.godot").write_text(
            'config_version=5\n[application]\nrun/main_scene="res://ui/Hud.tscn"\n',
            encoding="utf-8",
        )

    def _create_mockup_png(self, path: Path, outline_px: int = 4, bezel_px: int = 16, content_px: int = 16) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is required for mockup PNG generation")

        w, h = 800, 500
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        # Draw a framed panel inside HD01 region (0.015, 0.02, 0.40, 0.17) -> (12, 10) to (320, 85)
        x0, y0, x1, y1 = int(0.015 * w), int(0.02 * h), int(0.40 * w), int(0.17 * h)
        pw, ph = x1 - x0, y1 - y0
        for py in range(ph):
            for px in range(pw):
                dist = min(px, py, pw - 1 - px, ph - 1 - py)
                if dist < outline_px:
                    color = (20, 25, 40, 255)
                elif dist < outline_px + bezel_px:
                    color = (55, 130, 190, 255)
                else:
                    color = (215, 225, 235, 255)
                img.putpixel((x0 + px, y0 + py), color)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)

    def test_stage_0_check_prerequisites_detects_unset_art_style_and_missing_gdignore(self):
        # 1. Missing scene, unset art style, missing docs/.gdignore
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        prereqs = mockup_dissect.check_prerequisites(
            self.root,
            scene="ui/Hud.tscn",
            mockup="docs/mockups/hud_ref.png",
        )
        self.assertFalse(prereqs["ok"])
        self.assertFalse(prereqs["scene_exists"])
        self.assertFalse(prereqs["art_style_configured"])
        self.assertTrue(prereqs["ask_user_art_style"])
        codes = {f["code"] for f in prereqs["findings"]}
        self.assertIn("PREREQ_SCENE_MISSING", codes)
        self.assertIn("PREREQ_GDIGNORE_MISSING", codes)
        self.assertIn("ART_STYLE_DIRECTION_UNSET", codes)

        # 2. Simulate missing Pillow when mockup is provided
        with patch.object(mockup_dissect.importlib.util, "find_spec", return_value=None):
            no_pil = mockup_dissect.check_prerequisites(
                self.root,
                scene="ui/Hud.tscn",
                mockup="docs/mockups/hud_ref.png",
            )
            no_pil_codes = {f["code"] for f in no_pil["findings"]}
            self.assertIn("PREREQ_PILLOW_MISSING", no_pil_codes)

        # 3. Create scene, docs/.gdignore, and configure user art style in .context/project_state.json
        (self.root / "docs" / ".gdignore").write_text("", encoding="utf-8")
        scene_file = self.root / "ui" / "Hud.tscn"
        scene_file.parent.mkdir(parents=True, exist_ok=True)
        scene_file.write_text('[gd_scene format=3]\n[node name="Hud" type="Control"]\n', encoding="utf-8")
        ctx_dir = self.root / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "project_state.json").write_text(
            json.dumps({"art_style_direction": "Minimalist Sci-Fi Vector HUD"}, sort_keys=True),
            encoding="utf-8",
        )

        prereqs_ok = mockup_dissect.check_prerequisites(self.root, scene=None, mockup="")
        self.assertTrue(prereqs_ok["ok"])
        self.assertTrue(prereqs_ok["scene_exists"])
        self.assertEqual(prereqs_ok["scene"], "ui/Hud.tscn")
        self.assertTrue(prereqs_ok["art_style_configured"])
        self.assertFalse(prereqs_ok["ask_user_art_style"])
        self.assertEqual(prereqs_ok["art_style_direction"], "Minimalist Sci-Fi Vector HUD")
        self.assertEqual(prereqs_ok["findings"], [])

    def test_bezel_profiler_supports_style_agnostic_transitions_and_wood_palettes(self):
        # 1. Style-agnostic transition scanline: 3px dark outline + 12px cyan bezel + 20px interior
        scanline = (
            [(15, 20, 35, 255)] * 3
            + [(40, 140, 210, 255)] * 12
            + [(225, 235, 245, 255)] * 25
        )
        measured = bezel_profiler.measure_scanline(scanline)
        self.assertEqual(measured["outer_outline_px"], 3)
        self.assertEqual(measured["wood_bezel_px"], 12)
        self.assertEqual(measured["required_patch_margin_px"], 15)
        self.assertGreaterEqual(measured["required_content_margin_px"], 14)

        # 2. Warm wood/parchment scanline: 4px ink + 18px wood + 3px inner lip + 16px parchment
        wood_scanline = (
            [(35, 25, 20, 255)] * 4
            + [(145, 95, 50, 255)] * 18
            + [(85, 55, 35, 255)] * 3
            + [(230, 210, 175, 255)] * 16
        )
        wood_measured = bezel_profiler.measure_scanline(wood_scanline)
        self.assertEqual(wood_measured["outer_outline_px"], 4)
        self.assertEqual(wood_measured["wood_bezel_px"], 18)
        self.assertEqual(wood_measured["inner_lip_px"], 3)
        self.assertEqual(wood_measured["required_patch_margin_px"], 25)

    def test_five_stage_connected_ui_pipeline_flow_fail_then_fix_and_pass(self):
        # Stage 0 setup: configure art style, .gdignore, and reference mockup PNG (4px outline + 16px bezel = 20px patch)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        (self.root / "docs" / ".gdignore").write_text("", encoding="utf-8")
        (self.root / ".context").mkdir(parents=True, exist_ok=True)
        (self.root / ".context" / "project_state.json").write_text(
            json.dumps({"art_style_direction": "Clean Flat Vector"}, sort_keys=True),
            encoding="utf-8",
        )
        mockup_path = self.root / "docs" / "mockup_flat.png"
        self._create_mockup_png(mockup_path, outline_px=4, bezel_px=16)

        # Create initial .tscn with intentional margin mismatch (patch_margin=6 vs 20, content_margin=4 vs >=12)
        # and sibling overlap between StatusCard and InventoryCard
        bad_tscn = """[gd_scene load_steps=3 format=3]

[ext_resource type="Texture2D" path="res://assets/ui/panel.png" id="1_tex"]

[sub_resource type="StyleBoxTexture" id="StyleBoxTexture_bad"]
texture = ExtResource("1_tex")
texture_margin_left = 6.0
texture_margin_top = 6.0
texture_margin_right = 6.0
texture_margin_bottom = 6.0
content_margin_left = 4.0
content_margin_top = 4.0
content_margin_right = 4.0
content_margin_bottom = 4.0

[node name="Hud" type="Control"]

[node name="StatusCard" type="PanelContainer" parent="."]
offset_left = 10.0
offset_top = 10.0
offset_right = 210.0
offset_bottom = 110.0
theme_override_styles/panel = SubResource("StyleBoxTexture_bad")

[node name="InventoryCard" type="PanelContainer" parent="."]
offset_left = 150.0
offset_top = 50.0
offset_right = 350.0
offset_bottom = 150.0
theme_override_styles/panel = SubResource("StyleBoxTexture_bad")
"""
        scene_file = self.root / "ui" / "Hud.tscn"
        scene_file.parent.mkdir(parents=True, exist_ok=True)
        scene_file.write_text(bad_tscn, encoding="utf-8")

        # Stage 1: Dissect (using fallback static parser by passing non-existent godot binary)
        dissect_res = mockup_dissect.dissect_ui(
            self.root,
            scene="ui/Hud.tscn",
            mockup="docs/mockup_flat.png",
            out_dir="artifacts/ui_pipeline",
            godot="",
        )
        manifest_path = Path(dissect_res["dissection_manifest"])
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["scene"], "ui/Hud.tscn")
        self.assertEqual(manifest["styled_control_count"], 2)
        self.assertIn("pipeline_connection", manifest)
        self.assertIn("mockup-grade", manifest["pipeline_connection"]["stage_3_grade"])

        req_patch = manifest["measured_layers_px"]["required_patch_margin_px"]
        self.assertEqual(req_patch, 20)

        # Stage 3 (first pass): Grade catches BEZEL_PATCH_MARGIN_MISMATCH, CONTENT_MARGIN_TOO_SMALL, SIBLING_CONTROL_OVERLAP
        grade_fail = mockup_grade.grade_dissection(manifest_path, tolerance_px=2.0)
        self.assertFalse(grade_fail["passed"])
        self.assertEqual(grade_fail["status"], "failed")
        fail_rules = {f["rule"] for f in grade_fail["failed_components"]}
        self.assertIn("BEZEL_PATCH_MARGIN_MISMATCH", fail_rules)
        self.assertIn("CONTENT_MARGIN_TOO_SMALL", fail_rules)
        self.assertIn("SIBLING_CONTROL_OVERLAP", fail_rules)
        self.assertEqual(
            grade_fail["pipeline_connection"]["next_stage"],
            "stage_2_scene_first_edit",
        )

        # Stage 2: Update .tscn margins to match measured 20px patch margin, 14px content margin, and non-overlapping rects
        fixed_tscn = f"""[gd_scene load_steps=3 format=3]

[ext_resource type="Texture2D" path="res://assets/ui/panel.png" id="1_tex"]

[sub_resource type="StyleBoxTexture" id="StyleBoxTexture_good"]
texture = ExtResource("1_tex")
texture_margin_left = {float(req_patch)}
texture_margin_top = {float(req_patch)}
texture_margin_right = {float(req_patch)}
texture_margin_bottom = {float(req_patch)}
content_margin_left = 14.0
content_margin_top = 14.0
content_margin_right = 14.0
content_margin_bottom = 14.0

[node name="Hud" type="Control"]

[node name="StatusCard" type="PanelContainer" parent="."]
offset_left = 10.0
offset_top = 10.0
offset_right = 210.0
offset_bottom = 110.0
theme_override_styles/panel = SubResource("StyleBoxTexture_good")

[node name="InventoryCard" type="PanelContainer" parent="."]
offset_left = 230.0
offset_top = 10.0
offset_right = 430.0
offset_bottom = 110.0
theme_override_styles/panel = SubResource("StyleBoxTexture_good")
"""
        scene_file.write_text(fixed_tscn, encoding="utf-8")

        # Re-run Stage 1 & Stage 3
        mockup_dissect.dissect_ui(
            self.root,
            scene="ui/Hud.tscn",
            mockup="docs/mockup_flat.png",
            out_dir="artifacts/ui_pipeline",
            godot="",
        )
        grade_pass = mockup_grade.grade_dissection(manifest_path, tolerance_px=2.0)
        self.assertTrue(grade_pass["passed"], grade_pass)
        self.assertEqual(grade_pass["status"], "success")
        self.assertEqual(grade_pass["failed_count"], 0)
        self.assertEqual(grade_pass["pipeline_connection"]["next_stage"], "stage_4_capture")
        self.assertIn("python game.py capture --scene ui/Hud.tscn", grade_pass["next_command"])

        # Verify game.py CLI integration if mockup-dissect / mockup-grade subcommands are registered
        _, subcommands = game.build_parser()
        if "mockup-dissect" in subcommands and "mockup-grade" in subcommands:
            code, cli_prereq = call(
                "--project",
                str(self.root),
                "mockup-dissect",
                "--scene",
                "ui/Hud.tscn",
                "--check-prereqs",
                "--compact",
            )
            self.assertEqual(code, 0, cli_prereq)
            code, cli_grade = call(
                "--project",
                str(self.root),
                "mockup-grade",
                "--manifest",
                "artifacts/ui_pipeline/dissection_manifest.json",
                "--compact",
            )
            self.assertEqual(code, 0, cli_grade)


if __name__ == "__main__":
    unittest.main()
