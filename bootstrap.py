#!/usr/bin/env python3
"""Inspect -> review a hashed setup plan -> apply explicitly approved actions."""
import datetime
import difflib
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
TEMPLATES = REPO / "templates"
spec = importlib.util.spec_from_file_location("harness", TEMPLATES / "game.py")
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def source_snapshot():
    return {p.relative_to(REPO).as_posix(): file_hash(p) for p in sorted(TEMPLATES.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def dependency_commands(root, package="graphifyy"):
    environment = game.safe_target(root, ".harness/venv")
    return [[sys.executable, "-m", "venv", str(environment)],
            [str(environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")), "-m", "pip", "install", package]]


def pillow_available(root):
    if importlib.util.find_spec("PIL") is not None:
        return True
    python = root / ".harness/venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if python.is_file():
        checked = game.execute([str(python), "-c", "import PIL"], timeout=10, log=False)
        return checked.returncode == 0
    return False


def instruction_adapter():
    return """# Godot harness workflow
Before codebase investigations, check python game.py graph --json, refresh missing/stale graphs, then use graph --query "<question>" --json. Verify findings against source.
In fresh sessions read docs/harness/PROJECT.md, TOOLS.md, CHECKPOINT.md and AGENTS.md; run python game.py info --json.
Inspect first, present a tailored plan, and wait for user review/approval before setup changes. Preserve user content.
Keep graph/context current after code changes. Tool evidence is not gameplay or IDE-compliance proof.
"""


def make_plan(root, ide="antigravity", graphify="existing", smoke=False, godot=None, timeout=30, png_grid=False):
    root = game.resolve_project(str(root))
    context = {"project_root": str(root)}
    try:
        context.update(game.inspect_context(root, godot, timeout))
    except game.HarnessError as exc:
        if exc.code != "ENGINE_NOT_FOUND" or godot:
            raise
        context["engine_discovery_note"] = str(exc)
    changes, preserved, conflicts = [], [], []
    def propose(relative, content, managed=False):
        path = game.safe_target(root, relative)
        if path.exists() and not path.is_file():
            conflicts.append(f"{relative} is not a regular file")
            return
        previous = path.read_text(encoding="utf-8") if path.exists() else ""
        if managed:
            content = game.merge_managed(previous, content)
        elif path.exists() and previous != content:
            conflicts.append(f"{relative} exists with different content; manually merge/adopt the template and re-plan")
            preserved.append(relative)
            return
        if previous != content:
            changes.append(dict(path=relative, before_sha256=file_hash(path), content=content))
    for path in sorted((TEMPLATES / "core/tools").iterdir()):
        if path.is_file() and path.name != "test_harness_smoke.gd" and path.suffix in (".py", ".gd", ".json"):
            propose("core/tools/" + path.name, path.read_text(encoding="utf-8"))
    propose("game.py", (TEMPLATES / "game.py").read_text(encoding="utf-8"))
    propose("AGENTS.md", (TEMPLATES / "AGENTS.md").read_text(encoding="utf-8"), managed=True)
    for relative, body in game.context_documents(root, context).items():
        propose(relative, body, managed=True)
    if not game.safe_target(root, "docs/harness/CHECKPOINT.md").exists():
        propose("docs/harness/CHECKPOINT.md", "# Session checkpoint\n\nNo game checks have run yet. Add decisions and next steps outside the managed block.", managed=True)
    if ide in ("antigravity", "both"):
        relative = ".agents/rules/godot-harness.md"
        path = game.safe_target(root, relative)
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing and (not existing.startswith("---\n") or not re.search(r"(?m)^trigger:\s*always_on\s*$", existing.split("---", 2)[1])):
            conflicts.append(f"{relative} needs valid always_on YAML frontmatter; review it manually")
        if not existing:
            content = "---\ntrigger: always_on\ndescription: Godot tools, Graphify navigation and persistent context.\n---\n\n" + game.merge_managed("", instruction_adapter())
            propose(relative, content)
        else:
            propose(relative, instruction_adapter(), managed=True)
    if ide in ("vscode", "both"):
        propose(".github/copilot-instructions.md", instruction_adapter(), managed=True)
    ignore = game.safe_target(root, ".gitignore")
    existing_ignore = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    patterns = [p for p in ("screenshots/", "screenshots/debug/", "qa-evidence/", ".harness/", "graphify-out/", "__pycache__/", "*.pyc", "*.png", "scene_manifest.json", "batch_results.json") if p not in existing_ignore.splitlines()]
    if ignore.exists() and not ignore.is_file():
        conflicts.append(".gitignore is not a regular file")
    elif patterns:
        changes.append(dict(path=".gitignore", before_sha256=file_hash(ignore),
                            content=existing_ignore.rstrip() + "\n\n# Godot harness local state\n" + "\n".join(patterns) + "\n"))
    if smoke:
        propose("tests/test_harness_smoke.gd", (TEMPLATES / "core/tools/test_harness_smoke.gd").read_text(encoding="utf-8"))
    dependencies = []
    if graphify == "install" and not game.get_graphify_bin(root):
        dependencies.append({"action": "install_graphify", "package": "graphifyy", "environment": ".harness/venv", "commands": dependency_commands(root)})
    if png_grid and not pillow_available(root):
        dependencies.append({"action": "install_pillow", "package": "Pillow", "environment": ".harness/venv", "commands": dependency_commands(root, "Pillow")})
    if graphify == "existing" and not game.get_graphify_bin(root):
        conflicts.append("Graphify is missing: regenerate with --graphify install, or explicitly select skip")
    plan = dict(schema_version=1, project_root=str(root), source_snapshot=source_snapshot(),
                graph_before_sha256=file_hash(game.safe_target(root, "graphify-out/graph.json")),
                project_digest=game.fingerprint(root), context=context, ide=ide, graphify=graphify, smoke=smoke, png_grid=png_grid,
                changes=changes, dependencies=dependencies, preserved=preserved, conflicts=conflicts,
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                post_apply_actions=["Record fresh project context", "Discover installed tools"] +
                    (["Preserve an existing untracked/modified graph in .harness/graph-backups, then build persistent source graph"] if graphify != "skip" else []) +
                    (["Execute the selected main-scene smoke test (runs game code)"] if smoke else []))
    plan["approval_digest"] = digest(plan)
    return plan


def write_plan(plan):
    root = Path(plan["project_root"])
    identifier = plan["approval_digest"]
    path = game.safe_target(root, ".harness/plans/" + identifier + ".json")
    review = game.safe_target(root, "tasks/godot-harness-setup-" + identifier[:12] + ".md")
    sections = ["# Godot harness setup plan", "Status: awaiting explicit user review/approval.",
                "Review with your IDE agent. Adjust options by generating a new plan; no installation or game execution has occurred.",
                f"IDE: {plan['ide']}. Graphify: {plan['graphify']}. Main-scene smoke test: {plan['smoke']}. PNG review grids: {plan['png_grid']}.",
                "Project context:\n~~~json\n" + json.dumps(plan["context"], indent=2) + "\n~~~",
                "Dependencies:\n~~~json\n" + json.dumps(plan["dependencies"], indent=2) + "\n~~~",
                "Post-apply actions:\n" + "\n".join("- " + p for p in plan["post_apply_actions"]),
                "Conflicts (must resolve and re-plan):\n" + ("\n".join("- " + p for p in plan["conflicts"]) or "None."),
                "Preserved existing files:\n" + ("\n".join("- " + p for p in plan["preserved"]) or "None.")]
    for entry in plan["changes"]:
        target = game.safe_target(root, entry["path"])
        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), entry["content"].splitlines(keepends=True),
                                          fromfile=entry["path"] + " (current)", tofile=entry["path"] + " (proposed)"))
        sections.append("## " + entry["path"] + "\n\n~~~diff\n" + diff + "~~~\n")
    sections.append("Approve only after reviewing changes and resolving conflicts. Run from the harness checkout:\n\n" +
                    f'~~~powershell\npython bootstrap.py apply --plan "{path}" --approve {identifier}\n~~~\n' +
                    "The digest identifies this exact plan; it cannot prove human review. Agents must obtain approval in conversation before invoking apply.")
    game.atomic_write(path, json.dumps(plan, indent=2) + "\n")
    game.atomic_write(review, "\n\n".join(sections) + "\n")
    return game.result("setup-plan", "Review the tailored plan before applying; no dependencies installed", artifacts=[str(review), str(path)], approval_digest=identifier, conflicts=plan["conflicts"])


def apply_plan(plan_path, approval, timeout=120):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    recorded = plan.pop("approval_digest")
    if recorded != digest(plan) or approval != recorded:
        raise game.HarnessError("PLAN_NOT_APPROVED", "Supply the digest of the exact reviewed plan; altered plans require regeneration")
    if plan.get("schema_version") != 1:
        raise game.HarnessError("PLAN_UNSUPPORTED", "Unsupported setup plan schema")
    root = game.resolve_project(plan["project_root"])
    if plan["conflicts"]:
        raise game.HarnessError("SETUP_CONFLICT", "Resolve plan conflicts and regenerate before applying")
    lock = game.safe_target(root, ".harness/setup.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        state_file = game.safe_target(root, ".harness/setup-state.json")
        if state_file.is_file() and json.loads(state_file.read_text(encoding="utf-8")).get("plan_digest") == recorded:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if all(file_hash(game.safe_target(root, p)) == value for p, value in state["installed_hashes"].items()):
                failures = [game.finding("VERIFICATION_FAILED", c["command"] + ": " + c["summary"]) for c in state["checks"] if c["status"] not in ("success", "skipped")]
                return game.result("setup-apply", "This exact plan was already applied; no changes or installs repeated", failures, checks=state["checks"], ide_session_compliance="unverified")
            raise game.HarnessError("PLAN_STALE", "Installed files changed; regenerate to preserve those changes")
        if plan["source_snapshot"] != source_snapshot() or plan["project_digest"] != game.fingerprint(root):
            raise game.HarnessError("PLAN_STALE", "Template/project source changed since review; regenerate")
        if plan["graph_before_sha256"] != file_hash(game.safe_target(root, "graphify-out/graph.json")):
            raise game.HarnessError("PLAN_STALE", "Existing graph changed since review; regenerate before adopting the managed graph")
        for entry in plan["changes"]:
            target = game.safe_target(root, entry["path"])
            if file_hash(target) != entry["before_sha256"]:
                raise game.HarnessError("PLAN_STALE", f"{entry['path']} changed since review; regenerate")
        for dependency in plan["dependencies"]:
            package = {"install_graphify": "graphifyy", "install_pillow": "Pillow"}.get(dependency.get("action"))
            if package is None or dependency != {"action": dependency["action"], "package": package, "environment": ".harness/venv", "commands": dependency_commands(root, package)}:
                raise game.HarnessError("INVALID_DEPENDENCY", "Unsupported dependency action")
            for command in dependency["commands"]:
                completed = game.execute(command, timeout=timeout)
                if completed.returncode:
                    return game.result("setup-apply", "Dependency installation failed; project files were not changed",
                                       [game.finding("DEPENDENCY_FAILED", "See stderr; local environment may be partially installed")])
        originals = {}
        if plan["project_digest"] != game.fingerprint(root) or any(file_hash(game.safe_target(root, e["path"])) != e["before_sha256"] for e in plan["changes"]):
            raise game.HarnessError("PLAN_STALE", "Project changed during dependency installation; regenerate before writing files")
        try:
            for entry in plan["changes"]:
                target = game.safe_target(root, entry["path"])
                originals[target] = target.read_bytes() if target.is_file() else None
                game.atomic_write(target, entry["content"])
        except (OSError, game.HarnessError):
            for target, content in originals.items():
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    game.atomic_write(target, content.decode("utf-8"))
            raise
        game.atomic_write(game.safe_target(root, ".harness/context-state.json"), json.dumps({"source_digest": game.fingerprint(root)}) + "\n")
        checks = []
        commands = [["info", "--json"], ["context", "--refresh", "--json"]]
        if plan["graphify"] != "skip":
            commands.append(["graph", "--refresh", "--json"])
        if plan["smoke"]:
            commands.append(["test", "--suite", "tests/test_harness_smoke.gd", "--json"])
        for command in commands:
            invocation = [sys.executable, str(root / "game.py"), "--project", str(root), "--timeout", str(timeout)]
            if plan["context"].get("engine_binary"):
                invocation += ["--godot", plan["context"]["engine_binary"]]
            completed = game.execute([*invocation, *command], cwd=root, timeout=timeout, log=False)
            try:
                checks.append(json.loads(completed.stdout))
            except ValueError:
                checks.append(game.result(command[0], "Installed tool returned invalid JSON", [game.finding("VERIFICATION_FAILED", completed.stderr[-1500:])]))
        failures = [game.finding("VERIFICATION_FAILED", c["command"] + ": " + c["summary"]) for c in checks if c["status"] not in ("success", "skipped")]
        state = {"plan_digest": recorded, "ide": plan["ide"], "graphify": plan["graphify"], "smoke": plan["smoke"], "png_grid": plan["png_grid"], "checks": checks, "ide_session_compliance": "unverified",
                 "installed_hashes": {e["path"]: file_hash(game.safe_target(root, e["path"])) for e in plan["changes"]}}
        game.atomic_write(state_file, json.dumps(state, indent=2) + "\n")
        return game.result("setup-apply", "Approved setup applied; inspect verification results", failures,
                           artifacts=[str(game.safe_target(root, e["path"])) for e in plan["changes"]], checks=checks,
                           ide_session_compliance="unverified", graphify_skipped=plan["graphify"] == "skip")
    finally:
        lock.unlink()


def main(argv=None):
    parser = game.Parser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--project", required=True)
    plan.add_argument("--ide", choices=["antigravity", "vscode", "both"], default="antigravity")
    plan.add_argument("--graphify", choices=["existing", "install", "skip"], default="existing")
    plan.add_argument("--smoke", action="store_true", help="Propose a main-scene smoke test and execute after approval")
    plan.add_argument("--png-grid", action="store_true", help="Propose optional Pillow installation for PNG contact sheets")
    plan.add_argument("--godot")
    plan.add_argument("--timeout", type=float, default=30)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--approve", required=True, help="Digest of the plan explicitly reviewed by the user")
    apply.add_argument("--timeout", type=float, default=120)
    try:
        args = parser.parse_args(argv)
        if args.timeout <= 0:
            raise game.HarnessError("INVALID_ARGUMENT", "Timeout must be positive")
        response = write_plan(make_plan(args.project, args.ide, args.graphify, args.smoke, args.godot, args.timeout, args.png_grid)) if args.command == "plan" else apply_plan(args.plan, args.approve, args.timeout)
    except game.HarnessError as exc:
        response = game.result("setup", str(exc), [game.finding(exc.code, str(exc))])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        response = game.result("setup", str(exc), [game.finding("SETUP_FAILED", str(exc))])
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response["status"] == "success" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
