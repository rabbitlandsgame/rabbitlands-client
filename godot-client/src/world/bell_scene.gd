extends Node3D
## Bellwatch presentation. Server snapshots own gates, enemies and the bell.

const ROOT := "res://../eloria-assets/maps/bellwatch/"
var gates: Dictionary = {}
var lamps: Dictionary = {}
var cart: Node3D
var rung := false
var initialized := false
var layout: Dictionary = {}

func configure(imported: Node3D, _manifest: WorldManifest) -> void:
	layout = JSON.parse_string(FileAccess.get_file_as_string(ROOT + "layout.json"))
	for node: Node in imported.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		for i in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(i) as BaseMaterial3D
			if material:
				material.vertex_color_use_as_albedo = true
				material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	for gate: Dictionary in layout.gates:
		var leaf := Node3D.new()
		leaf.position = Vector3(gate.at[0], .4, -gate.at[1])
		leaf.rotation.y = deg_to_rad(float(gate.get("rotation", 0)))
		add_child(leaf)
		for i in range(12):
			_box(leaf, Vector3(i - 5.5, 1.45, 0), Vector3(.72, 2.9, .3), Color("44392b"))
		_box(leaf, Vector3(0, .8, .22), Vector3(12, .15, .16), Color("9b8259"))
		_box(leaf, Vector3(0, 2.1, .22), Vector3(12, .15, .16), Color("9b8259"))
		gates[str(gate.requires)] = leaf
		var light := OmniLight3D.new()
		light.position = leaf.position + Vector3(0, 3.2, 0)
		light.omni_range = 9
		light.light_energy = 1.6
		add_child(light)
		lamps[str(gate.requires)] = light
	for point in [Vector3(68, 3, -78), Vector3(79, 3, -78), Vector3(72, 4, -85)]:
		var light := OmniLight3D.new()
		light.position = point
		light.light_color = Color("ffd295")
		light.light_energy = 1.7
		light.omni_range = 12
		add_child(light)
	cart = Node3D.new()
	cart.position = Vector3(59, .4, -72)
	add_child(cart)
	_box(cart, Vector3(0, 1.1, 0), Vector3(4, .3, 2), Color("765733"))
	_box(cart, Vector3(0, 1.9, -.95), Vector3(4, 1.5, .15), Color("947650"))
	_box(cart, Vector3(0, 1.9, .95), Vector3(4, 1.5, .15), Color("947650"))
	for x in [-1.3, 1.3]:
		for z in [-1.15, 1.15]:
			var wheel := MeshInstance3D.new()
			var cylinder := CylinderMesh.new()
			cylinder.top_radius = .65
			cylinder.bottom_radius = .65
			cylinder.height = .15
			wheel.mesh = cylinder
			wheel.rotation.x = PI / 2
			wheel.position = Vector3(x, .65, z)
			var material := StandardMaterial3D.new()
			material.albedo_color = Color("332c25")
			wheel.material_override = material
			cart.add_child(wheel)

func _box(parent: Node3D, at: Vector3, size: Vector3, color: Color) -> void:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.position = at
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = .85
	mesh.material_override = material
	parent.add_child(mesh)

func apply_state(state: Dictionary) -> void:
	var flags: Dictionary = state.get("flags", {})
	for key: String in gates:
		gates[key].visible = not bool(flags.get(key, false))
		lamps[key].light_color = Color("ffd295") if bool(flags.get(key, false)) else Color("b37d65")
	rung = bool(flags.get("rung", false))
	initialized = true
	# Keep the waiting cart at its authoritative clickable boarding position.
	# The warm western gate marks a safe road after the bell is rung.
	if rung and lamps.has("west"):
		lamps.west.light_energy = 2.5
