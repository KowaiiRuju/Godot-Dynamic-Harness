extends SceneTree

func _initialize() -> void:
	call_deferred("_check_main_scene")

func _check_main_scene() -> void:
	var main_scene: String = str(ProjectSettings.get_setting("application/run/main_scene", ""))
	if main_scene.is_empty():
		push_error("No main scene configured")
		quit(1)
		return
	var packed: PackedScene = load(main_scene) as PackedScene
	if packed == null:
		push_error("Main scene failed to load")
		quit(1)
		return
	var instance: Node = packed.instantiate()
	root.add_child(instance)
	await process_frame
	await process_frame
	quit(0)
