extends SceneTree
## Reference-framed actual-engine portraits and head projection maps.
## All pose offsets are per-instance frozen portrait poses. Shared animations,
## skeleton rests, skin binds and source assets remain untouched.
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const MPFB := preload("res://src/actors/mpfb_prototype_appearance.gd")
var stage: Node3D
var camera: Camera3D
var output: String
var records: Array = []
var failures := 0
var registration: Dictionary = {}
var anchors: Dictionary = {}
var overrides: Dictionary = {}
var looks: Dictionary = {}
var pose_overrides: Dictionary = {}
var black_mask: StandardMaterial3D
var eye_mask_shader: Shader
const VIEWS := {"front":{"azimuth_degrees":0.0,"elevation_degrees":2.0},
	"side":{"azimuth_degrees":82.0,"elevation_degrees":2.0},
	"isometric":{"azimuth_degrees":-34.0,"elevation_degrees":20.0}}

func _init() -> void: run.call_deferred()

func json_file(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path): return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func vec(values: Variant, fallback := Vector3.ZERO) -> Vector3:
	return Vector3(float(values[0]),float(values[1]),float(values[2])) if values is Array and values.size()==3 else fallback

func numbers(v: Vector3) -> Array: return [v.x,v.y,v.z]

func matrix(t: Transform3D) -> Dictionary:
	return {"x":numbers(t.basis.x),"y":numbers(t.basis.y),"z":numbers(t.basis.z),"origin":numbers(t.origin)}

func expect(ok: bool, text: String) -> void:
	if not ok:
		failures += 1
		push_error(text)

func reference(name: String, kit: String, view: String) -> Dictionary:
	for item: Dictionary in registration.get("records",[]):
		if item.character==name.to_lower() and item.kit==kit and item.view==view: return item
	var pupil_y := 173.0 if name=="Mira" else 129.0
	return {"portrait_roi":[340,-30,720,398],"landmarks":{
		"eye_image_left":[494,pupil_y],"eye_image_right":[550,pupil_y],
		"eye_visible":[423 if name=="Mira" else 443,pupil_y],
		"mouth_corner_visible":[425 if name=="Mira" else 444,pupil_y+54]}}

func selected(env: String, defaults: PackedStringArray) -> PackedStringArray:
	var text := OS.get_environment(env)
	return defaults if text.is_empty() else text.split(",",false)

func current_anchors(actor: ReplicatedActor3D, sex: String, prototype: bool) -> Dictionary:
	if prototype and anchors.get("models",{}).has(sex):
		var result:Dictionary=anchors.models[sex].landmarks.duplicate(true)
		var appearance:=MPFB.shape_appearance(actor._appearance,actor._model_config)
		var shape:=CharacterProportions.face_shape(appearance)
		if not CharacterProportions.face_is_neutral(shape):
			# Identity-only study variants must project the same rest-space field
			# applied to their skin/eyes, rather than the authored neutral anchors.
			var frame:=CharacterProportions.face_frame(actor._native_model,actor.get_skeleton())
			for key:String in result:
				result[key]=numbers(CharacterProportions.face_point(vec(result[key]),frame,shape))
		return result
	var frame := CharacterProportions.face_frame(actor._native_model,actor.get_skeleton())
	var mouth := Vector3(0,frame.mouth_y,frame.eye_z+.025)
	return {"eye_image_left":numbers(frame.eye_left),"eye_image_right":numbers(frame.eye_right),
		"mouth_center":numbers(mouth),"nose_tip":numbers(Vector3(0,frame.eye_y-.033,frame.eye_z+.04)),
		"chin":numbers(mouth+Vector3(0,-.035,-.003))}

func world_point(rig: Skeleton3D, head_local: Vector3) -> Vector3:
	return rig.global_transform*(rig.get_bone_global_pose(rig.find_bone("Head"))*head_local)

func frozen_pose(rig: Skeleton3D, profile: Dictionary) -> Array:
	var before: Array = []
	for index: int in rig.get_bone_count():
		before.append([rig.get_bone_pose_position(index),rig.get_bone_pose_rotation(index),rig.get_bone_pose_scale(index)])
	for bone: String in ["neck_01","Head"]:
		var angles := vec(profile.get("neck_add_degrees" if bone=="neck_01" else "head_add_degrees",[0,0,0]))*PI/180.0
		var index := rig.find_bone(bone)
		var pose := rig.get_bone_global_pose(index)
		if bone=="Head" and bool(profile.get("neutralize_idle_head_yaw",true)):
			# The accepted idle glances about10.5deg sideways. A front/side
			# reference must not mistake that glance for the authored face shape.
			var forward:Vector3=rig.global_basis*pose.basis.z
			var yaw:=atan2(forward.x,forward.z)
			var target:=deg_to_rad(float(profile.get("head_world_yaw_degrees",0)))
			var axis:Vector3=(rig.global_basis.inverse()*Vector3.UP).normalized()
			pose.basis=Basis(Quaternion(axis,target-yaw))*pose.basis
			profile.idle_head_yaw_correction_degrees=rad_to_deg(target-yaw)
		elif angles.is_zero_approx(): continue
		pose.basis = Basis.from_euler(angles)*pose.basis
		rig.set_bone_global_pose(index,pose)
		rig.force_update_all_bone_transforms()
	return before

func restore_pose(rig: Skeleton3D, before: Array) -> void:
	for index: int in rig.get_bone_count():
		rig.set_bone_pose_position(index,before[index][0])
		rig.set_bone_pose_rotation(index,before[index][1])
		rig.set_bone_pose_scale(index,before[index][2])
	rig.force_update_all_bone_transforms()

func camera_frame(rig: Skeleton3D, points: Dictionary, ref: Dictionary, profile: Dictionary, view: String) -> Dictionary:
	var roi: Array = ref.portrait_roi
	var source: Dictionary = ref.landmarks
	var keys := ["eye_image_left","eye_image_right"] if view!="side" else ["eye_visible","mouth_corner_visible"]
	var model_keys := ["eye_image_left","eye_image_right"] if view!="side" else ["eye_image_right","mouth_center"]
	var a := world_point(rig,vec(points[model_keys[0]]));var b := world_point(rig,vec(points[model_keys[1]]))
	var target_a := Vector2(float(source[keys[0]][0])-float(roi[0]),float(source[keys[0]][1])-float(roi[1]))
	var target_b := Vector2(float(source[keys[1]][0])-float(roi[0]),float(source[keys[1]][1])-float(roi[1]))
	target_a *= Vector2(root.size)/Vector2(float(roi[2])-float(roi[0]),float(roi[3])-float(roi[1]))
	target_b *= Vector2(root.size)/Vector2(float(roi[2])-float(roi[0]),float(roi[3])-float(roi[1]))
	var yaw := deg_to_rad(float(profile.get("azimuth_degrees",0)))
	var elevation := deg_to_rad(float(profile.get("elevation_degrees",0)))
	var direction := Vector3(sin(yaw)*cos(elevation),sin(elevation),cos(yaw)*cos(elevation))
	var eye := (a+b)*.5 if view!="side" else a
	var target := (target_a+target_b)*.5 if view!="side" else target_a
	camera.fov = float(profile.get("fov_degrees",18))
	camera.position = eye+direction
	camera.look_at(eye)
	var right := camera.global_basis.x;var up := camera.global_basis.y
	var delta := a-b
	var projected_span := Vector2(delta.dot(right),delta.dot(up)).length()
	var distance := clampf(projected_span*root.size.y/(2*target_a.distance_to(target_b)*tan(deg_to_rad(camera.fov)*.5)),.5,4)
	var focus := eye
	for iteration: int in 4:
		var height := 2*distance*tan(deg_to_rad(camera.fov)*.5)
		var width := height*float(root.size.x)/float(root.size.y)
		focus = eye-right*(target.x/root.size.x-.5)*width+up*(target.y/root.size.y-.5)*height
		camera.position = focus+direction*distance;camera.look_at(focus)
		var current_span := camera.unproject_position(a).distance_to(camera.unproject_position(b))
		distance *= current_span/target_a.distance_to(target_b)
	return {"projection":"perspective","fov_degrees":camera.fov,"transform":matrix(camera.global_transform),
		"distance_m":distance,"focus":numbers(focus),"reference_roi":roi,
		"scale_anchors":keys,"reference_anchor_pixels":[[target_a.x,target_a.y],[target_b.x,target_b.y]]}

func signature(animation: Animation) -> String:
	var values: Array = [animation.length,animation.loop_mode]
	for track: int in animation.get_track_count():
		var row: Array = [animation.track_get_path(track),animation.track_get_type(track)]
		for key: int in animation.track_get_key_count(track): row.append([animation.track_get_key_time(track,key),animation.track_get_key_value(track,key)])
		values.append(row)
	return var_to_bytes(values).hex_encode().sha256_text()

func rest_signature(rig: Skeleton3D) -> String:
	var values:Array=[]
	for bone:int in rig.get_bone_count(): values.append([rig.get_bone_name(bone),rig.get_bone_parent(bone),rig.get_bone_rest(bone)])
	return var_to_bytes(values).hex_encode().sha256_text()

func bind_signature(skin: Skin) -> String:
	var values:Array=[]
	for bind:int in skin.get_bind_count(): values.append([skin.get_bind_name(bind),skin.get_bind_bone(bind),skin.get_bind_pose(bind)])
	return var_to_bytes(values).hex_encode().sha256_text()

func fit_portrait_roll(rig: Skeleton3D, points: Dictionary, ref: Dictionary, profile: Dictionary, view: String) -> Dictionary:
	var framing:=camera_frame(rig,points,ref,profile,view)
	var total:=0.0
	if view!="side" and bool(profile.get("fit_eye_line_roll",true)):
		for _iteration:int in 2:
			var desired: Array=framing.reference_anchor_pixels
			var target:=(Vector2(desired[1][0],desired[1][1])-Vector2(desired[0][0],desired[0][1])).angle()
			var left:=camera.unproject_position(world_point(rig,vec(points.eye_image_left)))
			var right:=camera.unproject_position(world_point(rig,vec(points.eye_image_right)))
			var correction:=wrapf(target-(right-left).angle(),-PI,PI)
			var axis:=(rig.global_basis.inverse()*camera.global_basis.z).normalized()
			var bone:=rig.find_bone("Head");var pose:=rig.get_bone_global_pose(bone)
			pose.basis=Basis(Quaternion(axis,-correction))*pose.basis
			rig.set_bone_global_pose(bone,pose);rig.force_update_all_bone_transforms()
			total-=rad_to_deg(correction)
			framing=camera_frame(rig,points,ref,profile,view)
	framing.portrait_only_view_axis_roll_degrees=total
	return framing

func projection_map(actor: ReplicatedActor3D, filename: String, ref: Dictionary) -> Dictionary:
	var rig := actor.get_skeleton()
	var mesh := actor._native_model.find_child("body",true,false) as MeshInstance3D
	var arrays := mesh.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var binds: Array[Transform3D] = []
	for bind: int in mesh.skin.get_bind_count():
		var bone := rig.find_bone(mesh.skin.get_bind_name(bind)) if mesh.skin.get_bind_name(bind)!=&"" else mesh.skin.get_bind_bone(bind)
		binds.append(rig.get_bone_global_pose(bone)*mesh.skin.get_bind_pose(bind))
	var width := weights.size()/vertices.size()
	var positions: Array = [];var directions: Array = [];var pixels: Array = [];var coordinates: Array = []
	var roi: Array = ref.portrait_roi
	for index: int in vertices.size():
		var point := Vector3.ZERO;var normal := Vector3.ZERO
		for slot: int in width:
			var offset := index*width+slot
			if weights[offset]<=0: continue
			var transform := binds[joints[offset]]
			point += (transform*vertices[index])*weights[offset]
			normal += (transform.basis.inverse().transposed()*normals[index])*weights[offset]
		point = rig.global_transform*point
		normal = (rig.global_basis.inverse().transposed()*normal).normalized()
		var pixel := camera.unproject_position(point)
		positions.append(numbers(point));directions.append(numbers(normal));coordinates.append([uv[index].x,uv[index].y])
		pixels.append([float(roi[0])+pixel.x/root.size.x*(float(roi[2])-float(roi[0])),float(roi[1])+pixel.y/root.size.y*(float(roi[3])-float(roi[1]))])
	var data := {"vertex_positions_world":positions,"vertex_normals_world":directions,"vertex_uv":coordinates,
		"projected_source_pixels":pixels,"triangle_indices":Array(indices),"source_image":ref.get("path",""),
		"source_sha256":ref.get("sha256",""),"uv_convention":"glTF; image y=v",
		"skinning":"Skeleton world * sum(global bone pose * bind * vertex * weight)","camera":matrix(camera.global_transform)}
	FileAccess.open(output.path_join(filename+"-projection.json"),FileAccess.WRITE).store_string(JSON.stringify(data))
	return {"file":filename+"-projection.json","vertices":vertices.size(),"triangles":indices.size()/3}

func eye_visibility_mask(actor: ReplicatedActor3D, filename: String) -> String:
	if black_mask==null:
		black_mask=StandardMaterial3D.new();black_mask.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED;black_mask.albedo_color=Color.BLACK
		eye_mask_shader=Shader.new()
		eye_mask_shader.code="shader_type spatial; render_mode unshaded; uniform sampler2D mask_texture; void fragment(){if(texture(mask_texture,UV).a<0.5){discard;} ALBEDO=vec3(1.0);}"
	var originals:Dictionary={}
	for item:Node in actor._native_model.find_children("*","MeshInstance3D",true,false):
		var mesh:=item as MeshInstance3D
		originals[mesh]=mesh.material_override
		if mesh.name=="eyes":
			var material:=ShaderMaterial.new();material.shader=eye_mask_shader
			var source:=mesh.get_active_material(0)
			material.set_shader_parameter("mask_texture",source.get_shader_parameter("base_texture") if source is ShaderMaterial else (source as StandardMaterial3D).albedo_texture)
			mesh.material_override=material
		else: mesh.material_override=black_mask
	for _frame:int in 3: await process_frame
	await RenderingServer.frame_post_draw
	var path:=filename+"-eye-mask.png"
	expect(root.get_texture().get_image().save_png(output.path_join(path))==OK,"eye mask saved")
	for mesh:MeshInstance3D in originals: mesh.material_override=originals[mesh]
	return path

func hair_projection_map(actor: ReplicatedActor3D, filename: String, ref: Dictionary) -> Dictionary:
	var parts:Array=[]
	var roi:Array=ref.portrait_roi
	for item:Node in actor._native_model.find_children("*","MeshInstance3D",true,false):
		var mesh:=item as MeshInstance3D
		if not mesh.has_meta("rl_concept_hair") or mesh.mesh==null: continue
		for surface:int in mesh.mesh.get_surface_count():
			var arrays:=mesh.mesh.surface_get_arrays(surface)
			var vertices:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
			var normals:PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
			var colors:PackedColorArray=arrays[Mesh.ARRAY_COLOR]
			var uv:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV]
			var material:=mesh.get_active_material(surface) as ShaderMaterial
			var length:=float(material.get_shader_parameter("hair_length_delta")) if material!=null else 0.0
			var volume:=float(material.get_shader_parameter("hair_volume_delta")) if material!=null else 0.0
			var positions:Array=[];var directions:Array=[];var pixels:Array=[];var coordinates:Array=[]
			for index:int in vertices.size():
				var point:=vertices[index]
				var pin:float=colors[index].a if not colors.is_empty() else 0.0
				point.x*=1.0+.13*volume*pin;point.z*=1.0+.13*volume*pin
				point.y+=.018*length*pin*signf(point.y-.11)
				point=mesh.global_transform*point
				var normal:Vector3=(mesh.global_basis.inverse().transposed()*normals[index]).normalized()
				var pixel:=camera.unproject_position(point)
				positions.append(numbers(point));directions.append(numbers(normal));coordinates.append([uv[index].x,uv[index].y])
				pixels.append([float(roi[0])+pixel.x/root.size.x*(float(roi[2])-float(roi[0])),float(roi[1])+pixel.y/root.size.y*(float(roi[3])-float(roi[1]))])
			parts.append({"node":str(actor._native_model.get_path_to(mesh)),"surface":surface,"transform":matrix(mesh.global_transform),
				"vertex_positions_world":positions,"vertex_normals_world":directions,"vertex_uv":coordinates,
				"projected_source_pixels":pixels,"triangle_indices":Array(arrays[Mesh.ARRAY_INDEX]),"hair_length_delta":length,"hair_volume_delta":volume})
	var file:=filename+"-hair-projection.json"
	FileAccess.open(output.path_join(file),FileAccess.WRITE).store_string(JSON.stringify({"parts":parts,"reference":ref.get("path",""),"camera":matrix(camera.global_transform),
		"vertex_note":"World positions include current Head attachment and concept-hair length/volume shader displacement; normal deformation is exact at the reference presets where both deltas are zero."}))
	return {"file":file,"parts":parts.size()}

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	output = OS.get_environment("RL_MPFB_PORTRAIT_OUTPUT")
	if output.is_empty(): output=ProjectSettings.globalize_path("res://test-artifacts/mpfb-concept-portraits")
	DirAccess.make_dir_recursive_absolute(output)
	registration=json_file(OS.get_environment("RL_MPFB_REFERENCE_REGISTRATION"))
	anchors=json_file(OS.get_environment("RL_MPFB_LANDMARKS"))
	overrides=json_file(OS.get_environment("RL_MPFB_PORTRAIT_MODEL_OVERRIDES"))
	looks=json_file(OS.get_environment("RL_MPFB_PORTRAIT_LOOKS"))
	pose_overrides=json_file(OS.get_environment("RL_MPFB_PORTRAIT_POSE_OVERRIDES"))
	# Projection coordinates must be capture pixels, not the application's
	# stretched UI canvas (which can otherwise be1280x1440 in an800x900 window).
	root.content_scale_mode=Window.CONTENT_SCALE_MODE_DISABLED
	root.size=Vector2i(800,900);root.msaa_3d=Viewport.MSAA_2X
	stage=Node3D.new();root.add_child(stage)
	var environment:=WorldEnvironment.new();environment.environment=Environment.new()
	environment.environment.background_mode=Environment.BG_COLOR
	environment.environment.background_color=Color("d3d1cb")
	environment.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color=Color("e9e3d8")
	environment.environment.ambient_light_energy=.40
	stage.add_child(environment)
	var key:=DirectionalLight3D.new();key.rotation_degrees=Vector3(-28,-32,0);key.light_color=Color("fff1dc");key.light_energy=.85
	key.shadow_enabled=OS.get_environment("RL_MPFB_PORTRAIT_SHADOWS")=="1";key.light_angular_distance=0;key.directional_shadow_max_distance=5
	key.shadow_bias=.20;key.shadow_normal_bias=4.0
	stage.add_child(key)
	var fill:=DirectionalLight3D.new();fill.rotation_degrees=Vector3(-10,125,0);fill.light_color=Color("e1e8ef");fill.light_energy=.15;stage.add_child(fill)
	camera=Camera3D.new();camera.projection=Camera3D.PROJECTION_PERSPECTIVE;camera.near=.02;camera.far=20;camera.current=true;camera.cull_mask=3;stage.add_child(camera)
	var models:Dictionary=json_file("res://data/actors/models.json").models
	var gear:=json_file("res://data/actors/equipment.json");var animations:=json_file("res://data/animations/luminous.json")
	var prototype_root:=OS.get_environment("RL_MPFB_PROTOTYPE_ROOT")
	for name:String in selected("RL_MPFB_PORTRAIT_CHARACTERS",PackedStringArray(["Rowan","Mira"])):
		var sex:="female" if name=="Mira" else "male"
		for kit:String in selected("RL_MPFB_PORTRAIT_KITS",PackedStringArray(["equipped"])):
			var actor:=ReplicatedActor3D.new();actor.apply_render_quality(2,true);stage.add_child(actor)
			var model:Dictionary=models["luminous_"+sex].duplicate(true)
			if not prototype_root.is_empty():
				model.scene=prototype_root.path_join(sex+"/luminous_"+sex+".glb");model.geometryProfile="mpfb"
				model.erase("faceAppearance");model.erase("skinPalette")
				var metadata:=json_file(prototype_root.path_join(sex+"/fit.json"))
				model.mpfbFaceFrame=metadata.get("face_frame_head_local",{})
				MPFB.configure_art(model,metadata,prototype_root.path_join(sex))
			model.merge(overrides.get(sex,{}),true)
			var appearance:=PRESETS.appearance(name).merged({"shirt":5,"pants":2,"boots":2});appearance.merge(looks.get(name,{}),true)
			var style:=str(AppearanceVariants.hair_style(int(appearance.get("hair",0))))
			var hair_scene:=str(model.get("hairStyleOverrides",{}).get(style,{}).get("scene",""))
			var hair_hash:=FileAccess.get_sha256(hair_scene) if FileAccess.file_exists(hair_scene) else ""
			var loadout:Dictionary=({5:225,2:100} if sex=="female" else {5:209,2:105}) if kit=="equipped" else {}
			var errors:=actor.configure({"actor_id":9931,"kind":1,"name":"","x":0,"y":0,"rotation":0,"appearance":appearance,"equipment_visuals":loadout},CoordinateAdapter.new({"walkingHeight":0.0}),model,animations,gear)
			expect(errors.is_empty(),str(errors))
			if not errors.is_empty(): actor.free();continue
			actor.set_process(false);actor.set_physics_process(false);actor.rotation.y=PI;actor._advance_facing_offset(1)
			for child:Node in actor.get_children():
				if child is Node3D and child.name!="NativeModel": (child as Node3D).hide()
			actor.play_action(&"idle",true);actor.animation_player.seek(.4,true);actor.animation_player.pause()
			var rig:=actor.get_skeleton();rig.force_update_all_bone_transforms()
			var points:=current_anchors(actor,sex,not prototype_root.is_empty())
			var animation:=actor.animation_player.get_animation(actor.resolver.clip_for_action(&"idle"))
			expect(animation!=null,"accepted idle clip exists")
			var clip_hash:=signature(animation)
			var rest_hash:=rest_signature(rig)
			var body:=actor._native_model.find_child("body",true,false) as MeshInstance3D
			var bind_hash:=bind_signature(body.skin)
			var source_hash:=FileAccess.get_sha256(model.scene)
			for view:String in selected("RL_MPFB_PORTRAIT_VIEWS",PackedStringArray(["front","side","isometric"])):
				var ref:=reference(name,kit,view)
				var profile:Dictionary=VIEWS[view].duplicate(true);profile.merge(ref.get("camera_initial",{}),true)
				profile.merge(pose_overrides.get(name,{}).get(view,{}),true)
				var previous:=frozen_pose(rig,profile)
				var framing:=fit_portrait_roll(rig,points,ref,profile,view)
				var projected:Dictionary={}
				for point_name:String in points:
					var pixel:=camera.unproject_position(world_point(rig,vec(points[point_name])))
					projected[point_name]=[pixel.x,pixel.y]
				var filename:=name.to_lower()+"-"+kit+"-"+view
				for _frame:int in 6: await process_frame
				await RenderingServer.frame_post_draw
				var captured:=root.get_texture().get_image()
				expect(captured.get_size()==Vector2i(800,900) and root.get_visible_rect().size.is_equal_approx(Vector2(800,900)),"projection coordinates equal capture pixels")
				expect(captured.save_png(output.path_join(filename+".png"))==OK,"portrait saved")
				var bake:Dictionary={}
				var hair_bake:Dictionary={}
				if OS.get_environment("RL_MPFB_NO_PROJECTION_MAP")!="1":
					bake=projection_map(actor,filename,ref)
					hair_bake=hair_projection_map(actor,filename,ref)
				var eye_mask:=""
				if OS.get_environment("RL_MPFB_PORTRAIT_EYE_MASK")=="1": eye_mask=await eye_visibility_mask(actor,filename)
				records.append({"character":name,"sex":sex,"kit":kit,"view":view,"file":filename+".png","camera":framing,"pose":profile,
					"landmarks_capture_pixels":projected,"projection_map":bake,"hair_projection_map":hair_bake,"eye_mask":eye_mask,"reference":ref,"model_scene":model.scene,
					"model_sha256":source_hash,"hair_scene":hair_scene,"hair_sha256":hair_hash,"appearance":appearance,"equipment":loadout,"idle_clip_sha256":clip_hash,"rest_sha256":rest_hash,"skin_bind_sha256":bind_hash,
					"head_global_pose":matrix(rig.get_bone_global_pose(rig.find_bone("Head"))),"skeleton_global":matrix(rig.global_transform)})
				restore_pose(rig,previous)
				expect(signature(animation)==clip_hash,"portrait offsets do not modify animation resources")
				expect(rest_signature(rig)==rest_hash and bind_signature(body.skin)==bind_hash,"portrait offsets do not change rests or skin binds")
				expect(FileAccess.get_sha256(model.scene)==source_hash,"source asset unchanged during capture")
				if not hair_hash.is_empty(): expect(FileAccess.get_sha256(hair_scene)==hair_hash,"hair asset unchanged during capture")
			print("MPFB MATCHED PORTRAITS ",name," ",kit)
			actor.free();await process_frame
	FileAccess.open(output.path_join("manifest.json"),FileAccess.WRITE).store_string(JSON.stringify({"graphics":"High","renderer":RenderingServer.get_current_rendering_method(),
		"dimensions":[800,900],"pose_policy":"accepted idle frozen at0.4s, optional portrait-only additive Head/neck rotations; no source animation changes",
		"lighting":{"policy":"fixed studio key/fill/ambient; identical across views, no retouching","cast_shadows":key.shadow_enabled,
			"shadow_bias":key.shadow_bias,"shadow_normal_bias":key.shadow_normal_bias,"light_angular_distance":key.light_angular_distance,
			"key_energy":key.light_energy,"fill_energy":fill.light_energy,"ambient_energy":environment.environment.ambient_light_energy},
		"registration":"manual source landmarks with uncertainty; actual game render, no retouching",
		"failures":failures,"portraits":records},"  "))
	NativeAnimationImporter.clear();GlbSceneCache.clear()
	quit(1 if failures else 0)
