extends SceneTree
## Focused P3 hard-mask and generated-arrival source binding fixtures.
const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const GROUND := preload("res://src/dev/map_authoring_region/ground_region_control.gd")
const GAMEPLAY := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const MATERIAL := preload("res://src/dev/map_authoring_pilot/style/ground_region_material.gd")
var failures := 0
var fixture_root := ""
var payload: Dictionary = {}
var storage: Dictionary = {}
var reference: Dictionary = {}
var region: Node3D
var snapshot

func _init() -> void: call_deferred("_run")

func _write(relative: String, value: String) -> String:
	var path := fixture_root.path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
	file.close()
	return path

func _save_payload() -> void:
	var path := _write(reference.path, JSON.stringify(payload))
	reference.sha256 = FileAccess.get_sha256(path)

func _resolve(spawns: Array = []) -> Dictionary:
	snapshot.errors.clear()
	return snapshot._generated_arrival_record(region, storage, {"checkout": fixture_root}, {"spawnPoints": spawns})

func _expect(condition: bool, message: String) -> void:
	if condition: print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	snapshot = SNAPSHOT.new()
	fixture_root = ProjectSettings.globalize_path("user://ground-arrival-fixture")
	region = REGION.new()
	region.region_id = "fixture"
	region.continent_translation = Vector3(100, 0, 200)
	root.add_child(region)
	var geography := {"translation": [100.0, 0.0, 200.0], "ownershipPolygons": [
		[[98.0,198.0],[102.0,198.0],[102.0,202.0],[98.0,202.0]],
		[[104.0,198.0],[108.0,198.0],[108.0,202.0],[104.0,202.0]]]}
	region.ownership_polygon_sha256 = GEOMETRY.hash(GEOMETRY.from_geography(geography))
	_write("eloria-assets/maps/continent-v2/fixture/world.json",JSON.stringify({"continentGeography":geography}))
	var partition := _write("eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json", "{\"sections\":[]}")
	reference = {"path":"eloria-assets/maps/continent-v2/fixture/content/arrival.json", "sha256":""}
	storage = {"server":{"origin":[5,5],"cells":[12,12]}, "source":{"document":{"gameplay":{"generatedArrival":reference}}}}
	payload = {"schema":"eloria-continent-v2-generated-arrival-v1", "map":"fixture", "id":"generated-arrival-fixture",
		"position":[0.5,2.0,-0.5],"serverTile":[5,5],"facing":[0,0,-1],"default":true,"generated":true,
		"frame":{"origin":[5.0,5.0],"cells":[12.0,12.0],"translation":[100,0,200]},
		"provenance":{"algorithm":"nearest-owned-safe-baseline-tile-v1", "clientBaseCommit":"a".repeat(40),
			"sectionsSpecSha256":FileAccess.get_sha256(partition),"frameSha256":"a".repeat(64),
			"sourceMap":"sw_isle","sourceTile":[10,20],"sourceWorldSha256":"a".repeat(64),
			"sourceCollisionSha256":"a".repeat(64),"sourceServedGridSha256":"a".repeat(64)}}
	_save_payload()
	var valid := _resolve()
	_expect(not valid.is_empty() and snapshot.errors.is_empty() and valid.binding == reference,
		"finite source metadata binds by raw bytes while numeric integer/float frames agree")
	var ground_doc := {"regionId":"fixture","authority":{"gameplay":true},"gameplay":{"spawnPoints":[]},
		"terrain":{"width":2,"height":2,"previewUvMetresInverse":0.17},"waterRegions":[],
		"seams":{"ownershipPolygonSha256":region.ownership_polygon_sha256},"generatedArrival":valid.payload}
	snapshot._validate_document(region,ground_doc)
	_expect(snapshot.errors.is_empty(),"validated generated arrival permits authoritative empty authored spawns")
	var expected_hash: String = reference.sha256
	reference.sha256 = "0".repeat(64)
	_expect(_resolve().is_empty() and not snapshot.errors.is_empty(),"stale raw source binding is rejected")
	reference.sha256 = expected_hash
	_expect(_resolve([{"default":true}]).is_empty(),"authored and generated defaults cannot mix")
	var good := payload.duplicate(true)
	payload.frame.origin[0] = 6
	_save_payload()
	_expect(_resolve().is_empty(),"changed arrival frame is rejected")
	payload = good.duplicate(true)
	payload.position = [3.0,2.0,-0.5]
	payload.serverTile = [8,5]
	_save_payload()
	_expect(_resolve().is_empty(),"gap between detached ownership rings stays outside")
	payload.position = [4.5,2.0,-0.5]
	payload.serverTile = [9,5]
	_save_payload()
	_expect(not _resolve().is_empty(),"second detached ownership ring is accepted")
	payload.serverTile = [8,5]
	_save_payload()
	_expect(_resolve().is_empty(),"arrival tile must match its local position")
	payload = good.duplicate(true)
	payload.provenance.sectionsSpecSha256 = "0".repeat(64)
	_save_payload()
	_expect(_resolve().is_empty(),"changed partition source hash is rejected")
	var correct_path: String = reference.path
	reference.path = "../escape.json"
	_expect(_resolve().is_empty(),"source path escape is rejected")
	reference.path = correct_path
	var surface := MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.SOIL)
	var mask := PackedVector2Array([Vector2(-2,-1),Vector2(2,-1),Vector2(2,1),Vector2(-2,1)])
	var material := MATERIAL.create(surface,Transform2D.IDENTITY,Vector2(4,3),0,1.25,0.65,2,mask)
	_expect(material != null and material.get_shader_parameter("region_clip_count") == 4 and
		is_equal_approx(float(material.get_shader_parameter("region_blend_width")),1.25) and
		is_equal_approx(float(material.get_shader_parameter("region_opacity")),0.65),
		"hard mask uniforms preserve original ellipse blend and opacity")
	_expect(not MapAuthoringGroundRegion.clip_error(PackedVector2Array([
		Vector2(0,0),Vector2(2,2),Vector2(0,2),Vector2(2,0)])).is_empty(),
		"self-intersecting clip rings are rejected")
	var ground_parent := Node3D.new()
	ground_parent.name = "Ground"
	region.add_child(ground_parent)
	var regions := Node3D.new()
	regions.name = "Regions"
	ground_parent.add_child(regions)
	var paint := GROUND.new()
	paint.region_id = "paint"
	paint.enabled = true
	paint.shape = 1
	paint.surface = surface
	paint.clip_polygon = PackedVector2Array([Vector2(0,0),Vector2(0.4,0),Vector2(0.4,2),Vector2(0,2)])
	paint.uv_anchor_continent_enabled = true
	paint.uv_anchor_continent = Vector2(80,180)
	paint.source_layer_ordinal = 4
	regions.add_child(paint)
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2.ZERO
	terrain.grid_size = Vector2i(2,2)
	terrain.set("_effective_heights",PackedFloat32Array([0,0,0,0]))
	terrain.set("_clip_mask",PackedByteArray([0]))
	region.add_child(terrain)
	terrain._build_ground_region_previews()
	var mesh_instance := terrain.get_node_or_null("__GroundRegionPreviews/GroundRegion_paint") as MeshInstance3D
	_expect(mesh_instance != null,"hard ground mask preserves fragments in cells whose centre is outside ownership")
	if mesh_instance != null:
		var arrays := mesh_instance.mesh.surface_get_arrays(0)
		var coordinates: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		_expect(coordinates[0].is_equal_approx(Vector2(20,20)*terrain.preview_uv_metres_inverse),
			"editor ground UV phase retains the source continent anchor")
		_expect(mesh_instance.material_override.render_priority == -124,
			"source layer ordinal preserves editor overlay ordering")
	snapshot.errors.clear()
	var ground_records: Array[Dictionary] = snapshot._ground_region_records(region)
	_expect(ground_records.size() == 1 and ground_records[0].clipPolygon.size() == 4 and
		ground_records[0].uvAnchorContinent == [80.0,180.0] and ground_records[0].sourceLayerOrdinal == 4,
		"snapshot preserves optional local mask, UV anchor and original layer ordinal")
	var gameplay_root := Node3D.new()
	gameplay_root.name = "Gameplay"
	region.add_child(gameplay_root)
	var nested := Node3D.new()
	nested.name = "RuntimePoints"
	gameplay_root.add_child(nested)
	var standalone := Node3D.new()
	standalone.name = "RuntimePoints"
	region.add_child(standalone)
	for location in [nested, standalone]:
		var hub := GAMEPLAY.new()
		hub.record_id = "nested-hub" if location == nested else "standalone-hub"
		hub.kind = "runtime_point"
		hub.position = Vector3(0.5, 2, -0.5)
		location.add_child(hub)
	snapshot.errors.clear()
	var gameplay_records: Dictionary = snapshot._gameplay_records(region)
	_expect(gameplay_records.runtimePoints.size() == 2 and gameplay_records.runtimePoints[0].id == "nested-hub" and gameplay_records.runtimePoints[1].id == "standalone-hub" and snapshot.errors.is_empty(),
		"snapshot retains nested and top-level dedicated runtime controls exactly once")
	region.queue_free()
	print("P3 ground/arrival framework: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
