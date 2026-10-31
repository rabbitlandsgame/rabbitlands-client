extends "res://tests/integration/crowd_presentation_benchmark.gd"
## Exercises real protocol reduction without Main, a map, models or rendering.
var _health_packets := {"damage": 0, "heal": 0}
var _checks := 0

func _run() -> void:
	_report = {"failures": []}
	_app_state = root.get_node("AppState")
	_app_state.set("local_actor_id", FIRST_ACTOR_ID)
	var gauntlet: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(GAUNTLET_FIXTURE))
	_check_main_dto_bridge(gauntlet)
	_exercise(production_undead_records(3, Vector2i(453, 168), "twinbrook"), false)
	_exercise(authored_gauntlet_records(gauntlet), true)
	for maximum: int in [1, 2, 3, 90, 1088]:
		for health: int in range(1, maximum + 1):
			var delta := bounded_combat_health_delta({"health": health, "max_health": maximum, "alive": true})
			_check(health + delta > 0 and health + delta <= maximum, "edge-state health remains live and bounded")
	_check(bounded_combat_health_delta({"health": 0, "max_health": 90, "alive": false}) == 0,
		"invalid corpses are not silently revived")
	_check(_health_packets.damage > 1000 and _health_packets.heal > 1000,
		"long driver actually reduced damage and heals")
	_print_result()

func _check_main_dto_bridge(gauntlet: Dictionary) -> void:
	# Construct Main without parenting it: execute its real DTO bridge without
	# _ready, a map, UI construction, actor imports or GPU work.
	var main := (load("res://src/app/main.gd") as Script).new() as Control
	var undead := production_undead_records(3, Vector2i(453, 168), "twinbrook")
	var lich: Dictionary = undead[FIRST_ACTOR_ID + 3]
	_send_packet(EloriaProtocol.ServerMessage.ELORIA_ACTOR_FOOTPRINTS, PackedByteArray([0, 0]))
	_check((main.call("_presentation_dto", lich) as Dictionary).footprint == Vector2i.ONE,
		"negative control reproduces missing-login footprint replacement")
	_creatures = UNDEAD_PROFILES.duplicate(true)
	_seed_cohort_footprints()
	for record: Dictionary in undead.values():
		var dto: Dictionary = main.call("_presentation_dto", record)
		_check(dto.footprint == record.get("footprint", Vector2i.ONE), "real Main DTO preserves seeded species footprint")
	_creatures = _authored_gauntlet_profiles()
	_check(_creatures.size() == 2, "actual JSON profile loader resolves both retained gauntlet species")
	_seed_cohort_footprints()
	_check(_report.creatureFootprints == {"624": [1, 1], "583": [1, 1]}, "JSON numeric actor keys normalize to integer strings")
	for record: Dictionary in authored_gauntlet_records(gauntlet).values():
		var dto: Dictionary = main.call("_presentation_dto", record)
		_check(dto.footprint == record.get("footprint", Vector2i.ONE), "real Main DTO preserves authored gauntlet footprint")
	# Exercise the actual snapshot against Main and its real CanvasLayer type.
	var curtain := (load("res://src/ui/arrival_curtain.gd") as Script).new() as CanvasLayer
	curtain.visible = false
	main.set("arrival_curtain", curtain)
	_main = main
	_headless = true
	var state := _steady_pacing_snapshot()
	_check(not bool(state.arrivalVisible) and not bool(state.cameraWarmup.active), "actual Main steady snapshot handles CanvasLayer curtain")
	_check(_warming_complete(state), "headless steady state requires no in-flight arrival")
	var rendered := state.duplicate(true)
	rendered.warmingRequired = true
	rendered.cameraWarmup = {"active": false, "view": 240, "views": 240, "frames_per_view": 2, "timed_out": false}
	_check(_warming_complete(rendered), "complete two-draw 240-view warming qualifies")
	for field: String in ["view", "frames_per_view"]:
		var incomplete := rendered.duplicate(true)
		incomplete.cameraWarmup[field] = 1
		_check(not _warming_complete(incomplete), "partial warming refused: " + field)
	curtain.free()
	_main = null
	main.free()

func _exercise(records: Dictionary, gauntlet: bool) -> void:
	_production_undead = not gauntlet
	_authored_gauntlet = gauntlet
	_app_state.set("actors", records)
	var fighting: Array[int] = []
	var due: Array[int] = []
	for id: int in records:
		if id != FIRST_ACTOR_ID:
			fighting.append(id)
			# Begin one hit from death so the first real packet tests the bound.
			(records[id] as Dictionary)["health"] = 1
	for index: int in fighting.size():
		due.append(index)
	# 1,024 attacks per actor at adversarial live phases that never heal under
	# the historical tick rule. This exceeds the old goblin death threshold
	# many times without waiting for wall-clock combat or loading any models.
	for round_index: int in 1024:
		_drive_combat(fighting, due, round_index * 40)
		for id: int in fighting:
			var record: Dictionary = (_app_state.get("actors") as Dictionary)[id]
			_check(bool(record.alive) and int(record.health) > 0 and int(record.health) <= int(record.max_health),
				"actual reduced creature health stays live throughout the driver")

func _send_packet(command: int, payload: PackedByteArray) -> void:
	if command == EloriaProtocol.ServerMessage.GET_ACTOR_DAMAGE:
		_health_packets.damage += 1
	elif command == EloriaProtocol.ServerMessage.GET_ACTOR_HEAL:
		_health_packets.heal += 1
	super._send_packet(command, payload)

func _check(value: bool, label: String) -> void:
	_checks += 1
	_expect(value, label)

func _print_result() -> void:
	print("production creature long health driver: %d checks, %d failures, %s" % [_checks, _failures, _health_packets])
	quit(1 if _failures else 0)
