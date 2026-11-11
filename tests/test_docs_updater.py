import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_game_cli import ROOT

spec = importlib.util.spec_from_file_location("docs", ROOT / "templates/core/tools/docs_updater.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class Rules(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        original = docs.JSON_LOG
        docs.JSON_LOG = self.root / "rules.json"
        self.addCleanup(setattr, docs, "JSON_LOG", original)
        docs.save_changes({"version_migrations": [], "engine_best_practices": {}})
        self.script = self.root / "example.gd"
        self.script.write_text("old_api()\n", encoding="utf-8")

    def learn(self, **overrides):
        values = dict(practice_key=None, practice_desc=None, syntax_old="old_api()", syntax_new="new_api()",
                      syntax_context="Reviewed test rule", verified=True, min_version="4.0",
                      max_version_exclusive="4.8", matcher="call", literal="old_api",
                      source_url="https://docs.godotengine.org/en/4.7/")
        values.update(overrides)
        return docs.cmd_learn(SimpleNamespace(**values))

    def test_learn_scan_query_and_version_bounds(self):
        self.learn()
        self.assertEqual(len(docs.scan_file(self.script, "4.7.2")["findings"]), 1)
        self.assertFalse(docs.scan_file(self.script, "4.8")["findings"])
        self.assertEqual(len(docs.cmd_query(SimpleNamespace(keyword="old_api"))["matches"]), 1)
        self.assertIn("already exists", self.learn()["summary"])

    def test_unverified_notes_stay_inactive(self):
        self.learn(verified=False)
        self.assertFalse(docs.scan_file(self.script, "4.7")["findings"])

    def test_invalid_conflicting_and_locked_updates_preserve_bytes(self):
        self.learn()
        original = docs.JSON_LOG.read_bytes()
        for change in ({"syntax_new": "other()"}, {"syntax_old": "other", "matcher": "regex"}):
            with self.assertRaises(ValueError):
                self.learn(**change)
            self.assertEqual(original, docs.JSON_LOG.read_bytes())
        docs.JSON_LOG.with_suffix(".lock").write_text("locked")
        with self.assertRaises(FileExistsError):
            self.learn()
        self.assertEqual(original, docs.JSON_LOG.read_bytes())

    def test_strings_comments_annotations_and_token_boundaries(self):
        self.learn()
        self.script.write_text('# old_api()\nvar text = "old_api() # text"\nother_old_api()\nold_api ()\n', encoding="utf-8")
        self.assertEqual([f["line"] for f in docs.scan_file(self.script, "4.7")["findings"]], [4])
        rule = {"matcher": "annotation", "literal": "export var"}
        self.assertFalse(docs.matcher(rule).search("@export var x"))
        self.assertTrue(docs.matcher(rule).search("export   var x"))

    def test_malformed_database_rejected_without_write(self):
        docs.JSON_LOG.write_text("{broken")
        with self.assertRaises(ValueError):
            docs.load_changes()
        self.assertEqual(docs.JSON_LOG.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
