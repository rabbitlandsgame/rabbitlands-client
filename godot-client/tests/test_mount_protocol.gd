extends SceneTree
const Codec := preload("res://src/mounts/mount_protocol.gd")
var checks := 0
var failures := 0

func check(ok: bool) -> void:
	checks += 1
	if not ok:
		failures += 1

func decode(value: Dictionary) -> Dictionary:
	return Codec.decode(JSON.stringify(value).to_utf8_buffer())

func _init() -> void:
	var row := {"schema_version": 1, "actor_id": 42, "mode": "mounted", "gait": "burst",
		"mount_id": "moor_pony", "selected_mount_id": "moor_pony", "step_us": 133333,
		"endurance_ms": 7000, "summon_remaining_ms": 0, "combat_remaining_ms": 0,
		"can_summon": false, "blocked_reason": "", "map": "four_gates", "owner": "Rider"}
	var message := {"schema_version": 1, "map": "four_gates", "states": [row]}
	check(decode(message).type == "mount_states")
	var horse: Dictionary = message.duplicate(true)
	horse.states[0].mount_id = "golden_plains_horse"
	horse.states[0].selected_mount_id = "golden_plains_horse"
	horse.states[0].owned_mount_ids = ["moor_pony", "golden_plains_horse"]
	check(decode(horse).type == "mount_states")
	var tortoise: Dictionary = horse.duplicate(true)
	tortoise.states[0].mount_id = "crystalback_tortoise"
	tortoise.states[0].selected_mount_id = "crystalback_tortoise"
	tortoise.states[0].owned_mount_ids.append("crystalback_tortoise")
	check(decode(tortoise).type == "mount_states")
	for step: int in [2000000,666667,444444]:
		tortoise.states[0].step_us = step
		check(decode(tortoise).type == "mount_states")
	for bad: Variant in [["moor_pony"], ["golden_plains_horse", "golden_plains_horse"], ["unicorn"], "all", [null]]:
		var copy: Dictionary = horse.duplicate(true)
		copy.states[0].owned_mount_ids = bad
		check(decode(copy).type == "invalid")
	check(decode({"schema_version": 1, "map": "four_gates", "states": []}).states.is_empty())
	check(Codec.decode("{".to_utf8_buffer()).type == "invalid")
	for bad: Variant in [false, -1, 65536, 1.5, "42"]:
		var copy: Dictionary = message.duplicate(true)
		copy.states[0].actor_id = bad
		check(decode(copy).type == "invalid")
	var duplicate: Dictionary = message.duplicate(true)
	duplicate.states.append(row)
	check(decode(duplicate).type == "invalid")
	for bad: Variant in ["unicorn", null, 7]:
		var copy: Dictionary = message.duplicate(true)
		copy.states[0].mount_id = bad
		check(decode(copy).type == "invalid")
	var invalid: Dictionary = message.duplicate(true)
	invalid.states[0].endurance_ms = 9000
	check(decode(invalid).type == "invalid")
	print("MOUNT_PROTOCOL_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
