#!/usr/bin/env python3
"""Version-scoped migration hints and explicit, atomic rule learning; not a compiler."""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

JSON_LOG = Path(__file__).resolve().parent / "gdscript_version_changes.json"
# Mask comments and strings while preserving newlines and therefore finding locations.
NON_CODE = re.compile(r'(["\'])\1\1[\s\S]*?\1\1\1|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|#[^\n]*')


def code_text(text):
    return NON_CODE.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m.group()), text)


def version_tuple(value):
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise ValueError(f"Expected a numeric engine version, got {value!r}")
    return tuple((list(map(int, value.split("."))) + [0, 0])[:3])


def validate_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("version_migrations", []), list):
        raise ValueError("Invalid rule database")
    practices = data.get("engine_best_practices", {})
    if not isinstance(practices, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in practices.items()):
        raise ValueError("Practices must be string notes")
    for migration in data.get("version_migrations", []):
        if not isinstance(migration, dict) or not isinstance(migration.get("changes"), list):
            raise ValueError("Invalid migration block")
        for change in migration["changes"]:
            if not isinstance(change, dict) or not all(isinstance(change.get(k), str) and change[k] for k in ("old", "new")):
                raise ValueError("A rule needs nonempty old/new strings")
            if "verified" in change and not isinstance(change["verified"], bool):
                raise ValueError("verified must be a boolean")
            if change.get("verified"):
                if change.get("matcher") not in ("token", "call", "annotation"):
                    raise ValueError("Only escaped token/call/annotation matchers are allowed")
                if not isinstance(change.get("literal"), str) or not 0 < len(change["literal"]) <= 500:
                    raise ValueError("Invalid rule literal")
                low = version_tuple(change["min_version"])
                high = version_tuple(change["max_version_exclusive"])
                if low >= high:
                    raise ValueError("Invalid rule version range")
                source = urlparse(change.get("source_url", ""))
                if source.scheme != "https" or not source.netloc:
                    raise ValueError("Verified rules require an HTTPS source URL")
    return data


def load_changes():
    return validate_data(json.loads(JSON_LOG.read_text(encoding="utf-8")))


def save_changes(data, expected_digest=None):
    validate_data(data)
    if expected_digest is not None and hashlib.sha256(JSON_LOG.read_bytes()).hexdigest() != expected_digest:
        raise ValueError("Rule database changed; retry learning after reviewing the new file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=JSON_LOG.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, JSON_LOG)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def active_rules(data, version):
    target = version_tuple(version)
    active, inactive = [], []
    for migration in data.get("version_migrations", []):
        for change in migration["changes"]:
            if change.get("type") == "best_practice" or not change.get("verified"):
                inactive.append({"old": change["old"], "reason": "Style advice or unverified/versionless note"})
            elif version_tuple(change["min_version"]) <= target < version_tuple(change["max_version_exclusive"]):
                active.append(change)
            else:
                inactive.append({"old": change["old"], "reason": "Outside the selected engine version range"})
    return active, inactive


def matcher(rule):
    literal = re.escape(rule["literal"]).replace(r"\ ", r"\s+")
    prefix = "" if rule["literal"].startswith(".") else r"(?<![\w@])"
    suffix = r"\s*\(" if rule["matcher"] == "call" else r"(?!\w)"
    return re.compile(prefix + literal + suffix)


def scan_file(path, version, data=None):
    data = load_changes() if data is None else validate_data(data)
    rules, inactive = active_rules(data, version)
    patterns = [(matcher(rule), rule) for rule in rules]
    findings = []
    for line, text in enumerate(code_text(Path(path).read_text(encoding="utf-8")).splitlines(), 1):
        for pattern, rule in patterns:
            if pattern.search(text):
                findings.append(dict(code="MIGRATION_HINT", file=str(path), line=line,
                                     message=f"{rule['old']} -> {rule['new']}", source_url=rule["source_url"]))
    return {"findings": findings, "inactive_rules": inactive, "rules_checked": len(rules)}


def cmd_query(args):
    data = load_changes()
    matches = [c for m in data.get("version_migrations", []) for c in m["changes"]
               if args.keyword.lower() in (c["old"] + " " + c["new"]).lower()]
    return {"matches": matches, "practice_notes": {key: value for key, value in data.get("engine_best_practices", {}).items() if args.keyword.lower() in (key + " " + value).lower()}}


def cmd_scan(args):
    return scan_file(args.file, args.engine_version)


def cmd_learn(args):
    lock = JSON_LOG.with_suffix(".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        original = JSON_LOG.read_bytes()
        data = validate_data(json.loads(original))
        if args.practice_key and args.practice_desc:
            practices = data.setdefault("engine_best_practices", {})
            if args.practice_key in practices and practices[args.practice_key] != args.practice_desc:
                raise ValueError("Practice already exists with different content; refusing overwrite")
            practices[args.practice_key] = args.practice_desc
        elif args.syntax_old and args.syntax_new:
            change = dict(old=args.syntax_old, new=args.syntax_new, type="learned",
                          context=args.syntax_context or "Explicitly learned project note.", verified=args.verified)
            if args.verified:
                change.update(min_version=args.min_version, max_version_exclusive=args.max_version_exclusive,
                              matcher=args.matcher, literal=args.literal, source_url=args.source_url)
            for block in data.get("version_migrations", []):
                for existing in block["changes"]:
                    if existing["old"] == change["old"]:
                        if existing != change:
                            raise ValueError("Rule already exists with different content; refusing conflicting update")
                        return {"summary": "Identical rule already exists"}
            block = next((m for m in data["version_migrations"] if m.get("from_version") == "Learned"), None)
            if block is None:
                block = {"from_version": "Learned", "to_version": "Version-scoped", "changes": []}
                data["version_migrations"].append(block)
            block["changes"].append(change)
        else:
            raise ValueError("Supply a complete practice or syntax pair")
        save_changes(data, hashlib.sha256(original).hexdigest())
        return {"summary": "Saved verified rule" if args.verified else "Saved note; unverified syntax notes do not become scan rules"}
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    query = sub.add_parser("query")
    query.add_argument("keyword")
    scan = sub.add_parser("scan")
    scan.add_argument("file")
    scan.add_argument("--engine-version", required=True)
    learn = sub.add_parser("learn")
    for key in ("practice-key", "practice-desc", "syntax-old", "syntax-new", "syntax-context",
                "min-version", "max-version-exclusive", "matcher", "literal", "source-url"):
        learn.add_argument("--" + key)
    learn.add_argument("--verified", action="store_true", help="Explicit assertion that source and version range were reviewed")
    args = parser.parse_args(argv)
    try:
        output = {"query": cmd_query, "scan": cmd_scan, "learn": cmd_learn}[args.command](args)
        print(json.dumps(output, ensure_ascii=False))
        return 1 if output.get("findings") else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
