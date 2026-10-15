extends Node3D
## The four gates mirror the private adventure's authoritative walkability.

var layout: Dictionary = {}
var gates: Dictionary = {}
var restored: Dictionary = {}
var workshop: Node3D
var resource_labels: Dictionary = {}

func configure(imported: Node3D, manifest: WorldManifest) -> void:
	layout = JSON.parse_string(FileAccess.get_file_as_string("res://../eloria-assets/maps/" + manifest.asset_id() + "/layout.json"))
	for node: Node in imported.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		for i in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(i) as BaseMaterial3D
			if material:
				material.vertex_color_use_as_albedo = true
	for gate: Dictionary in layout.gates:
		if manifest.asset_id() in ["cinderbank", "reedway"]:
			var frame := Node3D.new()
			frame.position = Vector3(gate.at[0], .4, -gate.at[1])
			frame.rotation.y = deg_to_rad(float(gate.rotation))
			var iron := StandardMaterial3D.new()
			iron.albedo_color = Color("41453e")
			iron.metallic = .65
			var caravan := manifest.asset_id() == "reedway"
			if caravan:
				iron.albedo_color = Color("614d32")
				iron.metallic = 0.0
			for i in range(5 if caravan else 15):
				var bar := MeshInstance3D.new()
				var shape := BoxMesh.new()
				shape.size = Vector3(.16, 1.35, .16) if caravan else Vector3(.095, 2.7, .13)
				bar.mesh = shape
				bar.position = Vector3((i-2)*2.1, .675, 0) if caravan else Vector3((i-7)*.6, 1.35, 0)
				bar.material_override = iron
				frame.add_child(bar)
			for height in ([.45, 1.1] if caravan else [.45, 2.35]):
				var rail := MeshInstance3D.new()
				var shape := BoxMesh.new()
				shape.size = Vector3(9, .15, .18)
				rail.mesh = shape
				rail.position.y = height
				rail.material_override = iron
				frame.add_child(rail)
			add_child(frame)
			gates[str(gate.id)] = frame
			continue
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
	for target: Dictionary in layout.targets:
		if str(target.kind) == "harvestable":
			var label := Label3D.new()
			label.position = Vector3(target.tile[0], 2.1, -target.tile[1])
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.font_size = 34
			label.outline_size = 6
			label.no_depth_test = false
			label.visible = false
			add_child(label)
			resource_labels[str(target.objectId)] = label
		if str(target.kind) != "information": continue
		var beacon := MeshInstance3D.new()
		var globe := SphereMesh.new()
		globe.radius=.35;globe.height=.7
		beacon.mesh=globe
		beacon.position=Vector3(target.tile[0],3.4,-target.tile[1])
		var material := StandardMaterial3D.new()
		material.albedo_color=Color("efcc70")
		material.emission_enabled=true;material.emission=Color("edb54f")
		beacon.material_override=material
		add_child(beacon);restored[str(target.id)]=beacon
		beacon.hide()
	if manifest.asset_id() in ["cinderbank", "reedway"]:
		# Saved prop changes replace floating completion bulbs in authored maps.
		for beacon: Node3D in restored.values(): beacon.queue_free()
		restored.clear()
		workshop = preload("res://src/world/cinderbank_scene.gd").new()
		add_child(workshop)
		workshop.configure(imported, layout.get("presentation", {}))

func apply_state(state: Dictionary) -> void:
	var resources: Dictionary = state.get("resource_labels", {})
	for key: String in resource_labels:
		var label: Label3D = resource_labels[key]
		label.visible = resources.has(key)
		label.text = str(resources.get(key, ""))
	var flags: Dictionary = state.get("flags", {})
	for key: String in gates:
		gates[key].visible = not bool(flags.get(key, false))
	var completed: Array=state.get("completed_objects",[])
	for key: String in restored:restored[key].visible=key in completed
	if workshop: workshop.apply_state(state)
