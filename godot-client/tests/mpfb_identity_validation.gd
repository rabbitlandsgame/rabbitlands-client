extends "res://tests/mpfb_concept_portrait.gd"
## Focused reusable-head review: six identities from the same two source GLBs.
## Checks identity persistence through action/palette changes and audits the
## bounded field on actual face vertices. Optional portraits use game pixels.
const PROPORTIONS := preload("res://src/actors/character_proportions.gd")
const IDENTITY_FIELDS := ["jaw", "cheekbones", "nose", "face_length", "eye_size", "eye_tilt", "eye_spacing", "nose_width", "lip_fullness", "brow_depth"]
const ACTION_REVIEW := [&"idle", &"walk", &"run", &"attack_primary", &"attack_secondary", &"attack_flurry", &"combat_idle"]
const IDENTITIES := {
	"soft": {"jaw":20,"cheekbones":35,"nose":24,"face_length":22,"eye_size":76,"eye_tilt":63,"eye_spacing":57,"nose_width":30,"lip_fullness":78,"brow_depth":25},
	"angular": {"jaw":88,"cheekbones":88,"nose":82,"face_length":84,"eye_size":25,"eye_tilt":34,"eye_spacing":35,"nose_width":76,"lip_fullness":20,"brow_depth":93}}
var assertion_count := 0
var identity_records: Array = []
var groom_records: Array = []
var hair_records: Array = []
var headwear_records: Array = []
var capture_enabled := false

func expect(ok: bool, label: String) -> void:
	assertion_count += 1
	super.expect(ok, label)

func encoded_sha(value: Variant) -> String:
	return var_to_bytes(value).hex_encode().sha256_text()

func mesh_signature(actor: ReplicatedActor3D, positions_only: bool = true) -> Dictionary:
	var result := {}
	for part: String in ["body", "eyes"]:
		var mesh := actor._native_model.find_child(part, true, false) as MeshInstance3D
		if mesh == null or mesh.mesh == null: continue
		var values: Array = []
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			values.append(arrays[Mesh.ARRAY_VERTEX] if positions_only else [arrays[Mesh.ARRAY_TEX_UV], arrays[Mesh.ARRAY_INDEX], arrays[Mesh.ARRAY_BONES], arrays[Mesh.ARRAY_WEIGHTS]])
		result[part] = encoded_sha(values)
	return result

func retained_body_signature(actor: ReplicatedActor3D) -> String:
	var body := actor._native_model.find_child("body",true,false) as MeshInstance3D
	return encoded_sha(body.mesh.surface_get_arrays(1)) if body != null and body.mesh.get_surface_count()>1 else ""

func retained_body_points(actor: ReplicatedActor3D) -> PackedVector3Array:
	var body := actor._native_model.find_child("body",true,false) as MeshInstance3D
	return body.mesh.surface_get_arrays(1)[Mesh.ARRAY_VERTEX]

func body_delta(source: PackedVector3Array, target: PackedVector3Array) -> Dictionary:
	var maximum:=0.0;var protected_maximum:=0.0;var moved:=0;var low:=Vector3(INF,INF,INF);var high:=-low
	for index: int in mini(source.size(),target.size()):
		var distance:=source[index].distance_to(target[index])
		maximum=maxf(maximum,distance)
		if source[index].y<=1.40 or absf(source[index].x)>=.13: protected_maximum=maxf(protected_maximum,distance)
		if distance>.000001: moved+=1;low=low.min(source[index]);high=high.max(source[index])
	return {"maximum_position_delta_m":maximum,"protected_body_maximum_delta_m":protected_maximum,"moved_vertices_over_1um":moved,"moved_source_bounds_m":[numbers(low),numbers(high)] if moved else [],"protected_region":"Canonical torso/arms/hands/legs: source y<=1.40m or abs(x)>=0.13m; tiny continuous upper-neck face-field tail reported separately."}

func native_head_points(actor: ReplicatedActor3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	var rig := actor.get_skeleton()
	var frame := PROPORTIONS.face_frame(actor._native_model,rig)
	for part: String in ["body","eyes"]:
		var mesh := actor._native_model.find_child(part,true,false) as MeshInstance3D
		var to_head: Transform3D = frame.to_head * PROPORTIONS._to_root(rig,actor._native_model).affine_inverse() * PROPORTIONS._to_root(mesh,actor._native_model)
		var arrays := mesh.mesh.surface_get_arrays(0)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var used := {}
		for index: int in arrays[Mesh.ARRAY_INDEX]: used[index]=true
		for index: int in used:
			var point := to_head*points[index]
			if part=="eyes" or (point.y>frame.eye_y-.15 and point.y<frame.eye_y+.065 and point.z>frame.eye_z-.04):
				result.append(point)
	return result

func face_statistics(actor: ReplicatedActor3D) -> Dictionary:
	var points := native_head_points(actor)
	var low := Vector3(INF,INF,INF);var high := -low
	for point: Vector3 in points:
		expect(point.is_finite(),"all indexed face/eye coordinates are finite")
		low=low.min(point);high=high.max(point)
	return {"sample_count":points.size(),"head_local_bounds_m":[numbers(low),numbers(high)],"head_local_extent_m":numbers(high-low)}

func shape_checks(actor: ReplicatedActor3D, model: Dictionary, baseline: Dictionary) -> Dictionary:
	var frame := PROPORTIONS.face_frame(actor._native_model,actor.get_skeleton())
	var points := native_head_points(actor)
	var cases: Array = []
	for field: String in IDENTITY_FIELDS:
		for endpoint: int in [0,100]:
			var values := baseline.duplicate();values[field]=endpoint
			cases.append({"label":field+"="+str(endpoint),"appearance":values})
	for combination: int in 4:
		var values:=baseline.duplicate()
		for index: int in IDENTITY_FIELDS.size(): values[IDENTITY_FIELDS[index]]=100 if (index+combination)%4<2 else 0
		cases.append({"label":"combined_"+str(combination),"appearance":values})
	var all_low:=baseline.duplicate();var all_high:=baseline.duplicate()
	for field: String in IDENTITY_FIELDS: all_low[field]=0;all_high[field]=100
	cases.append({"label":"all_minimum","appearance":all_low});cases.append({"label":"all_maximum","appearance":all_high})
	var measured: Array = []
	for entry: Dictionary in cases:
		var shape:=PROPORTIONS.face_shape(MPFB.shape_appearance(entry.appearance,model))
		var maximum_delta:=0.0;var minimum_determinant:=INF;var inverse_error:=0.0;var maximum_fixed_delta:=0.0;var sampled:=0
		for index: int in range(0,points.size(),17):
			var point:=points[index]
			var moved:=PROPORTIONS.face_point(point,frame,shape)
			var jacobian:=PROPORTIONS.face_jacobian(point,frame,shape)
			maximum_delta=maxf(maximum_delta,point.distance_to(moved))
			minimum_determinant=minf(minimum_determinant,jacobian.determinant())
			inverse_error=maxf(inverse_error,PROPORTIONS.inverse_face_point(moved,frame,shape).distance_to(point))
			sampled+=1
		# Neck, back of skull and hairline anchor probes must remain stationary.
		for point: Vector3 in [Vector3(0,frame.eye_y-.20,frame.eye_z),Vector3(.10,frame.eye_y,frame.eye_z),Vector3(0,frame.eye_y+.09,frame.eye_z),Vector3(0,frame.eye_y,frame.eye_z-.10)]:
			maximum_fixed_delta=maxf(maximum_fixed_delta,PROPORTIONS.face_point(point,frame,shape).distance_to(point))
		expect(minimum_determinant>.10,entry.label+" retains positive sampled local volume")
		expect(maximum_delta<.030,entry.label+" stays within30mm bounded identity envelope")
		expect(inverse_error<.00005,entry.label+" inverse mapping returns within0.05mm")
		expect(maximum_fixed_delta<.000001,entry.label+" neck/skull/hairline probes stay fixed")
		measured.append({"case":entry.label,"sample_count":sampled,"maximum_displacement_m":maximum_delta,"minimum_jacobian_determinant":minimum_determinant,"maximum_inverse_error_m":inverse_error,"maximum_fixed_anchor_delta_m":maximum_fixed_delta})
	return {"cases":measured,"scope":"Rest-field audit on indexed front face and eye vertices at stride17, all single endpoints and six mixed corners. Not an exhaustive proof of every slider combination or a substitute for visual eyelid review."}

func settle(actor: ReplicatedActor3D, action: StringName, phase: float) -> void:
	actor.play_action(action,true)
	actor.animation_player.advance(.20)
	var animation:=actor.animation_player.get_animation(actor.animation_player.assigned_animation)
	actor.animation_player.seek(minf(animation.length*phase,animation.length-.000001),true)
	actor.animation_player.pause();actor.get_skeleton().force_update_all_bone_transforms()

func capture_identity(actor: ReplicatedActor3D, sex: String, name: String, identity: String) -> Array:
	var files: Array=[]
	if not capture_enabled: return files
	actor.play_action(&"idle",true)
	actor.animation_player.seek(.4,true);actor.animation_player.pause()
	actor.get_skeleton().force_update_all_bone_transforms()
	var rig:=actor.get_skeleton()
	var points:=current_anchors(actor,sex,true)
	for view: String in ["front","side"]:
		var ref:=reference(name,"equipped",view)
		var profile:Dictionary=VIEWS[view].duplicate(true);profile.merge(ref.get("camera_initial",{}),true)
		var previous:=frozen_pose(rig,profile)
		var framing:=fit_portrait_roll(rig,points,ref,profile,view)
		for _frame: int in 6: await process_frame
		await RenderingServer.frame_post_draw
		var filename:=name.to_lower()+"-"+identity+"-"+view+".png"
		expect(root.get_texture().get_image().save_png(output.path_join(filename))==OK,"identity portrait saved")
		var projected:Dictionary={}
		for key:String in points:
			var pixel:=camera.unproject_position(world_point(rig,vec(points[key])))
			projected[key]=[pixel.x,pixel.y]
		files.append({"view":view,"file":filename,"camera":framing,"pose":profile,"source_landmarks_capture_pixels":projected})
		restore_pose(rig,previous)
	return files

func check_groom_controls(actor: ReplicatedActor3D, model: Dictionary, baseline: Dictionary, sex: String, name: String) -> Dictionary:
	if not bool(model.get("headMasks",false)):
		return {"tested":false,"reason":"Input stage has no packed head masks"}
	actor.apply_appearance_variants(baseline)
	var before:=mesh_signature(actor);var topology:=mesh_signature(actor,false)
	var body:=actor._native_model.find_child("body",true,false) as MeshInstance3D
	var eye_mesh:=actor._native_model.find_child("eyes",true,false) as MeshInstance3D
	var clean:=body.get_active_material(0) as ShaderMaterial
	expect(clean!=null and clean.get_shader_parameter("head_masks_enabled")==true,sex+" packed head coverage enabled")
	expect(clean.get_shader_parameter("stubble_enabled")==false,sex+" clean shave clears stubble")
	var metadata:=json_file(str(model.scene).get_base_dir().path_join("fit.json"))
	var lip_values:Array=metadata.get("head_lip_uv_bounds",[])
	var lip_bounds:Vector4=clean.get_shader_parameter("lip_uv_bounds")
	var lip_report:Dictionary={"tested":false}
	if lip_values.size()==4:
		var expected:=Vector4(lip_values[0],lip_values[1],lip_values[2],lip_values[3])
		expect(lip_bounds.is_equal_approx(expected),sex+" lip surface receives authored UV bounds")
		expect(lip_bounds.x>=0 and lip_bounds.y>=0 and lip_bounds.z<=1 and lip_bounds.w<=1 and lip_bounds.z>lip_bounds.x and lip_bounds.w>lip_bounds.y,sex+" lip UV rectangle is nonempty and bounded")
		var texture:=clean.get_shader_parameter("base_texture") as Texture2D
		var image:=texture.get_image().duplicate() as Image
		image.convert(Image.FORMAT_RGBA8)
		var pixels:=image.get_data();var width:=image.get_width();var height:=image.get_height()
		var low_inside:=0;var low_outside:=0
		for y:int in height:
			for x:int in width:
				if pixels[(y*width+x)*4+3]>=128:continue
				var uv:=Vector2((x+.5)/width,(y+.5)/height)
				if uv.x>=lip_bounds.x and uv.y>=lip_bounds.y and uv.x<=lip_bounds.z and uv.y<=lip_bounds.w:low_inside+=1
				else:low_outside+=1
		expect(low_inside>30 and low_outside>30,sex+" shared alpha contains separate lip and brow coverage")
		lip_report={"tested":true,"lip_uv_bounds":lip_values,"low_alpha_lip_texels":low_inside,"low_alpha_brow_texels":low_outside,"same_texture":true}
	var original_body_material:=body.get_active_material(1)
	var original_eye_material:=eye_mesh.get_active_material(0)
	var stubbled:=baseline.duplicate();stubbled.facial_hair=1
	actor.apply_appearance_variants(stubbled)
	var shaded:=body.get_active_material(0) as ShaderMaterial
	expect(shaded.get_shader_parameter("stubble_enabled")==true,sex+" stubble1 enables head pigment")
	expect(shaded.get_shader_parameter("lip_uv_bounds")==lip_bounds,sex+" stubble does not change the lip surface selection")
	expect(body.get_active_material(1)==original_body_material and eye_mesh.get_active_material(0)==original_eye_material,sex+" stubble toggle leaves body/eye materials unchanged")
	expect(mesh_signature(actor)==before and mesh_signature(actor,false)==topology,sex+" stubble uses pigment without mesh/UV/skin changes")
	expect(actor._native_model.find_child("PortraitFacialHair",true,false)==null,sex+" short stubble adds no shell mesh")
	var files:=await capture_identity(actor,sex,name,"stubble")
	var recolored:=stubbled.duplicate()
	recolored.hair=AppearanceVariants.pack_hair(AppearanceVariants.hair_style(int(baseline.hair)),(AppearanceVariants.hair_color_index(int(baseline.hair))+3)%AppearanceVariants.HAIR_COLOR_COUNT)
	actor.apply_appearance_variants(recolored)
	var tinted:=body.get_active_material(0) as ShaderMaterial
	expect(tinted.get_shader_parameter("lip_uv_bounds")==lip_bounds,sex+" grooming color does not change lip roughness coverage")
	expect(tinted.get_shader_parameter("base_texture")==clean.get_shader_parameter("base_texture"),sex+" grooming color cannot repaint the shared lip texture")
	var selected_groom:Color=tinted.get_shader_parameter("groom_color")
	expect(not selected_groom.is_equal_approx(clean.get_shader_parameter("groom_color")),sex+" grooming palette actually changes brow/stubble pigment")
	for node:Node in actor._native_model.find_children("*","MeshInstance3D",true,false):
		if not node.has_meta("rl_concept_hair"):continue
		var hair_material:=(node as MeshInstance3D).get_active_material(0) as ShaderMaterial
		var hair_color:Color=hair_material.get_shader_parameter("hair_color")
		expect(selected_groom.is_equal_approx(hair_color),sex+" brows/stubble share the selected concept hair pigment")
	expect(mesh_signature(actor)==before,sex+" grooming recolor preserves chosen face shape")
	if OS.get_environment("RL_MPFB_IDENTITY_CAPTURE_GROOM")=="1":
		files.append_array(await capture_identity(actor,sex,name,"groom-color"))
	actor.apply_appearance_variants(baseline)
	var restored:=body.get_active_material(0) as ShaderMaterial
	expect(restored.get_shader_parameter("stubble_enabled")==false,sex+" clean shave clears cached stubble")
	expect(mesh_signature(actor)==before,sex+" grooming toggle returns exact identity")
	return {"tested":true,"stubble1_head_only":true,"clean_shave_reset":true,"groom_recolor":true,"lip_surface":lip_report,"additional_geometry":0,"portraits":files}

func glb_uv_channels(path: String) -> Dictionary:
	# Inspect exported coordinates independently of the imported engine arrays.
	# These authored hair exports use packed float VEC2 accessors.
	var raw:=FileAccess.get_file_as_bytes(path)
	if raw.size()<28 or raw.decode_u32(0)!=0x46546c67: return {}
	var json_size:=raw.decode_u32(12)
	var document:Dictionary=JSON.parse_string(raw.slice(20,20+json_size).get_string_from_utf8())
	var binary_start:=28+json_size
	var primitive:Dictionary=document.meshes[0].primitives[0]
	var channels:Dictionary={"texcoord":0,"attributes":{}}
	var material:Dictionary=document.materials[primitive.material].get("pbrMetallicRoughness",{})
	channels.texcoord=int(material.get("baseColorTexture",{}).get("texCoord",0))
	for attribute: String in ["TEXCOORD_0","TEXCOORD_1"]:
		if not primitive.attributes.has(attribute): continue
		var accessor:Dictionary=document.accessors[primitive.attributes[attribute]]
		expect(accessor.componentType==5126 and accessor.type=="VEC2","hair source has float VEC2 "+attribute)
		if accessor.componentType!=5126 or accessor.type!="VEC2":continue
		var view:Dictionary=document.bufferViews[accessor.bufferView]
		var offset:=binary_start+int(view.get("byteOffset",0))+int(accessor.get("byteOffset",0))
		var stride:=int(view.get("byteStride",8))
		var values:=PackedVector2Array();values.resize(accessor.count)
		for index: int in accessor.count: values[index]=Vector2(raw.decode_float(offset+index*stride),raw.decode_float(offset+index*stride+4))
		channels.attributes[attribute]=values
	return channels

func uv_error(imported: PackedVector2Array, exported: PackedVector2Array) -> float:
	if imported.size()!=exported.size():return INF
	var maximum:=0.0
	for index: int in imported.size(): maximum=maxf(maximum,imported[index].distance_to(exported[index]))
	return maximum

func check_hair_import(actor: ReplicatedActor3D, model: Dictionary, appearance: Dictionary, sex: String) -> Dictionary:
	var style:=str(AppearanceVariants.hair_style(int(appearance.hair)))
	var entry:Dictionary=model.get("hairStyleOverrides",{}).get(style,{})
	if entry.is_empty():return {"tested":false,"reason":"Selected hairstyle uses the ordinary production path"}
	var scene:=str(entry.scene);var exported:=glb_uv_channels(scene)
	expect(not exported.is_empty(),sex+" authored hair source UV contract readable")
	var parts:Array=[]
	for child: Node in actor._native_model.find_children("*","MeshInstance3D",true,false):
		var hair:=child as MeshInstance3D
		if not hair.has_meta("rl_concept_hair") or hair.mesh==null:continue
		var material:=hair.get_active_material(0) as ShaderMaterial
		expect(material!=null,sex+" concept hair has its dedicated material")
		if material==null:continue
		var painted:=bool(entry.get("painted_texture",false))
		expect(bool(material.get_shader_parameter("use_reference_texture"))==painted,sex+" imported hair paint flag agrees with authored metadata")
		var atlas:=material.get_shader_parameter("reference_paint") as Texture2D
		var image:Image=atlas.get_image() if atlas!=null else null
		if painted:
			expect(image!=null and image.has_mipmaps(),sex+" reference hair atlas has mipmaps")
			expect(exported.texcoord==1,sex+" exported paint selects texCoord1")
		var arrays:=hair.mesh.surface_get_arrays(0)
		var vertices:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var primary:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV]
		var secondary:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV2] if arrays[Mesh.ARRAY_TEX_UV2]!=null else PackedVector2Array()
		expect(primary.size()==vertices.size(),sex+" primary hair UV covers every imported vertex")
		if painted:expect(secondary.size()==vertices.size(),sex+" growth UV2 covers every imported vertex")
		var finite:=true
		for uv:Vector2 in primary:finite=finite and uv.is_finite()
		for uv:Vector2 in secondary:finite=finite and uv.is_finite()
		expect(finite,sex+" imported paint/growth UVs are finite")
		var expected_primary:PackedVector2Array=exported.get("attributes",{}).get("TEXCOORD_1" if painted else "TEXCOORD_0",PackedVector2Array())
		var primary_error:=uv_error(primary,expected_primary)
		var growth_error:=uv_error(secondary,exported.attributes.get("TEXCOORD_0",PackedVector2Array())) if painted else primary_error
		# ArrayMesh UV packing quantizes coordinates by about1/65535. At1k,
		# this bound permits less than0.031texel while rejecting a channel swap.
		expect(primary_error<.00003,sex+" glTF importer routes the selected paint atlas to primary UV within mesh quantization")
		expect(growth_error<.00003,sex+" original lock-growth UV is retained in "+("UV2" if painted else "UV")+" within mesh quantization")
		parts.append({"source":scene,"source_sha256":FileAccess.get_sha256(scene),"painted_texture":painted,"source_texcoord":exported.texcoord,"imported_vertices":vertices.size(),"primary_uv_count":primary.size(),"growth_uv2_count":secondary.size(),"primary_uv_maximum_error":primary_error,"growth_uv_maximum_error":growth_error,"atlas_has_mipmaps":image!=null and image.has_mipmaps(),"atlas_dimensions":[image.get_width(),image.get_height()] if image!=null else [],"atlas_image_bytes":image.get_data().size() if image!=null else 0})
	expect(not parts.is_empty(),sex+" selected concept hairstyle is actually present")
	for part: String in ["body","eyes"]:
		var mesh:=actor._native_model.find_child(part,true,false) as MeshInstance3D
		var material:=mesh.get_active_material(0) as ShaderMaterial
		var texture:=material.get_shader_parameter("base_texture") as Texture2D
		var image:Image=texture.get_image() if texture!=null else null
		expect(image!=null and image.has_mipmaps(),sex+" "+part+" paint has mipmaps")
	return {"tested":true,"parts":parts,"routing":"Painted texCoord1 atlas becomes Godot UV; original growth TEXCOORD_0 becomes UV2. Unpainted fallback retains growth in UV."}

func visible_concept_hair(actor: ReplicatedActor3D) -> int:
	var count:=0
	for node:Node in actor._native_model.find_children("*","MeshInstance3D",true,false):
		if node.has_meta("rl_concept_hair") and (node as MeshInstance3D).is_visible_in_tree(): count+=1
	return count

func covering_helmet(actor: ReplicatedActor3D, registry: Dictionary) -> Dictionary:
	var keys:Array=registry.models.keys();keys.sort()
	for key:String in keys:
		if not key.begins_with("3:"):continue
		var visual:=int(key.get_slice(":",1));var config:=actor._equipment_model_config(3,visual)
		var path:=str(config.get("scene",""))
		if path.is_empty():continue
		for piece:Dictionary in actor._equipment_pieces(path):
			if bool(piece.get("covers_hair",false)):
				return {"visual_id":visual,"scene":path,"source_sha256":FileAccess.get_sha256(path)}
	return {}

func check_headwear(actor: ReplicatedActor3D, registry: Dictionary, baseline: Dictionary, sex: String, name: String) -> Dictionary:
	actor.apply_equipment_visuals({});actor.apply_appearance_variants(baseline)
	var original:=mesh_signature(actor)
	expect(visible_concept_hair(actor)>0,sex+" chosen concept hairstyle visible before headwear")
	var helmet:=covering_helmet(actor,registry)
	expect(not helmet.is_empty(),sex+" registry supplies a real hair-covering helmet")
	if helmet.is_empty():return {"tested":false,"reason":"No covering helmet available"}
	actor.apply_equipment_visuals({3:helmet.visual_id})
	expect(actor.equipment_diagnostics().fallback==0,sex+" covering headwear uses its native equipment asset")
	expect(actor._hidden_body_surfaces.has("hair") and visible_concept_hair(actor)==0,sex+" helmet hides authored hair regardless of mesh node name")
	var changed:=baseline.duplicate();changed.facial_hair=1;changed.hair_length=100;changed.hair_volume=0
	actor.apply_appearance_variants(changed)
	expect(visible_concept_hair(actor)==0,sex+" appearance/groom changes under a helmet cannot reveal hair")
	var bald:=changed.duplicate();bald.hair=AppearanceVariants.pack_hair(0,AppearanceVariants.hair_color_index(int(baseline.hair)))
	actor.apply_appearance_variants(bald);actor.apply_equipment_visuals({})
	expect(visible_concept_hair(actor)==0,sex+" removing helmet after choosing bald cannot restore old hair")
	actor.apply_appearance_variants(baseline)
	expect(visible_concept_hair(actor)>0,sex+" choosing the concept hairstyle after bald restores it")
	expect(mesh_signature(actor)==original,sex+" helmet/bald/groom cycle preserves exact chosen face")
	var files:Array=[]
	if OS.get_environment("RL_MPFB_IDENTITY_CAPTURE_HEADGEAR")=="1":
		actor.apply_equipment_visuals({3:helmet.visual_id})
		files=await capture_identity(actor,sex,name,"headgear")
		actor.apply_equipment_visuals({});actor.apply_appearance_variants(baseline)
		expect(visible_concept_hair(actor)>0,sex+" concept hair restores after the headwear capture")
	return {"tested":true,"helmet":helmet,"helmet_hides_hair":true,"groom_edits_remain_hidden":true,"bald_does_not_restore_old_hair":true,"chosen_style_restores":true,"portraits":files,"cosmetic_head_note":"Retired cosmetic head byte has no hat styles; actual headwear is tested through the existing equipment slot."}

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	output=OS.get_environment("RL_MPFB_IDENTITY_OUTPUT")
	if output.is_empty(): output=ProjectSettings.globalize_path("res://test-artifacts/mpfb-identities")
	DirAccess.make_dir_recursive_absolute(output)
	registration=json_file(OS.get_environment("RL_MPFB_REFERENCE_REGISTRATION"));anchors=json_file(OS.get_environment("RL_MPFB_LANDMARKS"))
	capture_enabled=OS.get_environment("RL_MPFB_IDENTITY_CAPTURE")=="1" and DisplayServer.get_name()!="headless"
	root.content_scale_mode=Window.CONTENT_SCALE_MODE_DISABLED;root.size=Vector2i(800,900);root.msaa_3d=Viewport.MSAA_2X
	stage=Node3D.new();root.add_child(stage)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new()
	environment.environment.background_mode=Environment.BG_COLOR;environment.environment.background_color=Color("d3d1cb")
	environment.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR;environment.environment.ambient_light_color=Color("e9e3d8");environment.environment.ambient_light_energy=.40;stage.add_child(environment)
	var key:=DirectionalLight3D.new();key.rotation_degrees=Vector3(-28,-32,0);key.light_color=Color("fff1dc");key.light_energy=.85;stage.add_child(key)
	var fill:=DirectionalLight3D.new();fill.rotation_degrees=Vector3(-10,125,0);fill.light_color=Color("e1e8ef");fill.light_energy=.15;stage.add_child(fill)
	camera=Camera3D.new();camera.near=.02;camera.far=20;camera.current=true;camera.cull_mask=3;stage.add_child(camera)
	var models:Dictionary=json_file("res://data/actors/models.json").models
	var gear:=json_file("res://data/actors/equipment.json");var animations:=json_file("res://data/animations/luminous.json")
	var prototype_root:=OS.get_environment("RL_MPFB_PROTOTYPE_ROOT")
	var groom_only:=OS.get_environment("RL_MPFB_IDENTITY_GROOM_ONLY")=="1"
	expect(not prototype_root.is_empty(),"explicit local MPFB root is required")
	if prototype_root.is_empty(): quit(1);return
	for name: String in ["Rowan","Mira"]:
		var sex:="female" if name=="Mira" else "male"
		var model:Dictionary=models["luminous_"+sex].duplicate(true)
		model.scene=prototype_root.path_join(sex+"/luminous_"+sex+".glb");model.geometryProfile="mpfb";model.erase("faceAppearance");model.erase("skinPalette")
		var metadata:=json_file(prototype_root.path_join(sex+"/fit.json"));model.mpfbFaceFrame=metadata.get("face_frame_head_local",{})
		MPFB.configure_art(model,metadata,prototype_root.path_join(sex))
		var source_hash:=FileAccess.get_sha256(model.scene)
		var actor:=ReplicatedActor3D.new();actor.apply_render_quality(2,true);stage.add_child(actor)
		var baseline:=PRESETS.appearance(name).merged({"shirt":5,"pants":2,"boots":2})
		var errors:=actor.configure({"actor_id":9941,"kind":1,"name":"","x":0,"y":0,"rotation":0,"appearance":baseline,"equipment_visuals":{}},CoordinateAdapter.new({"walkingHeight":0.0}),model,animations,gear)
		expect(errors.is_empty(),sex+" actual actor configured")
		if not errors.is_empty(): actor.free();continue
		actor.set_process(false);actor.set_physics_process(false);actor.rotation.y=PI;actor._advance_facing_offset(1)
		actor.animation_player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		for child: Node in actor.get_children():
			if child is Node3D and child.name!="NativeModel": (child as Node3D).hide()
		var rig:=actor.get_skeleton();var body:=actor._native_model.find_child("body",true,false) as MeshInstance3D
		var rest_hash:=rest_signature(rig);var bind_hash:=bind_signature(body.skin)
		var topology:=mesh_signature(actor,false);var retained_body:=retained_body_signature(actor);var original_body_points:=retained_body_points(actor)
		var before:=mesh_signature(actor);var field_audit:=shape_checks(actor,model,baseline)
		hair_records.append({"sex":sex,"import":check_hair_import(actor,model,baseline,sex)})
		var identity_hashes: Array=[]
		for identity: String in (["concept"] if groom_only else ["concept","soft","angular"]):
			var appearance:=baseline.duplicate();appearance.merge(IDENTITIES.get(identity,{}),true)
			actor.apply_appearance_variants(appearance)
			var shape_hash:=mesh_signature(actor);identity_hashes.append(shape_hash)
			expect(mesh_signature(actor,false)==topology,sex+" "+identity+" preserves topology, UVs and skin weights")
			var retained_delta:=body_delta(original_body_points,retained_body_points(actor))
			expect(retained_delta.protected_body_maximum_delta_m<.000001,sex+" "+identity+" leaves canonical torso/limbs exact")
			expect(retained_delta.maximum_position_delta_m<.00025,sex+" "+identity+" upper-neck field tail remains below0.25mm")
			var statistics:=face_statistics(actor)
			for action: StringName in ACTION_REVIEW:
				for phase: float in [.0,.37,.73]:
					settle(actor,action,phase)
					expect(mesh_signature(actor)==shape_hash,sex+" "+identity+" "+str(action)+" preserves rest identity")
				expect(rest_signature(rig)==rest_hash and bind_signature(body.skin)==bind_hash,sex+" action cannot change canonical rests/binds")
			var palette:=appearance.duplicate();palette.skin=(int(palette.skin)+3)%10;palette.eyes=(int(palette.eyes)+4)%12
			actor.apply_appearance_variants(palette)
			expect(mesh_signature(actor)==shape_hash,sex+" "+identity+" palette changes preserve identity")
			actor.apply_appearance_variants(appearance)
			expect(mesh_signature(actor)==shape_hash,sex+" "+identity+" repeated finish does not accumulate deformation")
			var files:=await capture_identity(actor,sex,name,identity)
			identity_records.append({"character":name,"sex":sex,"identity":identity,"appearance":appearance,"source_scene":model.scene,"source_sha256":source_hash,"rest_sha256":rest_hash,"bind_sha256":bind_hash,"position_signatures":shape_hash,"topology_uv_weight_signatures":topology,"retained_body_delta":retained_delta,"retained_body_all_arrays_exact":retained_body_signature(actor)==retained_body,"geometry":statistics,"portraits":files,"field_audit":field_audit if identity=="concept" else {}})
		if not groom_only:expect(identity_hashes[0]!=identity_hashes[1] and identity_hashes[1]!=identity_hashes[2] and identity_hashes[0]!=identity_hashes[2],sex+" three identities have distinct head/eye geometry")
		actor.apply_appearance_variants(baseline)
		expect(mesh_signature(actor)==before,sex+" switching identities returns exactly to concept baseline")
		var groom_controls:=await check_groom_controls(actor,model,baseline,sex,name)
		groom_records.append({"sex":sex,"groom_controls":groom_controls})
		if not groom_only:headwear_records.append({"sex":sex,"headwear":await check_headwear(actor,gear,baseline,sex,name)})
		expect(FileAccess.get_sha256(model.scene)==source_hash,sex+" source GLB remains unchanged")
		print("MPFB IDENTITY VALIDATION ",sex," complete")
		actor.free();await process_frame
	FileAccess.open(output.path_join("identity-validation.json"),FileAccess.WRITE).store_string(JSON.stringify({"schema":"RL reusable MPFB identity review1","assertions":assertion_count,"failures":failures,"graphics":"High","renderer":RenderingServer.get_current_rendering_method(),"capture_enabled":capture_enabled,"groom_only":groom_only,"dimensions":[800,900],"identity_parameters":"Ten compact bounded values over one reusable head per sex; no per-identity GLB copies","expression_scope":"Existing shared body/finger/cape actions contain no authored facial expressions or blink targets; this test establishes identity persistence through those existing actions, not expression/blink quality.","records":identity_records,"groom_controls":groom_records,"hair_import":hair_records,"headwear":headwear_records},"  "))
	NativeAnimationImporter.clear();GlbSceneCache.clear();PROPORTIONS.clear()
	quit(1 if failures else 0)
