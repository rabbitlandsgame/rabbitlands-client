extends SceneTree
## Interactive equipment review: the real client actor in a turntable viewer.
##
## Launched by review-equipment.bat:
##   Godot --path godot-client --script res://tools/equipment_review/equipment_review.gd -- [options]
## Options: --race luminous --sex male --set "<set name>" --clip Idle_Subtle --review-dir <dir>
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
