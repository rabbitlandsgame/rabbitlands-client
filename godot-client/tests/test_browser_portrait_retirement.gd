extends SceneTree

class HeadReads extends RefCounted:
	var busy := true
	var pins := {"portrait:old":true, "portrait:waiting":true}
	var pending: Array[String] = []
	func retire(owner: String) -> void:
		if busy: pending.append(owner)
		else: pins.erase(owner)
	func finish() -> void:
		busy = false
		for owner: String in pending: pins.erase(owner)
		pending.clear()

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	var script := load("res://src/ui/leaderboard_portraits.gd") as GDScript
	assert(script != null and script.can_instantiate())
	var portraits: Variant = script.new()
	var reads := HeadReads.new()
	portraits._asset_owners = {"portrait:old":true, "portrait:waiting":true}
	portraits._retire_asset_owners(reads.retire)
	assert(portraits._asset_owners.is_empty(), "teardown transfers every live and waiting job")
	assert(reads.pins.size() == 2 and reads.pending.size() == 2, "pending head reads keep source pins")
	portraits._retire_asset_owners(reads.retire)
	assert(reads.pending.size() == 2, "reentrant or repeated teardown does not retire a job twice")
	portraits._asset_owners["portrait:new"] = true
	reads.pins["portrait:new"] = true
	reads.finish()
	assert(reads.pins == {"portrait:new":true}, "late old-job drain cannot drop the next portrait generation")
	portraits._retire_asset_owners(reads.retire)
	assert(reads.pins.is_empty())
	portraits.free()
	print("browser portrait teardown transfers all pending head leases once: PASS")
	quit()
