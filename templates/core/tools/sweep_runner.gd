extends SceneTree

# sweep_runner.gd - Loads one scene, reports whether it stayed healthy, exits.
# Driven by core/tools/scene_sweep.py. Reads a single scene per process so a
# crash in one scene cannot mask the rest of the project.

var target_scene: String = ""

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		args = OS.get_cmdline_args()
	for i in range(args.size()):
		if args[i] == "--scene" and i + 1 < args.size():
			target_scene = args[i + 1]
	call_deferred("_run")

func _run() -> void:
	if target_scene.is_empty():
		printerr("[sweep] no --scene given")
		quit(1)
		return

	if not ResourceLoader.exists(target_scene):
		printerr("[sweep] FAIL missing: " + target_scene)
		quit(1)
		return

	var res: Resource = load(target_scene)
	if res == null or not (res is PackedScene):
		printerr("[sweep] FAIL unloadable: " + target_scene)
		quit(1)
		return

	var inst: Node = (res as PackedScene).instantiate()
	if inst == null:
		printerr("[sweep] FAIL instantiate: " + target_scene)
		quit(1)
		return

	root.add_child(inst)
	await process_frame
	await process_frame
	print("[sweep] OK %s (%d children)" % [target_scene, inst.get_child_count()])
	quit(0)
