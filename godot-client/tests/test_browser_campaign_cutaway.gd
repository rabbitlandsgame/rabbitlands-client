extends SceneTree
## Browser group admission must precede raw room/cast loading, independently
## of whether the archives were saved earlier or still need downloading.
const Cutaway := preload("res://src/world/campaign_cutaway.gd")
var failures := 0
var checks := 0

class PendingCutaway extends Cutaway:
	var admitted := false
	var requests := 0
	var starts := 0
	var progress := 0
	var failed: Array = []
	var pins: Dictionary = {}
	var released: Array = []
	var retries := 0
	func _uses_browser_assets() -> bool: return true
	func _request_browser_assets() -> bool:
		requests += 1
		pins[_asset_owner] = _asset_groups.duplicate()
		return admitted
	func _browser_asset_state() -> Dictionary:
		return {"completed_archives":progress,"failed_groups":failed,"error":"fixture download failure"}
	func _browser_asset_release() -> Callable:
		return func(owner: String) -> void: pins.erase(owner); released.append(owner)
	func _retry_browser_asset_groups() -> int:
		retries += 1
		failed.clear()
		return 1
	func _begin() -> void: starts += 1

func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func snapshot(run_id := "first") -> Dictionary:
	return {"active":true,"kind":"rescue","run_id":run_id,"map":"landfall",
		"scene":{"id":"measure.rescue.shadow","cutaway":{"map":"landfall_insides",
		"actors":{"goblin_boss":{"model":"model:boss"},"lich":{"model":"model:lich"}},"anchors":{}}}}

func run() -> void:
	root.get_node("Network").call("block_for_hud_preview")
	var previous := WebPrototype._configuration
	var previous_loaded := WebPrototype._loaded
	WebPrototype._configuration = {"maps":{"landfall_insides":["map:mine"]},"groups":{
		"map:mine":{"dependencies":["shared:mine"]},"shared:mine":{"dependencies":[]},
		"model:boss":{"dependencies":[]},"model:lich":{"dependencies":[]},
		"equipment:cape":{"dependencies":[]}}}
	WebPrototype._loaded = true
	var resolutions: Array = []
	var module := PendingCutaway.new()
	root.add_child(module)
	module.configure({}, Callable(), func(dto: Dictionary) -> Array:
		resolutions.append(dto.model)
		return [dto.model,"equipment:cape"])
	var state := snapshot()
	var warming := state.duplicate(true)
	warming.scene.id = "measure.rescue.resolved"
	warming.scene.preload_cutaway = warming.scene.cutaway
	warming.scene.erase("cutaway")
	module.prepare(warming,"landfall",100.0)
	var owner := str(module.status().asset_owner)
	expect(module.starts == 0 and module.status().asset_waiting and module._elapsed == 0.0,
		"cold outdoor preloading waits for raw files without spending the geometry timeout")
	expect(module.pins[owner] == ["map:mine","model:boss","equipment:cape","model:lich"],
		"remote map and exact factory-resolved cast/equipment share a deduplicated lease")
	module.prepare(state,"landfall",0.016)
	expect(module.requests == 1 and resolutions.size() == 2 and module.status().asset_owner == owner,
		"resolved-to-shadow reuse neither recomputes dependencies nor polls per frame")
	module.admitted = true
	module._asset_check_at = 0
	module.prepare(state,"landfall",0.016)
	expect(module.starts == 1 and module.status().asset_admitted and not module.status().asset_waiting,
		"raw room loading starts once only after map and every cast group are ready")
	module.prepare(state,"landfall",0.016)
	expect(module.starts == 1 and module.requests == 2,
		"an admitted room does not keep polling the download service")
	# A retiring native worker must retain old raw files, and its eventual
	# release must never erase the next preparation's different owner.
	var worker := Thread.new()
	var semaphore := Semaphore.new()
	worker.start(func() -> Variant: semaphore.wait(); return null)
	module._asset_worker = worker
	module.clear()
	module.admitted = false
	module.prepare(snapshot("second"),"landfall",0.016)
	var next_owner := str(module.status().asset_owner)
	expect(next_owner != owner and module.pins.has(owner) and module.pins.has(next_owner),
		"clear and immediate reuse preserve the retiring worker's separate lease")
	semaphore.post()
	while worker.is_alive(): await process_frame
	worker.wait_to_finish()
	await create_timer(0.3).timeout
	expect(not module.pins.has(owner) and module.pins.has(next_owner),
		"the old completed worker releases only its captured generation's pins")
	module.clear()
	expect(module.pins.is_empty() and module.status().asset_owner.is_empty(),
		"ordinary clear releases all current pins and admission state")
	module.prepare(snapshot("failure"),"landfall",0.016)
	module.failed = ["shared:mine"]
	module._asset_check_at = 0
	module.prepare(snapshot("failure"),"landfall",0.016)
	expect(str(module.status().error).begins_with("remote_browser_asset_download:"),
		"a failed dependency reports a download failure before any raw load")
	expect(module.pins.is_empty() and module.status().asset_owner.is_empty(),
		"failed preparation releases its raw file lease")
	module.prepare(snapshot("failure"),"landfall",0.016)
	expect(module.retries == 0, "failed download retries never run automatically")
	module.retry_browser_assets()
	expect(module.retries == 1 and module.failed.is_empty(),
		"explicit Retry resets the sticky download failure before a fresh preparation")
	module.clear()
	module.prepare(snapshot("failure"),"landfall",0.016)
	expect(str(module.status().error).is_empty() and module.status().asset_waiting,
		"the same scene can request its files again after explicit Retry")
	module.clear()
	module.failed = ["unrelated:world"]
	module.prepare(snapshot("timeout"),"landfall",0.016)
	expect(str(module.status().error).is_empty(), "unrelated download failures do not reject this cutaway")
	module._asset_progress_at = Time.get_ticks_msec() - Cutaway.ASSET_WAIT_MSEC - 1
	module._asset_check_at = 0
	module.prepare(snapshot("timeout"),"landfall",0.016)
	expect(module.status().error == "remote_browser_asset_timeout", "a stalled asset wait has a bounded timeout")
	module.clear()
	var native := Cutaway.new()
	root.add_child(native)
	native.configure({}, Callable())
	native.prepare(state,"landfall",0.016)
	expect(native.status().error == "remote_manifest_unavailable" and native.status().asset_owner.is_empty(),
		"desktop keeps its original direct loader and requires no browser resolver")
	native.queue_free()
	module.queue_free()
	await process_frame
	WebPrototype._configuration = previous
	WebPrototype._loaded = previous_loaded
	print("Browser campaign cutaway: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)
