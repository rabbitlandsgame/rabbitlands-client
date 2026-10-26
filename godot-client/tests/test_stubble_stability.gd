extends SceneTree
const HIGH := preload("res://src/actors/high_portrait_appearance.gd")
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	HIGH.clear()
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for sex: String in ["male", "female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		actor.apply_render_quality(1, true)
		var look := {"hair": 106, "skin": 2, "facial_hair": 0, "jaw": 65}
		var errors := actor.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0, "kind": 1,
			"name": "", "appearance": look, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
			models["luminous_" + sex], animations, equipment)
		expect(errors.is_empty(), sex + " real actor loads")
		expect(HIGH.cache_metrics().texture_bundles == 0, "Medium initial build loads no High textures")
		var native := actor.get_node("NativeModel") as Node3D
		var body := native.find_child("body", true, false) as MeshInstance3D
		var source := body.mesh
		var uv: PackedVector2Array = source.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV]
		for style: int in [1, 0, 1, 2, 1]:
			look.facial_hair = style
			actor.apply_appearance_variants(look)
			var face := body.get_active_material(0) as ShaderMaterial
			expect(face != null, "face uses the production skin material")
			expect(bool(face.get_shader_parameter("stubble_enabled")) == (style == 1), "stubble enable/disable is reversible")
			if style != 1:
				continue
			expect(native.get_node_or_null("PortraitFacialHair") == null, "stubble has no overlapping shell")
			expect(body.mesh == source, "stubble never replaces the skin mesh")
			expect((body.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV] as PackedVector2Array) == uv, "stubble follows original skin UVs")
			var texture := face.get_shader_parameter("stubble_mask") as Texture2D
			expect(texture != null and texture.get_image().has_mipmaps(), "follicles are sampled from a mip-filtered texture")
			actor.play_action(&"walk", true)
			actor.set_process(false)
			actor.set_physics_process(false)
			for frame: int in range(12):
				actor.animation_player.seek(actor.animation_player.current_animation_length * frame / 12.0, true)
				expect(body.mesh == source and face.get_shader_parameter("stubble_mask") == texture,
					"animation does not rebuild or reproject stubble")
		actor.free()
	await process_frame
	print("STUBBLE_STABILITY: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
