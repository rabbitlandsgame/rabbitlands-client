extends SceneTree
const Controls := preload("res://src/platform/browser_storage_controls.gd")

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	var login := VBoxContainer.new()
	root.add_child(login)
	assert(Controls.attach_to(login, false) == null and login.get_child_count() == 0,
		"native login must not gain browser controls")
	var opened := [0]
	var button := Controls.attach_to(login, true, func(): opened[0] += 1)
	assert(button.get_parent() == login and button.text == "Asset storage & shortcut")
	assert(button.is_visible_in_tree() and opened[0] == 0,
		"settings are available before login and open only when requested")
	button.pressed.emit()
	assert(opened[0] == 1)
	login.hide()
	assert(not button.is_visible_in_tree(), "login visibility also hides its storage control")
	login.free()
	print("PASS browser storage login control, activation and native guard")
	quit()
