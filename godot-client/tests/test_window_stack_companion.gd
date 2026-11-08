extends SceneTree

const Stack = preload("res://src/ui/window_stack.gd")
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var surface := Control.new()
	root.add_child(surface)
	var stack := Stack.new()
	surface.add_child(stack)
	stack.configure(surface)
	var ledger := Panel.new()
	var card := Panel.new()
	var confirmation := Panel.new()
	for panel: Control in [ledger, card, confirmation]:
		surface.add_child(panel)
		panel.hide()
		stack.register(panel, panel == confirmation)
	stack.keep_above(card, ledger)
	ledger.show()
	card.show()
	await process_frame
	for iteration: int in 3:
		Stack.activate(ledger)
		await process_frame
		expect(card.get_index() > ledger.get_index(), "item card retains pointer priority after ledger activation")
		expect(card.z_index > ledger.z_index, "item card draws above the ledger")
	confirmation.show()
	Stack.activate(ledger)
	await process_frame
	expect(confirmation.get_index() > card.get_index() and confirmation.z_index > card.z_index,
		"confirmation stays above both non-blocking windows")
	confirmation.hide()
	card.hide()
	Stack.activate(ledger)
	await process_frame
	expect(not card.visible, "ledger activation does not reopen a dismissed card")
	card.show()
	await process_frame
	expect(card.get_index() > ledger.get_index(), "reopened card returns to the front")
	ledger.hide()
	var unrelated := Panel.new()
	surface.add_child(unrelated)
	stack.register(unrelated)
	Stack.activate(unrelated)
	await process_frame
	expect(unrelated.get_index() > card.get_index(), "normal window order resumes when the ledger closes")
	surface.queue_free()
	await process_frame
	print("Window stack companion: %s" % ("PASS" if failures == 0 else "FAIL"))
	quit(failures)
