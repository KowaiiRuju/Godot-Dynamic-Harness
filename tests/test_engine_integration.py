import tempfile
import concurrent.futures
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from test_game_cli import call, game
from test_bootstrap import bootstrap


class EngineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.binary = game.get_godot_bin()
        except game.HarnessError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gdh engine ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.configure()

    def configure(self, width=640, height=360):
        (self.root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Harness fixture"\n'
            'run/main_scene="res://Main.tscn"\n[display]\n'
            f'window/size/viewport_width={width}\nwindow/size/viewport_height={height}\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (self.root / "Main.tscn").write_text(
            '[gd_scene format=3]\n[node name="Main" type="Control"]\n'
            'layout_mode=3\nanchors_preset=15\nanchor_right=1.0\nanchor_bottom=1.0\n'
            '[node name="Label" type="Label" parent="."]\ntext="Harness fixture"\n', encoding="utf-8")

    def invoke(self, *args):
        # Real-engine startup can page heavily on this shared 8 GB Windows host.
        # Explicit failure tests override this budget; the product default stays 30s.
        return call("--project", str(self.root), "--godot", self.binary, "--timeout", "90", *args)

    def test_probe_reads_settings_without_running_target_autoload(self):
        with (self.root / "project.godot").open("a", encoding="utf-8") as file:
            file.write('[autoload]\nDanger="*res://danger.gd"\n')
        (self.root / "danger.gd").write_text(
            'extends Node\nfunc _init() -> void:\n\tFileAccess.open("res://AUTLOAD_RAN", FileAccess.WRITE)\n', encoding="utf-8")
        code, out = self.invoke("info")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["context"]["authored_settings"]["viewport_width"], 640)
        self.assertFalse((self.root / "AUTLOAD_RAN").exists())
        self.configure(720, 1280)
        code, out = self.invoke("info")
        self.assertEqual(out["context"]["authored_settings"]["viewport_height"], 1280)
        (self.root / "project.godot").write_text("config_version=5\n")
        code, out = self.invoke("info")
        self.assertEqual(code, 0, out)
        self.assertIsNone(out["context"]["authored_settings"]["viewport_width"])
        self.assertIsNone(out["context"]["authored_settings"]["viewport_height"])

    def test_capture_defaults_override_and_artifact_failures(self):
        code, out = self.invoke("capture")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["capture"]["viewport"], [640, 360])
        self.assertEqual(out["capture"]["renderer"], "gl_compatibility")
        first = out["artifacts"]
        code, out = self.invoke("capture", "--width", "720", "--height", "1280")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["capture"]["viewport"], [720, 1280])
        self.assertNotEqual(first, out["artifacts"])
        for blocked in ("capture.png", "scene_manifest.json"):
            directory = self.root / ("blocked-" + blocked)
            (directory / blocked).mkdir(parents=True)
            code, out = self.invoke("capture", "--output", str(directory))
            self.assertEqual(code, 1, out)

    def test_engine_validation_valid_parse_error_and_broken_resource(self):
        (self.root / "valid.gd").write_text("extends Node\nfunc _ready() -> void:\n\tpass\n")
        code, out = self.invoke("validate", "--engine")
        self.assertEqual(code, 0, out)
        (self.root / "broken.gd").write_text("extends Node\nfunc invalid(:\n")
        code, out = self.invoke("validate", "--engine")
        self.assertEqual(code, 1, out)
        (self.root / "broken.gd").unlink()
        (self.root / "Broken.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://missing.gd" id="1"]\n[node name="Broken" type="Node"]\nscript=ExtResource("1")\n')
        code, out = self.invoke("validate")
        self.assertEqual(code, 1, out)
        self.assertTrue(any(f["code"] == "RESOURCE_REFERENCE" for f in out["findings"]))

    def test_nested_suites_success_assertion_and_timeout(self):
        directory = self.root / "tests/ui"
        directory.mkdir(parents=True)
        suite = directory / "test_smoke.gd"
        suite.write_text('extends SceneTree\nfunc _initialize() -> void:\n\tassert(load("res://Main.tscn") != null)\n\tquit(0)\n')
        code, out = self.invoke("test", "--suite", "tests/ui/test_smoke.gd")
        self.assertEqual(code, 0, out)
        suite.write_text('extends SceneTree\nfunc _initialize() -> void:\n\tcall_deferred("quit", 0)\n\tassert(false, "Intentional failing assertion")\n')
        code, out = self.invoke("test")
        self.assertEqual(code, 1, out)
        suite.write_text('extends SceneTree\nfunc _initialize() -> void:\n\tpass\n')
        code, out = self.invoke("test", "--timeout", "3")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["findings"][0]["code"], "TIMEOUT")

    def test_concurrent_calls_have_distinct_profiles_and_artifacts(self):
        command = [sys.executable, str(game.PROJECT_ROOT / "game.py"), "--project", str(self.root), "--godot", self.binary, "--timeout", "90", "capture", "--json"]
        def run():
            # Discovery/preflight/render each have a 90s child budget; allow the wrapper to finish
            # and kill its whole owned tree if the outer test budget is exceeded.
            completed = game.execute(command, timeout=600, log=False)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(lambda _: run(), range(2)))
        self.assertNotEqual(a["artifacts"], b["artifacts"])
        self.assertNotEqual(a["capture"]["user_data_dir"], b["capture"]["user_data_dir"])

    def test_reviewed_setup_with_graph_smoke_and_fresh_process_context(self):
        if not game.get_graphify_bin(self.root):
            self.skipTest("Graphify unavailable")
        plan = bootstrap.make_plan(self.root, ide="both", graphify="existing", smoke=True, godot=self.binary)
        review = bootstrap.write_plan(plan)
        self.assertFalse((self.root / "game.py").exists())
        self.assertFalse((self.root / "graphify-out/graph.json").exists())
        with contextlib.redirect_stderr(io.StringIO()):
            output = bootstrap.apply_plan(review["artifacts"][1], plan["approval_digest"])
        self.assertEqual(output["status"], "success", output)
        self.assertEqual(output["ide_session_compliance"], "unverified")
        command = [sys.executable, str(self.root / "game.py"), "--godot", self.binary]
        completed = subprocess.run([*command, "info", "--json"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        info = json.loads(completed.stdout)
        self.assertEqual(info["graph"]["status"], "fresh")
        self.assertFalse(info["context_stale"])
        completed = subprocess.run([*command, "graph", "--query", "Main", "--json"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Main.tscn", json.loads(completed.stdout)["output"])
        with (self.root / "Main.tscn").open("a") as file:
            file.write("\n# Changed after graph creation\n")
        completed = subprocess.run([*command, "info", "--json"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60)
        info = json.loads(completed.stdout)
        self.assertEqual(info["graph"]["status"], "stale")
        self.assertTrue(info["context_stale"])

    def test_unsafe_user_data_setting_is_rejected_before_target_autoload(self):
        with (self.root / "project.godot").open("a") as file:
            file.write('[autoload]\nDanger="*res://danger.gd"\n')
        (self.root / "danger.gd").write_text('extends Node\nfunc _init() -> void:\n\tFileAccess.open("res://AUTLOAD_RAN", FileAccess.WRITE)\n')
        (self.root / "override.cfg").write_text('[application]\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="../outside"\n')
        code, out = self.invoke("capture")
        self.assertEqual(code, 1, out)
        self.assertFalse((self.root / "AUTLOAD_RAN").exists())

    def test_batch_capture_grid_continues_after_failure_and_keeps_duplicate_basenames(self):
        scenes = []
        for index in range(6):
            directory = self.root / f"scene-{index}"
            directory.mkdir()
            path = directory / "Menu.tscn"
            path.write_text((self.root / "Main.tscn").read_text().replace("Harness fixture", f"Scene {index + 1}"))
            scenes.append("res://" + path.relative_to(self.root).as_posix())
        code, out = self.invoke("capture", "--scenes", *scenes, "res://missing.tscn", "--width", "360", "--height", "640")
        self.assertEqual(code, 1, out)
        self.assertEqual([c["status"] for c in out["captures"]], ["success"] * 6 + ["failed"], out)
        self.assertEqual([c["scene"] for c in out["captures"]], scenes + ["res://missing.tscn"])
        self.assertEqual(len({c["artifacts"][0] for c in out["captures"] if c["artifacts"]}), 6)
        self.assertTrue(any(p.endswith("gallery.html") for p in out["artifacts"]))
        if out["grid"]["png_grid"] == "available":
            self.assertEqual(sum(p.endswith(".png") and "contact_sheet_" in p for p in out["artifacts"]), 2)

    def test_capture_does_not_accept_stale_artifacts_from_a_scene_that_quits(self):
        code, out = self.invoke("capture", "--output", "same-output")
        self.assertEqual(code, 0, out)
        (self.root / "quitting.gd").write_text('extends Control\nfunc _ready() -> void:\n\tget_tree().quit(0)\n')
        (self.root / "Quitting.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://quitting.gd" id="1"]\n[node name="Quitting" type="Control"]\nscript=ExtResource("1")\n')
        code, out = self.invoke("capture", "--scene", "res://Quitting.tscn", "--output", "same-output")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["findings"][0]["code"], "ARTIFACT_INVALID")


if __name__ == "__main__":
    unittest.main()
