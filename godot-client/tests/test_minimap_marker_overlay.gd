extends SceneTree
## The player's own mark is drawn over every other mark on the minimap and the
## full map, so an NPC or harvest node standing beside the player cannot hide it.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var overlay: Control = load("res://src/ui/minimap_marker_overlay.gd").new() as Control
	var own := {"type": &"self", "colour": Color.WHITE}
	var npc := {"type": &"npc", "colour": Color.YELLOW}
	var harvest := {"type": &"harvest", "colour": Color.GREEN}
	var creature := {"type": &"creature", "colour": Color.RED}
	# main.gd hands the player's mark over first, which drew it underneath.
	var marks: Array[Dictionary] = [own, npc, harvest, creature]
	var order: Array[Dictionary] = overlay.call("draw_order", marks)
	_expect(order.size() == marks.size(), "every mark is still drawn")
	_expect(order.back() == own, "the player's own mark is drawn last, on top")
	_expect(order.slice(0, 3) == [npc, harvest, creature],
		"the other marks keep the order they were handed over in")
	var without_self: Array[Dictionary] = [npc, harvest]
	_expect(overlay.call("draw_order", without_self) == without_self,
		"a map without the player's mark draws what it was given")
	overlay.free()
	print("Minimap marker overlay: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)

func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
