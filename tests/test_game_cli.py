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
        child = "import time; from pathlib import Path; time.sleep(1); Path(" + repr(str(marker)) + ").write_text('survived')"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(10)"
        with self.assertRaises(game.HarnessError) as caught:
            game.execute([sys.executable, "-c", parent], timeout=.3)
        self.assertEqual(caught.exception.code, "TIMEOUT")
        time.sleep(1.3)
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


if __name__ == "__main__":
    unittest.main()

