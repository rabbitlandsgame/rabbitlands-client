extends SceneTree
## Baked images match stable IDs and exact protocol looks; no live fallback.
const Portraits := preload("res://src/ui/creation_base_portraits.gd")
const Library := preload("res://src/ui/creation_base_library.gd")
var checks := 0
var failures := 0
const FIXTURE_PATH := "user://creation_base_portraits_test.json"

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func _initialize() -> void:
	var first := {"actor_type": 1, "appearance": {"hair": 1, "skin": 2}, "equipment_visuals": {}}
	var reordered := {"equipment_visuals": {}, "appearance": {"skin": 2, "hair": 1}, "actor_type": 1}
	var older := first.duplicate(true)
	older.appearance["hair"] = 2
	var stale := first.duplicate(true)
	stale.appearance["skin"] = 3
	check(Portraits.look_hash(first) == Portraits.look_hash(reordered), "Look fingerprint sorts nested keys")
	var primary := "res://assets/branding/rabbitlands-logo.png"
	var variant := "res://assets/actors/native/rl_head_textures/hair_clump.png"
	var manifest := {"schema_version": 1, "portraits": {
		"known": {"texture": primary, "look_sha256": Portraits.look_hash(first), "variants": [
			{"texture": variant, "look_sha256": Portraits.look_hash(older), "protocol_version": 2}]},
		"missing": {"texture": "res://assets/ui/creation_base_portraits/not_baked.png", "look_sha256": Portraits.look_hash(first)},
		"scene": {"texture": "res://src/app/main.tscn", "look_sha256": Portraits.look_hash(first)},
	}}
	var file := FileAccess.open(FIXTURE_PATH, FileAccess.WRITE)
	file.store_string(JSON.stringify(manifest))
	file.close()
	var portraits := Portraits.new()
	portraits.configure(FIXTURE_PATH)
	check(portraits.texture_path("known", first) == primary, "Primary image matches the current look")
	check(portraits.texture_path("known", older) == variant, "Protocol variant matches its own look")
	check(portraits.texture_path("known", stale).is_empty(), "Stale look gets a placeholder")
	check(portraits.texture_path("unknown", first).is_empty(), "Missing ID gets a placeholder")
	check(portraits.texture_path("scene", first).is_empty(), "A scene cannot be a portrait resource")
	var image := portraits.texture("known", first)
	check(image != null and not image is ViewportTexture, "Baked image is a static texture")
	check(portraits.texture("known", first) == image, "Repeated use shares the static texture")
	check(portraits.texture("known", older) != null, "Older protocol loads its static variant")
	check(portraits.texture("missing", first) == null, "Absent file never triggers runtime rendering")
	check(portraits.texture("known", stale) == null, "Mismatched appearance never triggers runtime rendering")
	portraits.configure("user://no_creation_portrait_manifest.json")
	check(portraits.texture("known", first) == null, "Missing manifest is a static placeholder")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(FIXTURE_PATH))
	_check_catalog()
	print("Creation static portraits: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _check_catalog() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(Portraits.MANIFEST_PATH)) \
		if FileAccess.file_exists(Portraits.MANIFEST_PATH) else null
	check(manifest is Dictionary and manifest.get("portraits") is Dictionary, "Current catalog has an offline portrait manifest")
	if manifest is not Dictionary or manifest.get("portraits") is not Dictionary:
		return
	check((manifest.portraits as Dictionary).size() == 25, "All 25 starting looks have portrait entries")
	var portraits := Portraits.new()
	portraits.configure()
	var textures := {}
	for protocol: int in [0, 1, 2, 3]:
		var rows := Library.rows(registry, protocol)
		check(rows.size() == 25, "All 25 looks remain available on PC/%d" % protocol)
		for row: Dictionary in rows:
			var path := portraits.texture_path(str(row.portrait_id), row.look)
			check(not path.is_empty(), "%s PC/%d matches its exact baked look" % [row.id, protocol])
			var image := portraits.texture(str(row.portrait_id), row.look)
			check(image != null and not image is ViewportTexture, "%s PC/%d loads only a static image" % [row.id, protocol])
			if image != null:
				check(image.get_size() == Vector2(512, 512), "Portrait retains the authored 512px size")
				textures[path] = true
	check(textures.size() == int(manifest.get("portrait_count", 0)), "Manifest accounts for every distinct portrait asset")
