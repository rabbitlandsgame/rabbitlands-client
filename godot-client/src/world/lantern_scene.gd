extends Node3D
## Presentation of server-owned rescue state. Actors, items, harvesting and
## picking belong to the normal client; this adds only the map's moving props.

const ROOT := "res://../eloria-assets/maps/lantern-reach/"
const BOAT_DOCK := Vector3(110, -.6, -22)
var layout: Dictionary
var gates: Dictionary = {}
var beacon: OmniLight3D
var beam: MeshInstance3D
var boat: Node3D
var lit := false
var initialized := false
var departure_ready := false
var boarding_point: MapObject3D
var boat_pick_body: StaticBody3D

func configure(imported: Node3D, _manifest: WorldManifest) -> void:
	layout = JSON.parse_string(FileAccess.get_file_as_string(ROOT+"layout.json"))
	var art: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ROOT+"art.json"))
	var water := ShaderMaterial.new()
	water.shader = preload("res://src/world/lantern_water.gdshader")
	var mask := Image.create(120,120,false,Image.FORMAT_R8)
	for y in range(120):
		for x in range(120): mask.set_pixel(x,y,Color.WHITE if int(layout.walkGrid[y*120+x]) else Color.BLACK)
	water.set_shader_parameter("land_mask",ImageTexture.create_from_image(mask))
	for node: Node in imported.find_children("*","MeshInstance3D",true,false):
		var mesh := node as MeshInstance3D
		for i in range(mesh.mesh.get_surface_count()):
			var mat := mesh.get_active_material(i) as BaseMaterial3D
			if mat:
				mat.vertex_color_use_as_albedo = true
				mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		if str(mesh.name).begins_with("Scenery_Water"):
			mesh.material_override = water
	for at: Array in art.lanterns:
		var light := OmniLight3D.new()
		light.position = Vector3(at[0],at[1],at[2])
		light.light_color = Color("ffbe73")
		light.light_energy = 1.25
		light.omni_range = 5
		add_child(light)
	for gate: Dictionary in layout.gates:
		var root := GlbSceneCache.instantiate(ProjectSettings.globalize_path(ROOT+"models/gate.glb"))
		if root == null: continue
		var placement: Dictionary = art.gatePlacements[str(gate.id)]
		root.name = str(gate.id)
		root.position = Vector3(placement.position[0], placement.position[1], placement.position[2])
		root.scale = Vector3(placement.scale[0], placement.scale[1], placement.scale[2])
		add_child(root)
		var parts: Array[Node] = []
		for part: Node in root.find_children("GateLeaf*","MeshInstance3D",true,false): parts.append(part)
		gates[str(gate.requires)] = parts
	beacon = OmniLight3D.new()
	beacon.position = Vector3(99,12,-101)
	beacon.light_color = Color("ffcf7a")
	beacon.light_energy = 7
	beacon.omni_range = 22
	add_child(beacon)
	beam = _beam()
	beam.position = beacon.position
	add_child(beam)
	boat = GlbSceneCache.instantiate(ProjectSettings.globalize_path(ROOT+"models/boat.glb"))
	if boat:
		boat.position = Vector3(116,-.6,-48)
		add_child(boat)
	beacon.hide()
	beam.hide()

func _tile(at: Array) -> Vector3:
	var x := int(at[0])
	var y := int(at[1])
	return Vector3(x, float(layout.heightOrigin)+float(layout.walkGrid[y*120+x])*float(layout.heightStep), -y)

func apply_state(state: Dictionary) -> void:
	var flags: Dictionary = state.get("flags", {})
	for key: String in gates:
		for part: Node3D in gates[key]: part.visible = not bool(flags.get(key,false))
	lit = bool(flags.get("lit",false))
	departure_ready = bool(state.get("active", false)) and str(state.get("key", "")) == "depart"
	beacon.visible = lit
	beam.visible = lit
	if boat and not initialized:
		boat.position = BOAT_DOCK if lit else Vector3(116,-.6,-48)
	initialized = true
	_sync_boat_picking()

func bind_map_objects(objects: Dictionary) -> void:
	if not is_instance_valid(boat):
		return
	var target_id := -1
	for target: Dictionary in layout.get("targets", []):
		if str(target.get("id", "")) == "ferry":
			target_id = int(target.get("objectId", -1))
			break
	var target := objects.get(target_id) as MapObject3D
	if target != boarding_point or not is_instance_valid(boat_pick_body):
		if is_instance_valid(boarding_point):
			boarding_point.departure_available = false
		if is_instance_valid(boat_pick_body):
			boat_pick_body.collision_layer = 0
			boat_pick_body.queue_free()
		boarding_point = target
		boat_pick_body = target.bind_pick_model(boat) if is_instance_valid(target) else null
	_sync_boat_picking()

func _sync_boat_picking() -> void:
	var available := departure_ready and lit and is_instance_valid(boat) and boat.position.is_equal_approx(BOAT_DOCK)
	if is_instance_valid(boarding_point):
		boarding_point.departure_available = available
	if is_instance_valid(boat_pick_body):
		boat_pick_body.collision_layer = MapObject3D.PICK_LAYER if available else 0

func _process(delta: float) -> void:
	if lit:
		beam.rotation.y += delta*.18
		if boat: boat.position = boat.position.move_toward(BOAT_DOCK,delta*2.8)
	_sync_boat_picking()

func _beam() -> MeshInstance3D:
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(12):
		var a := TAU*i/12
		var b := TAU*(i+1)/12
		mesh.surface_set_color(Color(1,.73,.33,.24))
		mesh.surface_add_vertex(Vector3.ZERO)
		mesh.surface_set_color(Color(1,.73,.33,0))
		mesh.surface_add_vertex(Vector3(cos(a)*7,sin(a)*2.2,84))
		mesh.surface_set_color(Color(1,.73,.33,0))
		mesh.surface_add_vertex(Vector3(cos(b)*7,sin(b)*2.2,84))
	mesh.surface_end()
	var result := MeshInstance3D.new()
	result.mesh = mesh
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	result.material_override = material
	result.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return result
