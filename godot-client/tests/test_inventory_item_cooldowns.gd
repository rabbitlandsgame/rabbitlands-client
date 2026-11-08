extends SceneTree
## Exercise actual inventory/cooldown packets, including server consumption order.
var state: Node
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _item(slot: int, image: int, quantity: int = 3) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(8)
	bytes.encode_u16(0, image)
	bytes.encode_u32(2, quantity)
	bytes[6] = slot
	bytes[7] = 12
	return bytes

func _snapshot(items: Array) -> void:
	var bytes := PackedByteArray([items.size()])
	for item: PackedByteArray in items:
		bytes.append_array(item)
	state.call("_on_packet", 19, bytes)

func _cooldown(slot: int, seconds: int) -> void:
	state.call("_on_packet", 77, PackedByteArray([slot, seconds, 0, seconds, 0]))

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	state = root.get_node("AppState")
	_snapshot([_item(0, 10), _item(1, 20)])
	_cooldown(0, 30)
	_cooldown(1, 10)
	var timers: Dictionary = state.get("inventory_cooldowns")
	_expect(timers.has(0) and timers.has(1), "independent announcements merge")
	var deadline: int = timers[0].end_msec
	_snapshot([_item(1, 10), _item(0, 20)])
	_expect(timers[1].end_msec == deadline and timers[0].maximum_msec == 10000,
		"swapping items swaps their timers without restarting them")
	_snapshot([_item(10, 10), _item(0, 20)])
	_expect(not timers.has(1) and timers[10].end_msec == deadline,
		"moving out of the quick bar leaves no cooldown on the old slot")
	state.call("_on_packet", 22, PackedByteArray([10]))
	_expect(not timers.has(10), "removing the stack immediately clears its counter")
	state.call("_on_packet", 21, _item(4, 10))
	_expect(timers.has(4) and timers[4].end_msec == deadline,
		"separate remove and add packets also move the original deadline")
	_snapshot([_item(10, 20), _item(0, 10)])
	_expect(timers[0].end_msec == deadline and timers[10].maximum_msec == 10000,
		"reacquiring an item retains its unexpired cooldown")
	state.call("_on_packet", 21, _item(0, 10, 1))
	_expect(timers[0].end_msec == deadline, "quantity updates retain the deadline")
	state.call("_on_packet", 21, _item(0, 10, 0))
	_expect(not timers.has(0), "a zero quantity has no counter")
	state.call("_on_packet", 22, PackedByteArray([0]))
	_cooldown(0, 30)
	_expect(not timers.has(0), "a cooldown after the last item was consumed stays hidden")
	_snapshot([_item(0, 10)])
	_expect(timers.has(0), "the last consumed item's timer survives reacquisition")
	_snapshot([_item(0, 40, 1)])
	state.call("_on_packet", 22, PackedByteArray([0]))
	_cooldown(0, 20)
	_expect(not timers.has(0), "a fresh last-item timer never draws on an empty slot")
	_snapshot([_item(3, 40)])
	_expect(timers.has(3) and timers[3].maximum_msec == 20000,
		"remove-before-cooldown ordering retains the correct item identity")
	_snapshot([_item(0, 30), _item(10, 20)])
	_expect(not timers.has(0), "an unrelated replacement never inherits the counter")
	for timer: Dictionary in (state.get("_item_cooldowns") as Dictionary).values():
		timer.end_msec = Time.get_ticks_msec() - 1
	_snapshot([_item(0, 10)])
	_expect(timers.is_empty(), "expired timers do not return when an item moves")
	_cooldown(0, 30)
	state.call("_on_connection_state_changed", "disconnected")
	_expect(timers.is_empty() and (state.get("_item_cooldowns") as Dictionary).is_empty(),
		"disconnect clears item deadlines")
	print("inventory item cooldowns: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
