extends SceneTree

# test_smoke.gd - Loads scenes and asserts they are structurally sound.
#
# A suite that only reaches quit(0) proves nothing. This one loads each target
# scene and fails loudly on a null PackedScene, a null root, or a parse error,
# which is what a corrupt .tscn produces.

const TARGETS := [
	"res://scenes/main_menu.tscn",
]

func _initialize() -> void:
	var failures: Array[String] = []

	for path in TARGETS:
		if not ResourceLoader.exists(path):
			failures.append("%s: does not exist" % path)
			continue
		var res: Resource = load(path)
		if res == null:
			failures.append("%s: load() returned null (parse error)" % path)
			continue
		if not (res is PackedScene):
			failures.append("%s: not a PackedScene" % path)
			continue
		var inst: Node = (res as PackedScene).instantiate()
		if inst == null:
			failures.append("%s: instantiate() returned null" % path)
			continue
		root.add_child(inst)
		# Two frames is enough for _ready() and container layout to run, so a
		# crash in either surfaces here instead of on the first real frame.
		await process_frame
		await process_frame
		print("[smoke] OK   %s (%d children)" % [path, inst.get_child_count()])
		inst.queue_free()

	if failures.is_empty():
		print("[smoke] PASS: %d scene(s) loaded cleanly." % TARGETS.size())
		quit(0)
	else:
		for f in failures:
			printerr("[smoke] FAIL %s" % f)
		print("[smoke] FAIL: %d problem(s)." % failures.size())
		quit(1)
