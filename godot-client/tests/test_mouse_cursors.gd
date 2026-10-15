extends SceneTree
## The action pointer: the glyph set loads whole, and the decision table
## answers the way the legacy client's check_cursor_change does for every
## interaction this client carries.

var failures: int = 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_library()
	_check_decision_table()
	await _check_wiring()
	if failures == 0:
		print("test_mouse_cursors: all checks passed")
	quit(failures)

func _check_library() -> void:
	var cursors := MouseCursors.new()
	_expect(cursors.configure("res://assets/ui/cursors/cursors.json"),
		"cursor manifest and its glyphs load")
	_expect(cursors.loaded(), "all thirteen cursors are present")
	# The manifest order is the legacy cursors.h order for the first thirteen;
	# the ids only mean something while that holds. Past them sit Eloria's own,
	# today the grasping hand.
	var manifest_order: Array[String] = ["eye", "talk", "attack", "enter", "pick",
		"harvest", "walk", "arrow", "trade", "use_witem", "use", "wand", "text",
		"grab"]
	for cursor_id in range(manifest_order.size()):
		_expect(cursors.name_of(cursor_id) == manifest_order[cursor_id],
			"cursor %d is %s" % [cursor_id, manifest_order[cursor_id]])
	for cursor_id in range(MouseCursors.CURSOR_COUNT):
		var hotspot: Vector2 = cursors.hotspot_of(cursor_id)
		_expect(hotspot.x >= 0.0 and hotspot.y >= 0.0
			and hotspot.x < 32.0 and hotspot.y < 32.0,
			"cursor %d hotspot sits inside its 32x32 glyph" % cursor_id)
	_expect(cursors.current() == -1, "no cursor is applied before apply()")

func _check_decision_table() -> void:
	# Away from the world - a window, the HUD, the login screen - the pointer
	# is the plain arrow.
	_choice({}, MouseCursors.ARROW, "off the world the pointer is the arrow")
	_choice({"over_world": false, "target": "npc"}, MouseCursors.ARROW,
		"a hover that is not over the world never picks an action cursor")
	# Bare ground.
	_choice({"over_world": true}, MouseCursors.WALK, "bare ground walks")
	_choice({"over_world": true, "mode": "attack"}, MouseCursors.WALK,
		"attack mode still walks on bare ground, as the reference does")
	_choice({"over_world": true, "mode": "trade"}, MouseCursors.WALK,
		"trade mode still walks on bare ground")
	_choice({"over_world": true, "spell_target": "location"}, MouseCursors.WAND,
		"a spell waiting for ground shows the wand over ground")
	# NPCs.
	_choice({"over_world": true, "target": "npc"}, MouseCursors.TALK,
		"an NPC talks")
	_choice({"over_world": true, "target": "npc", "mode": "attack"},
		MouseCursors.TALK, "an NPC talks even in attack mode")
	_choice({"over_world": true, "target": "npc", "spell_target": "actor"},
		MouseCursors.WAND, "a spell waiting for an actor claims the NPC")
	# Creatures: alive defaults to attack in every mode, dead is scenery.
	_choice({"over_world": true, "target": "creature", "alive": true},
		MouseCursors.ATTACK, "an alive creature reads attack in walk mode")
	_choice({"over_world": true, "target": "creature", "alive": false},
		MouseCursors.WALK, "a dead creature walks")
	_choice({"over_world": true, "target": "creature", "spell_target": "actor"},
		MouseCursors.WAND, "a spell waiting for an actor claims the creature")
	# A summon of your own is a creature kind whose click is an order, so the
	# pointer offers to talk to it until a mode or Alt asks for the blow.
	_choice({"over_world": true, "target": "summon"},
		MouseCursors.TALK, "a summon is commanded, not attacked, by a plain click")
	_choice({"over_world": true, "target": "summon", "mode": "attack"},
		MouseCursors.ATTACK, "attack mode turns the pointer on your own summon")
	_choice({"over_world": true, "target": "summon", "alt": true},
		MouseCursors.ATTACK, "held Alt does the same")
	# Players: the mode decides, Alt previews attack, default is a look.
	_choice({"over_world": true, "target": "player"}, MouseCursors.EYE,
		"a player reads as a look in walk mode")
	_choice({"over_world": true, "target": "player", "mode": "trade"},
		MouseCursors.TRADE, "trade mode offers trade over a player")
	_choice({"over_world": true, "target": "player", "mode": "attack"},
		MouseCursors.ATTACK, "attack mode threatens a player")
	_choice({"over_world": true, "target": "player", "alt": true},
		MouseCursors.ATTACK, "held Alt previews the attack over a player")
	_choice({"over_world": true, "target": "player", "mode": "attack",
		"alive": false}, MouseCursors.EYE,
		"a dead player cannot be attacked, so the pointer does not offer it")
	_choice({"over_world": true, "target": "player", "mode": "trade",
		"alive": false}, MouseCursors.EYE,
		"a dead player cannot be traded with either")
	_choice({"over_world": true, "target": "self"}, MouseCursors.EYE,
		"your own actor reads as a look")
	_choice({"over_world": true, "target": "self", "spell_target": "actor"},
		MouseCursors.WAND, "a touch spell can target yourself")
	# The ground layer: bags, harvest nodes, portals, service points.
	_choice({"over_world": true, "target": "bag"}, MouseCursors.PICK,
		"a dropped bag offers a pick-up")
	_choice({"over_world": true, "target": "harvest"}, MouseCursors.HARVEST,
		"a harvest node offers the harvest")
	_choice({"over_world": true, "target": "harvest", "mode": "attack"},
		MouseCursors.HARVEST, "attack mode does not hide a harvest node")
	_choice({"over_world": true, "target": "portal"}, MouseCursors.ENTER,
		"a portal offers an entrance")
	_choice({"over_world": true, "target": "portal", "alt": true}, MouseCursors.EYE,
		"Alt inspects a portal instead of entering it")
	_choice({"over_world": true, "target": "interactive"}, MouseCursors.USE,
		"a service point offers a use")
	# The one interface target: an item slot whose click will move the item.
	_choice({"target": "item_grab"}, MouseCursors.GRAB,
		"an item the click will move shows the grasping hand")
	_choice({"over_world": false, "target": "item_grab"}, MouseCursors.GRAB,
		"the hand does not need the world - it lives on the interface")
	_choice({"target": "item_use"}, MouseCursors.USE,
		"an item the use tool would spend shows the pressing finger")
	_choice({"target": "item_inspect"}, MouseCursors.EYE,
		"an item the click will only look at shows the eye")
	_choice({"over_world": true, "target": "item_inspect"}, MouseCursors.EYE,
		"the interface pointers outrank the world, since the window is on top")

## The seams main.gd relies on: the scene builds a loaded cursor set, and the
## hover question it asks the viewport exists on this engine.
func _check_wiring() -> void:
	_expect(ClassDB.class_has_method("Viewport", "gui_get_hovered_control"),
		"the engine can name the hovered control")
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var cursors: MouseCursors = main.get("mouse_cursors") as MouseCursors
	_expect(cursors != null and cursors.loaded(),
		"the client builds its cursor set on startup")
	_expect(main.call("_cursor_context") == {},
		"before login the pointer context is empty, which the table answers with the arrow")
	main.queue_free()
	await process_frame

func _choice(context: Dictionary, wanted: int, label: String) -> void:
	var got: int = MouseCursors.choose(context)
	_expect(got == wanted, "%s (wanted %d, got %d)" % [label, wanted, got])

func _expect(ok: bool, label: String) -> void:
	if ok:
		return
	failures += 1
	push_error("FAIL: " + label)
