extends SceneTree
const Admission := preload("res://src/platform/browser_actor_assets.gd")

class Assets extends RefCounted:
	var ready := {}
	var pins := {}
	func model_groups(model: String) -> Array: return ["model:" + model]
	func equipment_groups(_equipment: Dictionary) -> Array: return []
	func mount_groups(_mount: String) -> Array: return []
	func pin_groups(owner: String, groups: Array) -> void: pins[owner] = groups.duplicate()
	func release_groups(owner: String) -> void: pins.erase(owner)
	func ensure_groups(groups: Array, owner: String, _priority := -1) -> bool:
		pin_groups(owner, groups)
		for group: String in groups:
			if not ready.has(group): return false
		return true

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	# Load after autoload registration, as Main's normal scene path does.
	var script := load("res://tests/fixtures/browser_preview_main.gd") as GDScript
	assert(script != null and script.can_instantiate())
	var main: Variant = script.new()
	var files := Assets.new()
	var gate := Admission.new(files, "creation_preview")
	main._browser_creation_assets = gate
	assert(not main._browser_creation_assets_ready("human", {}, {"hair":1}, ["head:a"], 2))
	files.ready = {"model:human":true, "head:a":true}
	gate._next_poll = 0
	assert(main._browser_creation_assets_ready("human", {}, {"hair":1}, ["head:a"], 2),
		"unchanged selected preview polls its pending admission and becomes ready")
	assert(not main._browser_creation_assets_ready("human", {}, {"hair":2}, ["head:b"], 2))
	assert(files.pins["creation_preview_active:0"].has("head:a"))
	assert(not main._browser_creation_assets_ready("human", {}, {"hair":3}, ["head:c"], 2))
	files.ready["head:c"] = true
	gate._next_poll = 0
	assert(main._browser_creation_assets_ready("human", {}, {"hair":3}, ["head:c"], 2))
	assert(not files.pins["creation_preview_active:0"].has("head:b"), "abandoned choice never replaces displayed look")
	var parked := Node3D.new()
	assert(main.crowd.park_node(9, parked, "same-player", 0))
	var changed := {"appearance":{"hair_module":22}}
	assert(not main._browser_parked_actor_ready(9, changed))
	assert(main.crowd.parked_count() == 1 and not parked.visible, "pending changed hair preserves parked body")
	assert(main.admitted_dto == changed)
	main.selected_ready = true
	assert(main._browser_parked_actor_ready(9, changed))
	assert(main.crowd.take_parked(9, "same-player") == parked)
	parked.free()
	gate.clear()
	gate.release_retired()
	main.free()
	print("browser selected-preview completion, rapid replacement and parked appearance admission: PASS")
	quit()
