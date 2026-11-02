extends SceneTree
const Admission := preload("res://src/platform/browser_actor_assets.gd")

class Assets extends RefCounted:
	var ready := {}
	var pins := {}
	var queries := 0
	func model_groups(model: String) -> Array: return ["model:" + model] if not model.is_empty() else []
	func mount_groups(model: String) -> Array: return model_groups(model)
	func equipment_groups(visuals: Dictionary) -> Array:
		var result := []
		for part: Variant in visuals: result.append("equipment:%s:%s" % [part, visuals[part]])
		return result
	func ensure_groups(groups: Array, owner: String, _priority := -1) -> bool:
		queries += 1
		pin_groups(owner, groups)
		for group: String in groups:
			if not ready.has(group): return false
		return true
	func pin_groups(owner: String, groups: Array) -> void: pins[owner] = groups.duplicate()
	func release_groups(owner: String) -> void: pins.erase(owner)

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	var files := Assets.new()
	var gate := Admission.new(files)
	assert(not gate.admit(1, "human", {2:184}, "pony"))
	assert(files.pins["actor_pending:1"].has("model:pony"))
	files.ready = {"model:human":true, "equipment:2:184":true, "model:pony":true}
	assert(gate.poll() == [1])
	assert(not files.pins.has("actor_pending:1"))
	var queries: int = files.queries
	assert(gate.admit(1, "human", {2:184}, "pony"))
	assert(files.queries == queries, "ready actors do not repeat resource requests")
	assert(not gate.admit(1, "human", {2:200}))
	assert(files.pins["actor_active:1"].has("equipment:2:184"), "displayed equipment stays pinned")
	files.ready["equipment:2:200"] = true
	gate._next_poll = 0
	assert(gate.poll() == [1])
	assert(files.pins["actor_active:1"] == ["model:human", "equipment:2:200"])
	gate.prune({}, [1])
	assert(files.pins.has("actor_active:1"), "parked actors retain source groups")
	gate.prune({})
	assert(files.pins.is_empty())
	assert(gate.admit(2, "", {}))
	gate.clear()
	assert(files.pins.is_empty())
	print("browser actor asset admission: PASS")
	quit()
