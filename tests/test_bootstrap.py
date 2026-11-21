import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

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

    def test_skills_planning_and_application(self):
        # 1. Verify skills="none" plans no skills dependency
        none_plan = bootstrap.make_plan(self.root, graphify="skip", skills="none")
        self.assertFalse(any(d.get("action") == "install_skills" for d in none_plan["dependencies"]))

        # 2. Verify skills="curated" plans core skills + graphify
        data = bootstrap.make_plan(self.root, graphify="skip", skills="curated")
        skills_dep = next((d for d in data["dependencies"] if d.get("action") == "install_skills"), None)
        self.assertIsNotNone(skills_dep)
        names = [s["name"] for s in skills_dep["skills"]]
        self.assertIn("graphify", names)
        self.assertIn("ponytail", names)
        self.assertIn("prompt-master", names)
        self.assertIn("godot-master", names)

        # 3. Verify write_plan formats proposed skills in markdown
        response = bootstrap.write_plan(data)
        review_md = Path(response["artifacts"][0]).read_text(encoding="utf-8")
        self.assertIn("Proposed skills (.agents/skills/):", review_md)
        self.assertIn("godot-master", review_md)
        self.assertIn("graphify", review_md)

        # 4. Verify apply_plan deploys core skills to .agents/skills/ and reference playbooks to .agents/playbooks/
        out = self.apply(data, Path(response["artifacts"][1]))
        self.assertEqual(out["status"], "success")
        graphify_skill = self.root / ".agents/skills/graphify/SKILL.md"
        self.assertTrue(graphify_skill.is_file())
        self.assertIn("name: graphify", graphify_skill.read_text(encoding="utf-8"))
        master_playbook = self.root / ".agents/playbooks/godot-master/SKILL.md"
        self.assertTrue(master_playbook.is_file())

    def test_gdh_v2_assets_installed_and_upgrade_flag_updates_modified_harness_files(self):
        # 1. Verify GDH v2 files are installed on initial apply
        data = bootstrap.make_plan(
            self.root,
            graphify="skip",
            ide="both",
            art_style="Dark Sci-Fi Vector UI",
            caveman="always",
            canva_mcp="enabled",
        )
        response = bootstrap.write_plan(data)
        out = self.apply(data, Path(response["artifacts"][1]))
        self.assertEqual(out["status"], "success")

        # GEMINI.md, docs/.gdignore, .context/project_state.json
        self.assertTrue((self.root / "GEMINI.md").is_file())
        self.assertTrue((self.root / "docs/.gdignore").is_file())
        state_file = self.root / ".context/project_state.json"
        self.assertTrue(state_file.is_file())
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state_data["art_style_direction"], "Dark Sci-Fi Vector UI")
        self.assertEqual(len(state_data["ctx_hash"]), 8)

        # Core tools: agent_lock.py and ui_pipeline/*
        self.assertTrue((self.root / "core/tools/agent_lock.py").is_file())
        for tool_name in ("bezel_profiler.py", "control_bounds_probe.gd", "mockup_dissect.py", "mockup_grade.py"):
            self.assertTrue((self.root / "core/tools/ui_pipeline" / tool_name).is_file(), f"Missing {tool_name}")

        # Focused rules in .agents/rules/
        for rule_name in ("directory_boundaries.md", "graphify.md", "canva_image_gen.md"):
            self.assertTrue((self.root / ".agents/rules" / rule_name).is_file(), f"Missing rule {rule_name}")

        # 6 core workflow skills in .agents/skills/
        for skill_name in (
            "core-architecture",
            "godot-test-qa",
            "ui-mockup-pipeline",
            "gdscript-migration",
            "agent-coordination",
            "token-budget",
        ):
            self.assertTrue((self.root / ".agents/skills" / skill_name / "SKILL.md").is_file(), f"Missing skill {skill_name}")
        self.assertTrue((self.root / ".agents/skills/ui-mockup-pipeline/references/style_guide_template.md").is_file())

        # 2. Simulate an outdated/modified harness file in an existing project and upgrade with upgrade=True
        (self.root / "game.py").write_text("# Old GDH v1 game.py\n", encoding="utf-8")
        (self.root / "core/tools/agent_lock.py").write_text("# Old agent_lock.py\n", encoding="utf-8")

        # Without upgrade=True, modified game.py blocks with conflict
        no_upgrade_plan = bootstrap.make_plan(self.root, graphify="skip", upgrade=False)
        self.assertTrue(no_upgrade_plan["conflicts"])

        # With upgrade=True, conflicts are resolved and harness files are cleanly updated
        upgrade_plan = bootstrap.make_plan(self.root, graphify="skip", upgrade=True)
        self.assertFalse(upgrade_plan["conflicts"], upgrade_plan["conflicts"])
        upgrade_resp = bootstrap.write_plan(upgrade_plan)
        upgrade_out = self.apply(upgrade_plan, Path(upgrade_resp["artifacts"][1]))
        self.assertEqual(upgrade_out["status"], "success")
        self.assertNotEqual((self.root / "game.py").read_text(encoding="utf-8"), "# Old GDH v1 game.py\n")
        self.assertIn("mockup-dissect", (self.root / "game.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

