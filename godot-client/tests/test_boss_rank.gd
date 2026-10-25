extends SceneTree
var failures := 0

class NativeRouteActor extends ReplicatedActor3D:
	var native_updates := 0
	func _apply_server_state_native(_dto: Dictionary, _adapter: CoordinateAdapter, _teleport := false) -> void:
		native_updates += 1

func _init() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
func packet(rank: int) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(17)
	bytes.encode_u16(0, 7)
	bytes[10] = 18
	bytes.encode_u16(12, 50)
	bytes.encode_u16(14, 50)
	bytes[16] = 5
	bytes.append_array("Rabbit".to_ascii_buffer())
	bytes.append(0)
	if rank >= 0:
		bytes.append_array(PackedByteArray([0, 128, 82, 75, 1, rank]))
	return bytes
func run() -> void:
	for rank: int in [0, 1, 2, 3]:
		var dto := EloriaProtocol.decode_actor(packet(rank), false)
		check(dto.boss_rank == (rank if rank in [1, 2] else 0), "only supported explicit ranks are recognized")
		check(dto.scale == 1.0 and dto.name == "Rabbit", "rank preserves legacy actor fields")
	check(EloriaProtocol.decode_actor(packet(-1), false).boss_rank == 0, "legacy packet is ordinary")
	var truncated := packet(2)
	truncated.resize(truncated.size() - 1)
	check(EloriaProtocol.decode_actor(truncated, false).boss_rank == 0, "partial trailer is ignored")
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.configure(EloriaProtocol.decode_actor(packet(2), false), CoordinateAdapter.new({}), {}, {})
	check(actor._boss_rank_label != null and actor._boss_rank_label.text == "BOSS", "boss label is distinct")
	actor.set_overhead_crowded(true)
	check(actor._boss_rank_label.visible, "rank survives ordinary crowd decluttering")
	actor.set_boss_rank(1)
	check(actor._boss_rank_label.text == "MINIBOSS", "promotion/demotion updates rank")
	actor.set_boss_rank(0)
	check(not actor._boss_rank_label.visible, "rank removal clears marker")
	actor.free()
	# A native presentation owner returns before the ordinary DTO sink. Rank
	# must update at the shared boundary, without requiring a native DLL.
	var previous_remote := RemotePresentation._current
	var remote := RemotePresentation.new()
	remote._ready_native = true
	RemotePresentation._current = weakref(remote)
	var native_actor := NativeRouteActor.new()
	root.add_child(native_actor)
	native_actor.actor_id = 7
	native_actor._remote_enrollment_ready = true
	for rank: int in [2, 1, 0]:
		native_actor.apply_server_state(EloriaProtocol.decode_actor(packet(rank), false), CoordinateAdapter.new({}))
		check(native_actor._boss_rank == rank, "native DTO early-return preserves rank update")
	check(native_actor.native_updates == 3, "rank bridge retains native-owned DTO routing")
	RemotePresentation._current = previous_remote
	native_actor.free()
	remote.free()
	await process_frame
	print("boss rank failures=", failures)
	quit(failures)
