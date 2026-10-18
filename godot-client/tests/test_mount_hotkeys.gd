extends SceneTree
const Controls := preload("res://src/mounts/mount_hotkeys.gd")
var checks := 0
var failures := 0

func key(code: Key, shift := false, ctrl := false) -> InputEventKey:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.pressed = true
	event.shift_pressed = shift
	event.ctrl_pressed = ctrl
	return event

func expect(actual: String, expected: String, label: String) -> void:
	checks += 1
	if actual != expected:
		failures += 1
		push_error(label + ": " + actual)

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var settings: Control = (load("res://src/ui/settings_window.gd") as Script).new()
	root.add_child(settings)
	expect(str(settings.call("restore_bindings", {"recenter_viewport": "Space"})), "0", "legacy camera binding ignored")
	var actions: Array = settings.call("bindable_actions")
	expect(str("toggle_mount" in actions and "toggle_gallop" in actions), "true", "mount shortcuts can be rebound in settings")
	expect(str("recenter_viewport" in actions), "false", "retired camera binding not offered")
	var mounted := {"mode": "mounted"}
	var on_foot := {"mode": "on_foot"}
	expect(str(InputMap.action_get_events("recenter_viewport").size()), "0", "retired camera binding is unbound")
	expect(Controls.request_for_event(key(KEY_R), on_foot), "#mount", "mount")
	expect(Controls.request_for_event(key(KEY_R), mounted), "#mount", "dismount")
	expect(Controls.request_for_event(key(KEY_R, true), mounted), "#mount", "dismount with run held")
	expect(Controls.request_for_event(key(KEY_R), {"mode": "summoning"}), "#mount", "cancel summon")
	expect(Controls.request_for_event(key(KEY_SPACE), mounted), "#gallop", "gallop")
	expect(Controls.request_for_event(key(KEY_SPACE, true), mounted), "#gallop", "gallop with run held")
	expect(Controls.request_for_event(key(KEY_SPACE), on_foot), "", "space does nothing on foot")
	expect(Controls.request_for_event(key(KEY_R, false, true), mounted), "", "guild shortcut preserved")
	expect(Controls.request_for_event(key(KEY_SPACE, false, true), mounted), "", "modified space not claimed")
	expect(Controls.request_for_event(key(KEY_R), {}), "", "servers without mounts unaffected")
	var repeat := key(KEY_SPACE)
	repeat.echo = true
	expect(Controls.request_for_event(repeat, mounted), "", "repeat ignored")
	var release := key(KEY_SPACE)
	release.pressed = false
	expect(Controls.request_for_event(release, mounted), "", "release ignored")
	InputMap.action_erase_events("toggle_mount")
	InputMap.action_add_event("toggle_mount", key(KEY_Y))
	expect(Controls.request_for_event(key(KEY_R), mounted), "", "old binding no longer claimed")
	expect(Controls.request_for_event(key(KEY_Y), mounted), "#mount", "rebound key works")
	settings.free()
	print("MOUNT_HOTKEY_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
