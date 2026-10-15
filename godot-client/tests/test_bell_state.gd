extends SceneTree
## A successful flee ends the combat overlay as well as the actor animation.
func _init() -> void:
	call_deferred("run")

func run() -> void:
	var state: Node=root.get_node("AppState")
	state.local_actor_id=1
	state.actors={1:{"actor_id":1,"x":1,"y":1,"in_combat":true},2:{"actor_id":2,"x":2,"y":1,"in_combat":true}}
	state.combat_state.active=true
	state._on_packet(2,PackedByteArray([2,0,19]))
	assert(state.combat_state.active,"Another actor leaving does not end our fight")
	state._on_packet(2,PackedByteArray([1,0,19]))
	assert(not state.combat_state.active,"Our flee must clear the combat overlay")
	assert(not state.actors[1].in_combat,"Actor and overlay agree")
	print("Bellwatch flee state: PASS")
	quit(0)
