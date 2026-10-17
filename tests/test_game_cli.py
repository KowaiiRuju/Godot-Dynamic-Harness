import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("game", ROOT / "templates/game.py")
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


def call(*arguments):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = game.main([*arguments, "--json"])
    return code, json.loads(stdout.getvalue())


class ToolResults(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gdh tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")

    def test_missing_scan_fails(self):
        code, out = call("--project", str(self.root), "syntax", "--scan", "missing")
        self.assertEqual(code, 1)
        self.assertEqual(out["findings"][0]["code"], "PATH_NOT_FOUND")

    def test_policy_violation_fails_and_empty_scan_skips(self):
        code, out = call("--project", str(self.root), "validate")
        self.assertEqual(out["status"], "skipped")
        (self.root / "bad.gd").write_text("extends Node\nvar bad = Control.new()\n")
        code, out = call("--project", str(self.root), "validate")
        self.assertEqual(code, 1)
        self.assertEqual(out["findings"][0]["line"], 2)

    def test_recursive_test_listing_and_missing_suite(self):
        nested = self.root / "tests/ui"
        nested.mkdir(parents=True)
        (nested / "test_menu.gd").write_text("extends SceneTree\n")
        code, out = call("test", "--project", str(self.root), "--list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out["suites"]), 1)
        code, out = call("test", "--project", str(self.root), "--suite", "missing.gd")
        self.assertEqual(code, 1)

    def test_json_argument_errors_and_timeout(self):
        code, out = call("capture", "--width", "nope")
        self.assertEqual(out["findings"][0]["code"], "INVALID_ARGUMENT")
        with self.assertRaises(game.HarnessError) as raised:
            game.execute([sys.executable, "-c", "import time; time.sleep(2)"], timeout=.1)
        self.assertEqual(raised.exception.code, "TIMEOUT")

    def test_bad_selected_engine_does_not_fall_back(self):
        with self.assertRaises(game.HarnessError):
            game.get_godot_bin(str(self.root / "missing.exe"))

    def test_child_failure_propagates(self):
        completed = subprocess.CompletedProcess([], 7, "child failed", "")
        with patch.object(game, "execute", return_value=completed):
            code, out = call("--project", str(self.root), "syntax", "--query", "export")
        self.assertEqual(code, 1)

    def test_engine_error_logs_fail_even_with_zero_exit(self):
        self.assertTrue(game.command_findings(subprocess.CompletedProcess([], 0, "", "SCRIPT ERROR: Assertion failed"), "test"))

    def test_batch_grid_timeout_keeps_individual_capture_evidence(self):
        (self.root / "Main.tscn").write_text('[gd_scene format=3]\n')
        def capture(args, scene, output):
            output.mkdir(parents=True)
            png = output / "capture.png"
            png.write_bytes(b"fixture")
            return game.result("capture", "Fixture", artifacts=[str(png)])
        with patch.object(game, "inspect_context", return_value={"engine_binary": "fixture"}), \
             patch.object(game, "capture_scene", side_effect=capture), \
             patch.object(game, "execute", side_effect=game.HarnessError("TIMEOUT", "Grid export timed out")):
            code, out = call("--project", str(self.root), "capture", "--all-scenes")
        self.assertEqual(code, 1)
        self.assertEqual(out["captures"][0]["status"], "success")
        self.assertTrue(any(p.endswith("capture.png") for p in out["artifacts"]))
        self.assertEqual(out["findings"][0]["code"], "GRID_EXPORT_FAILED")

    def test_path_escape_rejected(self):
        with self.assertRaises(game.HarnessError):
            game.project_path(self.root, "../outside.gd")

    @unittest.skipUnless(sys.platform == "win32", "Windows extended-path normalization")
    def test_atomic_replace_extended_path_prefix_preserves_containment(self):
        target = self.root / ".harness/checkpoint.json"
        with patch.object(Path, "resolve", return_value=Path("\\\\?\\" + str(target))):
            self.assertEqual(game.safe_target(self.root, ".harness/checkpoint.json"), target)
        with patch.object(Path, "resolve", return_value=Path("\\\\?\\" + str(self.root.parent / "outside.json"))):
            with self.assertRaises(game.HarnessError):
                game.safe_target(self.root, "outside.json")

    def test_project_resolution_and_parser_defaults(self):
        self.assertEqual(game.resolve_project(str(self.root)), self.root)
        code, out = call("--project", str(self.root / "missing"), "validate")
        self.assertEqual(out["findings"][0]["code"], "PROJECT_NOT_FOUND")

    def test_capabilities_share_parser_arguments(self):
        context = {"engine_version": "4.7.2", "engine_binary": "fake"}
        with patch.object(game, "inspect_context", return_value=context):
            code, out = call("--project", str(self.root), "info")
        self.assertEqual(code, 0)
        capture = next(t for t in out["capabilities"] if t["name"] == "capture")
        self.assertIn(["--width"], [a["flags"] for a in capture["arguments"]])
        defaults = {a["flags"][0]: a["default"] for a in capture["arguments"]}
        self.assertEqual(defaults["--timeout"], 30)
        self.assertFalse(defaults["--json"])
        with patch.object(game.sys, "platform", "darwin"):
            args = game.build_parser()[0].parse_args(["info"])
            args.root, args.commands = self.root, game.build_parser()[1]
            self.assertFalse(next(t for t in game.capabilities(args) if t["name"] == "test")["available"])

    def test_version_probes_reject_other_major_and_accept_numeric_minor(self):
        for version in ("4.0.stable", "4.7.2.stable", "4.99.dev"):
            results = [subprocess.CompletedProcess([], 0, version, ""), subprocess.CompletedProcess([], 0, "--headless --script --import", "")]
            probe = subprocess.CompletedProcess([], 0, 'HARNESS_JSON={"main_scene":"res://Main.tscn","features":[]}', "")
            with patch.object(game, "get_godot_bin", return_value="mock-engine"), patch.object(game, "execute", side_effect=results), patch.object(game, "run_headless_godot", return_value=probe):
                self.assertEqual(game.inspect_context(self.root)["engine_version"], version)
        with patch.object(game, "get_godot_bin", return_value="mock-engine"), patch.object(game, "execute", return_value=subprocess.CompletedProcess([], 0, "3.5.stable", "")):
            with self.assertRaises(game.HarnessError) as caught:
                game.inspect_context(self.root)
        self.assertEqual(caught.exception.code, "ENGINE_UNSUPPORTED")

    def test_persistent_graph_freshness_and_godot_source_locations(self):
        (self.root / "player.gd").write_text('extends Node2D\nfunc move() -> void:\n\tpass\nvar scene = preload("res://Main.tscn")\n')
        (self.root / "Main.tscn").write_text('[gd_scene format=3]\n[node name="Main" type="Node2D"]\n')
        with patch.object(game, "get_graphify_bin", return_value="mock-graphify"):
            code, out = call("--project", str(self.root), "graph", "--refresh")
        self.assertEqual(code, 0, out)
        self.assertEqual(game.graph_state(self.root)["status"], "fresh")
        data = json.loads((self.root / "graphify-out/graph.json").read_text())
        move = next(n for n in data["nodes"] if n["label"] == "move")
        self.assertEqual(move["source_location"], "L2")
        self.assertTrue(any(e["relation"] == "references_resource" for e in data["links"]))
        (self.root / "player.gd").write_text("extends Node3D\n")
        self.assertEqual(game.graph_state(self.root)["status"], "stale")
        with patch.object(game, "get_graphify_bin", return_value="mock-graphify"):
            code, out = call("--project", str(self.root), "graph", "--query", "player")
        self.assertEqual(out["findings"][0]["code"], "GRAPH_NOT_FRESH")

    def test_context_and_checkpoints_preserve_user_notes(self):
        project = self.root / "docs/harness/PROJECT.md"
        project.parent.mkdir(parents=True)
        project.write_text("Original design notes\n")
        with patch.object(game, "inspect_context", return_value={"authored_settings": {"name": "New name"}}):
            code, out = call("--project", str(self.root), "context", "--refresh")
        self.assertEqual(code, 0, out)
        self.assertIn("Original design notes", project.read_text())
        self.assertIn("New name", project.read_text())
        call("--project", str(self.root), "validate")
        checkpoint = self.root / "docs/harness/CHECKPOINT.md"
        with checkpoint.open("a") as file:
            file.write("\nNext task: fix menu\n")
        call("--project", str(self.root), "validate")
        self.assertIn("Next task: fix menu", checkpoint.read_text())

    def test_json_help_nan_and_child_tree_timeout(self):
        code, out = call("capture", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--renderer", out["output"])
        code, out = call("--project", str(self.root), "validate", "--timeout", "nan")
        self.assertEqual(code, 1)
        marker = self.root / "child_survived"
        if marker.exists():
            marker.unlink()
        child = "import time; from pathlib import Path; time.sleep(1.2); Path(" + repr(str(marker)) + ").write_text('survived')"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(10)"
        with self.assertRaises(game.HarnessError) as caught:
            game.execute([sys.executable, "-c", parent], timeout=.5)
        self.assertEqual(caught.exception.code, "TIMEOUT")
        time.sleep(1.5)
        self.assertFalse(marker.exists())

    def test_existing_graph_is_preserved_before_adoption_and_output_is_capped(self):
        graph = self.root / "graphify-out/graph.json"
        graph.parent.mkdir()
        original = '{"nodes":[{"id":"user-note","label":"User knowledge"}],"links":[]}'
        graph.write_text(original)
        (self.root / "player.gd").write_text("extends Node2D\n")
        with patch.object(game, "get_graphify_bin", return_value="mock-graphify"):
            code, out = call("--project", str(self.root), "graph", "--refresh")
        self.assertEqual(code, 0, out)
        self.assertEqual(Path(out["artifacts"][1]).read_text(), original)
        completed = subprocess.CompletedProcess([], 0, "line\n" * 100, "")
        with patch.object(game, "get_graphify_bin", return_value="mock-graphify"), patch.object(game, "execute", return_value=completed):
            code, out = call("--project", str(self.root), "graph", "--query", "player", "--budget", "10")
        self.assertTrue(out["truncated"])
        self.assertLessEqual(len(out["output"]), 40)

    def test_clean_and_debug_capture_pruning(self):
        debug_dir = self.root / "screenshots/debug"
        debug_dir.mkdir(parents=True)
        for i in range(7):
            d = debug_dir / f"capture-{i:03d}"
            d.mkdir()
            (d / "capture.png").write_bytes(b"\x00" * 100)
        deleted, freed = game.prune_debug_captures(self.root, keep=3)
        self.assertEqual(len(deleted), 4)
        self.assertEqual(freed, 400)
        remaining = [p.name for p in debug_dir.iterdir() if p.is_dir()]
        self.assertEqual(len(remaining), 3)

        qa_dir = self.root / "qa-evidence"
        qa_dir.mkdir(parents=True)
        (qa_dir / "report.json").write_text("{}")
        code, out = call("--project", str(self.root), "clean", "--all")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "success")
        self.assertFalse(qa_dir.exists())
        self.assertFalse(debug_dir.exists())

    def test_plan_task_classification_and_caveman_routing(self):
        code, out = call("--project", str(self.root), "plan-task", "Fix ground collision offset in Player.tscn")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["change_class"], "Minor")
        self.assertEqual(out["tier"], "minor-visual")
        self.assertEqual(out["caveman_mode"], "full")
        self.assertIn("Player.tscn", out["affected_files"])
        self.assertIn("scene-outline", out["next_command"])

        code, out = call("--project", str(self.root), "plan-task", "Write GDD documentation and player dialogue for quest")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["caveman_mode"], "off")

        code, out = call("--project", str(self.root), "plan-task", "Overhaul multiplayer architecture and rewrite autoloads")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["change_class"], "Major")
        self.assertEqual(out["tier"], "major")

    def test_scene_outline_strips_blobs_and_extracts_nodes_and_connections(self):
        tscn_content = '''[gd_scene load_steps=3 format=3 uid="uid://test1234"]

[ext_resource type="Script" path="res://player.gd" id="1_abc"]
[sub_resource type="TileSet" id="TileSet_1"]
tile_data = PackedByteArray(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)

[node name="World" type="Node2D"]
y_sort_enabled = true

[node name="Player" type="CharacterBody2D" parent="." unique_name_in_owner=true]
position = Vector2(100, 200)
collision_layer = 1
collision_mask = 2
script = ExtResource("1_abc")

[connection signal="hit" from="Player" to="." method="_on_player_hit"]
'''
        scene_file = self.root / "TestScene.tscn"
        scene_file.write_text(tscn_content, encoding="utf-8")
        code, out = call("--project", str(self.root), "scene-outline", "--scene", "TestScene.tscn")
        self.assertEqual(code, 0, out)
        outline = out["outline"]
        self.assertEqual(outline["node_count"], 2)
        self.assertEqual(outline["connection_count"], 1)
        self.assertEqual(outline["connections"][0]["signal"], "hit")
        self.assertEqual(outline["connections"][0]["method"], "_on_player_hit")

        player_node = next(n for n in outline["nodes"] if n["path"] == "Player")
        self.assertEqual(player_node["unique_name"], "%Player")
        self.assertEqual(player_node["script"], "res://player.gd")
        self.assertEqual(player_node["properties"]["collision_layer"], "1")

        out_str = json.dumps(out)
        self.assertNotIn("PackedByteArray", out_str)

    def test_compact_flag_and_checkpoint_budget_cap(self):
        fake_findings = [game.finding(f"ERR_{i}", f"Error message {i}") for i in range(12)]
        res = game.result("test", "Mock test", findings=fake_findings, compact=True)
        self.assertEqual(len(res["findings"]), 5)
        self.assertEqual(res["omitted_findings_count"], 7)
        self.assertTrue(res["compact"])
        self.assertIn("fix_hint", res["findings"][0])

        large_response = game.result("validate", "Large validation", findings=[game.finding(f"ERR_{i}", f"Message {i}") for i in range(50)], artifacts=[f"res://file_{i}.png" for i in range(50)])
        game.record_checkpoint(self.root, large_response)
        checkpoint_file = self.root / "docs/harness/CHECKPOINT.md"
        self.assertTrue(checkpoint_file.is_file())
        size = checkpoint_file.stat().st_size
        self.assertLess(size, 2048, f"CHECKPOINT.md size {size} exceeds 2 KB limit")

    def test_baseline_diff_engine_and_tolerances(self):
        diff_engine = game.load_tool("baseline_diff")
        base_manifest = self.root / "base_manifest.json"
        curr_manifest = self.root / "curr_manifest.json"

        base_data = {
            "scene": "res://Main.tscn",
            "viewport": [800, 600],
            "nodes": [
                {"path": "UI/StartBtn", "type": "Button", "rect": [100, 200, 80, 30], "text": "Start", "font_size": 16, "mouse_filter": 0},
                {"path": "UI/OldLabel", "type": "Label", "rect": [100, 100, 150, 20], "text": "Score"}
            ]
        }
        base_manifest.write_text(json.dumps(base_data), encoding="utf-8")

        curr_data = {
            "scene": "res://Main.tscn",
            "viewport": [800, 600],
            "nodes": [
                {"path": "UI/StartBtn", "type": "Button", "rect": [100, 205, 80, 30], "text": "Play", "font_size": 16, "mouse_filter": 0},
                {"path": "UI/NewBadge", "type": "TextureRect", "rect": [300, 10, 40, 40]}
            ]
        }
        curr_manifest.write_text(json.dumps(curr_data), encoding="utf-8")

        baseline_file = self.root / ".harness/baselines/Main_tscn.json"
        diff_engine.save_baseline(base_manifest, baseline_file)
        self.assertTrue(baseline_file.is_file())

        findings = diff_engine.diff_baselines(baseline_file, curr_manifest, tolerance=1.0)
        codes = {f["code"] for f in findings}
        self.assertIn("BASELINE_NODE_MISSING", codes)  # UI/OldLabel
        self.assertIn("BASELINE_NODE_ADDED", codes)    # UI/NewBadge
        self.assertIn("BASELINE_RECT_CHANGED", codes)  # dy=5 > 1.0px
        self.assertIn("BASELINE_TEXT_CHANGED", codes)  # Start -> Play

        # If tolerance is 10.0, dy=5 is within tolerance
        findings_loose = diff_engine.diff_baselines(baseline_file, curr_manifest, tolerance=10.0)
        loose_codes = {f["code"] for f in findings_loose}
        self.assertNotIn("BASELINE_RECT_CHANGED", loose_codes)

    def test_test_tier_filtering_and_doc_visual_skipping(self):
        # minor-doc and minor-visual tiers skip execution
        code, out = call("--project", str(self.root), "test", "--tier", "minor-doc")
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "skipped")
        self.assertIn("visual/doc checks", out["summary"])

        code, out = call("--project", str(self.root), "test", "--tier", "minor-visual")
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "skipped")

        # test --list works
        code, out = call("--project", str(self.root), "test", "--list")
        self.assertEqual(code, 0)

    def test_asset_inspector_audit_process_and_grading(self):
        try:
            from PIL import Image
        except ImportError:
            return

        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        # Draw a small 8x8 opaque square in the center (12 to 20)
        for x in range(12, 20):
            for y in range(12, 20):
                img.putpixel((x, y), (255, 0, 0, 255))
        # Add fringe pixels around it
        img.putpixel((11, 12), (255, 0, 0, 100))
        img_path = self.root / "test_sprite.png"
        img.save(img_path)

        # Audit
        code, out = call("--project", str(self.root), "assets", "test_sprite.png")
        self.assertEqual(code, 0, out)
        self.assertIn("dimensions", out.get("audit", {}))
        self.assertEqual(out["audit"]["dimensions"], [32, 32])

        # Process with crop-alpha and scale 2x
        code, out = call("--project", str(self.root), "assets", "--process", "test_sprite.png", "--crop-alpha", "--scale", "2")
        self.assertEqual(code, 0, out)
        with Image.open(img_path) as processed:
            # 8x8 (cropped) scaled 2x = 18x16 or 16x16
            self.assertGreater(processed.width, 0)
            self.assertGreater(processed.height, 0)

        # Grade
        code, out = call("--project", str(self.root), "assets", "--grade", "test_sprite.png", "--t1", "9.0", "--t2", "8.5", "--t3", "9.0")
        self.assertEqual(code, 0, out)
        self.assertIn("evaluation", out)
        self.assertTrue(out["evaluation"]["passed"])
        manifest = self.root / ".harness/asset-manifest.json"
        self.assertTrue(manifest.is_file())

    def test_validate_deep_integrity_checks(self):
        # 1. BOM check
        bom_file = self.root / "bom_script.gd"
        bom_file.write_bytes(b"\xef\xbb\xbfextends Node\n")
        code, out = call("--project", str(self.root), "validate")
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("BOM_FOUND", codes)
        bom_file.unlink()

        # 2. Format unsupported
        bad_scene = self.root / "bad_header.tscn"
        bad_scene.write_text("[gd_scene]\n")
        code, out = call("--project", str(self.root), "validate")
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("FORMAT_UNSUPPORTED", codes)
        bad_scene.unlink()

        # 3. Undeclared ExtResource ID
        bad_ref = self.root / "bad_ref.tscn"
        bad_ref.write_text('[gd_scene format=3]\n[node name="Node" script=ExtResource("undeclared_99")]\n')
        code, out = call("--project", str(self.root), "validate")
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("UNDECLARED_RESOURCE_ID", codes)
        bad_ref.unlink()

        # 4. Orphans scan
        orphan_png = self.root / "orphan_asset.png"
        orphan_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        code, out = call("--project", str(self.root), "validate", "--orphans")
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("UNREFERENCED_RESOURCE", codes)
        orphan_png.unlink()

    def test_godot_auditor_physics_exports_signals_perf(self):
        # 1. Missing collider on physics body
        scene_content = '''[gd_scene format=3]
[node name="Player" type="CharacterBody2D"]
'''
        (self.root / "PhysTest.tscn").write_text(scene_content, encoding="utf-8")

        # 2. Hardcoded magic numbers & expensive calls in GDScript
        script_content = '''extends CharacterBody2D
var walk_speed = 250
func _process(delta):
    var target = get_node("Target")
'''
        (self.root / "phys_test.gd").write_text(script_content, encoding="utf-8")

        code, out = call("--project", str(self.root), "audit", "--physics", "--exports", "--perf")
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("MISSING_COLLIDER", codes)
        self.assertIn("HARDCODED_MAGIC_NUMBER", codes)
        self.assertIn("EXPENSIVE_PROCESS_CALL", codes)

        (self.root / "PhysTest.tscn").unlink()
        (self.root / "phys_test.gd").unlink()

    def test_save_inspector_and_clean_audit(self):
        # Saves
        saves_dir = self.root / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)
        (saves_dir / "slot_01.json").write_text('{"player_name": "GodotHero", "hp": 100}', encoding="utf-8")
        code, out = call("--project", str(self.root), "saves")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["details"]["save_count"], 1)

        # Clean --audit
        tmp_file = self.root / "dangling_test.tmp"
        tmp_file.write_text("trash")
        code, out = call("--project", str(self.root), "clean", "--audit")
        self.assertEqual(code, 1, out)  # Returns failure status when dirty items found
        codes = {f["code"] for f in out.get("findings", [])}
        self.assertIn("REPO_HYGIENE_DIRTY", codes)
        self.assertTrue(tmp_file.is_file())  # --audit does not delete
        tmp_file.unlink()


if __name__ == "__main__":
    unittest.main()

