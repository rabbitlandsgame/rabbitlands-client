extends SceneTree
## Cancelled deferred browser work must not consume a newer job for the same cell.
func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var stream := ContinentChunkStream.new()
	root.add_child(stream)
	stream._web_pending = true
	stream._web_generation = 3
	stream._pending = {"id": "same_cell", "bounds": {"min": [-1, 0, -1], "max": [1, 1, 1]},
		"estimatedResidentBytes": 100}
	stream._prepare_web_chunk({"id": "same_cell"}, 2)
	if not stream._web_pending or stream._pending.get("id") != "same_cell":
		push_error("Stale browser callback consumed the new chunk request")
		quit(1)
		return
	if stream.can_retire() or int(stream.resource_estimates({}).in_flight_cells) != 1:
		push_error("Queued browser chunks must retain ownership and memory accounting")
		quit(1)
		return
	stream.pause_streaming()
	if stream._web_pending or not stream._pending.is_empty() or not stream.can_retire():
		push_error("Paused browser work was not cancelled")
		quit(1)
		return
	stream._prepare_web_chunk({"id": "same_cell"}, 3)
	stream.free()
	print("PASS: deferred browser chunk cancellation and ownership")
	quit(0)
