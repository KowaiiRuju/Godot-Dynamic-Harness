extends SceneTree

# scene_runner.gd
# General-purpose Godot SceneTree runner for headless offscreen scene capture and UI inspection.
# Configured via environment variables for cross-platform automation.

var output_dir: String = OS.get_environment("GAME_OUTPUT_DIR")
var target_scene: String = OS.get_environment("GAME_TARGET_SCENE")
var req_width: int = int(OS.get_environment("GAME_VIEWPORT_WIDTH"))
var req_height: int = int(OS.get_environment("GAME_VIEWPORT_HEIGHT"))

func _initialize() -> void:
	if output_dir.is_empty():
		output_dir = "res://screenshots/debug"
	if req_width <= 0:
		req_width = ProjectSettings.get_setting("display/window/size/viewport_width", 1280)
	if req_height <= 0:
		req_height = ProjectSettings.get_setting("display/window/size/viewport_height", 720)
	call_deferred("_run_capture")

func _run_capture() -> void:
	if target_scene.is_empty():
		push_error("Error: GAME_TARGET_SCENE environment variable is empty.")
		quit(1)
		return

	print("=== Headless Scene Capture: %s ===" % target_scene)
	var scene_res = load(target_scene)
	if not scene_res or not (scene_res is PackedScene):
		push_error("Failed to load PackedScene: " + target_scene)
		quit(1)
		return

	root.size = Vector2i(req_width, req_height)
	var instance = scene_res.instantiate()
	root.add_child(instance)

	# Await frames for layouts, themes, and shaders to settle
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw

	# Ensure target directory exists
	var dir_access = DirAccess.open("res://")
	var global_out_dir = ProjectSettings.globalize_path(output_dir)
	if not DirAccess.dir_exists_absolute(global_out_dir):
		DirAccess.make_dir_recursive_absolute(global_out_dir)

	# Capture offscreen viewport image
	var img: Image = root.get_texture().get_image()
	var base_name: String = target_scene.get_file().get_basename()
	var file_path: String = output_dir.path_join("%s_%dx%d.png" % [base_name, req_width, req_height])
	var global_path: String = ProjectSettings.globalize_path(file_path)
	var save_err = img.save_png(global_path)

	if save_err == OK:
		print("Saved screenshot: %s" % global_path)
	else:
		push_error("Failed to save screenshot: %d" % save_err)

	# Dump node hierarchy rects and font inspection manifest
	var node_records: Array = []
	_inspect_nodes(instance, node_records)
	var manifest_path = global_out_dir.path_join("scene_manifest.json")
	var file = FileAccess.open(manifest_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(node_records, "  "))
		file.close()
		print("Saved manifest: %s" % manifest_path)

	quit(0)

func _inspect_nodes(node: Node, records: Array) -> void:
	if node is Control and node.is_visible_in_tree():
		var c := node as Control
		var entry: Dictionary = {
			"path": str(node.get_path()),
			"name": str(node.name),
			"type": node.get_class(),
			"rect": [c.global_position.x, c.global_position.y, c.size.x, c.size.y],
			"mouse_filter": c.mouse_filter
		}
		if node is Label:
			entry["text"] = node.text
			entry["font_size"] = c.get_theme_font_size("font_size")
			entry["min_size"] = [node.get_minimum_size().x, node.get_minimum_size().y]
		elif node is RichTextLabel:
			entry["text"] = node.get_parsed_text()
			entry["font_size"] = c.get_theme_font_size("normal_font_size")
			entry["content_height"] = node.get_content_height()
		elif node is Button:
			entry["text"] = node.text
			entry["disabled"] = node.disabled
		records.append(entry)

	for child in node.get_children():
		_inspect_nodes(child, records)
