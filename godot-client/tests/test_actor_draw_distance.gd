extends SceneTree
## An actor too far away to read is not drawn, but its map dot is.
##
## Crownwater's lagoon is open enough to read the names of everyone standing on
## a pavilion a hundred and sixty metres off, stacked over the water in front of
## the player. Past the draw distance the body and the name come off the
## viewport; the dot stays, because a mark on a map is how a player finds
## someone across the water.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var body := _child(actor, MeshInstance3D.new(), "NativeModel")
	var nameplate := _child(actor, Label3D.new(), "Nameplate")
	var ring := _child(actor, MeshInstance3D.new(), "SelectionRing")
	ring.visible = false
	var dot := MapMarkerDisc.build(String(ReplicatedActor3D.MAP_DOT_NODE), 6.0, Color.WHITE)
	actor.add_child(dot)
	await process_frame

	_expect(actor.is_drawn(), "an actor is drawn until it is told otherwise")

	actor.set_drawn(false)
	_expect(not actor.is_drawn(), "and knows when it is not")
	_expect(not body.visible, "out of range the body is hidden")
	_expect(not nameplate.visible, "and so is the name over it")
	_expect(dot.visible, "the map dot stays, so the actor still marks the maps")
	_expect(actor.visible, "the actor itself is left alone; the section cull owns that")

	# An actor out of range still takes packets, and a child that arrives to say
	# what it is now wearing arrives visible.
	var worn := _child(actor, MeshInstance3D.new(), "WornSword")
	actor.set_drawn(false)
	_expect(not worn.visible, "a child that arrives while it is out of range is hidden too")

	actor.set_drawn(true)
	_expect(body.visible and nameplate.visible and worn.visible,
		"back in range the body, the name and what it wears are drawn again")
	_expect(not ring.visible,
		"and a selection ring nobody switched on is still off")

	actor.set_drawn(true)
	_expect(body.visible, "asking twice for what it already is changes nothing")

	print("actor draw distance tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _child(parent: Node, node: Node3D, node_name: String) -> Node3D:
	node.name = node_name
	parent.add_child(node)
	return node

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
