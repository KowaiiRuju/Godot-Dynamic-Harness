import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_game_cli import ROOT, call, game

AGENT_LOCK_PATH = ROOT / "templates/core/tools/agent_lock.py"
spec_lock = importlib.util.spec_from_file_location("agent_lock", AGENT_LOCK_PATH)
agent_lock = importlib.util.module_from_spec(spec_lock)
spec_lock.loader.exec_module(agent_lock)


def call_lock(root: Path, *argv):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = agent_lock.main(["--root", str(root), "--json", *argv])
    return code, json.loads(stdout.getvalue())


class AgentLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gdh agent_lock ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        self.target_file = self.root / "scenes/Player.tscn"
        self.target_file.parent.mkdir(parents=True, exist_ok=True)
        self.target_file.write_text('[gd_scene format=3]\n[node name="Player" type="Node2D"]\n', encoding="utf-8")

    def test_acquire_conflict_detection_and_check_status(self):
        # 1. Agent A acquires lease on scenes/Player.tscn
        code, res_a = call_lock(
            self.root,
            "acquire",
            "scenes\\Player.tscn",
            "--agent",
            "worker-alpha",
            "--task",
            "T-101",
            "--ttl",
            "120",
        )
        self.assertEqual(code, 0, res_a)
        self.assertEqual(res_a["status"], "success")
        self.assertEqual(res_a["acquired"], ["scenes/Player.tscn"])

        # 2. Check reports locked
        code, check_res = call_lock(self.root, "check", "res://scenes/Player.tscn")
        self.assertEqual(code, 1, check_res)
        self.assertEqual(check_res["status"], "locked")
        self.assertEqual(check_res["locked"][0]["owner"], "worker-alpha")

        # 3. Agent B attempts to acquire the same file -> conflict (exit code 1)
        code, res_b = call_lock(
            self.root,
            "acquire",
            "scenes/Player.tscn",
            "--agent",
            "worker-beta",
            "--task",
            "T-102",
        )
        self.assertEqual(code, 1, res_b)
        self.assertEqual(res_b["status"], "conflict")
        self.assertEqual(res_b["conflicts"][0]["owner"], "worker-alpha")
        self.assertEqual(res_b["conflicts"][0]["file"], "scenes/Player.tscn")

        # 4. Non-owner release without --force skips the lease
        code, rel_skip = call_lock(
            self.root,
            "release",
            "scenes/Player.tscn",
            "--agent",
            "worker-beta",
        )
        self.assertEqual(code, 0, rel_skip)
        self.assertEqual(rel_skip["released"], [])
        self.assertEqual(len(rel_skip["skipped"]), 1)

    def test_vscode_user_human_priority_preemption(self):
        # Worker acquires lease
        code, _ = call_lock(
            self.root,
            "acquire",
            "scenes/Player.tscn",
            "--agent",
            "worker-alpha",
            "--task",
            "T-101",
            "--ttl",
            "300",
        )
        self.assertEqual(code, 0)

        # vscode-user human agent preempts active worker lease without conflict
        code, human_res = call_lock(
            self.root,
            "acquire",
            "scenes/Player.tscn",
            "--agent",
            "vscode-user",
            "--task",
            "human-edit",
            "--ttl",
            "300",
        )
        self.assertEqual(code, 0, human_res)
        self.assertEqual(human_res["status"], "success")
        self.assertEqual(len(human_res["preempted"]), 1)
        self.assertEqual(human_res["preempted"][0]["previous_owner"], "worker-alpha")

        # Status shows vscode-user owns the lease with human priority
        code, status_res = call_lock(self.root, "status")
        self.assertEqual(code, 0, status_res)
        lease = status_res["active_leases"]["scenes/Player.tscn"]
        self.assertEqual(lease["agent_id"], "vscode-user")
        self.assertEqual(lease["priority"], "human")

    def test_write_off_sha256_journaling_and_release(self):
        call_lock(
            self.root,
            "acquire",
            "scenes/Player.tscn",
            "--agent",
            "worker-alpha",
            "--task",
            "T-200",
        )
        expected_sha = hashlib.sha256(self.target_file.read_bytes()).hexdigest()

        code, wo_res = call_lock(
            self.root,
            "write-off",
            "scenes/Player.tscn",
            "--agent",
            "worker-alpha",
            "--task",
            "T-200",
            "--summary",
            "Updated Player collision mask",
        )
        self.assertEqual(code, 0, wo_res)
        self.assertEqual(wo_res["status"], "success")
        self.assertEqual(wo_res["released"], ["scenes/Player.tscn"])
        self.assertEqual(wo_res["file_hashes"]["scenes/Player.tscn"], expected_sha)

        # Verify lease is now unlocked
        code, check_res = call_lock(self.root, "check", "scenes/Player.tscn")
        self.assertEqual(code, 0, check_res)
        self.assertEqual(check_res["status"], "unlocked")

        # Verify .agent-state/journal.jsonl contains the SHA-256 write-off entry
        journal_file = self.root / ".agent-state/journal.jsonl"
        self.assertTrue(journal_file.is_file())
        entries = [json.loads(line) for line in journal_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        write_offs = [e for e in entries if e["action"] == "write-off"]
        self.assertEqual(len(write_offs), 1)
        self.assertEqual(write_offs[0]["file_hashes"]["scenes/Player.tscn"], expected_sha)
        self.assertEqual(write_offs[0]["summary"], "Updated Player collision mask")

    def test_prune_expired_leases_directly_and_via_game_cli(self):
        # Acquire with negative TTL so it is already expired
        call_lock(
            self.root,
            "acquire",
            "scenes/Player.tscn",
            "--agent",
            "worker-stale",
            "--ttl",
            "-5",
        )
        code, prune_res = call_lock(self.root, "prune")
        self.assertEqual(code, 0, prune_res)
        self.assertEqual(prune_res["pruned_count"], 1)
        self.assertEqual(prune_res["remaining_count"], 0)

        # Verify game.py lock subcommand delegation if registered
        _, subcommands = game.build_parser()
        if "lock" in subcommands:
            code, cli_acq = call(
                "--project",
                str(self.root),
                "lock",
                "acquire",
                "scenes/Player.tscn",
                "--agent",
                "cli-worker",
                "--task",
                "CLI-1",
                "--ttl",
                "60",
            )
            self.assertEqual(code, 0, cli_acq)
            code, cli_wo = call(
                "--project",
                str(self.root),
                "lock",
                "write-off",
                "scenes/Player.tscn",
                "--agent",
                "cli-worker",
                "--summary",
                "CLI write-off test",
            )
            self.assertEqual(code, 0, cli_wo)
            code, cli_prune = call("--project", str(self.root), "lock", "prune")
            self.assertEqual(code, 0, cli_prune)


if __name__ == "__main__":
    unittest.main()
