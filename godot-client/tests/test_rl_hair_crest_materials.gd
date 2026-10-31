extends SceneTree
## Concrete crest names share only clump semantics; textures and caches differ.
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
const Quality := ActorRenderQuality.Quality
const CRESTS := ["rl_hair_clump_crest", "rl_hair_clump_crest_lod1", "rl_hair_clump_crest_lod2"]
var checks := 0
var failures := 0

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func _initialize() -> void:
	for mode: int in [0, 1]:
		Library.clear();Library._values_switch = mode
		var style := "fixture_crest_material_roles"
		var materials: Array=[]
		var textures: Dictionary={}
		var names: Array=["rl_hair_clump", "rl_hair_card"] + CRESTS
		for index: int in names.size():
			var name: String=names[index]
			var file := "fixture_crest_texture_%d.png" % index
			var image := Image.create(2,2,false,Image.FORMAT_RGBA8)
			image.fill(Color(float(index+1)/6.0, .25, .5, 1))
			var texture := ImageTexture.create_from_image(image)
			textures[name]=texture;Library._textures[Library.TEXTURE_DIR+file]=texture
			materials.append({"name":name,"extras":{"texture":file,"softHairline":true,
				"softRootCoverage":name in CRESTS,"paintFlatness":float(index)/10.0,"uvStrandHighlights":false}})
		Library._documents[Library.hair_path(style)]={"materials":materials}
		for quality: int in [Quality.LOW,Quality.MEDIUM,Quality.HIGH]:
			var cap := Library.material("rl_hair_clump","female",style,quality)
			var card := Library.material("rl_hair_card","female",style,quality)
			check(cap.get_shader_parameter("strand_texture")==textures.rl_hair_clump,"old cap texture is retained")
			check(not bool(cap.get_shader_parameter("card")) and is_equal_approx(float(cap.get_shader_parameter("alpha_scissor")),.5),"old clump semantics retained")
			check(bool(card.get_shader_parameter("card")) and is_equal_approx(float(card.get_shader_parameter("alpha_scissor")),.35),"old card semantics retained")
			var previous: ShaderMaterial=cap
			for name: String in CRESTS:
				var material := Library.material(name,"female",style,quality)
				check(material!=null and material!=cap and material!=previous,"concrete material caches remain independent")
				check(material==Library.material(name,"female",style,quality),"same concrete key reuses its material")
				check(material.resource_name==name and Library.material_role(name)=="rl_hair_clump","concrete name retained, explicit clump role")
				check(material.get_shader_parameter("strand_texture")==textures[name],"each crest loads its declared texture")
				check(not bool(material.get_shader_parameter("card")) and is_equal_approx(float(material.get_shader_parameter("alpha_scissor")),.5),"crest uses clump0.5 gate")
				check(bool(material.get_shader_parameter("soft_root_coverage")) and bool(material.get_shader_parameter("soft_hairline")),"crest forwards root coverage")
				check(material.shader.code.begins_with("#define RL_SOFT_ROOTS\n"),"crest selects alpha-to-coverage")
				check(Library.shader_values(material).has("hair_detail") and Library.shader_values(material).has("eye_color"),"crest retains detail and age carrier in both value modes")
				var copy := Library.face_material(material,{"hair_detail":.75,"hair_color":Color(.2,.1,.05,1),"eye_color":Color(.2,.3,.4,1)})
				check(copy.get_shader_parameter("strand_texture")==textures[name],"per-face values preserve concrete texture")
				previous=material
		check(Library.material("rl_hair_clump_crest_extra","female",style,Quality.HIGH)==null,"unknown suffix keeps imported material")
	Library.clear();Library._values_switch=-1
	print("RL crest material roles: %d checks, %d failures" % [checks,failures])
	quit(1 if failures else 0)
