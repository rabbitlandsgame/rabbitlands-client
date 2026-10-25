extends SceneTree
const Codec := preload("res://src/mounts/mount_protocol.gd")
var failures := 0
func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
func decode(row: Dictionary) -> Dictionary:
	return Codec.decode(JSON.stringify({"schema_version": 1, "map": "four_gates", "states": [row]}).to_utf8_buffer())
func run() -> void:
	root.size = Vector2i(1280, 720)
	var row := {"schema_version": 1, "actor_id": 42, "map": "four_gates", "owner": "Rider", "mode": "on_foot", "gait": "on_foot",
		"mount_id": "", "selected_mount_id": "moor_pony", "step_us": 200000, "endurance_ms": 8000,
		"summon_remaining_ms": 0, "combat_remaining_ms": 0, "can_summon": true, "blocked_reason": "",
		"owned_mount_ids": ["moor_pony"], "mount_progression": {"moor_pony": {"xp": 250, "stage": 0, "next_xp": 250, "can_evolve": true}}}
	expect(decode(row).type == "mount_states", "server progression snapshot is accepted")
	for invalid: Variant in [{"xp": -1, "stage": 0, "next_xp": 250, "can_evolve": false},
		{"xp": 250, "stage": 2, "next_xp": 0, "can_evolve": false},
		{"xp": 100, "stage": 0, "next_xp": 250, "can_evolve": true},
		{"xp": 1001, "stage": 2, "next_xp": 0, "can_evolve": false},
		{"xp": true, "stage": 0, "next_xp": 250, "can_evolve": false}]:
		var bad: Dictionary = row.duplicate(true)
		bad.mount_progression.moor_pony = invalid
		expect(decode(bad).type == "invalid", "malformed progression fails closed")
	var unowned: Dictionary = row.duplicate(true)
	unowned.mount_progression.golden_plains_horse = unowned.mount_progression.moor_pony
	expect(decode(unowned).type == "invalid", "progression cannot claim unowned mounts")
	var app := root.get_node("AppState")
	app.authenticated = true
	app.local_actor_id = 42
	app.actor_mounts[42] = row
	var window: Variant = (load("res://src/ui/mounts_window.gd") as Script).new()
	root.add_child(window)
	var sent: Array[String] = []
	window.send_command = func(text: String) -> void: sent.append(text)
	window.sync()
	expect(window.progression.visible and window.progression.text.contains("Familiar") and not window.evolve.disabled,
		"eligible owned mount shows its server-confirmed cosmetic stage")
	window._evolve()
	expect(sent == ["#mount evolve moor_pony 0"], "evolution sends expected current stage")
	expect(row.mount_progression.moor_pony.stage == 0, "sending never predicts successful evolution")
	row.mount_progression.moor_pony = {"xp": 250, "stage": 1, "next_xp": 1000, "can_evolve": false}
	window.sync()
	expect(window.evolve.disabled and window.progression.text.contains("Bonded"), "confirmed milestone waits for next travel requirement")
	window._evolve()
	expect(sent.size() == 1, "unmet requirement cannot send another evolution")
	row.erase("mount_progression")
	window.sync()
	expect(not window.progression.visible and not window.evolve.visible and decode(row).type == "mount_states",
		"older servers retain the existing mount controls")
	window.queue_free()
	await process_frame
	print("mount progression failures=", failures)
	quit(failures)
