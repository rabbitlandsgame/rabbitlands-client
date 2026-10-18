extends SceneTree
## Interactive equipment review: the real client actor in a turntable viewer.
##
## Launched by review-equipment.bat:
##   Godot --path godot-client --script res://tools/equipment_review/equipment_review.gd -- [options]
## Options: --race luminous --sex male --set "<set name>" --clip Idle_Subtle --review-dir <dir>
##   --travel yes (walks and runs move the actor at the client's pace)
##   --equipment <equipment.json> (a copy pointing at candidate GLBs)
##   --replay <notes.jsonl> [--notes 7,13] [--out <dir>] [--travel yes|no] (re-shoot noted views, then quit)
## Everything else lives in review_app.gd.

const ReviewApp := preload("res://tools/equipment_review/review_app.gd")

func _init() -> void:
	var args := {}
	var values := OS.get_cmdline_user_args()
	for i in range(0, values.size() - 1, 2):
		args[values[i].trim_prefix("--")] = values[i + 1]
	var app: Node = ReviewApp.new()
	app.set("options", args)
	root.add_child.call_deferred(app)
