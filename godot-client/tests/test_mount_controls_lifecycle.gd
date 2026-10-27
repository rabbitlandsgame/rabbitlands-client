extends SceneTree
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	var state := root.get_node("AppState")
	var controls_script: Script = load("res://src/mounts/mount_controls.gd")
	var before := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var unused: Variant = controls_script.new()
	var unused_label: WeakRef = weakref(unused.status)
	expect(not unused.is_inside_tree() and unused.status.get_parent()==unused,
		"constructed helper owns its label before entry")
	unused.set_options({"show_banner":false,"status":false})
	expect(not bool(unused.options.status) and not unused.wants_banner() and unused.status.text=="",
		"options remain usable before readiness")
	unused.free()
	expect(unused_label.get_ref()==null,"free-before-ready releases the label instead of orphaning it")
	expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))==before,
		"free-before-ready leaves no scene nodes")
	var old_authenticated: bool = state.authenticated
	var old_local_actor: int = state.local_actor_id
	var old_mounts: Dictionary = state.actor_mounts
	var old_connections := state.get_signal_connection_list("state_changed").size()
	state.authenticated = true
	state.local_actor_id = 19001
	state.actor_mounts = {19001:{"mode":"mounted","gait":"burst","endurance_ms":2500}}
	var active: Variant = controls_script.new()
	var active_label: WeakRef = weakref(active.status)
	root.add_child(active)
	expect(active.is_node_ready() and active.status.get_parent()==active and active.get_child_count()==1,
		"normal readiness retains one owned label")
	expect(active.status.text=="Gallop · 2.5s left" and active.wants_banner(),
		"normal mounted status still renders its existing text")
	active.set_options({"status":false})
	expect(active.status.text=="2.5s left","ready option changes still update the same label")
	state.actor_mounts = {}
	state.emit_signal("state_changed",&"mount_states")
	expect(not active.wants_banner(),"normal state-change connection still refreshes visibility")
	active.free()
	expect(active_label.get_ref()==null and state.get_signal_connection_list("state_changed").size()==old_connections,
		"normal destruction releases the label and its state connection")
	state.authenticated = old_authenticated
	state.local_actor_id = old_local_actor
	state.actor_mounts = old_mounts
	expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))==before,
		"normal destruction leaves no scene nodes")
	for frame: int in 4: await process_frame
	print("mount controls lifecycle: ","PASS" if failures==0 else "FAIL"," (",checks," checks, ",failures," failures)")
	quit(0 if failures==0 else 1)
