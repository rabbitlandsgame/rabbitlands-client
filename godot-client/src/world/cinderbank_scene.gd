extends Node3D
## Cinderbank art responds only to server-confirmed, persisted workshop outcomes.

const FLAGS := ["forge_lit", "sword_ready", "pump_repaired", "order_ready"]
var reveals: Dictionary = {}
var broken: Dictionary = {}
var lamps: Array[Dictionary] = []
var machinery: Array[Dictionary] = []
var current_flags: Dictionary = {}
var elapsed := 0.0
var outcome_flags: Array = FLAGS

func configure(imported: Node3D, presentation: Dictionary) -> void:
	outcome_flags = presentation.get("flags", FLAGS)
	for flag: String in outcome_flags:
		reveals[flag] = []
		broken[flag] = []
	for node: Node in imported.find_children("*", "MeshInstance3D", true, false):
		for flag: String in outcome_flags:
			if str(node.name).begins_with("Restore_" + flag):
				reveals[flag].append(node)
				node.hide()
			elif str(node.name).begins_with("Broken_" + flag):
				broken[flag].append(node)
	for spec: Dictionary in presentation.get("motion", []):
		var pivot := Node3D.new()
		pivot.position = _vector(spec.pivot)
		add_child(pivot)
		for node: Node in imported.find_children(str(spec.prefix) + "*", "MeshInstance3D", true, false):
			# GLB geometry is authored in world coordinates. Preserve that geometry
			# while giving the flywheel and piston a local mechanical pivot.
			# Keep source meshes in the imported tree: WorldLoader packs its cache
			# a few frames later, and must retain machinery for future visits.
			var part := MeshInstance3D.new()
			part.mesh = node.mesh
			part.position = -pivot.position
			pivot.add_child(part)
			node.hide()
		machinery.append({"node":pivot, "origin":pivot.position, "kind":spec.kind, "flag":spec.flag})
	for spec: Dictionary in presentation.get("lights", []):
		var lamp := OmniLight3D.new()
		lamp.position = _vector(spec.at)
		lamp.light_color = Color("ffba68")
		lamp.light_energy = float(spec.energy)
		lamp.omni_range = float(spec.range)
		lamp.shadow_enabled = false
		add_child(lamp)
		lamps.append({"node":lamp, "flag":str(spec.flag)})
	for spec: Dictionary in presentation.get("signs", []):
		var title := Label3D.new()
		title.text = str(spec.text)
		title.position = _vector(spec.at) + Vector3(0,.16,0)
		title.font_size = 40
		title.pixel_size = .0095
		title.modulate = Color("f4e1b7")
		title.outline_size = 2
		add_child(title)
		var subtitle := Label3D.new()
		subtitle.text = str(spec.subtitle)
		subtitle.position = _vector(spec.at) - Vector3(0,.2,0)
		subtitle.font_size = 32
		subtitle.pixel_size = .0055
		subtitle.modulate = Color("e0cba1")
		subtitle.outline_size = 1
		add_child(subtitle)
	apply_state({})

func apply_state(state: Dictionary) -> void:
	current_flags = state.get("flags", {})
	for flag: String in outcome_flags:
		var enabled := bool(current_flags.get(flag, false))
		for node: Node3D in reveals[flag]: node.visible = enabled
		for node: Node3D in broken[flag]: node.visible = not enabled
	for entry: Dictionary in lamps:
		entry.node.visible = entry.flag.is_empty() or bool(current_flags.get(entry.flag, false))
	set_process(bool(current_flags.get("pump_repaired", false)))

func _process(delta: float) -> void:
	elapsed += minf(delta, .1)
	for entry: Dictionary in machinery:
		if not bool(current_flags.get(entry.flag, false)): continue
		if entry.kind == "wheel":
			entry.node.rotation.z = elapsed * 1.8
		else:
			entry.node.position = entry.origin + Vector3(0, sin(elapsed * 1.8) * .25, 0)

static func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))
