extends SceneTree
## Replay the server's level-up sequence through state and the right HUD rail.

const P := preload("res://src/network/protocol.gd")
const XPTable := preload("res://src/state/experience_curve.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var state := load("res://src/state/app_state.gd").new() as Node
	var hud := load("res://src/app/main.gd").new() as Control
	var rows := VBoxContainer.new()
	hud.add_child(rows)
	hud.set("skill_rows", rows)
	hud.call("_build_skill_rows")
	state.state_changed.connect(func(path: StringName) -> void:
		if path == &"stats":
			hud.call("_sync_skill_rows", state.get("stats")))
	var feedback: Array[Dictionary] = []
	state.floating_feedback_requested.connect(
		func(event: Dictionary) -> void: feedback.append(event))

	state.call("_on_packet", P.ServerMessage.HERE_YOUR_STATS, _snapshot(5, 9))
	_expect(_level(rows, "Attack") == "5" and _level(rows, "Defense") == "9",
		"login keeps unequal attack and defense levels separate")
	for example: Array in [["attack", 33, 6, "Attack"], ["defense", 35, 10, "Defense"]]:
		feedback.clear()
		state.call("_on_packet", P.ServerMessage.SEND_PARTIAL_STAT,
			PackedByteArray([int(example[1]), int(example[2]), 0, 0, 0]))
		var stats: Dictionary = state.get("stats")
		_expect(int(stats[str(example[0]) + "_base"]) == int(example[2]),
			"%s level-up updates its own base level" % example[0])
		_expect(feedback.size() == 1 and feedback[0].kind == "level"
			and feedback[0].skill == example[0] and feedback[0].level == example[2],
			"%s floating level-up names the skill that advanced" % example[0])
		# announce_levels follows the base notification with an authoritative
		# snapshot so current levels and next-level XP do not await another action.
		var feedback_count := feedback.size()
		state.call("_on_packet", P.ServerMessage.HERE_YOUR_STATS,
			_snapshot(6, 9 if example[0] == "attack" else 10))
		_expect(_level(rows, str(example[3])) == str(example[2]),
			"%s right HUD level refreshes synchronously with the level-up sequence" % example[0])
		_expect(feedback.size() == feedback_count,
			"the full refresh does not duplicate level-up feedback")
	_expect(_level(rows, "Attack") == "6" and _level(rows, "Defense") == "10",
		"defense advancing leaves the attack HUD level alone")
	var midpoint := _snapshot(40, 10)
	midpoint.encode_u32(130, 859115) # Halfway between new levels 40 and 41.
	midpoint.encode_u32(134, 900302)
	state.call("_on_packet", P.ServerMessage.HERE_YOUR_STATS, midpoint)
	_expect(is_equal_approx((rows.get_node("SkillRowAttack") as ProgressBar).value, 0.5),
		"HUD progress uses the new floor, not the old level-40 threshold")
	_cap_displays(hud, rows)
	state.free()
	hud.free()
	print("skill updates: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _cap_displays(hud: Control, rows: VBoxContainer) -> void:
	var bottom := ProgressBar.new()
	var remaining := Label.new()
	var selected := Label.new()
	hud.add_child(bottom)
	hud.add_child(remaining)
	hud.add_child(selected)
	hud.set("experience_bottom", bottom)
	hud.set("experience_bottom_text", remaining)
	hud.set("experience_skill_label", selected)
	var app_state := root.get_node("AppState")
	var saved_wide: Dictionary = app_state.get("experience64")
	app_state.set("experience64", {})
	for skill: String in hud.get("EXPERIENCE_SKILLS"):
		var cap: int = 500 if skill == "overall" else 200
		hud.set("_selected_experience_skill", skill)
		# A temporary boost to the cap must still show the last trainable level.
		var below := _skill_stats(skill, cap, cap - 1,
			XPTable.for_level(cap) - 5000000, XPTable.for_level(cap))
		_assert_progress(hud, rows, skill, below, 0.5, false)
		_expect(remaining.text == "5,000,000", "%s still has XP to earn below its cap" % skill)
		var capped := _skill_stats(skill, cap - 5, cap,
			XPTable.for_level(cap) + 40, XPTable.for_level(cap + 1))
		# A drained skill remains capped because its trained base level is capped.
		_assert_progress(hud, rows, skill, capped, 1.0, true)
		_expect(remaining.text == "Max level", "%s has no next-level requirement at its cap" % skill)
		var tooltip := bottom.tooltip_text
		_expect(not tooltip.contains(" / "), "%s bottom tooltip has no next-level target" % skill)
		# Starting Overall at 200 still leaves three hundred trainable levels.
		if skill == "overall":
			var overall := _skill_stats(skill, 0, 200, 890469480, 895469480)
			_assert_progress(hud, rows, skill, overall, 0.5, false)
	# The login-wide total can lag ordinary XP ticks below the 32-bit limit.
	app_state.set("experience64", {"attack":{"experience":885469480, "post_cap_points":0}})
	var screenshot := _skill_stats("attack", 200, 200, 885469520, 895469480)
	var row := hud.call("_stats_skill_row", "attack", screenshot) as Control
	_expect((row.get_node("Experience/Totals") as Label).text == "885,469,520 · Max level",
		"the reported Attack 200 example shows live earned XP and Max level")
	row.free()
	# Lifetime totals and the existing post-cap point count remain visible.
	app_state.set("experience64", {"attack":{"experience":10000000000, "post_cap_points":911}})
	var wide := _skill_stats("attack", 200, 200, 0xFFFFFFFF, 895469480)
	row = hud.call("_stats_skill_row", "attack", wide) as Control
	_expect((row.get_node("Experience/Totals") as Label).text == "10,000,000,000 (+911) · Max level",
		"capped totals keep 64-bit experience and earned post-cap points")
	row.free()
	app_state.set("experience64", saved_wide)

func _assert_progress(hud: Control, rows: VBoxContainer, skill: String,
		stats: Dictionary, fraction: float, capped: bool) -> void:
	hud.call("_sync_skill_rows", stats)
	hud.call("_sync_experience_meter", stats)
	var rail := rows.get_node("SkillRow" + skill.capitalize()) as ProgressBar
	var bottom := hud.get("experience_bottom") as ProgressBar
	var row := hud.call("_stats_skill_row", skill, stats) as Control
	var bar := row.get_node("Experience/Bar") as ProgressBar
	var totals := row.get_node("Experience/Totals") as Label
	_expect(is_equal_approx(rail.value, fraction) and is_equal_approx(bar.value, fraction)
		and is_equal_approx(bottom.value / bottom.max_value, fraction),
		"%s progress agrees in statistics, skill rail and bottom bar" % skill)
	_expect(totals.text.contains("Max level") == capped,
		"%s statistics only show Max level at its trained cap" % skill)
	_expect(rail.tooltip_text.contains("experience to go") != capped,
		"%s rail only promises XP to go while it can level" % skill)
	row.free()

func _skill_stats(skill: String, level: int, base: int, xp: int, next_xp: int) -> Dictionary:
	var stats := {skill:level, skill + "_base":base,
		skill + "_exp":xp, skill + "_exp_next":next_xp}
	if skill == "overall":
		stats["overall_level"] = base
	return stats

func _snapshot(attack: int, defense: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(230)
	# Fixed wire offsets from eloria.stats.stats_packet, independent of the
	# client's lookup tables. Full and partial XP offsets intentionally differ.
	payload.encode_s16(64, attack)
	payload.encode_s16(66, attack)
	payload.encode_s16(68, defense)
	payload.encode_s16(70, defense)
	return payload

func _level(rows: VBoxContainer, skill: String) -> String:
	return (rows.get_node("SkillRow%s/Value" % skill) as Label).text

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)
