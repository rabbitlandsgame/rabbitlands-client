extends SceneTree

const MountState := preload("res://src/mounts/mount_preview_state.gd")
var failures := 0
var checks := 0

func _init() -> void:
	var model := MountState.new()
	model.reset(42, 3)
	var fixture := {
		"kind": "mount_preview", "schema_version": 1, "actor_id": 42,
		"epoch": 3, "revision": 1, "mode": "on_foot", "gait": "on_foot",
		"mount_id": "", "selected_mount_id": "moor_pony", "step_us": 200000,
		"endurance_ms": 8000, "summon_remaining_ms": 0,
		"combat_remaining_ms": 0, "can_summon": true, "blocked_reason": ""}
	_expect(model.apply_snapshot(fixture), "initial complete snapshot")
	_expect(not model.apply_snapshot(fixture), "duplicate snapshot is idempotent")
	fixture.revision = 2
	fixture.mode = "summoning"
	fixture.mount_id = "moor_pony"
	fixture.can_summon = false
	fixture.summon_remaining_ms = 1200
	_expect(model.apply_snapshot(fixture), "summon progress comes from server")
	fixture.revision = 3
	fixture.mode = "mounted"
	fixture.gait = "cruise"
	fixture.summon_remaining_ms = 0
	fixture.step_us = 133333
	_expect(model.apply_snapshot(fixture), "mounted pace")
	var inherited := model.state.duplicate(true)
	for pair: Array in [["epoch", 2], ["actor_id", 43], ["revision", 1],
		["endurance_ms", 8001], ["step_us", 0], ["mount_id", "dire_wolf"],
		["can_summon", true], ["gait", "flying"], ["schema_version", true],
		["endurance_ms", NAN], ["revision", 4.5], ["summon_remaining_ms", 1]]:
		var invalid: Dictionary = fixture.duplicate(true)
		invalid.revision = 4
		invalid[pair[0]] = pair[1]
		_expect(not model.apply_snapshot(invalid), "reject bad " + str(pair[0]))
		_expect(model.state == inherited, "bad snapshot preserves last valid state")
	fixture.revision = 5
	fixture.mode = "on_foot"
	fixture.gait = "on_foot"
	fixture.mount_id = ""
	fixture.blocked_reason = "combat"
	fixture.combat_remaining_ms = 10000
	_expect(model.apply_snapshot(fixture), "forced dismount clears active mount")
	_expect(model.state.mount_id == "", "no stale mount after forced dismount")
	model.reset()
	_expect(model.state.is_empty(), "actor removal clears mount")
	_expect(not model.apply_snapshot(fixture), "absent actor cannot acquire mount")
	model.reset(42, 4)
	_expect(not model.apply_snapshot(fixture), "reused actor rejects old epoch")
	fixture.epoch = 4
	fixture.revision = 1
	_expect(model.apply_snapshot(fixture), "new spawn may restart revisions")
	_expect(MountState.request("toggle").size() == 3, "toggle supplies no identity or speed")
	_expect(MountState.request("burst", true).enabled, "burst is a boolean intent")
	_expect(MountState.request("burst", 1).is_empty(), "integer is not a boolean intent")
	_expect(MountState.request("select", "dire_wolf").is_empty(), "only prototype pony is selectable")
	_expect(MountState.request("set_speed", 99).is_empty(), "no client speed request")
	print("MOUNT_PREVIEW_STATE_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)

func _expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
