extends Node3D
## The observatory's geometry and lamps mirror the server's private state.
const ROOT := "res://../eloria-assets/maps/stillglass/"
var layout: Dictionary = {}
var gates: Dictionary = {}
var lights: Array[OmniLight3D] = []
var arcs: Array[MeshInstance3D] = []

func configure(imported: Node3D, _manifest: WorldManifest) -> void:
	layout = JSON.parse_string(FileAccess.get_file_as_string(ROOT + "layout.json"))
	for node: Node in imported.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		for i in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(i) as BaseMaterial3D
			if material:
				material.vertex_color_use_as_albedo = true
	for gate: Dictionary in layout.gates:
		var leaf := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3(9, 2.8, .25)
		leaf.mesh = box
		leaf.position = Vector3(gate.at[0], 1.8, -gate.at[1])
		leaf.rotation.y = deg_to_rad(float(gate.rotation))
		var material := StandardMaterial3D.new()
		material.albedo_color = Color("504560")
		material.metallic = .6
		leaf.material_override = material
		add_child(leaf)
		gates[str(gate.id)] = leaf
	for i in range(3):
		var arc := MeshInstance3D.new()
		var ring := TorusMesh.new()
		ring.inner_radius = 2.5 + i * .4
		ring.outer_radius = 2.56 + i * .4
		arc.mesh = ring
		arc.position = Vector3(60, 4.3 + i * .4, -73)
		arc.rotation = Vector3(.25 * i, 0, .35 * i)
		var glow := StandardMaterial3D.new()
		glow.albedo_color = Color("d4c599")
		glow.emission_enabled = true
		glow.emission = Color("94bcd5")
		glow.emission_energy_multiplier = 1.4
		arc.material_override = glow
		add_child(arc)
		arcs.append(arc)
	for point: Vector3 in [Vector3(60, 4, -73), Vector3(60, 3, -100), Vector3(106, 3, -60), Vector3(60, 3, -21)]:
		var light := OmniLight3D.new()
		light.position = point
		light.light_color = Color("c8d3f2")
		light.light_energy = 1.8
		light.omni_range = 16
		add_child(light)
		lights.append(light)

func apply_state(state: Dictionary) -> void:
	var flags: Dictionary = state.get("flags", {})
	for key: String in gates:
		gates[key].visible = not bool(flags.get(key, false))
	for i in range(arcs.size()):
		arcs[i].visible = int(state.get("count", 0)) > i or bool(flags.get("rung", false))
