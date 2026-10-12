extends SceneTree

func _initialize() -> void:
	var profile: String = OS.get_environment("GAME_PROFILE_ROOT").replace("\\", "/").simplify_path()
	var user_dir: String = OS.get_user_data_dir().replace("\\", "/").simplify_path()
	if profile.is_empty() or not user_dir.to_lower().begins_with(profile.to_lower() + "/"):
		push_error("User data is not isolated: " + user_dir)
		quit(1)
		return
	var paths: Variant = JSON.parse_string(OS.get_environment("GAME_CHECK_FILES"))
	if not paths is Array:
		push_error("GAME_CHECK_FILES must be an array")
		quit(1)
		return
	for path: String in paths:
		if load(path) == null:
			push_error("Resource failed to load: " + path)
			quit(1)
			return
	print("HARNESS_JSON=" + JSON.stringify({"user_data_dir": user_dir, "resources_loaded": paths.size()}))
	quit(0)
