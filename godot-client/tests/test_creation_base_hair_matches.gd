extends SceneTree
## Named starting looks must select their reviewed style after save/load,
## appear under useful picker filters and keep compatibility family colours.
const BASES=preload("res://src/ui/creation_base_library.gd")
const MAP=preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const PC=preload("res://src/actors/portrait_customization.gd")
const AV=preload("res://src/actors/appearance_variants.gd")
const EXPECTED={
	"human_04":"shoulder_curls_male","human_05":"braided_crown_female",
	"human_09":"soft_wavy_bob_female","human_13":"loose_curly_crop_male",
	"human_16":"neat_rear_braid_male","human_18":"swept_curly_crop_male",
	"human_19":"wavy_layers_female","human_21":"rounded_wavy_bob_female",
	"human_22":"braided_crown_male","human_25":"twin_braids_female",
	"human_29":"curly_waves_female","human_31":"high_top_fade_male",
	"human_32":"low_ponytail_female","human_35":"neat_rear_braid_female",
	"human_36":"shoulder_curls_male"}
func _initialize()->void:
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var rows:=BASES.rows(registry,4)
	assert(rows.size()==41)
	for id:String in EXPECTED:
		var row:=BASES.find(rows,id);assert(not row.is_empty())
		var app:Dictionary=row.look.appearance
		assert(MAP.hair(app,row.sex)==EXPECTED[id],id+" selects its reviewed hairstyle")
		var resolved:Dictionary=MAP.HAIR_MODULE_LOOKUP.resolve(int(app.hair_module),row.sex)
		assert(int(resolved.fallback_style)==AV.hair_style(int(app.hair)),id+" keeps a compatible saved family")
		for version:int in [3,4]:
			var saved:Dictionary=PC.decode(PC.encode(app,version),0)
			saved.hair=app.hair
			assert(MAP.hair(saved,row.sex)==EXPECTED[id],id+" retains hair after protocol round trip")
	for id:String in ["human_13","human_18"]:
		var tags:Array=BASES.find(rows,id).hair_tags
		assert(tags.has("Curly") and tags.has("Short") and not tags.has("Afro"),id+" filters as short loose curls")
	assert(BASES.find(rows,"human_25").hair_tags.has("Braided"))
	assert(BASES.find(rows,"human_32").hair_tags.has("Low ponytail"))
	var bastien:=BASES.find(rows,"human_31")
	assert(int(bastien.look.appearance.facial_hair)==4 and MAP.face(bastien.look.appearance,"male").beard=="short_beard")
	assert(BASES.find(rows,"study_mira").label=="Mira")
	assert(MAP.hair(BASES.find(rows,"study_mira").look.appearance,"female")=="mira_bun")
	print("creation hair matches: 15 saved looks and picker filters, 0 failures")
	quit()
