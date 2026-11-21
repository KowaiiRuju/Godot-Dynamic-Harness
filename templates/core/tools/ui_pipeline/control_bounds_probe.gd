extends SceneTree

func _init() -> void:
	var scene_path: String = OS.get_environment("GAME_PROBE_SCENE")
	if scene_path.is_empty():
		scene_path = str(ProjectSettings.get_setting("application/run/main_scene", ""))
	if scene_path.is_empty():
		print("HARNESS_JSON=" + JSON.stringify({"ok": false, "error": "GAME_PROBE_SCENE is empty and no application/run/main_scene is configured", "controls": []}, "", true))
		quit(1)
		return
	var vp_w: int = int(OS.get_environment("GAME_VIEWPORT_W")) if OS.get_environment("GAME_VIEWPORT_W").is_valid_int() else 1280
	var vp_h: int = int(OS.get_environment("GAME_VIEWPORT_H")) if OS.get_environment("GAME_VIEWPORT_H").is_valid_int() else 720
	root.size = Vector2i(vp_w, vp_h)

	var packed: Resource = ResourceLoader.load(scene_path)
	if packed == null or not (packed is PackedScene):
		print("HARNESS_JSON=" + JSON.stringify({"ok": false, "error": "Failed to load PackedScene: " + scene_path, "controls": []}, "", true))
		quit(1)
		return

	var instance: Node = packed.instantiate()
	if instance == null:
		print("HARNESS_JSON=" + JSON.stringify({"ok": false, "error": "Failed to instantiate: " + scene_path, "controls": []}, "", true))
		quit(1)
		return

	root.add_child(instance)
	await process_frame
	await process_frame

	var controls: Array = []
	_collect_controls(instance, instance, controls)
	print("HARNESS_JSON=" + JSON.stringify({
		"ok": true,
		"scene": scene_path,
		"viewport": [vp_w, vp_h],
		"control_count": controls.size(),
		"controls": controls,
	}, "", true))
	quit(0)


func _collect_controls(node: Node, scene_root: Node, out: Array) -> void:
	if node is Control:
		var ctrl := node as Control
		var r: Rect2 = ctrl.get_global_rect()
		var min_sz: Vector2 = ctrl.custom_minimum_size
		var styles: Dictionary = {}
		for style_name in ["panel", "normal", "hover", "pressed", "fill", "background"]:
			if ctrl.has_theme_stylebox_override(style_name) or ctrl.has_theme_stylebox(style_name):
				var sb: StyleBox = ctrl.get_theme_stylebox(style_name)
				if sb != null:
					styles[style_name] = _serialize_stylebox(sb)
		out.append({
			"name": str(ctrl.name),
			"path": str(scene_root.get_path_to(ctrl)),
			"class": ctrl.get_class(),
			"visible": ctrl.is_visible_in_tree(),
			"rect": {
				"x": snapped(r.position.x, 0.01),
				"y": snapped(r.position.y, 0.01),
				"w": snapped(r.size.x, 0.01),
				"h": snapped(r.size.y, 0.01),
			},
			"custom_minimum_size": {
				"x": snapped(min_sz.x, 0.01),
				"y": snapped(min_sz.y, 0.01),
			},
			"styles": styles,
		})
	for child in node.get_children():
		_collect_controls(child, scene_root, out)


func _serialize_stylebox(sb: StyleBox) -> Dictionary:
	var data := {
		"type": sb.get_class(),
		"content_margin_left": sb.content_margin_left,
		"content_margin_top": sb.content_margin_top,
		"content_margin_right": sb.content_margin_right,
		"content_margin_bottom": sb.content_margin_bottom,
	}
	if sb is StyleBoxTexture:
		var sbt := sb as StyleBoxTexture
		data["patch_margin_left"] = sbt.texture_margin_left
		data["patch_margin_top"] = sbt.texture_margin_top
		data["patch_margin_right"] = sbt.texture_margin_right
		data["patch_margin_bottom"] = sbt.texture_margin_bottom
		data["texture"] = sbt.texture.resource_path if sbt.texture != null else ""
	elif sb is StyleBoxFlat:
		var sbf := sb as StyleBoxFlat
		data["border_width_left"] = sbf.border_width_left
		data["border_width_top"] = sbf.border_width_top
		data["border_width_right"] = sbf.border_width_right
		data["border_width_bottom"] = sbf.border_width_bottom
		data["corner_radius_top_left"] = sbf.corner_radius_top_left
		data["corner_radius_top_right"] = sbf.corner_radius_top_right
		data["corner_radius_bottom_right"] = sbf.corner_radius_bottom_right
		data["corner_radius_bottom_left"] = sbf.corner_radius_bottom_left
	return data
