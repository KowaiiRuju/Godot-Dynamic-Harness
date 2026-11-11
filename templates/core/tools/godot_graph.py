"""A source-located Godot declaration/reference index for Graphify navigation."""
import re


def extract(root, files, code_text):
    nodes, links, ids = [], [], set()

    def node(identifier, label, path, line, **extra):
        if identifier not in ids:
            ids.add(identifier)
            nodes.append(dict(id=identifier, label=label, file_type="code", source_file=path,
                              source_location=f"L{line}", _origin="godot_source_index", **extra))

    def link(source, target, relation, path, line):
        links.append(dict(source=source, target=target, relation=relation, confidence="EXTRACTED",
                          source_file=path, source_location=f"L{line}", weight=1.0, _origin="godot_source_index"))

    # shortcut: declarations and explicit res:// references only; use source/engine checks for runtime wiring and dynamic paths.
    for file in files:
        relative = file.relative_to(root).as_posix()
        identifier = "godot::" + relative
        node(identifier, relative, relative, 1)
        text = file.read_text(encoding="utf-8")
        masked = code_text(text)
        for line, content in enumerate(masked.splitlines(), 1):
            declaration = re.match(r"\s*(?:static\s+)?(func|signal|class_name|class)\s+(\w+)", content)
            if declaration:
                kind, name = declaration.groups()
                child = identifier + "::" + kind + "::" + name + "::L" + str(line)
                node(child, name, relative, line, declaration_kind=kind)
                link(identifier, child, "declares", relative, line)
            extends_match = re.match(r"\s*extends\s+([\"']?)([\w/.:]+)\1", content)
            if extends_match:
                parent_type = extends_match.group(2)
                parent_id = ("godot::" + parent_type.removeprefix("res://")) if "res://" in parent_type else ("godot::class::" + parent_type)
                node(parent_id, parent_type, relative, line, is_builtin_or_type=True)
                link(identifier, parent_id, "extends", relative, line)
        offset = 0
        for line, content in enumerate(text.splitlines(), 1):
            if file.suffix in (".tscn", ".tres"):
                if content.startswith("[node "):
                    attrs = dict(re.findall(r'(\w+)="([^"\n]*)"', content))
                    name = attrs.get("name", "node")
                    child = identifier + "::node::" + attrs.get("parent", "") + "/" + name
                    node(child, name + " : " + attrs.get("type", "instance"), relative, line)
                    link(identifier, child, "contains_scene_node", relative, line)
                elif content.startswith("[connection "):
                    c_attrs = dict(re.findall(r'(\w+)="([^"\n]*)"', content))
                    sig = c_attrs.get("signal", "signal")
                    from_node = identifier + "::node::" + c_attrs.get("from", "")
                    to_node = identifier + "::node::" + c_attrs.get("to", "")
                    method = c_attrs.get("method", "")
                    link(from_node, to_node, f"signals::{sig}::{method}", relative, line)
                references = re.findall(r'^\[ext_resource\b.*?\bpath="(res://[^"\n]+)"', content)
                uid_matches = re.findall(r'\buid="(uid://[^"\n]+)"', content)
                for uid_val in uid_matches:
                    uid_id = "godot::uid::" + uid_val
                    node(uid_id, uid_val, relative, line, is_uid=True)
                    link(identifier, uid_id, "has_uid", relative, line)
            else:
                references = [match.group(1) for match in re.finditer(r'\b(?:load|preload)\s*\(\s*"(res://[^"\n]+)"', content)
                              if masked[offset + match.start():offset + match.start() + 4].strip()]
                uid_matches = [match.group(1) for match in re.finditer(r'\b(?:load|preload)\s*\(\s*"(uid://[^"\n]+)"', content)]
                for uid_val in uid_matches:
                    uid_id = "godot::uid::" + uid_val
                    node(uid_id, uid_val, relative, line, is_uid=True)
                    link(identifier, uid_id, "loads_uid", relative, line)
            for reference in references:
                target_path = reference.removeprefix("res://")
                target = (root / target_path).resolve()
                if target.is_relative_to(root):
                    target_id = "godot::" + target.relative_to(root).as_posix()
                    node(target_id, target_path, target_path, 1, reference_only=not target.exists())
                    link(identifier, target_id, "references_resource", relative, line)
            offset += len(content) + 1
    return {"nodes": nodes, "links": links, "directed": True}
