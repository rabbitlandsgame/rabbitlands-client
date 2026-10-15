extends SceneTree

## Arrival proof rejects a wrong first packet even if a later walk repairs it.
## Live movement/physics remain in rendered_landscape_walk.gd; these tests feed
## protocol bytes through its observer and validate published coordinate frames.
const Walk := preload("res://tests/integration/rendered_landscape_walk.gd")
var failures := 0

func _init() -> void:
	var expected := {"map":"crownwater", "tile":[72,91], "global":[287.5,1531.5],
		"units":"metres", "point":"tile-center"}
	var step := {"tile":[20,30], "destination":"crownwater", "expectedArrival":expected}
	_expect(Walk._arrival_fixture_error(step, true).is_empty(), "exact published ferry fixture is accepted")
	_expect(not Walk._arrival_fixture_error({"destination":"crownwater"}, true).is_empty(),
		"a ferry map-only transition is rejected")
	_expect(Walk._arrival_fixture_error({"tile":[20,30]}, true).is_empty(), "ordinary ferry approach steps remain movement")
	_expect(Walk._arrival_fixture_error({"destination":"old_interior"}).is_empty(), "legacy non-ferry transition remains compatible")
	for bad: Dictionary in [{"tile":[72.1,91]}, {"tile":[-1,91]}, {"global":[INF,1]},
		{"global":[287.5]}, {"units":"tiles"}, {"point":"tile-anchor"}, {"map":"westhaven"}]:
		var broken := step.duplicate(true)
		(broken.expectedArrival as Dictionary).merge(bad, true)
		_expect(not Walk._arrival_fixture_error(broken, true).is_empty(), "malformed arrival fails: " + str(bad))
	var manifest := WorldManifest.new()
	manifest.data = {"asset":{"id":"crownwater"}, "coordinateTransform":{"metresPerTile":1,"serverOrigin":[75,130],
		"origin":[0,0,0],"walkingHeight":4,"invertServerY":true},
		"continentGeography":{"translation":[290,0,1493]}}
	var actor := {"actor_id":17,"x":72,"y":91}
	var observation: Dictionary = {}
	_spawn(observation, 17, 72, 91)
	_expect(not observation.has("first_actor"), "departure actor packet cannot prove a new map arrival")
	_map(observation, "crownwater")
	_spawn(observation, 18, 72, 91)
	_expect(not observation.has("first_actor"), "another actor at the landing cannot prove player arrival")
	_spawn(observation, 17, 72, 91)
	var result: Dictionary = Walk._arrival_identity(expected, observation, "crownwater", actor, manifest)
	_expect(bool(result.ok) and result.global == expected.global,
		"first decoded destination actor packet agrees with exact tile and published global centre")
	var wrong: Dictionary = {}
	_map(wrong, "crownwater")
	_spawn(wrong, 17, 73, 91)
	_spawn(wrong, 17, 72, 91)
	_expect(not bool(Walk._arrival_identity(expected, wrong, "crownwater", actor, manifest).ok),
		"later correct spawn or walking to landing cannot repair a wrong initial arrival")
	_expect(not bool(Walk._arrival_identity(expected, observation, "crownwater", {"x":73,"y":91}, manifest).ok),
		"authoritative state must still be exactly at the arrival before further movement")
	_map(observation, "westhaven")
	_expect(not bool(Walk._arrival_identity(expected, observation, "westhaven", actor, manifest).ok),
		"a return bounce cannot pass the destination identity check")
	_map(observation, "crownwater")
	manifest.data.continentGeography.translation = [291,0,1493]
	_expect(not bool(Walk._arrival_identity(expected, observation, "crownwater", actor, manifest).ok),
		"right map and tile fail when the rendered continent placement is wrong")
	manifest.data.continentGeography.translation = [290,0,1493]
	manifest.data.asset.id = "westhaven"
	_expect(not bool(Walk._arrival_identity(expected, observation, "crownwater", actor, manifest).ok),
		"another rendered package cannot pass even with identical placement")
	print("Landscape ferry arrival harness: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _map(observation: Dictionary, identity: String) -> void:
	Walk._observe_arrival(observation, EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.CHANGE_MAP, identity.to_utf8_buffer()), 17, "crownwater")

func _spawn(observation: Dictionary, identity: int, x: int, y: int) -> void:
	var payload := PackedByteArray()
	payload.resize(18)
	payload.encode_u16(0, identity)
	payload.encode_u16(2, x)
	payload.encode_u16(4, y)
	Walk._observe_arrival(observation, EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, payload), 17, "crownwater")

func _expect(ok: bool, label: String) -> void:
	if ok:
		print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
