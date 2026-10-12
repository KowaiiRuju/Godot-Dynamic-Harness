extends SceneTree

# Read authored configuration in a scratch project; never start target autoloads.
func _initialize() -> void:
	var config: ConfigFile = ConfigFile.new()
	var error: Error = config.load(OS.get_environment("GAME_PROJECT_CONFIG"))
	if error != OK:
		push_error("Cannot read project configuration: %s" % error)
		quit(1)
		return
	var profile_config_path: String = OS.get_environment("GAME_PROFILE_CONFIG")
	if not profile_config_path.is_empty():
		var profile_config: ConfigFile = ConfigFile.new()
		var override: ConfigFile = ConfigFile.new()
		var override_path: String = OS.get_environment("GAME_PROJECT_CONFIG").get_base_dir().path_join("override.cfg")
		if FileAccess.file_exists(override_path) and override.load(override_path) != OK:
			push_error("Cannot read override.cfg for user-data preflight")
			quit(1)
			return
		for source: ConfigFile in [config, override]:
			if not source.has_section("application"):
				continue
			for key: String in source.get_section_keys("application"):
				for prefix: String in ["config/name", "config/features", "config/use_custom_user_dir", "config/custom_user_dir_name"]:
					if key.begins_with(prefix):
						var value: Variant = source.get_value("application", key)
						if prefix in ["config/name", "config/custom_user_dir_name"]:
							var candidate: String = str(value).replace("\\", "/")
							if candidate.is_absolute_path() or ".." in candidate.split("/"):
								push_error("Unsafe user-data directory setting: " + key)
								quit(1)
								return
						profile_config.set_value("application", key, value)
		if profile_config.save(profile_config_path) != OK:
			push_error("Cannot write isolated user-data preflight configuration")
			quit(1)
			return
	var settings: Dictionary = {
		"name": config.get_value("application", "config/name", "Unnamed project"),
		"main_scene": config.get_value("application", "run/main_scene", ""),
		"features": config.get_value("application", "config/features", []),
		"viewport_width": config.get_value("display", "window/size/viewport_width") if config.has_section_key("display", "window/size/viewport_width") else null,
		"viewport_height": config.get_value("display", "window/size/viewport_height") if config.has_section_key("display", "window/size/viewport_height") else null,
		"renderer": config.get_value("rendering", "renderer/rendering_method") if config.has_section_key("rendering", "renderer/rendering_method") else null,
		"autoloads": {}
	}
	if config.has_section("autoload"):
		for key: String in config.get_section_keys("autoload"):
			settings["autoloads"][key] = config.get_value("autoload", key)
	print("HARNESS_JSON=" + JSON.stringify(settings))
	quit(0)
