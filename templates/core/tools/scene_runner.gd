extends SceneTree

# scene_runner.gd
# General-purpose Godot SceneTree runner for headless offscreen scene capture,
# UI baseline inspection, scripted inputs, and interactive GameDriver IPC.

var output_dir: String = OS.get_environment("GAME_OUTPUT_DIR")
var target_scene: String = OS.get_environment("GAME_TARGET_SCENE")
var req_width: int = int(OS.get_environment("GAME_VIEWPORT_WIDTH"))
var req_height: int = int(OS.get_environment("GAME_VIEWPORT_HEIGHT"))
var props_json: String = OS.get_environment("GAME_PROPERTIES")
var inputs_json: String = OS.get_environment("GAME_INPUTS")
var fixed_fps: int = int(OS.get_environment("GAME_FIXED_FPS"))
var interactive_port: int = int(OS.get_environment("GAME_INTERACTIVE_PORT"))

var _tcp_server: TCPServer = null
var _tcp_peer: StreamPeerTCP = null

func _initialize() -> void:
	# Prevent stealing window focus when windows are displayed
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)

	if fixed_fps > 0:
		Engine.physics_ticks_per_second = fixed_fps
		Engine.max_fps = fixed_fps

	if output_dir.is_empty():
		output_dir = "res://screenshots/debug"
	if req_width <= 0:
		req_width = int(ProjectSettings.get_setting_with_override("display/window/size/viewport_width"))
	if req_height <= 0:
		req_height = int(ProjectSettings.get_setting_with_override("display/window/size/viewport_height"))
	if req_width <= 0:
		req_width = 1280
	if req_height <= 0:
		req_height = 720

	if interactive_port > 0:
		_start_interactive_server()
	else:
		call_deferred("_run_capture")

func _start_interactive_server() -> void:
	_tcp_server = TCPServer.new()
	var err = _tcp_server.listen(interactive_port, "127.0.0.1")
	if err != OK:
		push_error("Failed to start interactive TCP server on port %d: %d" % [interactive_port, err])
		quit(1)
		return
	print("GameDriver TCP server listening on 127.0.0.1:%d" % interactive_port)

func _process(_delta: float) -> bool:
	if _tcp_server and _tcp_server.is_listening():
		if not _tcp_peer and _tcp_server.is_connection_available():
			_tcp_peer = _tcp_server.take_connection()
		if _tcp_peer and _tcp_peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			while _tcp_peer.get_available_bytes() > 0:
				var line = _tcp_peer.get_utf8_string(_tcp_peer.get_available_bytes())
				for cmd_str in line.split("\n"):
					if cmd_str.strip_edges().is_empty():
						continue
					_handle_driver_command(cmd_str.strip_edges())
	return false

func _handle_driver_command(cmd_str: String) -> void:
	var parsed = JSON.parse_string(cmd_str)
	if typeof(parsed) != TYPE_DICTIONARY:
		_send_driver_response({"status": "error", "message": "Invalid JSON command"})
		return

	var cmd = parsed.get("cmd", "")
	match cmd:
		"step":
			var frames = int(parsed.get("frames", 1))
			for i in range(frames):
				await process_frame
			_send_driver_response({"status": "ok", "stepped": frames})
		"set_prop":
			var target_path = parsed.get("target", "")
			var prop = parsed.get("property", "")
			var val = parsed.get("value")
			var node = root.get_node_or_null(target_path) if not target_path.begins_with("%") else root.find_child(target_path.substr(1), true, false)
			if node:
				node.set(prop, val)
				_send_driver_response({"status": "ok", "property": prop, "value": val})
			else:
				_send_driver_response({"status": "error", "message": "Node not found: " + target_path})
		"get_prop":
			var target_path = parsed.get("target", "")
			var prop = parsed.get("property", "")
			var node = root.get_node_or_null(target_path) if not target_path.begins_with("%") else root.find_child(target_path.substr(1), true, false)
			if node:
				_send_driver_response({"status": "ok", "property": prop, "value": node.get(prop)})
			else:
				_send_driver_response({"status": "error", "message": "Node not found: " + target_path})
		"click_node":
			var target_path = parsed.get("target", "")
			var node = root.get_node_or_null(target_path) if not target_path.begins_with("%") else root.find_child(target_path.substr(1), true, false)
			if node and node is BaseButton:
				(node as BaseButton).emit_signal("pressed")
				_send_driver_response({"status": "ok", "clicked": target_path})
			else:
				_send_driver_response({"status": "error", "message": "Clickable button not found: " + target_path})
		"capture":
			var dest_path = parsed.get("path", output_dir.path_join("capture.png"))
			var global_dest = ProjectSettings.globalize_path(dest_path)
			var img: Image = root.get_texture().get_image()
			if img and not img.is_empty():
				img.save_png(global_dest)
				_send_driver_response({"status": "ok", "artifact": global_dest})
			else:
				_send_driver_response({"status": "error", "message": "Capture failed: empty image"})
		"quit":
			_send_driver_response({"status": "ok", "message": "quitting"})
			quit(0)
		_:
			_send_driver_response({"status": "error", "message": "Unknown command: " + cmd})

func _send_driver_response(data: Dictionary) -> void:
	if _tcp_peer and _tcp_peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		_tcp_peer.put_utf8_string(JSON.stringify(data) + "\n")

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

	# Apply runtime property overrides if provided
	if not props_json.is_empty():
		var parsed_props = JSON.parse_string(props_json)
		if typeof(parsed_props) == TYPE_DICTIONARY:
			_apply_properties(instance, parsed_props)

	# Execute scripted input sequence if provided
	if not inputs_json.is_empty():
		var parsed_inputs = JSON.parse_string(inputs_json)
		if typeof(parsed_inputs) == TYPE_ARRAY:
			await _execute_inputs(instance, parsed_inputs)

	# Await frames for layouts, themes, and shaders to settle
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw

	# Ensure target directory exists
	var global_out_dir = ProjectSettings.globalize_path(output_dir)
	if not DirAccess.dir_exists_absolute(global_out_dir):
		if DirAccess.make_dir_recursive_absolute(global_out_dir) != OK:
			push_error("Cannot create capture output directory")
			quit(1)
			return

	# Capture offscreen viewport image
	var img: Image = root.get_texture().get_image()
	if img == null or img.is_empty():
		push_error("Renderer returned no image")
		quit(1)
		return
	var file_path: String = output_dir.path_join("capture.png")
	var global_path: String = ProjectSettings.globalize_path(file_path)
	var save_err = img.save_png(global_path)

	if save_err == OK:
		print("Saved screenshot: %s" % global_path)
	else:
		push_error("Failed to save screenshot: %d" % save_err)
		quit(1)
		return

	# Dump node hierarchy rects and font inspection manifest
	var node_records: Array = []
	_inspect_nodes(instance, node_records)
	var manifest_path = global_out_dir.path_join("scene_manifest.json")
	var file = FileAccess.open(manifest_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify({
			"capture_id": OS.get_environment("GAME_CAPTURE_ID"),
			"scene": target_scene, "viewport": [img.get_width(), img.get_height()],
			"requested_viewport": [req_width, req_height],
			"renderer": RenderingServer.get_current_rendering_method(),
			"user_data_dir": OS.get_user_data_dir(), "nodes": node_records
		}, "  "))
		file.flush()
		if file.get_error() != OK:
			push_error("Cannot write capture manifest")
			file.close()
			quit(1)
			return
		file.close()
		print("Saved manifest: %s" % manifest_path)
	else:
		push_error("Cannot open capture manifest for writing")
		quit(1)
		return

	quit(0)

func _apply_properties(node: Node, props: Dictionary) -> void:
	for key in props.keys():
		var val = props[key]
		if "." in key:
			var parts = key.split(".")
			var target_child = parts[0]
			var prop_name = parts[1]
			var target_node = node.find_child(target_child, true, false) if target_child.begins_with("%") or not node.has_node(target_child) else node.get_node(target_child)
			if target_node:
				target_node.set(prop_name, val)
		else:
			node.set(key, val)

func _execute_inputs(instance: Node, inputs: Array) -> void:
	for item in inputs:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		var action = item.get("action", "")
		match action:
			"wait":
				var frames = int(item.get("frames", 1))
				for f in range(frames):
					await process_frame
			"click_node":
				var target_name = item.get("target", "")
				var btn: BaseButton = null
				if target_name.begins_with("%"):
					btn = instance.find_child(target_name.substr(1), true, false) as BaseButton
				elif instance.has_node(target_name):
					btn = instance.get_node(target_name) as BaseButton
				if btn:
					btn.emit_signal("pressed")
			"tap":
				var key = item.get("key", "ui_accept")
				var ev_down = InputEventAction.new()
				ev_down.action = key
				ev_down.pressed = true
				Input.parse_input_event(ev_down)
				await process_frame
				var ev_up = InputEventAction.new()
				ev_up.action = key
				ev_up.pressed = false
				Input.parse_input_event(ev_up)

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
