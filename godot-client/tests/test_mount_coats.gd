extends SceneTree
const Portrait := preload("res://src/mounts/mount_portrait.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const Coats := preload("res://src/mounts/mount_coats.gd")
const Codec := preload("res://src/mounts/mount_protocol.gd")
const Interest := preload("res://src/network/interest_protocol.gd")
var checks := 0
var failures := 0
var maximum_normal_error := 0.0

func _init() -> void: call_deferred("run")
func expect(ok: bool, reason: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(reason)

func run() -> void:
	for id: String in Profiles.PATHS:
		var preview := Portrait.new()
		var other := Portrait.new()
		root.add_child(preview)
		root.add_child(other)
		preview.configure(id)
		other.configure(id)
		expect(not preview.coat.parts.is_empty(),id+" has coat surfaces")
		for coat_id: String in Coats.IDS:
			preview.set_coat(coat_id)
			expect(preview.coat.current == coat_id,id+" applies "+coat_id)
			for part: Dictionary in preview.coat.parts:
				var original := part.mesh as Mesh
				var visible := (part.node as MeshInstance3D).mesh
				expect(visible.get_surface_count() == original.get_surface_count(),"all surfaces retained")
				expect(visible.get_blend_shape_count() == original.get_blend_shape_count(),"corrective shapes retained")
				for surface: int in original.get_surface_count():
					var a := original.surface_get_arrays(surface)
					var b := visible.surface_get_arrays(surface)
					for attribute: int in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL,Mesh.ARRAY_BONES,Mesh.ARRAY_WEIGHTS,Mesh.ARRAY_TEX_UV,Mesh.ARRAY_INDEX]:
						if attribute == Mesh.ARRAY_NORMAL:
							var worst := 0.0
							for vertex: int in a[attribute].size(): worst = maxf(worst,a[attribute][vertex].distance_to(b[attribute][vertex]))
							maximum_normal_error = maxf(maximum_normal_error,worst)
							expect(worst < .0003,"normal repacking remains within native precision: "+id)
						else:
							expect(a[attribute] == b[attribute],"coat never changes geometry, UV, binds or influences: "+id+" attribute="+str(attribute))
					if coat_id == "ashen" and id in ["cave_salamander","lantern_stag","cheetah"]:
						var mask := 0.0
						for colour: Color in b[Mesh.ARRAY_COLOR]: mask += colour.a
						print("COAT_MASK ",id," mean=",mask/b[Mesh.ARRAY_COLOR].size()," base=",original.surface_get_material(surface).albedo_color)
					if coat_id != "original":
						expect(visible != original and part.node.get_surface_override_material(surface) is ShaderMaterial,"isolated material instance")
						expect(b[Mesh.ARRAY_CUSTOM0] != null,"pattern has fixed rest coordinates")
			for part: Dictionary in other.coat.parts:
				expect(part.node.mesh == part.mesh,"other instance remains original")
			var row := {"schema_version":1,"actor_id":42,"mode":"mounted","gait":"burst",
				"mount_id":id,"selected_mount_id":id,"step_us":100000,"endurance_ms":3000,
				"summon_remaining_ms":0,"combat_remaining_ms":0,"can_summon":false,"blocked_reason":"",
				"map":"four_gates","owner":"Rider","owned_mount_ids":Profiles.PATHS.keys(),
				"coat_id":coat_id,"mount_coats":{id:coat_id}}
			var message := {"schema_version":1,"map":"four_gates","states":[row]}
			var full := Codec.decode(JSON.stringify(message).to_utf8_buffer())
			expect(full.type == "mount_states" and full.states[42].coat_id == coat_id,"complete tables retain coat")
			var delta_row: Dictionary = row.duplicate(true)
			delta_row.merge({"schema_version":2,"summon_due":0,"combat_until":0,"endurance_at":1000,"endurance_rate":0,"endurance_max_ms":8000},true)
			var delta := Interest.decode_mount_deltas(JSON.stringify({"schema_version":2,"map":"four_gates","full":true,"states":[delta_row],"removed":[]}).to_utf8_buffer())
			expect(delta.type == "mount_update" and delta.states[42].coat_id == coat_id,"delta tables retain coat")
			row.coat_id = "res://arbitrary.png"
			expect(Codec.decode(JSON.stringify(message).to_utf8_buffer()).type == "invalid","network cannot select arbitrary textures")
		preview.set_coat("original")
		for part: Dictionary in preview.coat.parts:
			expect(part.node.mesh == part.mesh,"Original restores the exact shared mesh")
			expect(part.node.material_override == part.materialOverride,"Original restores runtime material override")
		# The same catalogue also accepts real replacement albedo textures.
		if id == "lantern_stag":
			var material := preview.coat.parts[0].active[0] as StandardMaterial3D
			var texture_path := "res://test-artifacts/mount-coats/replacement.tres"
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(texture_path.get_base_dir()))
			var fixture := Image.create(2,2,false,Image.FORMAT_RGB8)
			fixture.fill(Color.MAGENTA)
			ResourceSaver.save(ImageTexture.create_from_image(fixture),texture_path)
			Coats.catalogue().presets.snow["textures"] = {material.resource_name:texture_path}
			preview.set_coat("snow")
			expect(preview.coat.parts[0].node.get_active_material(0).get_shader_parameter("coat_texture") == load(texture_path),"catalogue resolves a replacement texture")
			Coats.catalogue().presets.snow.erase("textures")
		preview.free()
		other.free()
	print("MOUNT_COAT_CHECKS ",checks," failures=",failures," maxNormalError=",maximum_normal_error)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
