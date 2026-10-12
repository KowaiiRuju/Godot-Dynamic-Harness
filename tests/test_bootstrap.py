import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_game_cli import ROOT

spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gdh setup ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.godot").write_text("config_version=5\n")
        context = {"engine_version": "4.7.2", "authored_settings": {"name": "Fixture", "main_scene": "res://Main.tscn"}}
        mocked = patch.object(bootstrap.game, "inspect_context", return_value=context)
        mocked.start()
        self.addCleanup(mocked.stop)

    def plan(self, **options):
        data = bootstrap.make_plan(self.root, graphify="skip", **options)
        response = bootstrap.write_plan(data)
        return data, Path(response["artifacts"][1])

    def apply(self, data, path):
        completed = subprocess.CompletedProcess([], 0, json.dumps({"command": "info", "status": "success", "summary": "Mocked discovery"}), "")
        with patch.object(bootstrap.game, "execute", return_value=completed):
            return bootstrap.apply_plan(path, data["approval_digest"])

    def test_plan_only_writes_review_artifacts_and_never_installs(self):
        with patch.object(bootstrap.game, "execute", side_effect=AssertionError("No installation/target game execution during planning")):
            data, path = self.plan(ide="both", smoke=True)
        self.assertTrue(path.exists())
        self.assertFalse((self.root / "game.py").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".harness/venv").exists())
        self.assertIn("tests/test_harness_smoke.gd", [e["path"] for e in data["changes"]])

    def test_approval_and_edited_plan_rejected(self):
        data, path = self.plan()
        with self.assertRaises(bootstrap.game.HarnessError):
            bootstrap.apply_plan(path, "not-approved")
        altered = json.loads(path.read_text())
        altered["ide"] = "vscode"
        path.write_text(json.dumps(altered))
        with self.assertRaises(bootstrap.game.HarnessError):
            bootstrap.apply_plan(path, data["approval_digest"])
        self.assertFalse((self.root / "game.py").exists())

    def test_stale_project_target_and_template_rejected_before_writes(self):
        for target in ("project.godot", "AGENTS.md"):
            data, path = self.plan()
            (self.root / target).write_text("Changed after review")
            with self.assertRaises(bootstrap.game.HarnessError) as caught:
                self.apply(data, path)
            self.assertEqual(caught.exception.code, "PLAN_STALE")
            self.assertFalse((self.root / "game.py").exists())
            (self.root / target).unlink()
            (self.root / "project.godot").write_text("config_version=5\n")
        data, path = self.plan()
        with patch.object(bootstrap, "source_snapshot", return_value={}):
            with self.assertRaises(bootstrap.game.HarnessError):
                self.apply(data, path)

    def test_both_adapters_preserve_existing_guidance_and_repeat_setup(self):
        (self.root / "AGENTS.md").write_text("My original project guidance\n")
        (self.root / ".github").mkdir()
        (self.root / ".github/copilot-instructions.md").write_text("My Copilot rule\n")
        data, path = self.plan(ide="both")
        out = self.apply(data, path)
        self.assertEqual(out["status"], "success")
        self.assertIn("My original project guidance", (self.root / "AGENTS.md").read_text())
        self.assertIn("My Copilot rule", (self.root / ".github/copilot-instructions.md").read_text())
        self.assertIn("trigger: always_on", (self.root / ".agents/rules/godot-harness.md").read_text())
        with patch.object(bootstrap.game, "execute", side_effect=AssertionError("Repeat must not run installs/checks")):
            out = bootstrap.apply_plan(path, data["approval_digest"])
        self.assertEqual(out["status"], "success")
        with (self.root / "docs/harness/PROJECT.md").open("a") as file:
            file.write("\nCustom design decision\n")
        second, _ = self.plan(ide="both")
        self.assertFalse(second["conflicts"])
        self.assertFalse(any(e["path"] == "docs/harness/PROJECT.md" for e in second["changes"]))

    def test_existing_custom_tool_blocks_apply(self):
        (self.root / "game.py").write_text("# My customized helper\n")
        data, path = self.plan()
        self.assertTrue(data["conflicts"])
        with self.assertRaises(bootstrap.game.HarnessError):
            self.apply(data, path)
        self.assertEqual((self.root / "game.py").read_text(), "# My customized helper\n")

    def test_dependency_failure_stops_before_tool_writes(self):
        with patch.object(bootstrap.game, "get_graphify_bin", return_value=None):
            data = bootstrap.make_plan(self.root, graphify="install")
            out = bootstrap.write_plan(data)
        completed = subprocess.CompletedProcess([], 1, "", "Install failed")
        with patch.object(bootstrap.game, "execute", return_value=completed):
            out = bootstrap.apply_plan(out["artifacts"][1], data["approval_digest"])
        self.assertEqual(out["status"], "failed")
        self.assertFalse((self.root / "game.py").exists())

    def test_png_grid_dependency_is_planned_in_local_environment_only(self):
        with patch.object(bootstrap, "pillow_available", return_value=False):
            data = bootstrap.make_plan(self.root, graphify="skip", png_grid=True)
        self.assertEqual(data["dependencies"][0]["package"], "Pillow")
        self.assertEqual(data["dependencies"][0]["commands"][1][-1], "Pillow")
        self.assertIn(".harness", data["dependencies"][0]["commands"][1][0])
        self.assertFalse((self.root / ".harness/venv").exists())

    def test_paths_and_partial_write_failure_do_not_lose_existing_files(self):
        data, path = self.plan()
        actual = bootstrap.game.atomic_write
        count = [0]
        def fail_third(target, content):
            count[0] += 1
            if count[0] == 3:
                raise PermissionError("simulated write failure")
            return actual(target, content)
        with patch.object(bootstrap.game, "atomic_write", side_effect=fail_third):
            with self.assertRaises(PermissionError):
                self.apply(data, path)
        self.assertFalse((self.root / "game.py").exists())
        for entry in data["changes"]:
            self.assertFalse((self.root / entry["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
