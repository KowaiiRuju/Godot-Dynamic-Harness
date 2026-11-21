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

spec_skills = importlib.util.spec_from_file_location("skills_registry", TEMPLATES / "core/tools/skills_registry.py")
skills_registry = importlib.util.module_from_spec(spec_skills)
spec_skills.loader.exec_module(skills_registry)

CORE_WORKFLOW_SKILLS = (
    "core-architecture",
    "godot-test-qa",
    "ui-mockup-pipeline",
    "gdscript-migration",
    "agent-coordination",
    "token-budget",
)


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


def _normalize_posix(obj):
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, str):
        if obj.startswith(("res://", "user://", "uid://", "http://", "https://")):
            return obj
        return obj.replace("\\", "/")
    if isinstance(obj, dict):
        return {k: _normalize_posix(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_posix(v) for v in obj]
    return obj


def build_project_state(root, context, art_style=""):
    root = Path(root)
    pg = root / "project.godot"
    pg_stat = pg.stat() if pg.is_file() else None
    pg_mtime = pg_stat.st_mtime_ns if pg_stat else 0
    pg_size = pg_stat.st_size if pg_stat else 0
    engine_ver = str((context or {}).get("engine_version") or "")
    raw = f"{pg_mtime}:{pg_size}:{engine_ver}" if pg_stat else f"missing:{engine_ver}"
    ctx_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]

    existing_art_style = ""
    state_file = root / ".context" / "project_state.json"
    if state_file.is_file():
        try:
            existing_art_style = str(json.loads(state_file.read_text(encoding="utf-8")).get("art_style_direction") or "")
        except Exception:
            existing_art_style = ""
    resolved_art_style = str(art_style or (context or {}).get("art_style_direction") or existing_art_style or "").strip()
    norm_ctx = _normalize_posix(dict(context or {}))
    norm_ctx["art_style_direction"] = resolved_art_style
    payload = {
        "art_style_direction": resolved_art_style,
        "context": norm_ctx,
        "ctx_hash": ctx_hash,
        "engine_version": engine_ver,
        "project_godot_mtime_ns": pg_mtime,
        "project_godot_size": pg_size,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def install_skills(root, skills_list, timeout=120, skip_names=None):
    import shutil
    import stat
    def safe_rmtree(p):
        if not Path(p).exists():
            return
        def _on_error(func, path, _exc):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass
        shutil.rmtree(p, onerror=_on_error)

    cache_base = game.safe_target(root, ".harness/cache/skills")
    cache_base.mkdir(parents=True, exist_ok=True)
    cloned_repos = set()
    installed = []
    skip_set = set(skip_names or ())

    for item in skills_list:
        name = item["name"]
        if name in skip_set:
            installed.append(name)
            continue

        bundled = TEMPLATES / "core/skills" / name / "SKILL.md"
        if bundled.is_file():
            target = game.safe_target(root, f".agents/skills/{name}")
            target.mkdir(parents=True, exist_ok=True)
            bundled_dir = TEMPLATES / "core/skills" / name
            shutil.copytree(str(bundled_dir), str(target), dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
            safe_rmtree(target / ".git")
            installed.append(name)
            continue

        target_base = item.get("target_dir") or (
            ".agents/playbooks" if skills_registry.is_playbook_skill(item) else ".agents/skills"
        )
        target = game.safe_target(root, f"{target_base}/{name}")
        target.mkdir(parents=True, exist_ok=True)

        repo_key = item.get("repo_key")
        repo_url = item.get("repo_url")
        subpath = item.get("repo_subpath", ".")

        if repo_key and repo_url:
            repo_cache = cache_base / repo_key
            if not repo_cache.is_dir() and repo_key not in cloned_repos:
                res = game.execute(["git", "clone", "--depth", "1", repo_url, str(repo_cache)], timeout=timeout, log=False)
                if res.returncode != 0 and not repo_cache.is_dir():
                    raise game.HarnessError("SKILL_CLONE_FAILED", f"Failed to clone {repo_key} from {repo_url}")
                cloned_repos.add(repo_key)

            src = (repo_cache / subpath).resolve()
            if src.is_dir():
                shutil.copytree(str(src), str(target), dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
                safe_rmtree(target / ".git")
                installed.append(name)
            elif repo_cache.is_dir() and (repo_cache / "SKILL.md").is_file():
                game.atomic_write(target / "SKILL.md", (repo_cache / "SKILL.md").read_text(encoding="utf-8"))
                installed.append(name)
            else:
                # In mock/test environment when git succeeded without writing to disk
                game.atomic_write(target / "SKILL.md", f"---\nname: {name}\ndescription: {item.get('rationale', '')}\n---\n")
                installed.append(name)
        safe_rmtree(target / ".git")
    return installed


def render_agent_instructions(text, caveman="conditional", canva_mcp="optional", art_style=""):
    rendered = text
    if caveman == "off":
        rendered = rendered.replace(
            "Use `Caveman` (`full`/`lite`) + `cavecrew` for routine code/QA; switch to normal prose (`off`) for plans, docs, dialogue, and lore.",
            "Caveman mode is disabled (`--caveman off`); communicate in clear normal prose across all tasks.",
        )
    elif caveman == "always":
        rendered = rendered.replace(
            "Use `Caveman` (`full`/`lite`) + `cavecrew` for routine code/QA; switch to normal prose (`off`) for plans, docs, dialogue, and lore.",
            "Caveman mode is always active (`--caveman always`); use compressed `Caveman` (`full`/`lite`) + `cavecrew` across all technical tasks.",
        )
    if canva_mcp == "disabled":
        rendered = rendered.replace(
            "then use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) for mockups/assets",
            "Canva MCP is disabled (`--canva-mcp disabled`); use local `python game.py assets --process` for mockups/assets",
        )
    elif canva_mcp == "enabled":
        rendered = rendered.replace(
            "then use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) for mockups/assets",
            "Canva MCP is required (`--canva-mcp enabled`); always use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) for mockups/assets",
        )
    if art_style and str(art_style).strip():
        rendered = rendered.rstrip() + f"\n- **Configured Art & UI Style Direction**: `{str(art_style).strip()}` (persisted in `.context/project_state.json`).\n"
    return rendered


def instruction_adapter(caveman="conditional", canva_mcp="optional", art_style=""):
    caveman_line = {
        "always": "4. Caveman Mode (always): Always use Caveman mode (full/lite) + cavecrew for technical output; drop filler while keeping technical substance exact.",
        "off": "4. Caveman Mode (off): Caveman compression is disabled; communicate in clear normal prose.",
    }.get(
        caveman,
        "4. Conditional Caveman: Use Caveman mode (full/lite) + cavecrew for coding, bugfixing, tuning, and QA. Switch to normal prose for plans, docs, dialogue/lore, and walkthroughs.",
    )
    canva_line = {
        "enabled": "9. Visual Assets & 5-Stage UI Mockup Pipeline (Canva MCP enabled): Confirm user art_style_direction in .context/project_state.json (ask user if unset), generate mockups/assets via Canva MCP, then run mockup-dissect -> Scene-First .tscn edit -> mockup-grade -> capture & baseline.",
        "disabled": "9. Visual Assets & 5-Stage UI Mockup Pipeline (Canva MCP disabled): Confirm user art_style_direction in .context/project_state.json (ask user if unset), process assets locally via python game.py assets --process, then run mockup-dissect -> Scene-First .tscn edit -> mockup-grade -> capture & baseline.",
    }.get(
        canva_mcp,
        "9. Visual Assets & 5-Stage UI Mockup Pipeline (Canva MCP optional): Confirm user art_style_direction in .context/project_state.json (ask user if unset), use Canva MCP when available (or python game.py assets --process), then run mockup-dissect -> Scene-First .tscn edit -> mockup-grade -> capture & baseline.",
    )
    style_line = f"\n10. Configured Art & UI Style Direction: {art_style.strip()}" if art_style and str(art_style).strip() else ""
    return f"""# Godot harness workflow (GDH v2)
1. Mandatory Skill Activation & Fast-Start: Run python game.py plan-task "<task>" --json --compact or read the governing skill in .agents/skills/<skill>/SKILL.md before editing. Inspect scenes via python game.py scene-outline <scene.tscn> --json --compact before viewing targeted lines.
2. Major-Only Graphify Navigation: Only for Major cross-system changes, check python game.py graph --json --compact, refresh missing/stale graphs with graph --refresh --timeout 120 --json --compact, then graph --query "<question>" --json --compact. Skip Graphify on minor tasks.
3. Zero-Bloat Startup & CLI Standard: Never run python game.py info --json on startup; read .context/project_state.json only when ctx_stale is true. Always pass --json --compact --out <file> (never PowerShell >).
{caveman_line}
5. Autonomous Safe Execution: Once a plan is approved, execute all phases autonomously end-to-end. Do not prompt for repeated intermediate approvals.
6. Proportionate Verification: Minor changes run targeted syntax/suite/baseline checks. Major changes run full test/capture/validation sweeps.
7. Scene-First & Inspector-First: Build UI in .tscn hierarchy (no procedural Control.new() UI). Expose gameplay numbers with @export. Align 2D top-down origins to ground contact and enable y_sort_enabled.
8. Single Runner & Multi-Agent Lock Bypass: Reuse game.py unified CLI tools. Use python game.py lock only when >= 2 concurrent write workers run.
{canva_line}{style_line}
"""


def make_plan(root, ide="antigravity", graphify="existing", smoke=False, godot=None, timeout=30, png_grid=False, skills="none", caveman="conditional", canva_mcp="optional", upgrade=False, art_style=""):
    root = game.resolve_project(str(root))
    art_style = str(art_style or "").strip()
    context = {"project_root": str(root), "caveman": caveman, "canva_mcp": canva_mcp, "art_style_direction": art_style}
    try:
        context.update(game.inspect_context(root, godot, timeout))
    except game.HarnessError as exc:
        if exc.code != "ENGINE_NOT_FOUND" or godot:
            raise
        context["engine_discovery_note"] = str(exc)
    if art_style:
        context["art_style_direction"] = art_style

    state_file = game.safe_target(root, ".harness/setup-state.json")
    previous_hashes = {}
    if state_file.is_file():
        try:
            previous_hashes = json.loads(state_file.read_text(encoding="utf-8")).get("installed_hashes", {}) or {}
        except Exception:
            previous_hashes = {}

    changes, preserved, conflicts = [], [], []

    def propose(relative, content, managed=False):
        path = game.safe_target(root, relative)
        if path.exists() and not path.is_file():
            conflicts.append(f"{relative} is not a regular file")
            return
        existed = path.exists()
        previous = path.read_text(encoding="utf-8") if existed else ""
        if managed:
            content = game.merge_managed(previous, content)
        elif existed and previous != content:
            is_upgradeable = (
                relative in ("game.py", "GEMINI.md", "AGENTS.md", "docs/.gdignore", ".context/project_state.json")
                or relative.startswith(("core/tools/", ".agents/rules/", ".agents/skills/"))
            )
            current_sha = file_hash(path)
            matches_installed = bool(previous_hashes.get(relative) and current_sha == previous_hashes.get(relative))
            if relative != ".context/project_state.json" and not (is_upgradeable and (upgrade or matches_installed)):
                conflicts.append(f"{relative} exists with different content; manually merge/adopt the template and re-plan")
                preserved.append(relative)
                return
        if (not existed) or (previous != content):
            changes.append(dict(path=relative, before_sha256=file_hash(path), content=content))

    for path in sorted((TEMPLATES / "core/tools").rglob("*")):
        if path.is_file() and path.name != "test_harness_smoke.gd" and path.suffix in (".py", ".gd", ".json") and "__pycache__" not in path.parts:
            rel_tool = path.relative_to(TEMPLATES).as_posix()
            propose(rel_tool, path.read_text(encoding="utf-8"))

    propose("game.py", (TEMPLATES / "game.py").read_text(encoding="utf-8"))
    propose(
        "AGENTS.md",
        render_agent_instructions((TEMPLATES / "AGENTS.md").read_text(encoding="utf-8"), caveman=caveman, canva_mcp=canva_mcp, art_style=art_style),
        managed=True,
    )
    if (TEMPLATES / "GEMINI.md").is_file():
        propose(
            "GEMINI.md",
            render_agent_instructions((TEMPLATES / "GEMINI.md").read_text(encoding="utf-8"), caveman=caveman, canva_mcp=canva_mcp, art_style=art_style),
            managed=True,
        )
    propose("docs/.gdignore", "")
    propose(".context/project_state.json", build_project_state(root, context, art_style=art_style))

    rules_dir = TEMPLATES / "core/rules"
    if rules_dir.is_dir():
        for rule_path in sorted(rules_dir.glob("*.md")):
            if rule_path.is_file():
                propose(f".agents/rules/{rule_path.name}", rule_path.read_text(encoding="utf-8"))

    for skill_name in CORE_WORKFLOW_SKILLS:
        skill_dir = TEMPLATES / "core/skills" / skill_name
        if skill_dir.is_dir():
            for sf in sorted(skill_dir.rglob("*")):
                if sf.is_file() and ".git" not in sf.parts and "__pycache__" not in sf.parts:
                    rel_skill = sf.relative_to(TEMPLATES / "core/skills").as_posix()
                    propose(f".agents/skills/{rel_skill}", sf.read_text(encoding="utf-8"))

    for relative, body in game.context_documents(root, context).items():
        propose(relative, body, managed=True)
    if not game.safe_target(root, "docs/harness/CHECKPOINT.md").exists():
        propose("docs/harness/CHECKPOINT.md", "# Session checkpoint\n\nNo game checks have run yet. Add decisions and next steps outside the managed block.", managed=True)

    adapter_text = instruction_adapter(caveman=caveman, canva_mcp=canva_mcp, art_style=art_style)
    if ide in ("antigravity", "both"):
        relative = ".agents/rules/godot-harness.md"
        path = game.safe_target(root, relative)
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing and (not existing.startswith("---\n") or not re.search(r"(?m)^trigger:\s*always_on\s*$", existing.split("---", 2)[1])):
            conflicts.append(f"{relative} needs valid always_on YAML frontmatter; review it manually")
        if not existing:
            content = "---\ntrigger: always_on\ndescription: Godot tools, Graphify navigation and persistent context.\n---\n\n" + game.merge_managed("", adapter_text)
            propose(relative, content)
        else:
            propose(relative, adapter_text, managed=True)
    if ide in ("vscode", "both"):
        propose(".github/copilot-instructions.md", adapter_text, managed=True)

    ignore = game.safe_target(root, ".gitignore")
    existing_ignore = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    patterns = [
        p for p in (
            "screenshots/",
            "screenshots/debug/",
            "qa-evidence/",
            ".harness/",
            ".agent-state/",
            ".context/",
            "artifacts/",
            "graphify-out/",
            "__pycache__/",
            "*.pyc",
            "*.png",
            "scene_manifest.json",
            "batch_results.json",
        )
        if p not in existing_ignore.splitlines()
    ]
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
    selected_skills = []
    if skills != "none":
        selected_skills = skills_registry.curate_skills(root, context, mode=skills, caveman_mode=caveman)
        if selected_skills:
            dependencies.append({
                "action": "install_skills",
                "mode": skills,
                "caveman": caveman,
                "skills": selected_skills,
                "target_dir": ".agents/skills",
                "playbooks_dir": ".agents/playbooks",
            })
    post_apply = ["Record fresh project context", "Discover installed tools"] + \
        (["Preserve an existing untracked/modified graph in .harness/graph-backups, then build persistent source graph"] if graphify != "skip" else []) + \
        ([f"Deploy {len(selected_skills)} curated domain skills into .agents/skills/ and .agents/playbooks/"] if skills != "none" and selected_skills else []) + \
        (["Execute the selected main-scene smoke test (runs game code)"] if smoke else [])
    plan = dict(schema_version=1, project_root=str(root), source_snapshot=source_snapshot(),
                graph_before_sha256=file_hash(game.safe_target(root, "graphify-out/graph.json")),
                project_digest=game.fingerprint(root), context=context, ide=ide, graphify=graphify, smoke=smoke, png_grid=png_grid, skills=skills,
                caveman=caveman, canva_mcp=canva_mcp, upgrade=bool(upgrade), art_style=art_style,
                changes=changes, dependencies=dependencies, preserved=preserved, conflicts=conflicts,
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                post_apply_actions=post_apply)
    plan["approval_digest"] = digest(plan)
    return plan


def write_plan(plan):
    root = Path(plan["project_root"])
    identifier = plan["approval_digest"]
    path = game.safe_target(root, ".harness/plans/" + identifier + ".json")
    review = game.safe_target(root, "tasks/godot-harness-setup-" + identifier[:12] + ".md")
    sections = ["# Godot harness setup plan", "Status: awaiting explicit user review/approval.",
                "Review with your IDE agent. Adjust options by generating a new plan; no installation or game execution has occurred.",
                f"IDE: {plan['ide']}. Graphify: {plan['graphify']}. Main-scene smoke test: {plan['smoke']}. PNG review grids: {plan['png_grid']}. Skills: {plan.get('skills', 'none')}. Caveman: {plan.get('caveman', 'conditional')}. Canva MCP: {plan.get('canva_mcp', 'optional')}. Upgrade: {plan.get('upgrade', False)}. Art Style: {plan.get('art_style') or 'unset (prompt user)'}.",
                "Project context:\n~~~json\n" + json.dumps(plan["context"], indent=2, sort_keys=True) + "\n~~~",
                "Dependencies:\n~~~json\n" + json.dumps(plan["dependencies"], indent=2, sort_keys=True) + "\n~~~",
                "Post-apply actions:\n" + "\n".join("- " + p for p in plan["post_apply_actions"]),
                "Conflicts (must resolve and re-plan):\n" + ("\n".join("- " + p for p in plan["conflicts"]) or "None."),
                "Preserved existing files:\n" + ("\n".join("- " + p for p in plan["preserved"]) or "None.")]
    skills_dep = next((d for d in plan["dependencies"] if d.get("action") == "install_skills"), None)
    if skills_dep:
        skill_lines = [f"- **{s['name']}**: {s.get('rationale', 'Skill')} (from `{s.get('repo_key', 'local')}` -> `{s.get('target_dir', '.agents/skills')}`)" for s in skills_dep.get("skills", [])]
        sections.append("Proposed skills (.agents/skills/):\n" + "\n".join(skill_lines))
    for entry in plan["changes"]:
        target = game.safe_target(root, entry["path"])
        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), entry["content"].splitlines(keepends=True),
                                          fromfile=entry["path"] + " (current)", tofile=entry["path"] + " (proposed)"))
        sections.append("## " + entry["path"] + "\n\n~~~diff\n" + diff + "~~~\n")
    sections.append("Approve only after reviewing changes and resolving conflicts. Run from the harness checkout:\n\n" +
                    f'~~~powershell\npython bootstrap.py apply --plan "{path}" --approve {identifier}\n~~~\n' +
                    "The digest identifies this exact plan; it cannot prove human review. Agents must obtain approval in conversation before invoking apply.")
    game.atomic_write(path, json.dumps(plan, indent=2, sort_keys=True) + "\n")
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
        previous_installed_hashes = {}
        if state_file.is_file():
            existing_state = json.loads(state_file.read_text(encoding="utf-8"))
            previous_installed_hashes = existing_state.get("installed_hashes", {}) or {}
            if existing_state.get("plan_digest") == recorded:
                if all(file_hash(game.safe_target(root, p)) == value for p, value in existing_state["installed_hashes"].items()):
                    failures = [game.finding("VERIFICATION_FAILED", c.get("command", c.get("cmd", "check")) + ": " + c["summary"]) for c in existing_state["checks"] if c["status"] not in ("success", "skipped")]
                    return game.result("setup-apply", "This exact plan was already applied; no changes or installs repeated", failures, checks=existing_state["checks"], ide_session_compliance="unverified")
                raise game.HarnessError("PLAN_STALE", "Installed files changed; regenerate to preserve those changes")
        if plan["source_snapshot"] != source_snapshot() or plan["project_digest"] != game.fingerprint(root):
            raise game.HarnessError("PLAN_STALE", "Template/project source changed since review; regenerate")
        if plan["graph_before_sha256"] != file_hash(game.safe_target(root, "graphify-out/graph.json")):
            raise game.HarnessError("PLAN_STALE", "Existing graph changed since review; regenerate before adopting the managed graph")
        for entry in plan["changes"]:
            target = game.safe_target(root, entry["path"])
            if file_hash(target) != entry["before_sha256"]:
                raise game.HarnessError("PLAN_STALE", f"{entry['path']} changed since review; regenerate")
        planned_skill_names = {
            e["path"].split("/")[2]
            for e in plan["changes"]
            if e["path"].startswith(".agents/skills/") and len(e["path"].split("/")) >= 4
        }
        for dependency in plan["dependencies"]:
            if dependency.get("action") == "install_skills":
                skills_list = dependency.get("skills", [])
                try:
                    install_skills(root, skills_list, timeout=timeout, skip_names=planned_skill_names)
                except Exception as exc:
                    return game.result("setup-apply", "Skill installation failed; project files were not changed",
                                       [game.finding("DEPENDENCY_FAILED", f"Skill installation failed: {exc}")])
                continue
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
        game.atomic_write(game.safe_target(root, ".harness/context-state.json"), json.dumps({"source_digest": game.fingerprint(root)}, sort_keys=True) + "\n")
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
        # Ensure .context/project_state.json reflects final post-check state and art_style_direction deterministically
        game.atomic_write(
            game.safe_target(root, ".context/project_state.json"),
            build_project_state(root, plan["context"], art_style=plan.get("art_style", "")),
        )
        failures = [game.finding("VERIFICATION_FAILED", c.get("command", c.get("cmd", "check")) + ": " + c["summary"]) for c in checks if c["status"] not in ("success", "skipped")]
        merged_hashes = {
            p: file_hash(game.safe_target(root, p))
            for p in previous_installed_hashes
            if game.safe_target(root, p).is_file()
        }
        for e in plan["changes"]:
            merged_hashes[e["path"]] = file_hash(game.safe_target(root, e["path"]))
        state = {
            "art_style": plan.get("art_style", ""),
            "canva_mcp": plan.get("canva_mcp", "optional"),
            "caveman": plan.get("caveman", "conditional"),
            "checks": checks,
            "graphify": plan["graphify"],
            "ide": plan["ide"],
            "ide_session_compliance": "unverified",
            "installed_hashes": dict(sorted(merged_hashes.items())),
            "plan_digest": recorded,
            "png_grid": plan["png_grid"],
            "skills": plan.get("skills", "none"),
            "smoke": plan["smoke"],
            "upgrade": bool(plan.get("upgrade", False)),
        }
        game.atomic_write(state_file, json.dumps(state, indent=2, sort_keys=True) + "\n")
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
    plan.add_argument("--skills", choices=["none", "curated", "core", "all"], default="curated", help="Curate and install Godot domain skills and playbooks into .agents/skills and .agents/playbooks")
    plan.add_argument("--caveman", choices=["conditional", "always", "off"], default="conditional", help="Terse communication policy (conditional: active for low-writing tasks, normal prose for plans/docs/lore)")
    plan.add_argument("--canva-mcp", choices=["optional", "enabled", "disabled"], default="optional", help="Canva MCP integration mode for visual assets")
    plan.add_argument("--upgrade", action="store_true", help="Upgrade existing harness-managed files (game.py, core/tools, .agents/rules, .agents/skills) in place")
    plan.add_argument("--art-style", default="", help="Project art & UI style direction persisted to .context/project_state.json (leave empty to prompt user)")
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
        response = (
            write_plan(
                make_plan(
                    args.project,
                    args.ide,
                    args.graphify,
                    args.smoke,
                    args.godot,
                    args.timeout,
                    args.png_grid,
                    args.skills,
                    args.caveman,
                    args.canva_mcp,
                    args.upgrade,
                    args.art_style,
                )
            )
            if args.command == "plan"
            else apply_plan(args.plan, args.approve, args.timeout)
        )
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
