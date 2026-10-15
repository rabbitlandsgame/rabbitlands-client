# Verify a region package through the real client path, in-engine.
#
# `verify_runtime.py` reproduces the grounding contract offline, in Python,
# from the GLB. This does the same thing the other way round: it loads the
# package with the project's own WorldLoader, lets it build collision and
# navigation exactly as the game does, and casts main.gd's grounding ray
# (y = 400 down to y = -100, on NAVIGATION_SURFACE_LAYER) against the physics
# world. If the two agree, the offline check is trustworthy for this package.
#
# Run from the godot-client directory:
#   Godot_v4.7.2-stable_win64_console.exe --path . --headless \
#     --script ../eloria-assets/maps/nymara-regions/_toolkit/region_client_check.gd -- \
#     --manifest=<abs path to world.json> [--step=4] [--report=<abs path>]
extends SceneTree

const RAY_TOP := 400.0
const RAY_BOTTOM := -100.0


func _load_collision(manifest: Dictionary, manifest_path: String) -> Dictionary:
	"""The package's own walkability grid, or {} when it publishes no origin.

	EWCG v1: magic, u16 version, u16 reserved, u32 width, u32 height, then one
	byte per half-metre cell. Zero means blocked; 1..63 is a height code.
	"""
	var collision: Dictionary = manifest.get("collision", {})
	var origin: Variant = collision.get("originMetres")
	if origin is not Array or (origin as Array).size() < 2:
		return {}
	var binary := str(collision.get("binary", "collision.bin"))
	var path := manifest_path.get_base_dir().path_join(binary)
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var bytes := file.get_buffer(file.get_length())
	file.close()
	if bytes.size() < 16 or bytes.slice(0, 4).get_string_from_ascii() != "EWCG":
		return {}
	var width := bytes.decode_u32(8)
	var height := bytes.decode_u32(12)
	if width <= 0 or height <= 0 or bytes.size() < 16 + width * height:
		return {}
	return {
		"data": bytes.slice(16),
		"width": width,
		"height": height,
		"cell": float(collision.get("cellMetres", 0.5)),
		"x0": float((origin as Array)[0]),
		"z1": float((origin as Array)[1]),
	}


func _cell_walkable(grid: Dictionary, world_position: Vector3) -> bool:
	if grid.is_empty():
		return true
	var cell: float = grid["cell"]
	var column := int(floor((world_position.x - float(grid["x0"])) / cell))
	var row := int(floor((float(grid["z1"]) - world_position.z) / cell))
	if column < 0 or row < 0 or column >= int(grid["width"]) 			or row >= int(grid["height"]):
		return false
	var data: PackedByteArray = grid["data"]
	return data[row * int(grid["width"]) + column] != 0


func _args() -> Dictionary:
	var out := {}
	for raw in OS.get_cmdline_user_args():
		var arg := str(raw)
		if arg.begins_with("--") and arg.contains("="):
			var parts := arg.substr(2).split("=", true, 1)
			out[parts[0]] = parts[1]
	return out


func _init() -> void:
	var opts := _args()
	var manifest_path: String = opts.get("manifest", "")
	if manifest_path == "":
		printerr("[client-check] need --manifest=<world.json>")
		quit(2)
		return
	var step: int = int(opts.get("step", "4"))
	var report_path: String = opts.get("report", "")

	var root := get_root()
	var world_root := Node3D.new()
	world_root.name = "WorldRoot"
	root.add_child(world_root)

	var loader := WorldLoader.new()
	world_root.add_child(loader)
	loader.load_world(manifest_path)

	var manifest: Dictionary = loader.manifest.data
	if manifest.is_empty():
		printerr("[client-check] WorldLoader produced no manifest")
		quit(2)
		return
	var warnings: Array = loader.manifest.warnings
	print("[client-check] loader warnings=%d" % warnings.size())
	for w in warnings:
		print("    warning: ", w)

	# Collision and navigation bodies only exist once the physics server has
	# stepped; querying before that reports an empty world.
	for i in 4:
		await process_frame
	await physics_frame
	await physics_frame

	var space := world_root.get_world_3d().direct_space_state

	var transform: Dictionary = manifest.get("coordinateTransform", {})
	var adapter := CoordinateAdapter.new(transform)
	var cells: int = int(manifest.get("bounds", {}).get("serverCells", 0))
	if cells <= 0:
		var collision: Dictionary = manifest.get("collision", {})
		cells = int(round(float(collision.get("width", 0))
			* float(collision.get("cellMetres", 0.5))))
	if cells <= 0:
		printerr("[client-check] cannot determine the server grid size")
		quit(2)
		return
	print("[client-check] server grid %dx%d, sampling every %d tiles" % [cells, cells, step])

	# A miss is only a defect where the package says a player can stand. A
	# region has ground under every tile, so its criterion is "no misses at
	# all". An interior is rooms inside rock: most of its bounding square is
	# legitimately not floor, and judging it by a region's rule fails every
	# correctly-built interior. Where the package publishes a grid origin -
	# interiors do - misses are split into blocked cells (expected) and
	# walkable cells (real), and only the latter fail the run.
	var grid := _load_collision(manifest, manifest_path)
	var sampled := 0
	var misses := 0
	var misses_on_walkable := 0
	var miss_examples: Array = []
	var lowest := INF
	var highest := -INF
	for ty in range(0, cells, step):
		for tx in range(0, cells, step):
			var world_position: Vector3 = adapter.server_to_godot(float(tx), float(ty))
			var from := Vector3(world_position.x, RAY_TOP, world_position.z)
			var to := Vector3(world_position.x, RAY_BOTTOM, world_position.z)
			var query := PhysicsRayQueryParameters3D.create(
				from, to, WorldLoader.NAVIGATION_SURFACE_LAYER)
			var hit: Dictionary = space.intersect_ray(query)
			sampled += 1
			var position_value: Variant = hit.get("position")
			if position_value is Vector3:
				var y: float = (position_value as Vector3).y
				lowest = minf(lowest, y)
				highest = maxf(highest, y)
			else:
				misses += 1
				var standable: bool = _cell_walkable(grid, world_position)
				if standable:
					misses_on_walkable += 1
					if miss_examples.size() < 12:
						miss_examples.append([tx, ty,
							snappedf(world_position.x, 0.1),
							snappedf(world_position.z, 0.1)])

	print("[client-check] grounding: %d tiles sampled, %d misses (%.2f%%)"
		% [sampled, misses, 100.0 * float(misses) / maxf(1.0, float(sampled))])
	if grid.is_empty():
		misses_on_walkable = misses
	else:
		print("[client-check]   of those, %d are on cells collision.bin marks "
			% misses_on_walkable
			+ "walkable; %d are blocked cells and expected"
			% (misses - misses_on_walkable))
	if misses_on_walkable > 0:
		print("[client-check] miss examples (tile_x, tile_y, x, z): ", miss_examples)
	if lowest < INF:
		print("[client-check] surface height range: %.2f .. %.2f" % [lowest, highest])

	# Spawns: the manifest's stated Y should be where the client actually puts
	# an actor standing on that tile.
	var spawn_errors := 0
	var spawn_rows: Array = []
	for entry in manifest.get("spawnPoints", []):
		var spawn: Dictionary = entry
		var position: Array = spawn.get("position", [])
		if position.size() != 3:
			continue
		var from := Vector3(float(position[0]), RAY_TOP, float(position[2]))
		var to := Vector3(float(position[0]), RAY_BOTTOM, float(position[2]))
		var query := PhysicsRayQueryParameters3D.create(
			from, to, WorldLoader.NAVIGATION_SURFACE_LAYER)
		var hit: Dictionary = space.intersect_ray(query)
		var position_value: Variant = hit.get("position")
		if position_value is Vector3:
			var delta: float = absf((position_value as Vector3).y - float(position[1]))
			spawn_rows.append({"id": spawn.get("id", "?"),
				"manifestY": float(position[1]),
				"clientY": snappedf((position_value as Vector3).y, 0.001),
				"deltaMetres": snappedf(delta, 0.001)})
			if delta > 0.25:
				spawn_errors += 1
		else:
			spawn_rows.append({"id": spawn.get("id", "?"), "clientY": null,
				"deltaMetres": null})
			spawn_errors += 1
	for row in spawn_rows:
		print("[client-check] spawn ", row)

	# Opt-in: bind the manifest's own environment block through the shipped
	# WorldEnvironmentBinder and report the key light's actual emission vector.
	#
	# This exists because `environment.sun.direction` is the direction the light
	# TRAVELS, not where the sun sits: the binder aims the node's -Z at the
	# declared vector and a DirectionalLight3D emits along -Z, so a positive Y
	# component lights the world from underneath. No offline preview can show
	# that, and a capture harness using its own neutral sky cannot either, so a
	# manifest can ship with an inverted key light and nothing catches it.
	# Amberwood declares [-0.46, 0.50, 0.73] and is in exactly that state.
	var sun_report: Dictionary = {}
	if bool(opts.get("check-sun", "0") == "1"):
		var world_env := WorldEnvironment.new()
		world_root.add_child(world_env)
		var sun_light := DirectionalLight3D.new()
		world_root.add_child(sun_light)
		var bound: bool = WorldEnvironmentBinder.apply(
			loader.manifest, world_env, sun_light, world_root)
		var travel: Vector3 = -sun_light.global_transform.basis.z
		sun_report = {
			"environmentBound": bound,
			"travelDirection": [snappedf(travel.x, 0.001),
				snappedf(travel.y, 0.001), snappedf(travel.z, 0.001)],
			"lightsFromBelow": bound and travel.y > 0.0,
			"energy": sun_light.light_energy,
		}
		print("[client-check] sun ", sun_report)
		if sun_report["lightsFromBelow"]:
			printerr("[client-check] sun.direction has a positive Y: this "
				+ "manifest lights the world from underneath")

	var ok := misses_on_walkable == 0 and spawn_errors == 0
	print("[client-check] %s" % ("PASS" if ok else "FAIL"))

	if report_path != "":
		var report := {
			"manifest": manifest_path,
			"engine": Engine.get_version_info().get("string", ""),
			"renderingDriver": "headless" if DisplayServer.get_name() == "headless"
				else RenderingServer.get_video_adapter_name(),
			"loaderWarnings": warnings,
			"serverCells": cells,
			"sampleStep": step,
			"tilesSampled": sampled,
			"groundingMisses": misses,
			"groundingMissesOnWalkableCells": misses_on_walkable,
			"missCriterion": ("walkable cells only (collision grid available)"
				if not grid.is_empty()
				else "every sampled tile (no grid origin published)"),
			"missExamples": miss_examples,
			"surfaceHeightRange": [lowest, highest],
			"spawns": spawn_rows,
			"sun": sun_report,
			"pass": ok,
		}
		var file := FileAccess.open(report_path, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(report, "  ") + "\n")
			file.close()
			print("[client-check] wrote ", report_path)

	quit(0 if ok else 1)
