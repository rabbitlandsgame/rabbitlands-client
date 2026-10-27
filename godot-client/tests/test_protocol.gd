extends SceneTree

var failures := 0

func _init() -> void:
	_expect_bytes("empty frame", EloriaProtocol.encode(13), PackedByteArray([13, 1, 0]))
	_expect_bytes("move fixture", EloriaProtocol.move_to(0x1234, 0x5678),
		PackedByteArray([1, 5, 0, 0x34, 0x12, 0x78, 0x56]))
	_expect_bytes("sit fixture", EloriaProtocol.set_sitting(true),
		PackedByteArray([7, 2, 0, 1]))
	_expect_bytes("stand fixture", EloriaProtocol.set_sitting(false),
		PackedByteArray([7, 2, 0, 0]))
	# The capability handshake. Claiming a capability the client cannot decode
	# replaces a working dialogue fallback with a packet nothing reads, so the
	# advertised list is pinned to what is actually implemented.
	_expect_bytes("client capabilities fixture",
		EloriaProtocol.client_capabilities(),
		EloriaProtocol.chat("#clientcaps "
			+ ",".join(PackedStringArray(EloriaProtocol.CLIENT_CAPABILITIES))))
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("actor16_v1"),
		"the 16-bit actor capability stays advertised")
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.size() > 0
		and not EloriaProtocol.CLIENT_CAPABILITIES.has(""),
		"the advertised capability list is non-empty and has no blank entries")
	for capability: String in EloriaProtocol.CLIENT_CAPABILITIES:
		_expect(not capability.contains(",") and not capability.contains(" ")
			and capability == capability.strip_edges(),
			"capability %s survives the server's comma split" % capability)
	# Nothing may be advertised whose packet this client does not decode.
	var decoded_extensions: Dictionary = {
		"actor_customization_v1": EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR,
		"actor_customization_v2": EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR,
		"lantern_tutorial_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"second_bell_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"borrowed_sky_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"followup_tutorials_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"field_dispatch_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"signed_ashore_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"landfall_underground_v1": EloriaProtocol.ServerMessage.CHANGE_MAP,
		# No packet of its own: the change-map message naming landfall_town,
		# whose package and registry row this client ships.
		"landfall_town_v1": EloriaProtocol.ServerMessage.CHANGE_MAP,
		"tutorial_rewards_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"spell_ring_v1": EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE,
		"magic_book_v2": EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE,
		"techniques_v1": EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE,
		"magic_autocast_v1": EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE,
		"actor16_v1": EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED,
		"actor_wardrobe_v1": EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR,
		"weather_state_v1": EloriaProtocol.ServerMessage.ELORIA_WEATHER_STATE,
		"almanac_v1": EloriaProtocol.ServerMessage.ELORIA_ALMANAC_STATE,
		"seasons_v1": EloriaProtocol.ServerMessage.ELORIA_ALMANAC_STATE,
		"combat_hud_v1": EloriaProtocol.ServerMessage.ELORIA_COMBAT_STATE,
		"inventory_names_v1": EloriaProtocol.ServerMessage.ELORIA_INVENTORY_NAMES,
		"inventory_window_v1": EloriaProtocol.ServerMessage.ELORIA_INVENTORY_STATE,
		"item_detail_v1": EloriaProtocol.ServerMessage.ELORIA_ITEM_DETAIL,
		"mail_window_v1": EloriaProtocol.ServerMessage.ELORIA_MAIL_STATE,
		"map_digest_v1": EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST,
		"mix_window_v1": EloriaProtocol.ServerMessage.ELORIA_MIX_STATE,
		"market_window_v1": EloriaProtocol.ServerMessage.ELORIA_MARKETPLACE_STATE,
		"market_window_v2": EloriaProtocol.ServerMessage.ELORIA_MARKETPLACE_STATE,
		"market_window_v3": EloriaProtocol.ServerMessage.ELORIA_MARKETPLACE_STATE,
		"merchant_window_v1": EloriaProtocol.ServerMessage.ELORIA_MERCHANT_STATE,
		"merchant_weights_v1": EloriaProtocol.ServerMessage.ELORIA_MERCHANT_STATE,
		"merchant_descriptions_v1": EloriaProtocol.ServerMessage.ELORIA_MERCHANT_STATE,
		"merchant_lots_v1": EloriaProtocol.ServerMessage.ELORIA_MERCHANT_STATE,
		"navigation_hud_v1": EloriaProtocol.ServerMessage.ELORIA_NAVIGATION_STATE,
		"map_marker_actor_v1": EloriaProtocol.ServerMessage.SEND_MAP_MARKER,
		"achievements_window_v1":
			EloriaProtocol.ServerMessage.ELORIA_ACHIEVEMENTS_STATE,
		"achievements_catalog_v1":
			EloriaProtocol.ServerMessage.ELORIA_ACHIEVEMENTS_CATALOG,
		"leaderboards_v1": EloriaProtocol.ServerMessage.ELORIA_LEADERBOARD_STATE,
		"actor_titles_v1": EloriaProtocol.ServerMessage.ELORIA_ACTOR_TITLES,
		"quest_offers_v1": EloriaProtocol.ServerMessage.ELORIA_QUEST_OFFERS,
		"actor_occupations_v1":
			EloriaProtocol.ServerMessage.ELORIA_ACTOR_OCCUPATIONS,
		"adjacent_actors_v1": EloriaProtocol.ServerMessage.ELORIA_ADJACENT_MAPS,
		"player_interest_v1": EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
		"server_time_v1": EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME,
		"mount_deltas_v1": EloriaProtocol.ServerMessage.ELORIA_MOUNT_DELTAS,
		"actor_footprints_v1":
			EloriaProtocol.ServerMessage.ELORIA_ACTOR_FOOTPRINTS,
		"attribute_state_v1":
			EloriaProtocol.ServerMessage.ELORIA_ATTRIBUTE_STATE,
		"counter_layout_v1":
			EloriaProtocol.ServerMessage.ELORIA_COUNTER_LAYOUT,
		"degraded_items_v1": EloriaProtocol.ServerMessage.ELORIA_DEGRADED_ITEMS,
		"experience64_v1": EloriaProtocol.ServerMessage.ELORIA_EXPERIENCE_STATE,
		"guild_window_v1": EloriaProtocol.ServerMessage.ELORIA_GUILD_STATE,
		"party_window_v1": EloriaProtocol.ServerMessage.ELORIA_PARTY_STATE,
		"gauntlet_ready_v1": EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_READY_STATE,
		"perk_catalog_v3": EloriaProtocol.ServerMessage.ELORIA_PERK_CATALOG,
		"quest_archive_v1":
			EloriaProtocol.ServerMessage.ELORIA_QUEST_ARCHIVE_STATE,
		"player_info_v1": EloriaProtocol.ServerMessage.ELORIA_PLAYER_INFO,
		"quest_journal_v1": EloriaProtocol.ServerMessage.ELORIA_QUEST_JOURNAL_STATE,
		"spell_power_v1": EloriaProtocol.ServerMessage.ELORIA_SPELL_POWER,
		"spell_visuals_v1": EloriaProtocol.ServerMessage.SEND_SPECIAL_EFFECT,
		"spell_impacts_v1": EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE,
		"special_events_v1": EloriaProtocol.ServerMessage.ELORIA_SPECIAL_EVENT_STATE,
		"storage_window_v1": EloriaProtocol.ServerMessage.ELORIA_STORAGE_STATE,
		# No packet of its own: the stock change-map message naming a
		# continent-v2 map, which this client can draw (checked below).
		"continent_v2_maps_v1": EloriaProtocol.ServerMessage.CHANGE_MAP,
		# No packet of its own either: what the client does after a change of
		# map is answer it with `#arrived` once its character stands loaded.
		"arrival_ready_v1": EloriaProtocol.ServerMessage.CHANGE_MAP,
		"keyboard_intent_v1": EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT}
	var capability_probes: Dictionary = {
		EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_READY_STATE:
			'{"version":1,"open":false,"reason":"Cancelled"}'.to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.ELORIA_LEADERBOARD_STATE: (
			'{"version":1,"category":"overall","days":0,"request_id":0,'
			+ '"categories":[{"key":"overall","label":"Overall","group":"Skills","unit":"XP","icon":"overall"}],'
			+ '"rows":[],"self":{"name":"Mira","rank":null,"value":"0","level":null}}'
			).to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.ELORIA_WEATHER_STATE: "01" + "00000000000a00" + "01555a28374000" + "c800" + "0a" + "heavy_rain".to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.SEND_MAP_MARKER: "ea010c03e1012e2f6d6170732f666f75725f67617465732e656c6d00526565642062616e6b0060ea",
		EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE: '{"version":1,"active":false}'.to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.ELORIA_ADJACENT_MAPS: "010100" + "whitehorn_range".to_utf8_buffer().hex_encode() + "00",
		EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE: '{"kind":"recall","id":9,"entries":[]}'.to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.SEND_SPECIAL_EFFECT: "025b004d0005",
		EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT: "010103e803b80b",
		EloriaProtocol.ServerMessage.ELORIA_COMBAT_STATE:
			"016600120014001e002c00050052656564686f726e205374616700",
		EloriaProtocol.ServerMessage.ELORIA_INVENTORY_STATE:
			"fa00000014000000500000000000",
		EloriaProtocol.ServerMessage.ELORIA_ITEM_DETAIL:
			"a0000200000000410042004300440045004600470"
			+ "0",
		# One named slot: slot 2 holds "Medium Hide", the item whose shared
		# artwork is the reason this packet exists.
		EloriaProtocol.ServerMessage.ELORIA_INVENTORY_NAMES:
			"0100" + "02" + "4d656469756d204869646500",
		EloriaProtocol.ServerMessage.ELORIA_MAIL_STATE: "0000",
		# A run of torches going: two made, three still to go, and
		# storage close enough to draw from.
		EloriaProtocol.ServerMessage.ELORIA_MIX_STATE: "010103000200546f72636800",
		EloriaProtocol.ServerMessage.ELORIA_MARKETPLACE_STATE:
			"00fa0000000300000000 00".replace(" ", ""),
		EloriaProtocol.ServerMessage.ELORIA_MERCHANT_STATE:
			"5b00fa000000140000005000000000005300",
		EloriaProtocol.ServerMessage.ELORIA_NAVIGATION_STATE:
			"000000000000000000",
		# "amberwood" and a sha256 of zeroes: the map the server was built
		# against, and the digest of the package it means.
		EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST:
			"616d626572776f6f6400" + "30".repeat(64) + "00",
		# No party, no invitation: the shortest frame the server ever sends.
		EloriaProtocol.ServerMessage.ELORIA_PARTY_STATE: "0000000000",
		# No guild: the header, seven empty strings and seven empty
		# sections. A real state, and the one the window draws a founding
		# form from rather than waiting for a packet that never comes.
		EloriaProtocol.ServerMessage.ELORIA_GUILD_STATE:
			"01000000000000000000000000000000"
			+ "00000000000000000000000000000000",
		EloriaProtocol.ServerMessage.ELORIA_QUEST_ARCHIVE_STATE: "0000",
		# One perk, priced, with no reason to refuse it: tier 1 of 3 owned,
		# so what is priced is the second tier, and it sits on the Combat tab.
		EloriaProtocol.ServerMessage.ELORIA_PERK_CATALOG:
			"0100030090010000010354616e6b00780000436f6d62617400",
		# No degradation chains authored: a real answer, not a missing packet.
		EloriaProtocol.ServerMessage.ELORIA_DEGRADED_ITEMS: "0000",
		EloriaProtocol.ServerMessage.ELORIA_ACHIEVEMENTS_STATE: "00000000",
		# Two of the catalogue, wearing the title the second one grants: one
		# finished, one four hundredths of the way along. Taken from the
		# server's own builder in eloria/protocol.py.
		EloriaProtocol.ServerMessage.ELORIA_ACHIEVEMENTS_CATALOG:
			"7468652043756c6c657200020001000000010000000166697273745f626c"
			+ "6f6f6400466972737420426c6f6f6400436f6d626174004b696c6c20736f"
			+ "6d657468696e672e000004000000640000000063756c6c65720043756c6c"
			+ "6572206f66207468652057696c647300436f6d62617400412068756e6472"
			+ "65642063726561747572657320646f776e2e007468652043756c6c657200",
		# One player on the map, wearing one title.
		EloriaProtocol.ServerMessage.ELORIA_ACTOR_TITLES:
			"01005b007468652043756c6c657200",
		# One NPC on the map, with what they do.
		EloriaProtocol.ServerMessage.ELORIA_ACTOR_OCCUPATIONS:
			"01005b00" + "47726f76652d4b6565706572" + "00",
		EloriaProtocol.ServerMessage.ELORIA_QUEST_OFFERS: "01005b00",
		# One distant player at (100, 200), with three players and two
		# creatures near by held back by a cap of 160.
		EloriaProtocol.ServerMessage.ELORIA_PRESENCE:
			"01015058a000030002000100" + "5b006400c80000",
		EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME: "e8030000",
		EloriaProtocol.ServerMessage.ELORIA_MOUNT_DELTAS:
			'{"schema_version":2,"map":"landfall","full":true,"states":[],"removed":[]}'.to_utf8_buffer().hex_encode(),
		EloriaProtocol.ServerMessage.ELORIA_EXPERIENCE_STATE: "0000",
		# No creature larger than one tile in this profile: a real
		# answer, and the one an unchanged content pack still gives.
		EloriaProtocol.ServerMessage.ELORIA_ACTOR_FOOTPRINTS: "0000",
		# One attribute, at the starting value, with the ceiling the server
		# enforces. The name travels with it: this packet exists because the
		# client's own copy of the attribute list went stale once already.
		EloriaProtocol.ServerMessage.ELORIA_ATTRIBUTE_STATE:
			"0100040064006d6174746572004d617474657200",
		# One page holding one total, that total's breakdown, and one
		# achievement eight tenths of the way to its rung.
		EloriaProtocol.ServerMessage.ELORIA_COUNTER_LAYOUT:
			"01010101436f6d626174004b696c6c7300014b696c6c73000c000000"
			+ "4c6f77206c6576656c206b696c6c7300080000000a000000004b696c"
			+ "6c203130206c6f772d6c6576656c2063726561747572657300436f6d"
			+ "62617400",
		EloriaProtocol.ServerMessage.ELORIA_PLAYER_INFO: "5b0000004100",
		EloriaProtocol.ServerMessage.ELORIA_SPELL_POWER: "0000",
		# The server names a map by its id: the landing isle.
		EloriaProtocol.ServerMessage.CHANGE_MAP: "landfall".to_utf8_buffer().hex_encode() + "00",
		EloriaProtocol.ServerMessage.ELORIA_QUEST_JOURNAL_STATE: "0000",
		EloriaProtocol.ServerMessage.ELORIA_SPECIAL_EVENT_STATE: "00",
		# Category 0 holding one described row: "A", worn on "B".
		EloriaProtocol.ServerMessage.ELORIA_STORAGE_STATE:
			"000100" + "0000000001000000010000000041004200",
		EloriaProtocol.ServerMessage.ELORIA_ALMANAC_STATE: "010101000064004f7264696e61727920446179004e6f7468696e6720697320696e20666f7263652e0000000000"}
	# Probes for one capability where several share a command: 207's own probe
	# is the inactive frame every chapter decodes, which says nothing about the
	# chapter's shape. Signed Ashore's is its first card, live, carrying the
	# four countersigns in place of the Lantern's flags.
	var capability_specific_probes: Dictionary = {
		"magic_autocast_v1": '{"kind":"autocast","enabled":true,"active":false,"spell_id":-1,"target_id":-1}'.to_utf8_buffer().hex_encode(),
		"techniques_v1": '{"kind":"techniques","action_points":12,"max_action_points":200,"queued":"","stance":"","round":2.0,"techniques":[]}'.to_utf8_buffer().hex_encode(),
		"spell_impacts_v1": '{"kind":"spell_impact","effect":83,"actor_id":1,"target_id":2,"power":1,"release_delay":0.45,"flight_duration":0.3}'.to_utf8_buffer().hex_encode(),
		"market_window_v3": str((JSON.parse_string(FileAccess.get_file_as_string(
			"res://tests/fixtures/marketplace_v3.json")) as Dictionary).browse),
		"tutorial_rewards_v1": '{"version":1,"event":"experience","permanent":true,"rewards":[{"skill":"magic","amount":60},{"skill":"overall","amount":210}]}'.to_utf8_buffer().hex_encode(),
		"spell_ring_v1": '{"version":1,"active":false,"ring_training":true}'.to_utf8_buffer().hex_encode(),
		"signed_ashore_v1": ('{"version":1,"active":true,"tutorial":"signed_ashore",'
			+ '"chapter":"SIGNED ASHORE","stage":1,"total":10,"scene":1,"key":"signed_in",'
			+ '"title":"Follow Nash\'s lantern","hint":"Click Nash to talk.",'
			+ '"control":"world","item":"","map":"landfall","target_id":"wayfinder_nesh",'
			+ '"target":[142,225],"count":0,"required":1,'
			+ '"flags":{"grove":false,"temple":false,"gate":false,"light":false}}'
			).to_utf8_buffer().hex_encode()}
	for capability: String in EloriaProtocol.CLIENT_CAPABILITIES:
		_expect(decoded_extensions.has(capability),
			"advertised capability %s is one this suite knows the client decodes"
				% capability)
		if decoded_extensions.has(capability):
			var command: int = int(decoded_extensions[capability])
			var body: PackedByteArray = (_hex(str(capability_specific_probes[capability]))
				if capability_specific_probes.has(capability)
				else _hex(str(capability_probes[command]))
				if capability_probes.has(command) else _actor_bytes_extended())
			var probe: Dictionary = EloriaProtocol.decode_server(command, body)
			_expect(probe.type != "unknown" and probe.type != "invalid",
				"the packet behind %s actually decodes (%s)" % [capability,
					str(probe.get("error", probe.type))])
			if capability == "tutorial_rewards_v1":
				_expect(probe.type == "tutorial_experience" and probe.permanent
					and probe.rewards.size() == 2 and probe.rewards[0].skill == "magic"
					and int(probe.rewards[0].amount) == 60 and probe.rewards[1].skill == "overall"
					and int(probe.rewards[1].amount) == 210,
					"tutorial rewards preserve permanent skill amounts")
			if capability == "spell_ring_v1":
				_expect(probe.type == "lantern_tutorial" and probe.state.ring_training,
					"ring training survives its tutorial packet")
	# Held keyboard directions (keyboard_intent_v1): the server's direction
	# order, 255 for a release, the epoch the server last sent.
	_expect(EloriaProtocol.move_intent(3, Vector2i(1, -1), true)
		== PackedByteArray([254, 4, 0, 3, 3, 1]), "a held south-east is direction 3, run set")
	_expect(EloriaProtocol.move_intent(4, Vector2i.ZERO)
		== PackedByteArray([254, 4, 0, 4, 255, 0]), "a release is direction 255")
	var intent_state: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT, _hex("010103e803b80b"))
	_expect(intent_state.type == "move_intent" and bool(intent_state.enabled)
		and int(intent_state.epoch) == 3 and int(intent_state.keepalive_msec) == 1000
		and int(intent_state.idle_msec) == 3000, "the intent state decodes")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT,
		_hex("020103e803b80b")).type == "invalid", "another intent state version is refused")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT,
		_hex("010103e803")).type == "invalid", "a short intent state is refused")
	# The advertised map capability covers every active partition package.
	var map_catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://world_authoring/continent-v2/territories.json")) as Dictionary
	var shipped_maps: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/maps/registry.json")) as Dictionary).get("maps", {}) as Dictionary
	var partition: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(map_catalog.partitionSpecPath))) as Dictionary
	var expected := PackedStringArray()
	for section: Dictionary in partition.sections:
		expected.append(str(section.get("mapId", section.id)))
	expected.sort()
	var actual := PackedStringArray()
	for entry: Dictionary in map_catalog.entries:
		var id := str(entry.id)
		actual.append(id)
		var change_map: Dictionary = EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.CHANGE_MAP,
			_hex(id.to_utf8_buffer().hex_encode() + "00"))
		var row: Dictionary = MapRegistry.resolve(shipped_maps, str(change_map.get("map_name", "")))
		_expect(change_map.type == "change_map" and str(change_map.map_name) == id,
			"change-map preserves active section id %s" % id)
		_expect(str(row.get("status", "")) == "continent-v2-served"
			and str(row.get("manifest", "")) == str(entry.publishedManifestPath)
			and FileAccess.file_exists(str(row.get("manifest", ""))),
			"%s is served with its map_catalog package on disk" % id)
	actual.sort()
	_expect(not expected.is_empty() and actual == expected, "the map capability covers the full exact partition")
	for retired: String in map_catalog.get("retiredMapIds", []):
		_expect(not shipped_maps.has(retired), "retired map %s has no active message destination" % retired)
	# Command 209: which map package the server was built against. Two
	# NUL-terminated strings, and nothing else - a mismatched install is
	# something to be told about, not a negotiation.
	var digest_frame: PackedByteArray = _hex(
		"616d626572776f6f6400" + "61".repeat(64) + "00")
	var digest: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST, digest_frame)
	_expect(digest.type == "map_digest" and str(digest.map_id) == "amberwood"
		and str(digest.digest) == "a".repeat(64),
		"a map digest carries the map it is about and the package it expects")
	# An empty digest is a real answer and means the server publishes none for
	# this map; the client has nothing to compare and says nothing.
	var no_digest: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST, _hex("666f6f000000"))
	_expect(no_digest.type == "invalid",
		"a map digest with a third field is refused rather than half read")
	_expect(EloriaProtocol.decode_server(
			EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST,
			_hex("616d626572776f6f6400")).type == "invalid",
		"a map digest missing its digest is refused")
	_expect(EloriaProtocol.decode_server(
			EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST,
			PackedByteArray()).type == "invalid",
		"an empty map digest frame is refused")

	_expect_bytes("turn left fixture", EloriaProtocol.turn(true),
		PackedByteArray([11, 1, 0]))
	_expect_bytes("turn right fixture", EloriaProtocol.turn(false),
		PackedByteArray([12, 1, 0]))
	_expect(EloriaProtocol.is_turn_command(38) and EloriaProtocol.is_turn_command(45)
		and not EloriaProtocol.is_turn_command(37)
		and not EloriaProtocol.is_turn_command(46),
		"the eight CMD_TURN_* commands are the authoritative facing confirmations")
	_expect(EloriaProtocol.actor_command_direction(40) == Vector2i(1, 0)
		and EloriaProtocol.actor_command_direction(38) == Vector2i(0, 1)
		and EloriaProtocol.actor_command_step(40) == Vector2i.ZERO,
		"a turn command changes facing without moving the actor")
	# Recipe 7, five of them, out of storage. A recipe rather than the
	# inventory positions the ingredients sit in, which is what makes
	# mixing from storage sayable at all.
	_expect_bytes("mix request fixture", EloriaProtocol.mix_request(7, 5, true),
		PackedByteArray([200, 6, 0, 7, 0, 5, 0, 1]))
	_expect_bytes("mix request from inventory fixture",
		EloriaProtocol.mix_request(0, 1, false),
		PackedByteArray([200, 6, 0, 0, 0, 1, 0, 0]))
	# The end of a run, from the server's own builder in eloria/protocol.py:
	# one torch made before a harvest stopped it. The byte after the name's
	# terminator says so; a client that stops at the terminator reads the
	# same name and count it always did.
	var interrupted_run: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MIX_STATE,
		_hex("000000000100546f7263680001"))
	_expect(interrupted_run.get("type") == "mix_state"
		and not bool(interrupted_run.get("running", true))
		and int(interrupted_run.get("made", -1)) == 1
		and str(interrupted_run.get("output", "")) == "Torch"
		and bool(interrupted_run.get("interrupted", false)),
		"a run another action stopped says it was interrupted: %s"
			% interrupted_run)
	var finished_run: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MIX_STATE,
		_hex("010000000200546f7263680000"))
	_expect(int(finished_run.get("made", -1)) == 2
		and str(finished_run.get("output", "")) == "Torch"
		and not bool(finished_run.get("interrupted", true)),
		"a run that finished is not interrupted: %s" % finished_run)
	var older_server: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_MIX_STATE,
		_hex("010000000200546f72636800"))
	_expect(str(older_server.get("output", "")) == "Torch"
		and not bool(older_server.get("interrupted", true)),
		"no byte after the name, from an older server, is not interrupted: %s"
			% older_server)
	# A tool named rather than pointed at: the window never opens storage,
	# so it never learns which slot the tool is in.
	_expect_bytes("tool request fixture", EloriaProtocol.tool_request("Hammer"),
		PackedByteArray([201, 8, 0, 72, 97, 109, 109, 101, 114, 0]))
	_expect_bytes("chat fixture", EloriaProtocol.chat("Hello"),
		PackedByteArray([0, 7, 0, 72, 101, 108, 108, 111, 0]))
	_expect_bytes("active channel fixture", EloriaProtocol.set_active_channel(1),
		PackedByteArray([61, 2, 0, 6]))
	_expect_bytes("heartbeat fixture",
		EloriaProtocol.encode(EloriaProtocol.ClientMessage.HEART_BEAT),
		PackedByteArray([14, 1, 0]))
	_expect_bytes("resync actors fixture",
		EloriaProtocol.encode(EloriaProtocol.ClientMessage.SEND_ME_MY_ACTORS),
		PackedByteArray([8, 1, 0]))
	_expect_bytes("resync stats fixture",
		EloriaProtocol.encode(EloriaProtocol.ClientMessage.SEND_MY_STATS),
		PackedByteArray([17, 1, 0]))
	_expect_bytes("resync inventory fixture",
		EloriaProtocol.encode(EloriaProtocol.ClientMessage.SEND_MY_INVENTORY),
		PackedByteArray([18, 1, 0]))
	_expect_bytes("locate fixture", EloriaProtocol.locate_me(),
		PackedByteArray([15, 1, 0]))
	_expect_bytes("date fixture", EloriaProtocol.get_date(),
		PackedByteArray([230, 1, 0]))
	_expect_bytes("time fixture", EloriaProtocol.get_time(),
		PackedByteArray([231, 1, 0]))
	_expect_bytes("private message fixture", EloriaProtocol.private_message("Alice Hello"),
		PackedByteArray([2, 13, 0, 65, 108, 105, 99, 101, 32, 72, 101, 108, 108, 111, 0]))
	_expect_bytes("private reply fixture", EloriaProtocol.private_message("/Hello"),
		PackedByteArray([2, 8, 0, 47, 72, 101, 108, 108, 111, 0]))
	_expect_bytes("touch actor fixture", EloriaProtocol.touch_actor(0x12345678),
		PackedByteArray([28, 5, 0, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("npc response fixture", EloriaProtocol.npc_response(0x1234, 0x5678),
		PackedByteArray([29, 5, 0, 0x34, 0x12, 0x78, 0x56]))
	_expect_bytes("inspect inventory fixture", EloriaProtocol.look_at_inventory_item(7),
		PackedByteArray([19, 2, 0, 7]))
	_expect_bytes("use inventory fixture", EloriaProtocol.use_inventory_item(7),
		PackedByteArray([31, 2, 0, 7]))
	_expect_bytes("move inventory fixture", EloriaProtocol.move_inventory_item(7, 9),
		PackedByteArray([20, 3, 0, 7, 9]))
	_expect_bytes("cast spell fixture", EloriaProtocol.cast_spell([3, 23]),
		PackedByteArray([39, 4, 0, 2, 3, 23]))
	_expect_bytes("attack actor fixture", EloriaProtocol.attack_actor(0x12345678),
		PackedByteArray([40, 5, 0, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("trade request fixture", EloriaProtocol.trade_with(0x12345678),
		PackedByteArray([32, 5, 0, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("trade inventory offer fixture",
		EloriaProtocol.put_inventory_on_trade(7, 0x12345678),
		PackedByteArray([36, 7, 0, 1, 7, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("trade storage offer uses a two-byte position",
		EloriaProtocol.put_storage_on_trade(0x1234, 0x12345678),
		PackedByteArray([36, 8, 0, 2, 0x34, 0x12, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("trade offer removal fixture",
		EloriaProtocol.remove_trade_item(3, 0x12345678),
		PackedByteArray([37, 6, 0, 3, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("trade accept destinations fixture", EloriaProtocol.accept_trade(),
		PackedByteArray([33, 17, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]))
	var storage_destinations: PackedByteArray = PackedByteArray()
	storage_destinations.resize(16)
	storage_destinations.fill(1)
	storage_destinations[3] = 2
	_expect_bytes("trade per-slot storage destination fixture",
		EloriaProtocol.accept_trade(storage_destinations), PackedByteArray([
			33, 17, 0, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]))
	_expect_bytes("trade reject fixture", EloriaProtocol.reject_trade(),
		PackedByteArray([34, 1, 0]))
	_expect_bytes("trade exit fixture", EloriaProtocol.exit_trade(),
		PackedByteArray([35, 1, 0]))
	_expect_bytes("trade inspection fixture", EloriaProtocol.look_at_trade_item(3, true),
		PackedByteArray([38, 3, 0, 3, 1]))
	_expect_bytes("storage category fixture", EloriaProtocol.get_storage_category(4),
		PackedByteArray([44, 2, 0, 4]))
	_expect_bytes("storage deposit fixture", EloriaProtocol.deposit_storage(7, 0x12345678),
		PackedByteArray([45, 6, 0, 7, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("storage withdrawal fixture", EloriaProtocol.withdraw_storage(
		0x1234, 0x56789abc), PackedByteArray([
			46, 7, 0, 0x34, 0x12, 0xbc, 0x9a, 0x78, 0x56]))
	_expect_bytes("storage inspection fixture", EloriaProtocol.look_at_storage_item(0x1234),
		PackedByteArray([47, 3, 0, 0x34, 0x12]))
	_expect_bytes("inspect ground bag fixture", EloriaProtocol.inspect_bag(7),
		PackedByteArray([25, 2, 0, 7]))
	_expect_bytes("close ground bag fixture", EloriaProtocol.close_bag(),
		PackedByteArray([26, 1, 0]))
	_expect_bytes("pick up ground item fixture",
		EloriaProtocol.pick_up_ground_item(3, 0x12345678),
		PackedByteArray([23, 6, 0, 3, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("drop inventory item fixture",
		EloriaProtocol.drop_inventory_item(7, 0x12345678),
		PackedByteArray([22, 6, 0, 7, 0x78, 0x56, 0x34, 0x12]))
	_expect_bytes("knowledge inspection fixture", EloriaProtocol.get_knowledge_info(0x1234),
		PackedByteArray([41, 3, 0, 0x34, 0x12]))
	_expect_bytes("manufacturing fixture", EloriaProtocol.manufacture([
		{"slot": 7, "quantity": 0x1234}, {"slot": 2, "quantity": 3}], 255),
		PackedByteArray([30, 9, 0, 2, 7, 0x34, 0x12, 2, 3, 0, 255]))
	_expect(EloriaProtocol.actor_command_step(20) == Vector2i(0, 1), "walk north step")
	_expect(EloriaProtocol.actor_command_step(37) == Vector2i(-1, 1), "run northwest step")
	_expect(EloriaProtocol.actor_command_step(13) == Vector2i.ZERO, "sit has no step")
	_expect(EloriaProtocol.actor_command_direction(22) == Vector2i(1, 0),
		"walk command faces east")
	_expect(EloriaProtocol.actor_command_direction(40) == Vector2i(1, 0),
		"turn-only command faces east without moving")
	_expect_bytes("login fixture", EloriaProtocol.login("Test", "secret"),
		PackedByteArray([140, 13, 0, 84, 101, 115, 116, 32, 115, 101, 99, 114, 101, 116, 0]))
	_expect_bytes("create character fixture",
		EloriaProtocol.create_character("Test", "secret",
			{"skin": 1, "hair": 2, "shirt": 3, "pants": 4, "boots": 5,
			"actor_type": 0, "head": 2, "eyes": 6}),
		PackedByteArray([141, 22, 0, 84, 101, 115, 116, 32, 115, 101, 99, 114,
			101, 116, 0, 1, 2, 3, 4, 5, 0, 2, 6, 0]))
	_expect_bytes("create character class fixture",
		EloriaProtocol.create_character("Test", "secret",
			{"skin": 1, "actor_type": 37}, 3),
		PackedByteArray([141, 22, 0, 84, 101, 115, 116, 32, 115, 101, 99, 114,
			101, 116, 0, 1, 0, 0, 0, 0, 37, 0, 0, 3]))
	# Creation choices are skinned actor surfaces, never rigid attachments.
	# AppearanceVariants no longer exposes a function that says so by returning
	# an empty dictionary; the refusal lives at the one call site that built
	# actor presentation, so these fixtures pin the behaviour there instead.
	_expect(not ("equipment_visuals" in AppearanceVariants.new().get_method_list()
			.map(func(entry: Dictionary) -> String: return str(entry.get("name", "")))),
		"the unconditionally empty appearance-to-equipment function is gone")
	_expect(AppearanceVariants.skin_tint(0) != AppearanceVariants.skin_tint(1)
		and AppearanceVariants.eye_color(0) != AppearanceVariants.eye_color(1)
		and AppearanceVariants.hair_style(6) == 2
		and AppearanceVariants.head_style(7) == 0
		and AppearanceVariants.wardrobe_color("luminous",
			AppearanceVariants.PART_SHIRT, 0) != AppearanceVariants.wardrobe_color(
				"luminous", AppearanceVariants.PART_SHIRT, 1),
		"appearance variants work and retired cosmetic headwear stays hidden")
	for style: int in range(AppearanceVariants.HAIR_STYLE_COUNT):
		for color: int in range(20):
			var packed := AppearanceVariants.pack_hair(style, color)
			_expect(AppearanceVariants.hair_style(packed) == style
				and AppearanceVariants.hair_color(packed) == AppearanceVariants.hair_color(color),
				"hair style and color encode independently")
			var packet := EloriaProtocol.create_character("Test", "secret", {"hair": packed})
			_expect(AppearanceVariants.hair_from_wire(packet[16], packet[21]) == packed, "independent hair choices survive the creation packet")
	for value: int in range(100):
		_expect(AppearanceVariants.hair_style(value) == value % 4
			and AppearanceVariants.hair_color_index(value) == (value if value < 20 else (value - 20) / 4),
			"saved legacy hairstyles and independent colors remain compatible")
	_expect_bytes("version fixture",
		EloriaProtocol.version(10, 31, PackedByteArray([1, 9, 7, 0]),
			PackedByteArray([127, 0, 0, 1]), 2000),
		PackedByteArray([10, 15, 0, 10, 0, 31, 0, 1, 9, 7, 0, 127, 0, 0, 1, 7, 208]))

	var combined := EloriaProtocol.encode(11)
	combined.append_array(EloriaProtocol.encode(5, PackedByteArray([9, 0])))
	var first := EloriaProtocol.try_decode(combined)
	_expect(first.status == "ok" and first.command == 11 and first.consumed == 3, "combined first")
	var second := EloriaProtocol.try_decode(combined.slice(first.consumed))
	_expect(second.status == "ok" and second.command == 5, "combined second")
	_expect(EloriaProtocol.try_decode(PackedByteArray([1, 5])).status == "incomplete",
		"fragmented header")
	_expect(EloriaProtocol.try_decode(PackedByteArray([1, 0, 0])).status == "error",
		"invalid length")

	var created := EloriaProtocol.decode_server(252, PackedByteArray())
	_expect(created.type == "create_character_ok", "character creation ok")
	var creation_error := EloriaProtocol.decode_server(253, _nul_bytes("Name exists"))
	_expect(creation_error.type == "create_character_error"
		and creation_error.message == "Name exists", "character creation error")
	var login_ok := EloriaProtocol.decode_server(250, PackedByteArray())
	_expect(login_ok.type == "login_ok", "login ok")
	var login_error := EloriaProtocol.decode_server(251, _nul_bytes("Bad login"))
	_expect(login_error.type == "login_error" and login_error.message == "Bad login", "login error")
	var yourself := EloriaProtocol.decode_server(3, PackedByteArray([0x34, 0x12]))
	_expect(yourself.actor_id == 0x1234, "you are")
	var assistant_payload: PackedByteArray = JSON.stringify({
		"kind": "map", "map": {"id": "emberhaven"},
		"players": [{"name": "Master", "x": 10, "y": 20}],
		"creatures": [{"name": "Ash Wyrm", "boss": true}]}).to_utf8_buffer()
	var assistant: Dictionary = EloriaProtocol.decode_server(233, assistant_payload)
	_expect(assistant.type == "invasion_assistant"
		and assistant.state.kind == "map"
		and assistant.state.players[0].name == "Master",
		"invasion assistant JSON state")
	_expect(EloriaProtocol.decode_server(233, PackedByteArray([123])).type == "invalid",
		"malformed invasion assistant state")
	_expect(EloriaProtocol.decode_server(3, PackedByteArray()).type == "invalid", "short you are")
	var clock_sync := EloriaProtocol.decode_server(4, PackedByteArray([0x78, 0x56, 0x34, 0x12]))
	_expect(clock_sync.type == "clock_sync" and clock_sync.server_timestamp == 0x12345678,
		"clock synchronization")
	var new_minute := EloriaProtocol.decode_server(5, PackedByteArray([0x69, 0x01]))
	_expect(new_minute.type == "new_minute" and new_minute.minute == 1,
		"game clock wraps after six hours")
	var chat := EloriaProtocol.decode_server(0, PackedByteArray([3, 72, 105, 0]))
	_expect(chat.type == "chat" and chat.channel == 3 and chat.text == "Hi"
		and chat.colour == 0, "chat without a colour byte carries no colour")
	var active_channels: Dictionary = EloriaProtocol.decode_server(71,
		PackedByteArray([1, 1, 0, 0, 0, 4, 0, 0, 0, 12, 0, 0, 0]))
	_expect(active_channels.type == "active_channels"
		and active_channels.active_index == 1
		and active_channels.channels == [1, 4, 12], "active channel synchronization")
	_expect(EloriaProtocol.decode_server(71, PackedByteArray([0, 1])).type == "invalid",
		"active channel payload validation")
	var colored_pm: Dictionary = EloriaProtocol.decode_server(0,
		PackedByteArray([1, 128, 91, 80, 77, 32, 102, 114, 111, 109, 32, 65, 108,
			105, 99, 101, 58, 32, 104, 105, 93, 0]))
	_expect(colored_pm.type == "chat" and colored_pm.channel == 1
		and colored_pm.text == "[PM from Alice: hi]"
		and colored_pm.colour == 1,
		"personal channel strips legacy color controls but keeps the colour")
	var deep_blue_chat: Dictionary = EloriaProtocol.decode_server(0,
		PackedByteArray([0, 127 + 18, 72, 105, 0]))
	_expect(deep_blue_chat.colour == 18 and deep_blue_chat.text == "Hi",
		"the leading colour byte becomes the line's palette index")
	var unicode_chat: Dictionary = EloriaProtocol.decode_server(0,
		PackedByteArray([0, 128, 72, 195, 169, 108, 111, 0]))
	_expect(unicode_chat.text == "Hélo", "chat sanitizer preserves UTF-8 sequences")
	var option_payload: PackedByteArray = PackedByteArray([4, 0, 66, 121, 101, 0,
		0x34, 0x12, 0x78, 0x56])
	var npc_options: Dictionary = EloriaProtocol.decode_server(31, option_payload)
	_expect(npc_options.type == "npc_options" and npc_options.options.size() == 1
		and npc_options.options[0].label == "Bye"
		and npc_options.options[0].response_id == 0x1234
		and npc_options.options[0].actor_id == 0x5678, "npc options")
	_expect(EloriaProtocol.decode_server(31, PackedByteArray([9, 0, 65])).type ==
		"invalid", "truncated npc option")
	var commands := EloriaProtocol.decode_server(2,
		PackedByteArray([0x34, 0x12, 20, 0x78, 0x56, 7]))
	_expect(commands.commands.size() == 2 and commands.commands[1].actor_id == 0x5678,
		"batched actor commands")
	# The server batches removals into one packet. Dropping every id after the
	# first left dead creatures standing on the map for good.
	var removed_actors: Dictionary = EloriaProtocol.decode_server(6,
		PackedByteArray([0x34, 0x12, 0x78, 0x56, 0x02, 0x00]))
	_expect(removed_actors.type == "remove_actor"
		and removed_actors.actor_ids.size() == 3
		and removed_actors.actor_ids[0] == 0x1234
		and removed_actors.actor_ids[1] == 0x5678
		and removed_actors.actor_ids[2] == 2,
		"every actor in a batched removal packet is removed")
	var removed_actor: Dictionary = EloriaProtocol.decode_server(6,
		PackedByteArray([0x34, 0x12]))
	_expect(removed_actor.type == "remove_actor"
		and removed_actor.actor_ids == ([0x1234] as Array[int]),
		"a single-actor removal still decodes")
	_expect(EloriaProtocol.decode_server(6, PackedByteArray([1])).type == "invalid",
		"a truncated removal packet is rejected")
	var actor_wear: Dictionary = EloriaProtocol.decode_server(52,
		PackedByteArray([0x34, 0x12, 2, 25]))
	_expect(actor_wear.type == "actor_wear" and actor_wear.actor_id == 0x1234
		and actor_wear.part == 2 and actor_wear.visual_id == 25,
		"actor wear equipment fields")
	var actor_unwear: Dictionary = EloriaProtocol.decode_server(53,
		PackedByteArray([0x34, 0x12, 2]))
	_expect(actor_unwear.type == "actor_unwear" and actor_unwear.actor_id == 0x1234
		and actor_unwear.part == 2, "actor unwear equipment fields")
	_expect(EloriaProtocol.decode_server(52, PackedByteArray([1, 0, 2])).type == "invalid",
		"malformed actor wear rejected")
	var actor_damage: Dictionary = EloriaProtocol.decode_server(47,
		PackedByteArray([0x34, 0x12, 7, 0]))
	_expect(actor_damage.type == "actor_damage" and actor_damage.actor_id == 0x1234
		and actor_damage.amount == 7, "actor damage fields")
	var actor_heal: Dictionary = EloriaProtocol.decode_server(48,
		PackedByteArray([0x34, 0x12, 5, 0]))
	_expect(actor_heal.type == "actor_heal" and actor_heal.amount == 5,
		"actor heal fields")
	var actor_max_health: Dictionary = EloriaProtocol.decode_server(73,
		PackedByteArray([0x34, 0x12, 120, 0]))
	_expect(actor_max_health.type == "actor_max_health"
		and actor_max_health.max_health == 120, "actor maximum-health fields")
	_expect(EloriaProtocol.decode_server(47, PackedByteArray([1, 0, 2])).type == "invalid",
		"malformed actor damage rejected")

	var actor_payload := PackedByteArray([
		0x34, 0x12, 10, 0, 20, 0, 0, 0, 0xff, 0xff, 1, 7,
		100, 0, 90, 0, 1, 66, 111, 98, 0])
	var actor := EloriaProtocol.decode_server(1, actor_payload)
	_expect(actor.type == "actor_spawn" and actor.actor_id == 0x1234, "actor id")
	_expect(actor.x == 10 and actor.y == 20 and actor.rotation == -1, "actor transform")
	_expect(actor.name == "Bob" and actor.health == 90, "actor identity and health")
	_expect(EloriaProtocol.decode_server(1, PackedByteArray([1])).type == "invalid",
		"short actor")
	var extended_actor_payload := PackedByteArray([
		0x35, 0x12, 11, 0, 21, 0, 0, 0, 0xfe, 0xff, 0x33, 0x01, 7,
		120, 0, 88, 0, 2, 84, 111, 114, 97, 110, 0])
	var extended_actor := EloriaProtocol.decode_server(247, extended_actor_payload)
	_expect(extended_actor.type == "actor_spawn"
		and extended_actor.actor_type == 307 and extended_actor.actor_id == 0x1235,
		"extended Nymara actor type")
	_expect(extended_actor.x == 11 and extended_actor.y == 21
		and extended_actor.rotation == -2 and extended_actor.name == "Toran",
		"extended Nymara actor fields")
	var enhanced_actor_payload := PackedByteArray([
		0x36, 0x12, 12, 0, 22, 0, 0, 0, 0xfd, 0xff, 81, 0,
		1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
		100, 0, 90, 0, 1, 77, 105, 99, 97, 0,
		0, 0x40, 255, 12, 13])
	var enhanced_actor: Dictionary = EloriaProtocol.decode_server(
		51, enhanced_actor_payload)
	_expect(enhanced_actor.type == "actor_spawn"
		and enhanced_actor.actor_type == 81 and enhanced_actor.name == "Mica",
		"enhanced Nymara actor identity")
	_expect(int((enhanced_actor.appearance as Dictionary).eyes) == 12
		and int((enhanced_actor.equipment_visuals as Dictionary).get(7, 0)) == 13,
		"enhanced actor trailer preserves eyes and neck visual")
	var wardrobe_payload := enhanced_actor_payload.duplicate()
	wardrobe_payload.append_array(PackedByteArray([87, 65, 1, 5, 6, 10, 0]))
	var wardrobe_actor := EloriaProtocol.decode_server(51, wardrobe_payload)
	_expect(wardrobe_actor.appearance.shirt == 5 and wardrobe_actor.appearance.pants == 6
		and wardrobe_actor.appearance.boots == 10,
		"spawn carries saved clothing dyes independently of legacy visuals")
	for part: int in [4, 5, 6]:
		_expect(not wardrobe_actor.equipment_visuals.has(part),
			"an unworn clothing part %d does not turn a dye into equipment" % part)
	wardrobe_payload[wardrobe_payload.size() - 1] = (1 << 5) | (1 << 6)
	wardrobe_actor = EloriaProtocol.decode_server(51, wardrobe_payload)
	_expect(wardrobe_actor.equipment_visuals.get(5) == 3
		and wardrobe_actor.equipment_visuals.get(6) == 5
		and not wardrobe_actor.equipment_visuals.has(4)
		and wardrobe_actor.appearance.shirt == 5 and wardrobe_actor.appearance.boots == 10,
		"real equipment with low visual IDs survives without replacing saved dyes")
	for missing: int in range(1, 8):
		var partial := EloriaProtocol.decode_server(51,
			wardrobe_payload.slice(0, wardrobe_payload.size() - missing))
		_expect(partial.appearance == enhanced_actor.appearance
			and partial.equipment_visuals == enhanced_actor.equipment_visuals,
			"incomplete wardrobe extension keeps legacy interpretation %d" % missing)
	var equipment_config_file: FileAccess = FileAccess.open(
		"res://data/actors/equipment.json", FileAccess.READ)
	_expect(equipment_config_file != null, "equipment part registry opens")
	if equipment_config_file != null:
		var equipment_config_value: Variant = JSON.parse_string(equipment_config_file.get_as_text())
		_expect(equipment_config_value is Dictionary, "equipment part registry parses")
		if equipment_config_value is Dictionary:
			var equipment_parts: Dictionary = (equipment_config_value as Dictionary).get("parts", {})
			_expect(equipment_parts.size() == 8
				and str((equipment_parts.get("0", {}) as Dictionary).get("attachment", "")) == "right_hand"
				and str((equipment_parts.get("1", {}) as Dictionary).get("attachment", "")) == "left_hand",
				"weapon and shield use explicit native skeleton anchors")

	_expect(MapRegistry.normalize_server_map_id(" /MAPS\\StartMap.ELM ") ==
		"startmap", "map id normalization")
	# The registry is keyed by Eloria map id, which is what eloria-server
	# sends. A path-shaped name reduces to its basename with the extension
	# dropped, so an older server naming an Eternal Lands map file still
	# lands on the right map.
	_expect(MapRegistry.normalize_server_map_id("./maps/nymara/Westhaven.elm") ==
		"westhaven", "a nymara map reference reduces to its id")
	var registry: Dictionary = {
		"four_gates": {"manifest": "res://world.json"},
		"four-gates": {"alias": "four_gates"}}
	var resolved: Dictionary = MapRegistry.resolve(registry, "Four-Gates")
	_expect(resolved.get("manifest", "") == "res://world.json"
		and resolved.get("registryKey", "") == "four_gates", "map alias resolution")
	var registry_file: FileAccess = FileAccess.open("res://data/maps/registry.json", FileAccess.READ)
	_expect(registry_file != null, "production map registry opens")
	if registry_file != null:
		var parsed_registry: Variant = JSON.parse_string(registry_file.get_as_text())
		_expect(parsed_registry is Dictionary, "production map registry parses")
		if parsed_registry is Dictionary:
			var registry_root: Dictionary = parsed_registry as Dictionary
			var production_maps_value: Variant = registry_root.get("maps", {})
			if production_maps_value is Dictionary:
				var production_maps: Dictionary = production_maps_value as Dictionary
				# Every key is an Eloria map id: no directory, no extension. This is
				# the client half of the naming contract eloria-server keeps in
				# tests/test_client_content_sync.py - the server sends a map id, and
				# a key that drifted back to an Eternal Lands map path would only be
				# reachable by the tolerance in normalize_server_map_id.
				var malformed: Array[String] = []
				for raw_key: Variant in production_maps.keys():
					var key: String = str(raw_key)
					if key.contains("/") or not key.get_extension().is_empty():
						malformed.append(key)
				_expect(malformed.is_empty(),
					"every registry key is a bare map id: " + str(malformed))
				var four_gates: Dictionary = MapRegistry.resolve(production_maps, "four_gates")
				_expect(not four_gates.is_empty(), "runtime four_gates map id resolves")
				_expect(str(four_gates.get("registryKey", "")) == "four_gates",
					"runtime four_gates resolves to the production city map")
				# eloria-server sends the map id. A path-shaped name is still
				# reduced to one, so an older server or a typed console
				# argument resolves rather than dropping the player nowhere.
				var pathlike: Dictionary = MapRegistry.resolve(production_maps,
					"./maps/nymara/westhaven.elm")
				_expect(str(pathlike.get("registryKey", "")) == "westhaven",
					"a path-shaped map name still reduces to its id")
				var transform: Dictionary = four_gates.get("coordinateTransform", {})
				var city_package: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
					str(four_gates.manifest))) as Dictionary
				_expect(not transform.is_empty() and transform == city_package.get("coordinateTransform", {})
					and is_finite(float(transform.get("walkingHeight", NAN))),
					"Four Gates actor coordinates agree with its current authored package")
				var city_adapter := CoordinateAdapter.new(transform)
				var city_actor := ReplicatedActor3D.new()
				# A stand-in visual exercises the real placement path without importing a rig.
				city_actor.configure({"actor_id": 1, "x": 10, "y": 20, "rotation": 0}, city_adapter, {}, {})
				_expect(city_actor.position.is_equal_approx(city_adapter.tile_center(10, 20))
					and is_equal_approx(city_actor.position.y, float(transform.walkingHeight)),
					"Four Gates actor feet use the package's absolute walking height")
				city_actor.free()
				var regional_ids: Array[String] = ["mirrorhold", "crownwater", "whitehorn_range",
					"amethyst_barrens", "sunmane_steppe", "amberwood", "grey_moors", "westhaven",
					"verdant_stair", "ssarathi_ruins", "manymouth_delta"]
				for regional_id: String in regional_ids:
					var regional_map: Dictionary = MapRegistry.resolve(production_maps, regional_id)
					_expect(not regional_map.is_empty(), "runtime %s map id resolves" % regional_id)
					_expect(str(regional_map.get("manifest", "")).contains(
						"nymara-regions/%s/world.json" % regional_id),
						"runtime %s resolves to its production package" % regional_id)
	var coordinate: CoordinateAdapter = CoordinateAdapter.new({
		"metresPerTile": 0.5, "serverOrigin": [100.0, 200.0],
		"origin": [10.0, 30.0, -5.0], "walkingHeight": 30.0,
		"invertServerY": true})
	var godot_position: Vector3 = coordinate.server_to_godot(102.0, 198.0)
	_expect(godot_position.is_equal_approx(Vector3(11.0, 30.0, -4.0)),
		"coordinate walking height is absolute")
	_expect(coordinate.godot_to_server(godot_position) == Vector2i(102, 198),
		"coordinate round trip")
	_expect(is_equal_approx(coordinate.direction_to_godot(Vector2i(0, 1)), 0.0),
		"server north faces Godot forward")
	_expect(is_equal_approx(coordinate.direction_to_godot(Vector2i(1, 0)), -PI / 2.0),
		"server east faces Godot right")
	# Everything the server addresses by tile stands where the actor on that
	# tile stands: the tile's center. A bag placed at the tile's corner sat
	# half a tile away from the player who had just dropped it.
	var bag_fixture := GroundBag3D.new()
	bag_fixture.configure({"bag_id": 9, "x": 102, "y": 198}, coordinate)
	_expect(bag_fixture.position.is_equal_approx(coordinate.tile_center(102, 198)),
		"a dropped bag stands at the same tile center as the actor on it")
	bag_fixture.free()
	# The click-to-walk cross, behaving as the legacy highlight.c does: born
	# with its corners half a tile out and 0.3 m off the ground, collapsed
	# most of the way in at half life (age² pacing), and gone once its half
	# second is spent.
	var highlight_fixture := HighlightMarker3D.new()
	highlight_fixture.configure(Vector3(4.0, 2.0, 6.0), 1.0)
	var first_wedge: MeshInstance3D = highlight_fixture.get_node("Wedge0") as MeshInstance3D
	_expect(first_wedge != null
		and first_wedge.position.is_equal_approx(Vector3(-0.5, 0.0, -0.5))
		and is_equal_approx(highlight_fixture.position.y, 2.3),
		"a fresh walk cross starts half a tile wide and lifted off the ground")
	highlight_fixture.call("_process", 0.25)
	_expect(first_wedge.position.is_equal_approx(Vector3(-0.125, 0.0, -0.125))
		and is_equal_approx(highlight_fixture.position.y, 2.15),
		"the walk cross collapses towards the clicked tile as it ages")
	highlight_fixture.restart()
	_expect(first_wedge.position.is_equal_approx(Vector3(-0.5, 0.0, -0.5)),
		"re-clicking a tile restarts its cross instead of stacking another")
	highlight_fixture.free()

	# The playout schedule. A step that arrives on cadence continues the
	# schedule the last one set, so the body's speed on the ground does not
	# change with the packet's timing; one that arrives late pushes the
	# schedule out rather than restarting the step from a standstill; one
	# that arrives early is absorbed into a longer buffer, trimmed back at a
	# bounded pace rather than lurched through.
	var on_cadence := ReplicatedActor3D.scheduled_arrival(10.0, 10.05, 0.2, 0.25, 1.25)
	_expect(is_equal_approx(on_cadence, 10.25),
		"a step on cadence continues the schedule at one speed")
	var late_step := ReplicatedActor3D.scheduled_arrival(10.15, 10.05, 0.2, 0.25, 1.25)
	_expect(is_equal_approx(late_step, 10.4),
		"a late step is scheduled its buffer after it arrived, not lurched to")
	var early_burst := ReplicatedActor3D.scheduled_arrival(10.0, 10.25, 0.2, 0.25, 1.25)
	_expect(is_equal_approx(early_burst, 10.41),
		"a burst that runs the schedule ahead is trimmed no faster than the catch-up factor")
	var slight_lead := ReplicatedActor3D.scheduled_arrival(10.0, 10.1, 0.2, 0.25, 1.25)
	_expect(is_equal_approx(slight_lead, 10.26),
		"a schedule a little ahead of the buffer is trimmed toward it, not left to drift")
	var standing_start := ReplicatedActor3D.scheduled_arrival(10.0, -1.0, 0.2, 0.25, 1.25)
	_expect(is_equal_approx(standing_start, 10.25),
		"the first step from a standstill is given the arrival margin")
	# A diagonal step is 1.41 tiles and the server holds it for 1.41 times as
	# long; the cadence the schedule continues at is the pace per tile times
	# the tiles crossed, so it is shown over 1.41 times as long and crosses
	# the ground at the same speed as the straight step beside it.
	var straight_due := ReplicatedActor3D.scheduled_arrival(10.0, 10.05, 0.2, 0.25, 1.25)
	var diagonal_due := ReplicatedActor3D.scheduled_arrival(
		10.0, 10.0 + 0.05 * sqrt(2.0), 0.2 * sqrt(2.0), 0.25 * sqrt(2.0), 1.25)
	_expect(is_equal_approx(1.0 / (straight_due - 10.05), sqrt(2.0) / (diagonal_due - 10.0 - 0.05 * sqrt(2.0))),
		"a diagonal step is shown at the same ground speed as a straight one")
	_expect(is_equal_approx(ReplicatedActor3D.jitter_allowance(0.0, 0.15, 0.98, 0.35), 0.15)
		and is_equal_approx(ReplicatedActor3D.jitter_allowance(0.15, -0.05, 0.98, 0.35), 0.147)
		and is_equal_approx(ReplicatedActor3D.jitter_allowance(0.0, 0.9, 0.98, 0.35), 0.35),
		"the jitter allowance rises to a late step at once, decays slowly and is capped")
	_expect(is_equal_approx(ReplicatedActor3D.median_of(
			PackedFloat32Array([0.2, 0.05, 0.35, 0.2, 0.21]), 0.6), 0.2)
		and is_equal_approx(ReplicatedActor3D.median_of(PackedFloat32Array(), 0.6), 0.6),
		"the pace is the median of recent steps, so a burst and a hold do not move it")
	# A gap is a pause, not a cadence, once it is later than a network hold
	# could make it: a second stood looting between two running steps is not a
	# step that took a second, and a walking step's 600 ms is not late at all.
	_expect(ReplicatedActor3D.is_pause_gap(1.0, 0.2)
		and not ReplicatedActor3D.is_pause_gap(0.35, 0.2)
		and not ReplicatedActor3D.is_pause_gap(0.9, 0.6)
		and ReplicatedActor3D.is_pause_gap(1.1, 0.6),
		"a gap past what a network hold explains is a pause")
	_expect(ReplicatedActor3D.pace_gait(32, false) != ReplicatedActor3D.pace_gait(22, false)
		and ReplicatedActor3D.pace_gait(22, true) != ReplicatedActor3D.pace_gait(22, false)
		and ReplicatedActor3D.pace_gait(46, false) == ReplicatedActor3D.pace_gait(22, false),
		"running, walking and hastened steps are paced from separate histories")
	_expect(ReplicatedActor3D.confirms_new_pace(PackedFloat32Array([1.0, 1.02, 0.97, 1.05, 1.0]))
		and not ReplicatedActor3D.confirms_new_pace(PackedFloat32Array([1.0, 1.02, 0.97, 1.05]))
		and not ReplicatedActor3D.confirms_new_pace(PackedFloat32Array([0.8, 1.2, 0.9, 1.4, 1.0])),
		"only gaps that repeat themselves are taken for a pace that has slowed")

	var reduced_actor: Dictionary = ActorReducer.apply_command(actor, 21)
	_expect(int(reduced_actor.get("x", -1)) == 11
		and int(reduced_actor.get("y", -1)) == 21, "actor movement reducer")
	reduced_actor = ActorReducer.apply_command(reduced_actor, 13)
	_expect(bool(reduced_actor.get("sitting", false)), "actor sit reducer")
	reduced_actor = ActorReducer.apply_command(reduced_actor, 14)
	_expect(not bool(reduced_actor.get("sitting", true)), "actor stand reducer")
	var animation_actor: ReplicatedActor3D = ReplicatedActor3D.new()
	animation_actor.resolver = AnimationResolver.new({"actions": {
		"idle": "Idle", "walk": "Walk", "sit": "Sit",
		"seated_idle": "Seated", "stand": "Stand"}})
	var animation_player_fixture: AnimationPlayer = AnimationPlayer.new()
	var animation_library_fixture: AnimationLibrary = AnimationLibrary.new()
	for clip_name: String in ["Idle", "Walk", "Sit", "Seated", "Stand"]:
		var clip_fixture: Animation = Animation.new()
		clip_fixture.length = 1.0
		animation_library_fixture.add_animation(clip_name, clip_fixture)
	animation_player_fixture.add_animation_library("", animation_library_fixture)
	animation_actor.animation_player = animation_player_fixture
	animation_actor.current_action = &"sit"
	animation_actor.call("_on_animation_finished", &"Sit")
	_expect(animation_actor.current_action == &"seated_idle",
		"completed sit transition advances to seated idle")
	animation_actor.current_action = &"stand"
	animation_actor.call("_on_animation_finished", &"Stand")
	_expect(animation_actor.current_action == &"idle",
		"completed stand transition returns to idle")
	# A finished step coasts before it idles, so a late packet cannot flick the
	# pose to idle and straight back to walk on every tile.
	animation_actor.current_action = &"walk"
	animation_actor.call("_finish_movement_presentation")
	_expect(animation_actor.current_action == &"walk"
		and float(animation_actor.get("_movement_coast_remaining")) > 0.0,
		"a completed movement segment keeps walking through its coast")
	animation_actor.set("_movement_coast_remaining", 0.01)
	animation_actor.set("_snap_pending", false)
	animation_actor.set("_segment_duration", 0.0)
	animation_actor.call("_physics_process", 0.5)
	_expect(animation_actor.current_action == &"idle",
		"a movement segment idles once its coast runs out")
	animation_actor.set("_movement_coast_remaining", 0.0)
	animation_actor.set("_segment_duration", 0.0)
	_expect(animation_actor.call("_movement_aware_action", &"walk", true) == &"walk"
		and animation_actor.call("_movement_aware_action", &"walk", false) == &"idle"
		and animation_actor.call("_movement_aware_action", &"sit", false) == &"sit",
		"a walk command that moves the actor nowhere resolves to idle")
	var walk_stride := AnimationResolver.new({
		"actions": {"walk": "Walk"}, "playbackSpeeds": {"walk": 1.45},
		"strideMetresPerSecond": {"walk": 2.0}})
	_expect(is_equal_approx(walk_stride.stride_speed_for_action(&"walk"), 2.0)
		and is_equal_approx(walk_stride.stride_speed_for_action(&"idle"), 0.0),
		"stride speeds are read per action and absent for still poses")
	animation_actor.resolver = walk_stride
	animation_actor.set("_segment_start", Vector3.ZERO)
	animation_actor.server_target = Vector3(0.0, 0.0, 3.0)
	animation_actor.set("_segment_duration", 1.0)
	_expect(is_equal_approx(
		float(animation_actor.call("_playback_speed_for", &"walk")), 1.5),
		"a locomotion clip plays at the speed the actor is really travelling")
	var facing_adapter := CoordinateAdapter.new()
	var seated_yaw: float = ReplicatedActor3D.target_yaw_for_state(
		1.25, 13, 0, facing_adapter)
	_expect(is_equal_approx(seated_yaw, 1.25),
		"sitting preserves the actor's facing direction")
	# An actor command carries no rotation field. The rotation on the actor
	# state is whatever it spawned with, so a creature that had turned to face
	# the player it was attacking used to snap back to it on every swing.
	var swinging_yaw: float = ReplicatedActor3D.target_yaw_for_state(
		1.25, 46, 0, facing_adapter)
	_expect(is_equal_approx(swinging_yaw, 1.25),
		"attacking preserves the facing the actor was turned to")
	var entering_combat_yaw: float = ReplicatedActor3D.target_yaw_for_state(
		1.25, 18, 0, facing_adapter)
	_expect(is_equal_approx(entering_combat_yaw, 1.25),
		"so does entering combat")
	# What still states a facing: a turn or a step, which name their own
	# direction, and a spawn packet, which carries no command and a rotation
	# the server means.
	_expect(is_equal_approx(
		ReplicatedActor3D.target_yaw_for_state(1.25, 38, 0, facing_adapter),
		facing_adapter.direction_to_godot(Vector2i(0, 1))),
		"a turn command still turns the actor")
	_expect(is_equal_approx(
		ReplicatedActor3D.target_yaw_for_state(1.25, 22, 0, facing_adapter),
		facing_adapter.direction_to_godot(Vector2i(1, 0))),
		"a step still faces the way it walks")
	_expect(is_equal_approx(
		ReplicatedActor3D.target_yaw_for_state(1.25, -1, 16384, facing_adapter),
		facing_adapter.direction_to_godot(Vector2i(1, 0))),
		"a spawn packet's rotation is the actor's facing")
	# Everything one socket read carries is decoded, reduced and rendered as a
	# single state, so a creature's combat round - the turn onto its target and
	# the swing made behind it - reaches the actor as one dto. The turn is what
	# states the facing and the swing is what states the action; taking both
	# from the same field left only the swing, and every creature in a
	# multi-combat went on hitting the ground it spawned facing.
	var combat_round: Dictionary = ActorReducer.apply_command(actor, 44)
	combat_round = ActorReducer.apply_command(combat_round, 46)
	_expect(int(combat_round.get("command", -1)) == 46
		and int(combat_round.get("facing_command", -1)) == 44,
		"a coalesced round keeps the swing and the turn made behind it")
	var turning_actor := ReplicatedActor3D.new()
	turning_actor.apply_server_state(combat_round, facing_adapter)
	_expect(is_equal_approx(turning_actor.desired_facing_yaw(),
		facing_adapter.direction_to_godot(Vector2i(-1, 0))),
		"a creature turns west though its swing arrives in the same frame")
	# The burst that opens the fight is the same shape, with the enter-combat
	# command after the turn instead of a swing.
	var opening: Dictionary = ActorReducer.apply_command(actor, 40)
	opening = ActorReducer.apply_command(opening, 18)
	turning_actor.apply_server_state(opening, facing_adapter)
	_expect(is_equal_approx(turning_actor.desired_facing_yaw(),
		facing_adapter.direction_to_godot(Vector2i(1, 0))),
		"and so is the one that opens the fight")
	# A step names a direction too, and the later one wins: a creature that
	# walked after it turned is looking where it walked.
	var walked: Dictionary = ActorReducer.apply_command(combat_round, 24)
	_expect(int(walked.get("facing_command", -1)) == 24,
		"a step supersedes the turn before it")
	turning_actor.free()
	var animation_file: FileAccess = FileAccess.open(
		"res://data/animations/luminous.json", FileAccess.READ)
	var animation_data: Dictionary = JSON.parse_string(animation_file.get_as_text()) as Dictionary
	var transition_resolver := AnimationResolver.new(animation_data)
	_expect(is_equal_approx(transition_resolver.playback_speed_for_action(&"sit"), 0.5)
		and is_equal_approx(transition_resolver.playback_speed_for_action(&"seated_idle"), 0.25),
		"sitting and seated idle play four times slower than their original speeds")
	_expect(is_equal_approx(transition_resolver.playback_speed_for_action(&"stand"), 2.0),
		"standing up still plays at twice speed")
	# Actions the server holds an actor in must cycle for as long as they hold
	# it: a one-shot walk plays through and freezes mid-stride until the next
	# step packet restarts it. glTF cannot carry a loop flag, so the action
	# map's loopingClips list is the only place looping is stated - and
	# renaming an action's clip has to keep that list in step.
	for species_path: String in ["res://data/animations/luminous.json",
			"res://data/animations/creature.json"]:
		var species_file: FileAccess = FileAccess.open(species_path, FileAccess.READ)
		var species_resolver := AnimationResolver.new(
			JSON.parse_string(species_file.get_as_text()) as Dictionary)
		for held_action: String in ["idle", "walk", "run", "combat_idle", "seated_idle"]:
			_expect(species_resolver.looping_clips.has(
				str(species_resolver.clip_for_action(StringName(held_action)))),
				"%s declares a looping %s clip" % [species_path.get_file(), held_action])
		# Death and pain finish; a looping death is a corpse that keeps dying.
		for finishing_action: String in ["death", "pain"]:
			_expect(not species_resolver.looping_clips.has(
				str(species_resolver.clip_for_action(StringName(finishing_action)))),
				"%s keeps %s one-shot" % [species_path.get_file(), finishing_action])
	# The stand transition hands off to idle when it finishes, so the species
	# whose stand is a real transition clip must not loop it.
	_expect(not transition_resolver.looping_clips.has(
		str(transition_resolver.clip_for_action(&"stand"))),
		"the stand transition stays one-shot")
	# The canonical body rebuild aligned locomotion to rig forward. Restoring
	# the older body's ~23 degree correction would turn these clips sideways.
	_expect(is_zero_approx(transition_resolver.facing_offset_for_action(&"walk"))
		and is_zero_approx(transition_resolver.facing_offset_for_action(&"run")),
		"canonical walk and run retain their aligned facing (%.1f, %.1f deg)"
			% [transition_resolver.facing_offset_for_action(&"walk"),
				transition_resolver.facing_offset_for_action(&"run")])
	_expect(is_equal_approx(transition_resolver.facing_offset_for_action(&"idle"), 0.0)
		and is_equal_approx(transition_resolver.facing_offset_for_action(&"combat_idle"), 0.0),
		"a still pose keeps the facing the server states, uncorrected")
	# Emote actions the server can name. Each has to reach a distinct clip: two
	# emotes sharing one would look identical, and an action with no clip is
	# silently not animated, which is a thing to notice here rather than in
	# play. An action this client does not know at all is not an error - the
	# emote's words still arrive - but every one it claims must resolve.
	var emote_actions: Array[String] = []
	var emote_clips: Dictionary = {}
	for action: Variant in (animation_data.get("actions", {}) as Dictionary):
		if str(action).begins_with("emote_"):
			emote_actions.append(str(action))
			emote_clips[str(transition_resolver.clip_for_action(
				StringName(str(action))))] = true
	_expect(emote_actions.size() >= 12,
		"the client knows how to play the server's emotes: %d" % emote_actions.size())
	_expect(emote_clips.size() == emote_actions.size(),
		"every emote reaches a clip of its own: %d clips for %d actions"
			% [emote_clips.size(), emote_actions.size()])
	_expect(not emote_clips.has(""),
		"and no emote action falls through to an empty clip")
	reduced_actor = ActorReducer.apply_command(reduced_actor, 18)
	_expect(bool(reduced_actor.get("in_combat", false)), "actor enters combat")
	reduced_actor = ActorReducer.apply_command(reduced_actor, 19)
	_expect(not bool(reduced_actor.get("in_combat", true)), "actor leaves combat")
	reduced_actor = ActorReducer.apply_command(reduced_actor, 3)
	_expect(not bool(reduced_actor.get("alive", true))
		and int(reduced_actor.get("health", -1)) == 0, "actor death is authoritative")

	var stats_payload: PackedByteArray = PackedByteArray()
	stats_payload.resize(230)
	stats_payload.encode_s16(84, 18)
	stats_payload.encode_s16(86, 25)
	stats_payload.encode_s16(88, 12)
	stats_payload.encode_s16(90, 20)
	stats_payload.encode_s16(92, -7)
	stats_payload.encode_s16(0, 52)
	stats_payload.encode_s16(2, 50)
	stats_payload.encode_s16(64, 24)
	stats_payload.encode_s16(66, 23)
	stats_payload.encode_s16(60, 5)
	stats_payload.encode_s16(62, 17)
	stats_payload.encode_u32(130, 123456)
	stats_payload.encode_u32(134, 150000)
	stats_payload.encode_s16(226, 14)
	stats_payload.encode_s16(228, 30)
	var stats_event: Dictionary = EloriaProtocol.decode_server(18, stats_payload)
	_expect(stats_event.type == "stats" and int(stats_event.values.health) == 18
		and int(stats_event.values.max_health) == 25
		and int(stats_event.values.food) == -7
		and int(stats_event.values.physique) == 52
		and int(stats_event.values.physique_base) == 50
		and int(stats_event.values.attack) == 24
		and int(stats_event.values.attack_base) == 23
		and int(stats_event.values.overall) == 5
		and int(stats_event.values.overall_level) == 17
		and int(stats_event.values.attack_exp) == 123456
		and int(stats_event.values.attack_exp_next) == 150000
		and int(stats_event.values.action_points) == 14
		and int(stats_event.values.max_action_points) == 30, "full character stats")
	var partial_event: Dictionary = EloriaProtocol.decode_server(49,
		PackedByteArray([46, 0xfb, 0xff, 0xff, 0xff]))
	_expect(partial_event.type == "partial_stats" and int(partial_event.values.food) == -5,
		"signed partial food update")
	var partial_action_event: Dictionary = EloriaProtocol.decode_server(49,
		PackedByteArray([113, 9, 0, 0, 0, 114, 22, 0, 0, 0]))
	_expect(int(partial_action_event.values.action_points) == 9
		and int(partial_action_event.values.max_action_points) == 22,
		"partial action-point update")
	_expect(int(partial_action_event.values.pickpoints_spent) == 9
		and int(partial_action_event.values.pickpoints_earned) == 22
		and int(partial_action_event.values.overall_level) == 22,
		"partial pickpoint and overall-level aliases")
	var partial_experience_event: Dictionary = EloriaProtocol.decode_server(49,
		PackedByteArray([59, 0x40, 0xe2, 0x01, 0x00, 33, 25, 0, 0, 0,
			57, 0xd2, 0x04, 0, 0, 35, 7, 0, 0, 0,
			32, 26, 0, 0, 0, 34, 8, 0, 0, 0]))
	_expect(int(partial_experience_event.values.attack_exp) == 123456
		and int(partial_experience_event.values.attack_base) == 25
		and int(partial_experience_event.values.attack) == 26
		and int(partial_experience_event.values.defense_exp) == 1234
		and int(partial_experience_event.values.defense_base) == 7
		and int(partial_experience_event.values.defense) == 8,
		"partial skill experience and levels use the legacy stat identifier map")

	var inventory_payload: PackedByteArray = PackedByteArray([
		2,
		0x34, 0x12, 5, 0, 0, 0, 0, 12,
		0x78, 0x56, 0x2c, 0x01, 0, 0, 7, 6])
	var inventory_event: Dictionary = EloriaProtocol.decode_server(19, inventory_payload)
	_expect(inventory_event.type == "inventory" and inventory_event.items.size() == 2,
		"full inventory snapshot")
	_expect(int(inventory_event.items[0].image_id) == 0x1234
		and int(inventory_event.items[0].quantity) == 5
		and int(inventory_event.items[0].slot) == 0
		and bool(inventory_event.items[0].inventory_usable), "inventory item fields and flags")
	var inventory_update: Dictionary = EloriaProtocol.decode_server(21,
		PackedByteArray([0x34, 0x12, 4, 0, 0, 0, 0, 12]))
	_expect(inventory_update.type == "inventory_update"
		and int(inventory_update.item.quantity) == 4, "incremental inventory quantity")
	var inventory_remove: Dictionary = EloriaProtocol.decode_server(22,
		PackedByteArray([0, 7]))
	_expect(inventory_remove.type == "inventory_remove"
		and inventory_remove.slots == [0, 7], "batched inventory removal")
	var item_text: Dictionary = EloriaProtocol.decode_server(20,
		PackedByteArray([130, 80, 111, 116, 105, 111, 110, 0]))
	_expect(item_text.type == "inventory_text" and item_text.text == "Potion",
		"inventory inspection text")
	var ground_bag: Dictionary = EloriaProtocol.decode_server(27,
		PackedByteArray([0x34, 0x12, 0x78, 0x56, 7]))
	_expect(ground_bag.type == "ground_bag" and ground_bag.x == 0x1234
		and ground_bag.y == 0x5678 and ground_bag.bag_id == 7,
		"new ground bag fields")
	var ground_bags: Dictionary = EloriaProtocol.decode_server(28,
		PackedByteArray([2, 10, 0, 20, 0, 3, 30, 0, 40, 0, 4]))
	_expect(ground_bags.type == "ground_bags" and ground_bags.bags.size() == 2
		and ground_bags.bags[1].x == 30 and ground_bags.bags[1].bag_id == 4,
		"ground bag snapshot fields")
	var ground_items: Dictionary = EloriaProtocol.decode_server(23,
		PackedByteArray([2, 0x34, 0x12, 5, 0, 0, 0, 3,
			0x78, 0x56, 9, 0, 0, 0, 7]))
	_expect(ground_items.type == "ground_items" and ground_items.items.size() == 2
		and ground_items.items[0].image_id == 0x1234
		and ground_items.items[1].quantity == 9
		and ground_items.items[1].position == 7, "ground bag item fields")
	var ground_item_update: Dictionary = EloriaProtocol.decode_server(24,
		PackedByteArray([3, 0, 4, 0, 0, 0, 2]))
	_expect(ground_item_update.type == "ground_item"
		and ground_item_update.item.position == 2, "incremental ground item fields")
	_expect(EloriaProtocol.decode_server(25, PackedByteArray([3])).type ==
		"ground_item_remove" and EloriaProtocol.decode_server(26, PackedByteArray()).type ==
		"ground_bag_close" and EloriaProtocol.decode_server(29, PackedByteArray([7])).type ==
		"ground_bag_destroy", "ground bag lifecycle events")
	_expect(EloriaProtocol.decode_server(27, PackedByteArray([1])).type == "invalid"
		and EloriaProtocol.decode_server(28, PackedByteArray([1, 2])).type == "invalid"
		and EloriaProtocol.decode_server(23, PackedByteArray([1, 2])).type == "invalid"
		and EloriaProtocol.decode_server(26, PackedByteArray([0])).type == "invalid",
		"malformed ground bag packets rejected")
	var knowledge_list_event: Dictionary = EloriaProtocol.decode_server(55,
		PackedByteArray([0x09, 0x80]))
	_expect(knowledge_list_event.type == "knowledge_list"
		and knowledge_list_event.known == [0, 3, 15]
		and knowledge_list_event.capacity == 16, "knowledge ownership bitset")
	var new_knowledge_event: Dictionary = EloriaProtocol.decode_server(56,
		PackedByteArray([0x34, 0x12]))
	_expect(new_knowledge_event.type == "new_knowledge"
		and new_knowledge_event.index == 0x1234, "new knowledge index")
	var knowledge_text_event: Dictionary = EloriaProtocol.decode_server(57,
		PackedByteArray([77, 101, 116, 97, 108, 108, 117, 114, 103, 121, 0]))
	_expect(knowledge_text_event.type == "knowledge_text"
		and knowledge_text_event.text == "Metallurgy", "knowledge inspection text")
	_expect(EloriaProtocol.decode_server(56, PackedByteArray([1])).type == "invalid"
		and EloriaProtocol.decode_server(57, PackedByteArray()).type == "invalid",
		"malformed knowledge packets rejected")
	var trade_partner: Dictionary = EloriaProtocol.decode_server(41,
		PackedByteArray([1, 65, 108, 105, 99, 101, 0]))
	_expect(trade_partner.type == "trade_partner" and trade_partner.name == "Alice"
		and trade_partner.storage_available, "trade partner fields")
	var trade_inventory: Dictionary = EloriaProtocol.decode_server(40, inventory_payload)
	_expect(trade_inventory.type == "trade_inventory"
		and trade_inventory.items.size() == 2, "trade source inventory snapshot")
	var trade_object: Dictionary = EloriaProtocol.decode_server(35,
		PackedByteArray([0x34, 0x12, 5, 0, 0, 0, 1, 3, 1]))
	_expect(trade_object.type == "trade_object" and trade_object.image_id == 0x1234
		and trade_object.quantity == 5 and trade_object.source_type == 1
		and trade_object.slot == 3 and trade_object.other, "trade offer fields")
	var trade_remove: Dictionary = EloriaProtocol.decode_server(39,
		PackedByteArray([5, 0, 0, 0, 3, 0]))
	_expect(trade_remove.type == "trade_remove" and trade_remove.quantity == 5
		and trade_remove.slot == 3 and not trade_remove.other, "trade removal fields")
	var trade_accept: Dictionary = EloriaProtocol.decode_server(36, PackedByteArray([1, 2]))
	_expect(trade_accept.type == "trade_accept" and trade_accept.other
		and int(trade_accept.phase) == 2,
		"trade acceptance carries the authoritative phase, not a packet count")
	var trade_accept_first: Dictionary = EloriaProtocol.decode_server(36,
		PackedByteArray([0, 1]))
	_expect(trade_accept_first.type == "trade_accept" and not trade_accept_first.other
		and int(trade_accept_first.phase) == 1,
		"own first-stage acceptance decodes phase 1")
	_expect(EloriaProtocol.decode_server(36, PackedByteArray([0])).error
			== "trade_accept_length"
		and EloriaProtocol.decode_server(36, PackedByteArray([0, 3])).error
			== "trade_accept_phase",
		"a legacy one-byte accept and an out-of-range phase are both rejected")
	var trade_reject: Dictionary = EloriaProtocol.decode_server(37, PackedByteArray([0]))
	_expect(trade_reject.type == "trade_reject" and not trade_reject.other,
		"trade own rejection field")
	_expect(EloriaProtocol.decode_server(38, PackedByteArray()).type == "trade_exit",
		"trade exit event")
	_expect(EloriaProtocol.decode_server(35, PackedByteArray([1])).type == "invalid"
		and EloriaProtocol.decode_server(36, PackedByteArray()).type == "invalid"
		and EloriaProtocol.decode_server(38, PackedByteArray([0])).type == "invalid",
		"malformed trade packets rejected")
	var storage_categories: Dictionary = EloriaProtocol.decode_server(67,
		PackedByteArray([2, 0, 71, 101, 110, 101, 114, 97, 108, 0,
			4, 70, 108, 111, 119, 101, 114, 115, 0]))
	_expect(storage_categories.type == "storage_categories"
		and storage_categories.categories.size() == 2
		and storage_categories.categories[1].id == 4
		and storage_categories.categories[1].name == "Flowers",
		"storage category fields")
	var storage_items: Dictionary = EloriaProtocol.decode_server(68,
		PackedByteArray([0, 4, 0x34, 0x12, 5, 0, 0, 0, 0x78, 0x56]))
	_expect(storage_items.type == "storage_items" and storage_items.category_id == 4
		and not storage_items.update and storage_items.items.size() == 1
		and storage_items.items[0].position == 0x5678,
		"storage item fields")
	var storage_text: Dictionary = EloriaProtocol.decode_server(69,
		PackedByteArray([132, 83, 97, 102, 101, 0]))
	_expect(storage_text.type == "storage_text" and storage_text.text == "Safe",
		"storage inspection text")
	_expect(EloriaProtocol.decode_server(67, PackedByteArray([1, 0, 65])).type == "invalid"
		and EloriaProtocol.decode_server(68, PackedByteArray([0, 1, 2])).type == "invalid"
		and EloriaProtocol.decode_server(69, PackedByteArray()).type == "invalid",
		"malformed storage packets rejected")
	# The organizer packet: one described row, "Helm" worn on the Head, with a
	# strength of 12 and rarity tier 3, sitting at position 0x0102.
	var storage_state: Dictionary = EloriaProtocol.decode_server(239,
		PackedByteArray([4, 1, 0,
			0x02, 0x01, 0x34, 0x12, 7, 0, 0, 0, 12, 0, 0, 0, 3,
			72, 101, 108, 109, 0, 72, 101, 97, 100, 0]))
	_expect(storage_state.type == "storage_state"
		and storage_state.category_id == 4
		and storage_state.rows.size() == 1
		and storage_state.rows[0].position == 0x0102
		and storage_state.rows[0].image_id == 0x1234
		and storage_state.rows[0].quantity == 7
		and storage_state.rows[0].strength == 12
		and storage_state.rows[0].rarity == 3
		and storage_state.rows[0].name == "Helm"
		and storage_state.rows[0].subtype == "Head",
		"storage organizer fields")
	# A penalty on an item must survive as a negative, not wrap to two billion.
	var negative_strength: Dictionary = EloriaProtocol.decode_server(239,
		PackedByteArray([0, 1, 0,
			0, 0, 0, 0, 1, 0, 0, 0, 0xFB, 0xFF, 0xFF, 0xFF, 0,
			88, 0, 89, 0]))
	_expect(negative_strength.rows[0].strength == -5, "storage organizer signed strength")
	_expect(EloriaProtocol.decode_server(239, PackedByteArray([0, 1])).type == "invalid"
		and EloriaProtocol.decode_server(239, PackedByteArray([0, 1, 0, 1, 2])).type == "invalid"
		and EloriaProtocol.decode_server(239, PackedByteArray([0, 0, 0, 9])).type == "invalid",
		"malformed storage organizer rejected")
	var cooldown_event: Dictionary = EloriaProtocol.decode_server(77,
		PackedByteArray([7, 30, 0, 12, 0, 2, 60, 0, 1, 0]))
	_expect(cooldown_event.type == "item_cooldowns"
		and cooldown_event.cooldowns.size() == 2
		and int(cooldown_event.cooldowns[0].slot) == 7
		and int(cooldown_event.cooldowns[0].maximum_seconds) == 30
		and int(cooldown_event.cooldowns[0].remaining_seconds) == 12,
		"batched item cooldown fields")
	_expect(EloriaProtocol.decode_server(77, PackedByteArray([1, 2])).type == "invalid",
		"malformed item cooldown rejected")
	var sigils_event: Dictionary = EloriaProtocol.decode_server(42,
		PackedByteArray([8, 0, 128, 0, 2, 0, 0, 0]))
	_expect(sigils_event.type == "sigils" and sigils_event.owned == [3, 23, 33],
		"two-word sigil ownership mask")
	_expect(EloriaProtocol.decode_server(42, PackedByteArray([8, 0, 0, 0])).type == "invalid",
		"malformed sigil mask rejected")
	var spell_result: Dictionary = EloriaProtocol.decode_server(70, PackedByteArray([4, 1]))
	_expect(spell_result.type == "spell_result" and spell_result.status == 4
		and spell_result.spell_id == 1, "spell target result fields")
	_expect(EloriaProtocol.decode_server(70, PackedByteArray([1])).type == "invalid",
		"malformed spell result rejected")
	var active_spell: Dictionary = EloriaProtocol.decode_server(44, PackedByteArray([3, 90]))
	_expect(active_spell.type == "active_spell" and active_spell.buff_id == 3
		and active_spell.duration_seconds == 90, "active spell duration fields")
	_expect(EloriaProtocol.decode_server(19, PackedByteArray([1, 0])).type == "invalid",
		"malformed inventory snapshot rejected")
	# Command 238: the almanac. A client that shows the date or the day in
	# force used to have to read them out of chat lines.
	var almanac_payload := PackedByteArray([4, 4, 132, 0, 1, 100, 0])
	almanac_payload.append_array(_nul_bytes("Day of Sun Tzu"))
	almanac_payload.append_array(_nul_bytes("Attack and defense are doubled."))
	almanac_payload.append(1)
	almanac_payload.append_array(_nul_bytes("armor"))
	almanac_payload.append(1)
	almanac_payload.append_array(_nul_bytes("attack"))
	almanac_payload.append_array(PackedByteArray([200, 0]))
	almanac_payload.append_array(PackedByteArray([1, 0]))
	almanac_payload.append(0)
	almanac_payload.append_array(_nul_bytes("Ordinary Day"))
	almanac_payload.append_array(_nul_bytes("Nothing is in force."))
	var almanac: Dictionary = EloriaProtocol.decode_server(238, almanac_payload)
	_expect(almanac.type == "almanac" and almanac.day == 4 and almanac.month == 4
		and almanac.year == 132 and almanac.kind == "good"
		and str(almanac.name) == "Day of Sun Tzu"
		and (almanac.effects as Array) == ["armor"]
		and is_equal_approx(float((almanac.multipliers as Dictionary)["attack"]), 2.0)
		and (almanac.catalogue as Array).size() == 1
		and is_equal_approx(float(almanac.experience_bonus), 1.0),
		"almanac decodes the date, the day, its effects and the catalogue")
	_expect(EloriaProtocol.decode_server(238, PackedByteArray([1, 1, 0])).type
			== "invalid",
		"a truncated almanac is rejected rather than half-read")
	var short_catalogue := almanac_payload.slice(0, almanac_payload.size() - 4)
	_expect(EloriaProtocol.decode_server(238, short_catalogue).type == "invalid",
		"an almanac whose catalogue is cut short is rejected")
	var kind_out_of_range := almanac_payload.duplicate()
	kind_out_of_range[4] = 9
	_expect(EloriaProtocol.decode_server(238, kind_out_of_range).type == "invalid",
		"an unknown day kind is rejected rather than indexed past the end")

	# Commands 92, 93 and 94: which quest a piece of dialogue belongs to.
	_expect(EloriaProtocol.decode_server(92, PackedByteArray([])).type
			== "quest_dialogue_next",
		"the quest flag carries nothing and means the next line is one")
	_expect(EloriaProtocol.decode_server(92, PackedByteArray([1])).type
			== "invalid",
		"a quest flag with a payload is rejected")
	var quest_here: Dictionary = EloriaProtocol.decode_server(93,
		PackedByteArray([2, 0]))
	_expect(quest_here.type == "quest_id" and quest_here.quest_id == 2
		and not bool(quest_here.finished),
		"a quest id decodes and is not a completion")
	var quest_done: Dictionary = EloriaProtocol.decode_server(94,
		PackedByteArray([2, 0]))
	_expect(quest_done.type == "quest_id" and bool(quest_done.finished),
		"and the same id on 94 is one")
	_expect(EloriaProtocol.decode_server(93, PackedByteArray([1])).type
			== "invalid",
		"a truncated quest id is rejected")
	_expect_bytes("quest question fixture",
		EloriaProtocol.what_quest_is_this_id(2),
		PackedByteArray([63, 3, 0, 2, 0]))

	# Commands 85 and 87: an arrow going to a place rather than into somebody.
	# A miss used to be drawn as a shot at the target it missed.
	var ground_aim: Dictionary = EloriaProtocol.decode_server(85,
		PackedByteArray([0x5b, 0x00, 0xbc, 0x02, 0xe0, 0x01]))
	_expect(ground_aim.type == "ground_missile" and not bool(ground_aim.fired)
		and ground_aim.source_actor_id == 91 and ground_aim.x == 700
		and ground_aim.y == 480,
		"aiming at a tile decodes the shooter and the place")
	var ground_shot: Dictionary = EloriaProtocol.decode_server(87,
		PackedByteArray([0x5b, 0x00, 0xbc, 0x02, 0xe0, 0x01]))
	_expect(ground_shot.type == "ground_missile" and bool(ground_shot.fired)
		and ground_shot.x == 700 and ground_shot.y == 480,
		"and loosing at a tile decodes the same way, marked as fired")
	_expect(EloriaProtocol.decode_server(87, PackedByteArray([1, 0, 2, 0])).type
			== "invalid",
		"a ground missile of the wrong length is rejected")
	_expect_bytes("fire at object fixture",
		EloriaProtocol.fire_missile_at_object(700, 480),
		PackedByteArray([51, 5, 0, 0xbc, 0x02, 0xe0, 0x01]))

	# Command 89: an actor plays a named animation action. An emote's words are
	# sent separately, so an action this client has no clip for costs nothing.
	var animation_payload := PackedByteArray([0x5b, 0x00])
	animation_payload.append_array(_nul_bytes("emote_bow"))
	var animation: Dictionary = EloriaProtocol.decode_server(89, animation_payload)
	_expect(animation.type == "actor_animation" and animation.actor_id == 91
		and str(animation.action) == "emote_bow",
		"actor animation decodes the actor and the action it should play")
	_expect(EloriaProtocol.decode_server(89, PackedByteArray([1, 0])).type
			== "invalid",
		"an animation with no action name is rejected")
	var unterminated := PackedByteArray([1, 0])
	unterminated.append_array("emote_bow".to_utf8_buffer())
	_expect(EloriaProtocol.decode_server(89, unterminated).type == "invalid",
		"an unterminated action name is rejected rather than read past its end")
	var empty_action := PackedByteArray([1, 0, 0])
	_expect(EloriaProtocol.decode_server(89, empty_action).type == "invalid",
		"an empty action name is rejected")

	# The two client commands that had nothing behind them. Both share their
	# number with a server-to-client command, which the direction tells apart.
	_expect_bytes("emote fixture", EloriaProtocol.do_emote("bow"),
		PackedByteArray([70, 5, 0, 0x62, 0x6f, 0x77, 0]))
	_expect_bytes("item on item fixture", EloriaProtocol.item_on_item(3, 9),
		PackedByteArray([42, 3, 0, 3, 9]))

	var knowledge_entry_count := 0
	var knowledge_catalog_file: FileAccess = FileAccess.open(
		"res://data/knowledge/catalog.json", FileAccess.READ)
	_expect(knowledge_catalog_file != null, "knowledge catalog opens")
	if knowledge_catalog_file != null:
		var knowledge_catalog_value: Variant = JSON.parse_string(
			knowledge_catalog_file.get_as_text())
		_expect(knowledge_catalog_value is Dictionary, "knowledge catalog parses")
		if knowledge_catalog_value is Dictionary:
			var knowledge_entries: Array = (knowledge_catalog_value as Dictionary).get(
				"entries", []) as Array
			knowledge_entry_count = knowledge_entries.size()
			# The catalog is compiled from the profile the server actually
			# runs, not from the unmodified Eternal Lands data the fork was
			# built on. That profile has sixty-six books - the starting
			# reader, the fifteen the crafting ladder gates its tier-3 and
			# better recipes behind, the twenty-nine spell tomes and the
			# twenty-one technique manuals; the legacy one has 385, and
			# shipping those listed knowledge the server has never heard of.
			var knowledge_source: Dictionary = (knowledge_catalog_value
				as Dictionary).get("source", {}) as Dictionary
			_expect(str(knowledge_source.get("profile", "")) == "eloria",
				"knowledge catalog names the profile it was compiled from: "
					+ str(knowledge_source.get("profile", "")))
			_expect(knowledge_entries.size() == 66
				and str(knowledge_entries[0]) == "Beginnings"
				and knowledge_entries.has("Iron Working")
				and knowledge_entries.has("Tome of Magic Bolt")
				and str(knowledge_entries[65]) == "Manual of Mark Target",
				"knowledge catalog matches the served profile's own books: %s"
					% str(knowledge_entries))
	var manufacturing_catalog_file: FileAccess = FileAccess.open(
		"res://data/manufacturing/recipes.json", FileAccess.READ)
	_expect(manufacturing_catalog_file != null, "manufacturing catalog opens")
	if manufacturing_catalog_file != null:
		var manufacturing_value: Variant = JSON.parse_string(
			manufacturing_catalog_file.get_as_text())
		_expect(manufacturing_value is Dictionary, "manufacturing catalog parses")
		if manufacturing_value is Dictionary:
			var manufacturing_data: Dictionary = manufacturing_value as Dictionary
			var manufacturing_recipes: Array = manufacturing_data.get("recipes", []) as Array
			var sources: Dictionary = manufacturing_data.get("sources", {}) as Dictionary
			# The exact source digest used to be pinned here. It is not any
			# more: this side cannot see the server's config, so the constant
			# only ever said "somebody wrote a hex string down", and when
			# items.txt was renumbered and the catalog regenerated it went
			# stale along with every fixture below. What the catalog was built
			# from is now asserted where both halves are visible: the
			# server's content-sync test holds client_content_manifest.json's
			# catalog_sources to its tables, and tests/test_catalog_sources.py
			# holds this catalog's sources to that manifest whenever a server
			# checkout is found.
			# 539: the forty-two hand-authored recipes, the 493 remaining
			# crafting ladder recipes after procedural equipment retirement,
			# and four appended alternatives: the watchpost's Bandage, Landfall's
			# Feasting from Grapes and Cabbage, Gloam Wax from Rosemary, and
			# Bread from Wheat and Salt.
			_expect(str(sources.get("profile", "")) == "eloria"
				and manufacturing_recipes.size() == 539
				and str((manufacturing_recipes[0] as Dictionary).get("output", "")) == "Torch",
				"manufacturing catalog matches the served profile's own recipes")
			# Both catalogs come out of one generator run, so an index into the
			# knowledge catalog cannot point past its end.
			var dangling: Array[int] = []
			for recipe_value: Variant in manufacturing_recipes:
				var index: int = int((recipe_value as Dictionary).get(
					"knowledgeIndex", -1))
				if index >= knowledge_entry_count:
					dangling.append(index)
			_expect(dangling.is_empty(),
				"every recipe's knowledge index resolves in the knowledge"
					+ " catalog: %s" % str(dangling))
			var catalog: ManufacturingCatalog = ManufacturingCatalog.new()
			catalog.configure(manufacturing_data)
			# Recipe 0 is a Torch: two reagents held with a tool. The tool is
			# checked but never consumed, so it is not one of the selected
			# slots. Its ingredients are stocked from the catalog's own image
			# ids rather than from numbers written out here - the server has
			# renumbered them once already, and every fixture that spelled
			# them out went on passing against artwork nobody used.
			var torch: Dictionary = catalog.recipe(0)
			var stocked: Dictionary = {}
			var first_slot: int = -1
			for group: String in ["ingredients", "tools"]:
				for entry_value: Variant in torch.get(group, []) as Array:
					var entry: Dictionary = entry_value as Dictionary
					var slot: int = stocked.size()
					if first_slot < 0:
						first_slot = slot
					stocked[slot] = {
						"image_id": int(entry.get("imageId", -1)),
						"quantity": maxi(1, int(entry.get("quantity", 1)))}
			var ready: Dictionary = catalog.availability(0, stocked, [],
				{"food": 45, "ether": 0})
			var ready_selection: Array = ready.get("selection", []) as Array
			_expect((ready.get("reasons", []) as Array).is_empty()
				and ready_selection.size() == (torch.get("ingredients", []) as Array).size()
				and int((ready_selection[0] as Dictionary).get("slot", -1)) == first_slot,
				"recipe resolves authoritative inventory slots and quantities: "
					+ str(ready))
			var missing: Dictionary = catalog.availability(0, {}, [],
				{"food": 45, "ether": 0})
			_expect((missing.get("reasons", []) as Array).size() == 3,
				"missing ingredients and the absent tool each block"
					+ " manufacturing explicitly: %s" % str(missing))
			# Shared artwork. Several items in this profile draw as one
			# picture - five pelts do - so a client told only an image id
			# cannot say which of them a slot holds. Found rather than named,
			# because which recipe is affected is content, not contract.
			var shared_index: int = -1
			var shared_name := ""
			for index: int in range(catalog.count()):
				for entry_value: Variant in catalog.recipe(index).get("ingredients", []) as Array:
					var entry: Dictionary = entry_value as Dictionary
					if shared_index < 0 and bool(entry.get("ambiguousImage", false)):
						shared_index = index
						shared_name = str(entry.get("name", ""))
			_expect(shared_index >= 0,
				"the profile still has an item whose artwork is shared")
			if shared_index >= 0:
				var shared_stock: Dictionary = {}
				var shared_names: Dictionary = {}
				for entry_value: Variant in catalog.recipe(shared_index).get(
						"ingredients", []) as Array:
					var entry: Dictionary = entry_value as Dictionary
					var slot: int = shared_stock.size()
					shared_stock[slot] = {
						"image_id": int(entry.get("imageId", -1)),
						"quantity": maxi(1, int(entry.get("quantity", 1)))}
					shared_names[slot] = str(entry.get("name", ""))
				for entry_value: Variant in catalog.recipe(shared_index).get(
						"tools", []) as Array:
					var entry: Dictionary = entry_value as Dictionary
					var slot: int = shared_stock.size()
					shared_stock[slot] = {
						"image_id": int(entry.get("imageId", -1)), "quantity": 1}
					shared_names[slot] = str(entry.get("name", ""))
				# Without the server's slot names there is no honest way to
				# pick, so it says so rather than guessing.
				var guessed: Array = (catalog.availability(shared_index,
					shared_stock, [], {"food": 45, "ether": 40}).get(
						"reasons", []) as Array)
				var refused := false
				for reason: Variant in guessed:
					if str(reason).contains("automatic selection is unavailable"):
						refused = true
				_expect(refused,
					"ambiguous item artwork never guesses an authoritative item: "
						+ str(guessed))
				# With them, identity settles it and the recipe is offered.
				var named: Dictionary = catalog.availability(shared_index,
					shared_stock, [], {"food": 45, "ether": 40}, shared_names)
				_expect((named.get("reasons", []) as Array).is_empty()
					and (named.get("selection", []) as Array).size()
						== (catalog.recipe(shared_index).get("ingredients", []) as Array).size(),
					"the server's slot names resolve %s rather than refusing it: %s"
						% [shared_name, str(named)])
	var atlas_config_file: FileAccess = FileAccess.open(
		"res://data/items/atlases.json", FileAccess.READ)
	_expect(atlas_config_file != null, "legacy item atlas registry opens")
	if atlas_config_file != null:
		var atlas_config_value: Variant = JSON.parse_string(atlas_config_file.get_as_text())
		_expect(atlas_config_value is Dictionary, "legacy item atlas registry parses")
		if atlas_config_value is Dictionary:
			var atlas: ItemAtlas = ItemAtlas.new()
			atlas.configure(atlas_config_value as Dictionary)
			# The painted range grows with the generated sets, so the probes
			# lean on the declared count rather than pinning last year's size.
			var image_count: int = int(
				(atlas_config_value as Dictionary).get("imageCount", 0))
			var first_icon: Texture2D = atlas.icon_for(0)
			var last_icon: Texture2D = atlas.icon_for(image_count - 1)
			_expect(first_icon is AtlasTexture and first_icon.get_size() == Vector2(50, 50),
				"first legacy item icon resolves at native aspect")
			_expect(last_icon is AtlasTexture and last_icon.get_size() == Vector2(50, 50),
				"the last declared icon resolves at native aspect")
			_expect(not atlas.supports(image_count)
				and atlas.icon_for(image_count) != null
				and atlas.uses_substitute(image_count),
				"unsupported legacy item image receives the configured visible fallback")
			_expect(atlas.icon_for(397) != null and atlas.uses_substitute(397),
				"known legacy item image receives its data-driven Eloria substitute")
			var guard_shield_icon: AtlasTexture = atlas.icon_for(397) as AtlasTexture
			var guard_cape_icon: AtlasTexture = atlas.icon_for(460) as AtlasTexture
			_expect(guard_shield_icon != null and guard_shield_icon.region.position == Vector2(50, 150),
				"Four Gates guard shield uses the configured independent shield artwork")
			_expect(guard_cape_icon != null and guard_cape_icon.region.position == Vector2(200, 200),
				"Four Gates guard cape uses the configured independent cloak artwork")
	var spell_config_file: FileAccess = FileAccess.open(
		"res://data/spells/catalog.json", FileAccess.READ)
	_expect(spell_config_file != null, "spell catalog opens")
	if spell_config_file != null:
		var spell_config_value: Variant = JSON.parse_string(spell_config_file.get_as_text())
		_expect(spell_config_value is Dictionary, "spell catalog parses")
		if spell_config_value is Dictionary:
			var spell_catalog: SpellCatalog = SpellCatalog.new()
			spell_catalog.configure(spell_config_value as Dictionary)
			# The catalog mirrors the server's spellbook (dev-server
			# config/eloria/spells.xml): the sigil sequence is the CAST_SPELL
			# payload and the server's lookup key, so the order is the wire.
			var embermend: Dictionary = spell_catalog.spell(0)
			var embermend_sigils: Array = embermend.get("sigils", []) as Array
			_expect(embermend_sigils.size() == 2 and int(embermend_sigils[0]) == 0
				and int(embermend_sigils[1]) == 7,
				"Heal uses the server's ordered sigil sequence")
			var embermend_icon: Texture2D = spell_catalog.icon_for(0)
			_expect(embermend_icon is AtlasTexture
				and embermend_icon.get_size() == Vector2(64, 64),
				"spell icon resolves at native aspect")
			# Heal is known to every mage: no tome stands between a new
			# character and casting it.
			var ready_reasons: Array[String] = spell_catalog.unavailable_reasons(0,
				[], {"magic": 0, "ether": 5}, {
					0: {"image_id": 584, "quantity": 1},
					1: {"image_id": 67, "quantity": 1}})
			_expect(ready_reasons.is_empty(),
				"owned Heal requirements are locally ready")
			var blocked_reasons: Array[String] = spell_catalog.unavailable_reasons(0,
				[], {"magic": 0, "ether": 4}, {})
			# Heal is a self spell: one distillate and its anchor, and the
			# anchor costs nothing below Power 4.
			_expect(blocked_reasons.size() == 2,
				"the mana and the distillate are explicit, the free anchor is not")
			# Every other family waits on its tome, by the knowledge index the
			# server reports it under.
			var ward_reasons: Array[String] = spell_catalog.unavailable_reasons(2,
				[], {"magic": 99, "ether": 999}, {})
			_expect(ward_reasons.has("Read the Tome of Magic Ward"),
				"an unread tome is the first reason: %s" % str(ward_reasons))
			var read_ward: Array[int] = [spell_catalog.knowledge_index("Tome of Magic Ward")]
			_expect(not spell_catalog.unavailable_reasons(2, read_ward,
				{"magic": 99, "ether": 999}, {}).has("Read the Tome of Magic Ward"),
				"and reading it lifts that reason")
			# A reagent is stated by the server's name for the item, not by
			# the number the catalog files it under.
			_expect(blocked_reasons.has("Requires 1 Life Distillate (have 0)"),
				"a missing reagent is named: %s" % str(blocked_reasons))
			# The two ids are not interchangeable: a backpack holding the
			# item id rather than the image id is not holding the reagent.
			var mistaken_reasons: Array[String] = spell_catalog.unavailable_reasons(0,
				[], {"magic": 0, "ether": 5}, {
					0: {"image_id": 1850, "quantity": 1},
					1: {"image_id": 69, "quantity": 1}})
			_expect(mistaken_reasons.size() == 1,
				"reagents are counted by image id, not by the server's item id: %s"
					% str(mistaken_reasons))

	# Perks are server state. The client keeps no perk table: the names and
	# descriptions arrive on the wire, which is what makes a renamed or newly
	# added perk survive instead of being dropped by a hardcoded array.
	var perks_payload: PackedByteArray = PackedByteArray([2, 0])
	perks_payload.append_array(PackedByteArray([0, 5, 0]))
	perks_payload.append_array(_nul_bytes("Excavator"))
	perks_payload.append_array(_nul_bytes("Twice as many items."))
	perks_payload.append_array(PackedByteArray([1, 0xfd, 0xff]))
	perks_payload.append_array(_nul_bytes("Power Hungry"))
	perks_payload.append_array(_nul_bytes("Lose 3 food per minute."))
	var perks: Dictionary = EloriaProtocol.decode_server(234, perks_payload)
	_expect(perks.type == "perks" and (perks.perks as Array).size() == 2,
		"the perks packet decodes every entry")
	var first_perk: Dictionary = (perks.perks as Array)[0]
	var second_perk: Dictionary = (perks.perks as Array)[1]
	_expect(str(first_perk.name) == "Excavator"
		and str(first_perk.description) == "Twice as many items."
		and int(first_perk.pickpoints) == 5 and not bool(first_perk.from_gear),
		"a permanent perk carries its name, description and pick-point cost")
	_expect(str(second_perk.name) == "Power Hungry"
		and int(second_perk.pickpoints) == -3 and bool(second_perk.from_gear),
		"a negative pick-point cost is signed and a gear-granted perk is flagged")
	_expect(EloriaProtocol.decode_server(234, PackedByteArray([0, 0])).perks.is_empty(),
		"an empty perk list decodes as no perks rather than an error")
	_expect(EloriaProtocol.decode_server(234, PackedByteArray([1])).error
			== "perks_length"
		and EloriaProtocol.decode_server(234, PackedByteArray([1, 0, 0, 0, 0])).error
			== "perks_name_terminator"
		and EloriaProtocol.decode_server(234, perks_payload.slice(0,
			perks_payload.size() - 1)).type == "invalid",
		"short, unterminated and truncated perk packets are rejected")

	# Lifetime activity totals, with the category name beside each total.
	var counters_payload: PackedByteArray = PackedByteArray([1, 2])
	counters_payload.append_array(PackedByteArray([4, 0, 0, 0]))
	counters_payload.append_array(_nul_bytes("Kills"))
	counters_payload.append_array(PackedByteArray([0xff, 0xff, 0xff, 0xff]))
	counters_payload.append_array(_nul_bytes("Harvests"))
	var counters: Dictionary = EloriaProtocol.decode_server(235, counters_payload)
	_expect(counters.type == "activity_counters" and bool(counters.full)
		and (counters.counters as Array).size() == 2,
		"a full counter snapshot decodes every category")
	var kills_counter: Dictionary = (counters.counters as Array)[0]
	var harvest_counter: Dictionary = (counters.counters as Array)[1]
	_expect(str(kills_counter.name) == "Kills" and int(kills_counter.total) == 4
		and str(harvest_counter.name) == "Harvests"
		and int(harvest_counter.total) == 0xffffffff,
		"totals are unsigned 32-bit and keep their server category name")
	var delta_payload: PackedByteArray = PackedByteArray([0, 1, 9, 0, 0, 0])
	delta_payload.append_array(_nul_bytes("Drops"))
	var delta: Dictionary = EloriaProtocol.decode_server(235, delta_payload)
	_expect(delta.type == "activity_counters" and not bool(delta.full)
		and (delta.counters as Array).size() == 1
		and int((delta.counters as Array)[0].total) == 9,
		"a single changed counter decodes as a delta rather than a snapshot")
	_expect(EloriaProtocol.decode_server(235, PackedByteArray([1])).error
			== "activity_counters_length"
		and EloriaProtocol.decode_server(235, PackedByteArray([1, 1, 0, 0])).error
			== "activity_counter_entry_length"
		and EloriaProtocol.decode_server(235,
			PackedByteArray([1, 1, 0, 0, 0, 0, 65])).error
			== "activity_counter_terminator",
		"short, truncated and unterminated counter packets are rejected")

	# The nine Eloria extension windows. Every fixture below is the exact
	# output of the server's own builder in eloria/protocol.py, captured from
	# the independent Eloria configuration, so a change to either side of one
	# of these contracts breaks this suite rather than a window.
	# Command 245, experience without the legacy packet's 32-bit ceiling. A
	# capped player's total reads as exactly 4,294,967,295 through the old
	# window forever, which is the wall Eternal Lands never got past.
	var wide: Dictionary = EloriaProtocol.decode_server(245, _hex(
		"020061747461636b000080c6a47e8d030029b5017b000000000f2700006861727665"
		+ "7374696e67003930000000000000204e00000000000000000000"))
	_expect(wide.type == "experience_state"
		and (wide.skills as Array).size() == 2,
		"the wide experience packet decodes every skill it carries")
	var capped: Dictionary = (wide.skills as Array)[0]
	_expect(str(capped.skill) == "attack"
		and int(capped.experience) == 1000000000000000
		and int(capped.next_level) == 2063709481
		and int(capped.post_cap_points) == 9999,
		"a total far past 32 bits survives the read intact")
	var levelling: Dictionary = (wide.skills as Array)[1]
	_expect(str(levelling.skill) == "harvesting"
		and int(levelling.experience) == 12345
		and int(levelling.post_cap_points) == 0,
		"a skill still levelling reports no post-cap points")
	_expect(str(EloriaProtocol.decode_server(245,
		_hex("010061007b00")).get("error", "")) == "experience_skill_values",
		"a skill row cut short of its values is refused")
	_expect(EloriaProtocol.u64(_hex("ffffffffffffff7f")) == 9223372036854775807,
		"the 64-bit reader carries the whole signed range")

	# Command 244, everything countable in one packet rather than a dozen chat
	# lines that scroll away.
	var achievements: Dictionary = EloriaProtocol.decode_server(244, _hex(
		"030002004d757368726f6f6d7320656174656e000c000000506c616e747320686172"
		+ "76657374656400e0010000496e766173696f6e20626f73736573206b696c6c656400"
		+ "03000000426567696e6e6572205475746f7269616c00466972737420426c6f6f6400"))
	_expect(achievements.type == "achievements_state"
		and (achievements.counters as Array).size() == 3
		and (achievements.completed as Array).size() == 2,
		"the achievements packet decodes its counters and its completions")
	var harvested: Dictionary = (achievements.counters as Array)[1]
	_expect(str(harvested.label) == "Plants harvested"
		and int(harvested.value) == 480,
		"a counter carries its label and a value wider than one byte")
	_expect((achievements.completed as Array)[0] == "Beginner Tutorial",
		"completed achievements arrive by name")
	var no_achievements: Dictionary = EloriaProtocol.decode_server(244,
		_hex("00000000"))
	_expect(no_achievements.type == "achievements_state"
		and (no_achievements.counters as Array).is_empty(),
		"a character who has done nothing countable is still answered")
	_expect(str(EloriaProtocol.decode_server(244,
		_hex("010000004100")).get("error", "")) == "achievements_counter_value",
		"a counter whose value was cut off is refused rather than read as zero")

	# Command 219, the authored catalogue: what there is to be proud of, how
	# far along each one is, and the title it grants. A separate packet from
	# 244 above, which carries the older counters-and-names model that the
	# Counters tab still reads.
	var catalogue: Dictionary = EloriaProtocol.decode_server(219, _hex(
		"7468652043756c6c657200020001000000010000000166697273745f626c6f6f6400"
		+ "466972737420426c6f6f6400436f6d626174004b696c6c20736f6d657468696e67"
		+ "2e000004000000640000000063756c6c65720043756c6c6572206f662074686520"
		+ "57696c647300436f6d62617400412068756e647265642063726561747572657320"
		+ "646f776e2e007468652043756c6c657200"))
	_expect(catalogue.type == "achievements_catalog"
		and str(catalogue.worn_title) == "the Culler"
		and (catalogue.entries as Array).size() == 2,
		"the catalogue packet carries the worn title and every entry")
	var earned: Dictionary = (catalogue.entries as Array)[0]
	_expect(str(earned.key) == "first_blood" and str(earned.name) == "First Blood"
		and str(earned.category) == "Combat" and bool(earned.done)
		and int(earned.progress) == 1 and int(earned.target) == 1,
		"a finished entry carries its key, name, category and its bar")
	var pending: Dictionary = (catalogue.entries as Array)[1]
	_expect(not bool(pending.done) and int(pending.progress) == 4
		and int(pending.target) == 100 and str(pending.title) == "the Culler"
		and str(pending.description).begins_with("A hundred"),
		"an unfinished entry carries its progress, its title and its blurb")
	var empty_catalogue: Dictionary = EloriaProtocol.decode_server(219,
		_hex("000000"))
	_expect(empty_catalogue.type == "achievements_catalog"
		and (empty_catalogue.entries as Array).is_empty(),
		"a world with no achievements is answered rather than left silent")
	for broken_catalogue: String in ["00", "000100", "0001000100000001000000"]:
		_expect(EloriaProtocol.decode_server(219,
				_hex(broken_catalogue)).type == "invalid",
			"a malformed catalogue payload is rejected (%s)" % broken_catalogue)

	# Command 211, who on this map is calling themselves what. Its own packet
	# because the display name already packs a colour byte, a name and a guild
	# tag into one string this client unpicks by hand.
	var worn_titles: Dictionary = EloriaProtocol.decode_server(211,
		_hex("02005b007468652043756c6c657200" + "5c00" + "00"))
	_expect(worn_titles.type == "actor_titles"
		and (worn_titles.titles as Array).size() == 2,
		"the titles packet carries a row per player on the map")
	var first_title: Dictionary = (worn_titles.titles as Array)[0]
	_expect(int(first_title.actor_id) == 91
		and str(first_title.title) == "the Culler",
		"a title row names the actor wearing it")
	_expect(str(((worn_titles.titles as Array)[1] as Dictionary).title) == "",
		"an empty title is a real row: it is how somebody takes theirs off")
	for broken_titles: String in ["00", "0100", "01005b0041"]:
		_expect(EloriaProtocol.decode_server(211,
				_hex(broken_titles)).type == "invalid",
			"a malformed titles payload is rejected (%s)" % broken_titles)

	# Command 210, what the NPCs just shown do for a living: the line drawn under
	# their names. The titles' shape, for the titles' reason.
	var occupations: Dictionary = EloriaProtocol.decode_server(210,
		_hex("02005b00" + "47726f76652d4b6565706572" + "00" + "5c00"
			+ "546f6f6c6b6565706572" + "00"))
	_expect(occupations.type == "actor_occupations"
		and (occupations.occupations as Array).size() == 2,
		"the occupations packet carries a row per NPC")
	if (occupations.get("occupations", []) as Array).size() == 2:
		var first_occupation: Dictionary = (occupations.occupations as Array)[0]
		_expect(int(first_occupation.actor_id) == 91
			and str(first_occupation.occupation) == "Grove-Keeper",
			"an occupation row names the actor it describes")
		_expect(str(((occupations.occupations as Array)[1] as Dictionary).occupation)
				== "Toolkeeper", "and the second row its own")
	for broken_occupations: String in ["00", "0100", "01005b0041", "01005b004100ff"]:
		_expect(EloriaProtocol.decode_server(210,
				_hex(broken_occupations)).type == "invalid",
			"a malformed occupations payload is rejected (%s)" % broken_occupations)

	# Commands 242 and 243, the two halves of the worn-item answer. They exist
	# separately because the two wires carry different identity: a window that
	# knows an item's name can look it up, and the inventory grid, which knows
	# only an image id shared with the fresh item, cannot.
	var degraded: Dictionary = EloriaProtocol.decode_server(242,
		_hex("0200576f726e20426f6f747300576f726e2049726f6e204d61696c00"))
	_expect(degraded.type == "degraded_items"
		and (degraded.names as Array) == ["Worn Boots", "Worn Iron Mail"],
		"the worn-item names decode in the order the server sent them")
	_expect(str(EloriaProtocol.decode_server(242,
		_hex("020041000000")).get("error", "")) == "degraded_items_trailing",
		"a worn-item list with trailing bytes is refused")
	var worn: Dictionary = EloriaProtocol.decode_server(243,
		_hex("2500000000000000"))
	_expect(worn.type == "worn_slots" and int(worn.mask) == 37,
		"the worn-slot mask decodes as a bitmask over the player's own slots")
	var high_slot: Dictionary = EloriaProtocol.decode_server(243,
		_hex("0000000000010000"))
	_expect(high_slot.type == "worn_slots" and int(high_slot.mask) == 1 << 40,
		"a slot above the first byte survives the little-endian read")
	_expect(str(EloriaProtocol.decode_server(243,
		_hex("250000")).get("error", "")) == "worn_slots_length",
		"a short worn-slot frame is refused rather than read as zero")

	# Command 241, the completed-quest archive. Server-held on purpose: the
	# journal says what is open, this says what is done, and it has to survive
	# a reinstall - which a client-side log does not.
	var archive: Dictionary = EloriaProtocol.decode_server(241, _hex(
		"0200426567696e6e6572205475746f7269616c0049736c61205072696d6100596f75"
		+ "206c6561726e656420746f206d6f76652c2066696768742c2067617468657220616e"
		+ "64206d69782e00546865205765737465726e20526f6164004e796d6172610059"
		+ "6f752077616c6b65642074686520726f6164207765737420616e642063616d652062"
		+ "61636b2e00"))
	_expect(archive.type == "quest_archive"
		and (archive.entries as Array).size() == 2,
		"the quest archive decodes every completed entry")
	var archived: Dictionary = (archive.entries as Array)[0]
	_expect(str(archived.title) == "Beginner Tutorial"
		and str(archived.location) == "Isla Prima"
		and str(archived.detail).begins_with("You learned to move"),
		"an archive entry carries its title, where it happened and what it was")
	var no_archive: Dictionary = EloriaProtocol.decode_server(241, _hex("0000"))
	_expect(no_archive.type == "quest_archive"
		and (no_archive.entries as Array).is_empty(),
		"having finished nothing is a state rather than a missing packet")
	_expect(str(EloriaProtocol.decode_server(241,
		_hex("020041004200430000")).get("error", "")) == "quest_archive_entry_text",
		"an archive frame that promises more entries than it carries is refused")
	_expect(str(EloriaProtocol.decode_server(241,
		_hex("000000")).get("error", "")) == "quest_archive_trailing",
		"an archive frame with trailing bytes is refused")

	# Command 240, the party window. Offline members arrive as rows rather than
	# being omitted, which is what lets the window say "offline" instead of
	# quietly shrinking when somebody drops.
	var party: Dictionary = EloriaProtocol.decode_server(240, _hex(
		"0102037800b40028003c000003e0014b656c6c616e00666f75725f67617465730004"
		+ "5a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000"))
	_expect(party.type == "party" and bool(party.in_party)
		and (party.members as Array).size() == 2,
		"the party state decodes both of its members")
	var leader: Dictionary = (party.members as Array)[0]
	_expect(bool(leader.online) and bool(leader.leader) and not bool(leader.is_self)
		and int(leader.health) == 120 and int(leader.max_health) == 180
		and int(leader.ether) == 40 and int(leader.max_ether) == 60
		and str(leader.name) == "Kellan" and str(leader.map_id) == "four_gates"
		and int(leader.x) == 768 and int(leader.y) == 480,
		"the leader's row carries vitals, map and tile")
	var absent: Dictionary = (party.members as Array)[1]
	_expect(not bool(absent.online) and not bool(absent.leader)
		and bool(absent.is_self) and str(absent.name) == "Maren"
		and str(absent.map_id) == "mirrorhold",
		"an offline member keeps a row, and the reader's own row is flagged")

	var invited: Dictionary = EloriaProtocol.decode_server(240,
		_hex("00004b656c6c616e004b00"))
	_expect(invited.type == "party" and not bool(invited.in_party)
		and str(invited.invited_by) == "Kellan"
		and int(invited.invite_seconds) == 75,
		"a pending invitation arrives without a party")
	var no_party: Dictionary = EloriaProtocol.decode_server(240, _hex("0000000000"))
	_expect(no_party.type == "party" and not bool(no_party.in_party)
		and (no_party.members as Array).is_empty()
		and str(no_party.invited_by) == "",
		"an empty party is a state rather than a missing packet")
	_expect(str(EloriaProtocol.decode_server(240,
		_hex("0102000000")).get("error", "")) == "party_entry_length",
		"a party frame that promises more members than it carries is refused")
	_expect(str(EloriaProtocol.decode_server(240, _hex("0102")).get("error", ""))
		== "party_length",
		"a party frame too short to hold its own header is refused")
	_expect(str(EloriaProtocol.decode_server(240,
		_hex("000000000000")).get("error", "")) == "party_trailing",
		"a party frame with trailing bytes is refused")
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("party_window_v1"),
		"the client advertises the party window it can now draw")

	# Command 213, the guild window. Seven strings and seven counted sections
	# after an eleven-byte header, which is the shape a decoder gets wrong
	# quietly: a section read at the wrong offset produces plausible rubbish
	# rather than an error. Every fixture here is the server encoder's output.
	var guild: Dictionary = EloriaProtocol.decode_server(213, _hex(
		"010114ff00307500002714454c4f00456c6f7269612056616e6775617264004b656c"
		+ "6c616e004d7573746572206174206475736b2e00412074657374696e67206775696c"
		+ "640041736b20616e206f6666696365720068747470733a2f2f6578616d706c652e74"
		+ "65737400020014074b656c6c616e0005004d6172656e000100546f6d610001005249"
		+ "5600526976616c204775696c64000100125249560000000200454c4f00456c6f7269"
		+ "612056616e677561726400020052495600526976616c204775696c64000100020000"
		+ "72656400126461726b5f626c756500"))
	_expect(guild.type == "guild" and bool(guild.in_guild)
		and str(guild.tag) == "ELO" and str(guild.name) == "Eloria Vanguard"
		and str(guild.owner) == "Kellan" and str(guild.motd) == "Muster at dusk."
		and str(guild.url) == "https://example.test",
		"the guild state carries the guild whole, motd and all")
	_expect(int(guild.rank) == 20
		and (int(guild.permissions) & EloriaProtocol.GUILD_CAN_OWN) != 0
		and (int(guild.permissions) & EloriaProtocol.GUILD_CAN_LEAVE) == 0,
		"the reader is told their rank and exactly what it lets them do")
	_expect((guild.members as Array).size() == 2,
		"both members arrive")
	var guild_leader: Dictionary = (guild.members as Array)[0]
	var guild_absent: Dictionary = (guild.members as Array)[1]
	_expect(str(guild_leader.name) == "Kellan" and int(guild_leader.rank) == 20
		and bool(guild_leader.online) and bool(guild_leader.is_self)
		and bool(guild_leader.owner),
		"the owner's row is marked as the owner and as the reader's own")
	_expect(str(guild_absent.name) == "Maren" and not bool(guild_absent.online)
		and not bool(guild_absent.owner),
		"an offline member keeps a row and says so")
	_expect((guild.applicants as Array) == ["Toma"]
		and str(((guild.allies as Array)[0] as Dictionary).tag) == "RIV"
		and int(((guild.colours as Array)[0] as Dictionary).colour) == 18,
		"the applicant queue, the allies and the chosen colours all arrive")
	var guild_directory: Dictionary = (guild.directory as Array)[0]
	_expect(str(guild_directory.name) == "Eloria Vanguard"
		and int(guild_directory.members) == 2,
		"the directory carries the long name #join_guild wants, and a count")
	_expect(str(((guild.palette as Array)[1] as Dictionary).name) == "dark_blue"
		and int(((guild.palette as Array)[1] as Dictionary).colour) == 18,
		"the colour words #set_guild_color accepts travel with the state")

	# No guild is a state and not an omission: it still carries the price of
	# founding one and the directory to apply from.
	var guildless: Dictionary = EloriaProtocol.decode_server(213, _hex(
		"01000000003075000027140000000000000000000000000000000100456c6f726961"
		+ "2056616e6775617264000100454c4f00456c6f7269612056616e6775617264000200"
		+ "02000072656400126461726b5f626c756500"))
	_expect(guildless.type == "guild" and not bool(guildless.in_guild)
		and int(guildless.create_cost) == 30000
		and int(guildless.create_level) == 39 and int(guildless.join_level) == 20
		and (guildless.pending as Array) == ["Eloria Vanguard"]
		and (guildless.directory as Array).size() == 1,
		"a player in no guild is told the price, the queue and the directory")
	_expect(str(EloriaProtocol.decode_server(213, _hex("0100")).get("error", ""))
		== "guild_length",
		"a guild frame too short to hold its own header is refused")
	_expect(str(EloriaProtocol.decode_server(213,
		_hex("010000000000000000000000000000000000000000000000000000000000000000"))
			.get("error", "")) == "guild_trailing",
		"a guild frame with trailing bytes is refused")
	_expect(str(EloriaProtocol.decode_server(213,
		_hex("0100000000000000000000000000000000000200"))
			.get("error", "")) == "guild_members",
		"a guild frame promising more members than it carries is refused")
	_expect(str(EloriaProtocol.decode_server(213,
		_hex("010000000000000000000000000000000000"))
			.get("error", "")) == "guild_members",
		"a guild frame that ends before its first section is refused")
	_expect(str(EloriaProtocol.decode_server(213,
		_hex("010000000000000000000000000000")).get("error", "")) == "guild_text",
		"a guild frame that runs out inside its seven strings is refused")
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("guild_window_v1"),
		"the client advertises the guild window it can now draw")

	var marketplace: Dictionary = EloriaProtocol.decode_server(222, _hex(
		"00fa000000030000000100070000000c0000002300000058020000140053756e6c65"
		+ "616600416c69636500"))
	_expect(marketplace.type == "marketplace" and int(marketplace.gold) == 250
		and int(marketplace.returned_items) == 3
		and (marketplace.listings as Array).size() == 1,
		"the marketplace state decodes gold, escrow and its listings")
	var listing: Dictionary = (marketplace.listings as Array)[0]
	_expect(int(listing.listing_id) == 7 and int(listing.quantity) == 12
		and int(listing.unit_price) == 35 and int(listing.seconds_left) == 600
		and int(listing.image_id) == 20 and str(listing.item_name) == "Sunleaf"
		and str(listing.seller) == "Alice",
		"a listing carries its id, quantity, unit price, time left and seller")
	_expect(int(marketplace.version) == 1 and int(marketplace.offset) == 0
		and int(marketplace.total) == 1 and (marketplace.returns as Array).is_empty()
		and not bool(listing.own),
		"an older server's state reads as one unpaged page, nothing in escrow named")
	# market_window_v2: page 2 of a "lea" search. Taken from the server's own
	# builder (tests/test_marketplace_protocol.py in the server).
	var market_v2: String = ("00fa000000040000000200070000000c0000002300000058020000140053756e6c65"
		+ "616600416c6963650009000000020000002800000000828b011800536c6174650077"
		+ "72656e001400000039000000146c656100015075726368617365642053756e6c6561"
		+ "6620666f7220373020476f6c6420436f696e732e000001020003000000180001536c"
		+ "617465000100000014000253756e6c65616600")
	var paged: Dictionary = EloriaProtocol.decode_server(222, _hex(market_v2))
	_expect(paged.type == "marketplace" and int(paged.version) == 2
		and int(paged.offset) == 20 and int(paged.total) == 57
		and int(paged.page_size) == 20 and str(paged.query) == "lea",
		"a version-2 state says where its page sits in the whole search")
	_expect(int(paged.notice_kind) == EloriaProtocol.MARKET_NOTICE_DONE
		and str(paged.notice) == "Purchased Sunleaf for 70 Gold Coins.",
		"a version-2 state says how the last request went")
	var paged_rows: Array = paged.listings as Array
	_expect(paged_rows.size() == 2 and not bool((paged_rows[0] as Dictionary).own)
		and bool((paged_rows[1] as Dictionary).own)
		and int((paged_rows[1] as Dictionary).seconds_left) == 300 * 86400,
		"a version-2 state marks the player's own listing")
	var paged_returns: Array = paged.returns as Array
	_expect(paged_returns.size() == 2
		and str((paged_returns[0] as Dictionary).item_name) == "Slate"
		and int((paged_returns[0] as Dictionary).quantity) == 3
		and str((paged_returns[0] as Dictionary).reason) == "expired"
		and int((paged_returns[0] as Dictionary).image_id) == 24
		and str((paged_returns[1] as Dictionary).reason) == "cancelled",
		"a version-2 state names what waits in return escrow and why")
	for cut: int in [2, 12, 40, 44]:
		var short_hex: String = market_v2.substr(0, market_v2.length() - cut)
		_expect(str(EloriaProtocol.decode_server(222, _hex(short_hex))
			.get("type", "")) == "invalid",
			"a version-2 state cut short by %d hex digits is refused" % cut)

	var merchant: Dictionary = EloriaProtocol.decode_server(223, _hex(
		"5b00fa0000001400000050000000010053616c696e61000000280000000c00000005"
		+ "000000140053756e6c65616600"))
	_expect(merchant.type == "merchant" and int(merchant.actor_id) == 91
		and str(merchant.npc_name) == "Salina" and int(merchant.gold) == 250
		and int(merchant.carried) == 20 and int(merchant.capacity) == 80
		and (merchant.items as Array).size() == 1,
		"the merchant state decodes the NPC, the purse and the load")
	var stock: Dictionary = (merchant.items as Array)[0]
	_expect(int(stock.index) == 0 and int(stock.buy_price) == 40
		and int(stock.sell_price) == 12 and int(stock.owned) == 5
		and str(stock.name) == "Sunleaf",
		"a merchant row carries both prices and how many the player already has")
	var weighted_merchant := EloriaProtocol.decode_server(223, _hex(
		"5b00fa0000001400000050000000010053616c696e61000000280000000c00000005"
		+ "000000140053756e6c65616600010001000000"))
	_expect(int(weighted_merchant.items[0].emu) == 1,
		"the optional merchant weight supports carry previews")
	var described_merchant := EloriaProtocol.decode_server(223, _hex(
		"5b00fa0000001400000050000000010053616c696e61000000280000000c00000005"
		+ "000000140053756e6c656166000100010000000100412070616c65206c6561662e00"))
	_expect(described_merchant.type == "merchant"
		and described_merchant.items[0].description == "A pale leaf."
		and int(described_merchant.items[0].emu) == 1,
		"merchant descriptions and carry weights decode together")
	for trailer: String in ["01", "0200", "010041", "010000ff"]:
		var invalid_description := EloriaProtocol.decode_server(223, _hex(
			"5b00fa0000001400000050000000010053616c696e61000000280000000c00000005"
			+ "000000140053756e6c65616600010001000000" + trailer))
		_expect(invalid_description.has("error"), "incomplete or trailing merchant descriptions are refused")
	for trailer: String in ["020001000000", "0100010000"]:
		var invalid_merchant := EloriaProtocol.decode_server(223, _hex(
			"5b00fa0000001400000050000000010053616c696e61000000280000000c00000005"
			+ "000000140053756e6c65616600" + trailer))
		_expect(invalid_merchant.has("error"), "invalid merchant weights are refused")

	var journal: Dictionary = EloriaProtocol.decode_server(224, _hex(
		"01000001000000030000004b696c6c205468656d20416c6c00446566656174203320"
		+ "7261747300466f757220476174657300"))
	_expect(journal.type == "quest_journal"
		and (journal.entries as Array).size() == 1,
		"the quest journal decodes its entries")
	var quest: Dictionary = (journal.entries as Array)[0]
	_expect(not bool(quest.ready) and int(quest.current) == 1
		and int(quest.target) == 3 and str(quest.title) == "Kill Them All"
		and str(quest.objective) == "Defeat 3 rats"
		and str(quest.location) == "Four Gates",
		"a quest entry carries progress, readiness, objective and location")

	var detail: Dictionary = EloriaProtocol.decode_server(225, _hex(
		"a000020000000053756e6c656166005265736f75726365730000412070616c65206c"
		+ "6561662e00454d55203100477561726420436170650041726d6f7572203220"
		+ "2d3e203000"))
	_expect(detail.type == "item_detail" and int(detail.image_id) == 160
		and int(detail.quantity) == 2 and not bool(detail.equipped)
		and str(detail.name) == "Sunleaf" and str(detail.category) == "Resources"
		and str(detail.equip_type).is_empty()
		and str(detail.description) == "A pale leaf."
		and str(detail.stats) == "EMU 1"
		and str(detail.comparison_name) == "Guard Cape"
		and str(detail.comparison) == "Armour 2 -> 0",
		"item detail decodes every field including the empty equip type")

	var inventory_state: Dictionary = EloriaProtocol.decode_server(226, _hex(
		"fa000000140000005000000001000014000c00000001000000065375"
		+ "6e6c65616600466c6f7765727300"))
	_expect(inventory_state.type == "inventory_state"
		and int(inventory_state.gold) == 250
		and int(inventory_state.carried) == 20
		and int(inventory_state.capacity) == 80
		and (inventory_state.items as Array).size() == 1,
		"the inventory state decodes gold, carried weight and capacity")
	var organised: Dictionary = (inventory_state.items as Array)[0]
	_expect(int(organised.slot) == 0 and int(organised.image_id) == 20
		and int(organised.quantity) == 12 and int(organised.emu) == 1
		and str(organised.name) == "Sunleaf"
		and str(organised.category) == "Flowers",
		"an inventory entry carries the item name and category the ordinary"
			+ " inventory packet cannot")

	var combat: Dictionary = EloriaProtocol.decode_server(227, _hex(
		"016600120014001e002c00050052656564686f726e205374616700"))
	_expect(combat.type == "combat_state"
		and int(combat.event) == EloriaProtocol.COMBAT_EVENT_HIT
		and int(combat.target_id) == 102 and int(combat.player_health) == 18
		and int(combat.player_max_health) == 20
		and int(combat.target_health) == 30
		and int(combat.target_max_health) == 44
		and int(combat.recent_damage) == 5
		and str(combat.target_name) == "Reedhorn Stag",
		"the combat state decodes both health bars and the outcome")

	var mail: Dictionary = EloriaProtocol.decode_server(229, _hex(
		"01000300000000f1536500416c6963650048656c6c6f004d656574206d6520617420"
		+ "74686520676174652e00"))
	_expect(mail.type == "mail" and (mail.messages as Array).size() == 1,
		"the mail inbox decodes its messages")
	var message: Dictionary = (mail.messages as Array)[0]
	_expect(int(message.mail_id) == 3 and not bool(message.read)
		and str(message.sender) == "Alice" and str(message.subject) == "Hello"
		and str(message.body) == "Meet me at the gate.",
		"a mail message carries its id, read flag, sender, subject and body")

	var navigation: Dictionary = EloriaProtocol.decode_server(230, _hex(
		"010203e1010c00666f75725f676174657300526565642062616e6b00"))
	_expect(navigation.type == "navigation" and bool(navigation.active)
		and int(navigation.x) == 770 and int(navigation.y) == 481
		and int(navigation.distance) == 12
		and str(navigation.map_id) == "four_gates"
		and str(navigation.label) == "Reed bank",
		"the navigation state decodes the waypoint tile, distance and label")

	var events: Dictionary = EloriaProtocol.decode_server(232, _hex(
		"4861727665737420666573746976616c0050686173652032206f66203300"))
	_expect(events.type == "special_events"
		and (events.lines as Array) == ["Harvest festival", "Phase 2 of 3"],
		"the special-event panel decodes its NUL-delimited lines")
	_expect((EloriaProtocol.decode_server(232, PackedByteArray([0])).lines
			as Array).is_empty(),
		"a single empty line clears the panel rather than showing a blank row")

	# Every one of these rejects a truncated payload rather than half-decoding.
	for truncated: Array in [[222, "00fa0000000300000001000700"],
			[223, "5b00fa000000140000005000000001005361"],
			[224, "010000010000000300000041"],
			[225, "a00002000000005375"],
			[226, "fa0000001400000050000000010000140002"],
			[227, "016600120014001e002c000500"],
			[229, "01000300000000f153650041"],
			[230, "010203e1010c00666f75725f6761746573"]]:
		var rejected: Dictionary = EloriaProtocol.decode_server(
			int(truncated[0]), _hex(str(truncated[1])))
		_expect(rejected.type == "invalid",
			"a truncated command %d payload is rejected" % int(truncated[0]))

	# Which visible effects an actor is under. The only bit this server sets is
	# doubled movement speed, and it states the whole mask each time.
	var hastened: Dictionary = EloriaProtocol.decode_server(78, _hex(
		"4d00000400 00".replace(" ", "")))
	_expect(hastened.type == "actor_buffs" and int(hastened.actor_id) == 77
		and int(hastened.buffs) == EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED,
		"an actor buff mask decodes its actor and its bits")
	_expect(int(EloriaProtocol.decode_server(78,
			_hex("4d0000000000")).buffs) == 0,
		"the mask going empty is stated, not implied by silence")
	_expect(EloriaProtocol.decode_server(78, _hex("4d000004")).type == "invalid",
		"a truncated actor buff mask is rejected")

	# Ranged combat. Both fixtures are the server's own builder output: it
	# sends an aim before every shot and a fire when it looses.
	var aim: Dictionary = EloriaProtocol.decode_server(84, _hex("5b004d00"))
	_expect(aim.type == "missile" and not bool(aim.fired)
		and int(aim.source_actor_id) == 91
		and int(aim.target_actor_id) == 77,
		"an aim decodes the shooter and the target")
	var loosed: Dictionary = EloriaProtocol.decode_server(86, _hex("5b004d00"))
	_expect(loosed.type == "missile" and bool(loosed.fired)
		and int(loosed.source_actor_id) == 91,
		"a shot is told apart from an aim by its command, not its payload")
	for truncated: Array in [[84, "5b00"], [86, "5b004d0000"]]:
		_expect(EloriaProtocol.decode_server(int(truncated[0]),
				_hex(str(truncated[1]))).type == "invalid",
			"a malformed command %d payload is rejected" % int(truncated[0]))

	# Effects the server says happened in the world.
	var swarm: Dictionary = EloriaProtocol.decode_server(79, _hex("115b00"))
	_expect(swarm.type == "special_effect" and int(swarm.effect) == 17
		and int(swarm.actor_id) == 91 and int(swarm.target_id) == -1,
		"an effect at one actor decodes without inventing a target")
	var thrown: Dictionary = EloriaProtocol.decode_server(79, _hex("025b004d00"))
	_expect(thrown.type == "special_effect" and int(thrown.effect) == 2
		and int(thrown.actor_id) == 91 and int(thrown.target_id) == 77,
		"an effect between two actors decodes both of them")
	for malformed: String in ["11", "115b0000", "115b004d0000"]:
		_expect(EloriaProtocol.decode_server(79, _hex(malformed)).type == "invalid",
			"a malformed special effect is rejected (%s)" % malformed)

	# Guild tags. The server builds one display string - an optional colour
	# byte, the name, a space, an optional colour byte and the tag - and both
	# fixtures below are that builder's exact output.
	var tagged: Dictionary = EloriaProtocol.decode_server(51, _hex(
		"5b000203e1010000000001000001020304050b001e14071400120001416c6963652083"
		+ "454c4f000040ff0600"))
	_expect(tagged.type == "actor_spawn" and str(tagged.name) == "Alice"
		and str(tagged.guild_tag) == "ELO" and int(tagged.guild_colour) == 4
		and int(tagged.name_colour) == 0,
		"a display name splits into the name and the tag, with their colours:"
			+ " %s / %s" % [str(tagged.name), str(tagged.guild_tag)])
	var untagged: Dictionary = EloriaProtocol.decode_server(51, _hex(
		"5b000203e1010000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	_expect(str(untagged.name) == "Alice" and str(untagged.guild_tag).is_empty()
		and int(untagged.guild_colour) == 0,
		"a player in no guild has no tag rather than an empty-looking one")
	# The server writes a colour as chr(127 + colour); 0x89 is colour 10.
	var coloured: Dictionary = EloriaProtocol.decode_actor_name(
		_hex("89416c696365"))
	_expect(str(coloured.name) == "Alice" and int(coloured.name_colour) == 10,
		"a name the server coloured keeps the colour and loses the marker byte")
	# Creatures have no guild, and their names have spaces in them. The plain
	# actor packet is the one they arrive in.
	var creature: Dictionary = EloriaProtocol.decode_server(1, _actor_named(
		"Mirrorfin Otter"))
	_expect(str(creature.name) == "Mirrorfin Otter"
		and str(creature.guild_tag).is_empty(),
		"a two-word creature name is not split into a name and a guild tag: %s / %s"
			% [str(creature.name), str(creature.guild_tag)])
	var summoned: Dictionary = EloriaProtocol.decode_server(1, _actor_named(
		"Mirrorfin Otter", 4))
	_expect(str(summoned.name) == "Mirrorfin Otter"
		and int(summoned.name_colour) == 4
		and str(summoned.guild_tag).is_empty(),
		"a summoned creature keeps its whole name and loses the colour marker: %s"
			% str(summoned.name))

	# Asking what is lying on the ground. The bag packet carries an image id
	# and a quantity, so the name can only come from the server.
	_expect_bytes("look at ground item fixture",
		EloriaProtocol.look_at_ground_item(3),
		PackedByteArray([24, 2, 0, 3]))

	# Spell power. The trailing byte is the fork's addition to the legacy cast
	# frame; without a power the frame is exactly the legacy one.
	_expect_bytes("legacy cast fixture", EloriaProtocol.cast_spell([19, 15, 21]),
		PackedByteArray([39, 5, 0, 3, 19, 15, 21]))
	_expect_bytes("powered cast fixture",
		EloriaProtocol.cast_spell([19, 15, 21], 4),
		PackedByteArray([39, 6, 0, 3, 19, 15, 21, 4]))
	var powers: Dictionary = EloriaProtocol.decode_server(231, _hex(
		"0200 0104 736869656c6400 0301 6865616c00".replace(" ", "")))
	_expect(powers.type == "spell_power"
		and (powers.effects as Array).size() == 2,
		"the spell-power state decodes one row per effect")
	var shield_power: Dictionary = (powers.effects as Array)[0]
	var heal_power: Dictionary = (powers.effects as Array)[1]
	_expect(str(shield_power.effect) == "shield"
		and int(shield_power.preferred) == 1 and int(shield_power.limit) == 4
		and str(heal_power.effect) == "heal"
		and int(heal_power.preferred) == 3 and int(heal_power.limit) == 1,
		"each row carries the effect, the preferred power and the limit")
	for broken: String in ["02000104", "01000104", "010001047368690000"]:
		_expect(EloriaProtocol.decode_server(231, _hex(broken)).type == "invalid",
			"a malformed spell-power payload is rejected (%s)" % broken)

	# Looking at a player. The reply states the actor, the name and the
	# achievements, so nothing is paired with a remembered request and no
	# achievement catalog is duplicated in the client.
	_expect_bytes("look at player fixture", EloriaProtocol.look_at_player(91),
		PackedByteArray([5, 5, 0, 91, 0, 0, 0]))
	var described: Dictionary = EloriaProtocol.decode_server(228, _hex(
		"5b000100416c69636500426567696e6e6572205475746f7269616c00"))
	_expect(described.type == "player_info" and int(described.actor_id) == 91
		and str(described.name) == "Alice"
		and (described.achievements as Array) == ["Beginner Tutorial"],
		"the player-info reply names the actor and its achievements")
	var bare: Dictionary = EloriaProtocol.decode_server(228, _hex(
		"5b000000416c69636500"))
	_expect(bare.type == "player_info"
		and (bare.achievements as Array).is_empty(),
		"a player with nothing earned decodes to an empty list, not a failure")
	_expect(str(bare.get("title", "?")) == "",
		"a server that sends no title is not a failure; the field is absent")
	# The worn title, appended after the achievements. A server without titles
	# sends the frame above unchanged, which is the whole reason it is a
	# trailing field rather than one slotted into the middle.
	var titled: Dictionary = EloriaProtocol.decode_server(228, _hex(
		"5b0001004100466972737420426c6f6f64007468652043756c6c657200"))
	_expect(titled.type == "player_info"
		and str(titled.title) == "the Culler"
		and (titled.achievements as Array) == ["First Blood"],
		"the player-info reply carries the title they are wearing")
	# The last of these is an empty title followed by a byte that is nothing:
	# one trailing NUL is now a player wearing no title, which is a real answer.
	for malformed: Array in [[228, "5b0001"], [228, "5b000200416c69636500"],
			[228, "5b000000416c696365000000"]]:
		_expect(EloriaProtocol.decode_server(int(malformed[0]),
				_hex(str(malformed[1]))).type == "invalid",
			"a malformed player-info payload is rejected (%s)" % str(malformed[1]))

	# Map markers. The server owns them entirely: 90 places one, 91 takes it
	# away, and the map is named by the server's own file reference.
	var marker: Dictionary = EloriaProtocol.decode_server(90, _hex(
		"ea010c03e1012e2f6d6170732f666f75725f67617465732e656c6d00"
		+ "526565642062616e6b00"))
	_expect(marker.type == "map_marker" and int(marker.marker_id) == 490
		and int(marker.x) == 780 and int(marker.y) == 481
		and str(marker.map_id) == "four_gates"
		and str(marker.label) == "Reed bank",
		"a map marker decodes its id, tile, map and label")
	var attached: Dictionary = EloriaProtocol.decode_server(90, _hex(
		"ea010c03e1012e2f6d6170732f666f75725f67617465732e656c6d00"
		+ "526565642062616e6b0060ea"))
	_expect(attached.type == "map_marker" and attached.actor_id == 60000,
		"a creature marker decodes its explicit 16-bit actor identity")
	_expect(EloriaProtocol.map_id_from_reference("./maps/four_gates.elm")
			== "four_gates"
		and EloriaProtocol.map_id_from_reference("four_gates") == "four_gates",
		"the map reference reduces to the map id the client already knows")
	var removed: Dictionary = EloriaProtocol.decode_server(91, _hex("ea01"))
	_expect(removed.type == "remove_map_marker"
		and int(removed.marker_id) == 490,
		"removing a marker names the id and nothing else")
	for broken: Array in [[90, "ea010c03"], [90, "ea010c03e1012e2f6d6170"],
			[91, "ea0100"]]:
		_expect(EloriaProtocol.decode_server(int(broken[0]),
				_hex(str(broken[1]))).type == "invalid",
			"a malformed command %d payload is rejected" % int(broken[0]))

	# Harvesting and world objects. HARVEST(21), USE_MAP_OBJECT(16) and
	# LOOK_AT_MAP_OBJECT(27) were enum values with no encoder, and there was no
	# world-object pick path at all.
	_expect_bytes("harvest fixture", EloriaProtocol.harvest(0x0201),
		PackedByteArray([21, 3, 0, 0x01, 0x02]))
	_expect_bytes("use map object fixture", EloriaProtocol.use_map_object(0x04030201),
		PackedByteArray([16, 5, 0, 0x01, 0x02, 0x03, 0x04]))
	_expect_bytes("look at map object fixture",
		EloriaProtocol.look_at_map_object(0x04030201),
		PackedByteArray([27, 5, 0, 0x01, 0x02, 0x03, 0x04]))
	var map_objects_payload: PackedByteArray = PackedByteArray([1, 2, 0])
	map_objects_payload.append_array(PackedByteArray([
		0xf0, 0x01, EloriaProtocol.MAP_OBJECT_HARVEST, 0x02, 0x03, 0xe1, 0x01]))
	map_objects_payload.append_array(_nul_bytes("Reed"))
	map_objects_payload.append_array(_nul_bytes("Harvesting level 0"))
	map_objects_payload.append_array(PackedByteArray([
		0x0e, 0x00, EloriaProtocol.MAP_OBJECT_INTERACTIVE, 0x00, 0x03, 0x90, 0x05]))
	map_objects_payload.append_array(_nul_bytes("Storage"))
	map_objects_payload.append_array(_nul_bytes("A wayfarer's cache."))
	var map_objects: Dictionary = EloriaProtocol.decode_server(236, map_objects_payload)
	_expect(map_objects.type == "map_objects" and bool(map_objects.first)
		and (map_objects.objects as Array).size() == 2,
		"the map-object list decodes every entry and flags the first chunk")
	var harvest_object: Dictionary = (map_objects.objects as Array)[0]
	var interactive_object: Dictionary = (map_objects.objects as Array)[1]
	_expect(int(harvest_object.object_id) == 496
		and int(harvest_object.kind) == EloriaProtocol.MAP_OBJECT_HARVEST
		and int(harvest_object.x) == 770 and int(harvest_object.y) == 481
		and str(harvest_object.label) == "Reed"
		and str(harvest_object.detail) == "Harvesting level 0",
		"a harvest node carries its id, tile, resource name and requirement")
	_expect(int(interactive_object.object_id) == 14
		and int(interactive_object.kind) == EloriaProtocol.MAP_OBJECT_INTERACTIVE
		and int(interactive_object.y) == 1424,
		"an interactive carries its id and tile in the same list")
	var exit_payload: PackedByteArray = PackedByteArray([1, 1, 0])
	exit_payload.append_array(PackedByteArray([
		0x60, 0xea, EloriaProtocol.MAP_OBJECT_EXIT, 0x2c, 0x01, 0x0e, 0x00]))
	exit_payload.append_array(_nul_bytes("Grey Moors"))
	exit_payload.append_array(_nul_bytes("The way to Grey Moors."))
	var exit_objects: Dictionary = EloriaProtocol.decode_server(236, exit_payload)
	var exit_object: Dictionary = (exit_objects.objects as Array)[0]
	_expect(exit_objects.type == "map_objects" and int(exit_object.object_id) == 60000
		and int(exit_object.kind) == EloriaProtocol.MAP_OBJECT_EXIT
		and int(exit_object.x) == 300 and int(exit_object.y) == 14
		and str(exit_object.label) == "Grey Moors",
		"a map exit is a third kind in the same list, named for where it leads")
	_expect(EloriaProtocol.decode_server(236, PackedByteArray([1, 1])).error
			== "map_objects_length"
		and EloriaProtocol.decode_server(236,
			PackedByteArray([1, 1, 0, 1, 0, 9, 1, 0, 1, 0, 0, 0])).error
			== "map_object_kind"
		and EloriaProtocol.decode_server(236,
			map_objects_payload.slice(0, map_objects_payload.size() - 1)).type
			== "invalid",
		"short, unknown-kind and truncated map-object lists are rejected")
	var harvest_started: PackedByteArray = PackedByteArray([1, 0xf0, 0x01])
	harvest_started.append_array(_nul_bytes("Reed"))
	var harvest_state: Dictionary = EloriaProtocol.decode_server(237, harvest_started)
	_expect(harvest_state.type == "harvest_state" and bool(harvest_state.active)
		and int(harvest_state.object_id) == 496
		and str(harvest_state.resource) == "Reed",
		"the harvest state names the node and resource rather than a chat phrase")
	var harvest_stopped: Dictionary = EloriaProtocol.decode_server(237,
		PackedByteArray([0, 0, 0, 0]))
	_expect(harvest_stopped.type == "harvest_state" and not bool(harvest_stopped.active)
		and str(harvest_stopped.resource).is_empty(),
		"a stop is explicit, not the absence of a message")
	_expect(EloriaProtocol.decode_server(237, PackedByteArray([1, 0, 0])).error
			== "harvest_state_length"
		and EloriaProtocol.decode_server(237, PackedByteArray([1, 0, 0, 65])).error
			== "harvest_state_resource",
		"a short or unterminated harvest state is rejected")

	# Server popups. The server had no way to ask the player a question:
	# DISPLAY_POPUP(83) fell through to an unknown packet and POPUP_REPLY(50)
	# had no encoder at all.
	var popup_payload: PackedByteArray = PackedByteArray([0, 0, 0])
	popup_payload.append_array(_sized("Summon Behavior"))
	popup_payload.append_array(PackedByteArray([0x68, 0x01]))
	popup_payload.append_array(_sized("Choose how your summons pick targets."))
	popup_payload.append_array(PackedByteArray([9, 1]))
	popup_payload.append_array(_sized("Weakest first"))
	popup_payload.append(0)
	popup_payload.append_array(PackedByteArray([9, 1]))
	popup_payload.append_array(_sized("Strongest first"))
	popup_payload.append(1)
	popup_payload.append_array(PackedByteArray([1, 2]))
	popup_payload.append_array(_sized("This applies to every summon."))
	var popup: Dictionary = EloriaProtocol.decode_server(83, popup_payload)
	_expect(popup.type == "popup" and int(popup.popup_id) == 0
		and str(popup.title) == "Summon Behavior" and int(popup.size_hint) == 360
		and str(popup.text) == "Choose how your summons pick targets."
		and (popup.options as Array).size() == 3,
		"a real server popup decodes its id, title, size hint, text and options")
	var first_option: Dictionary = (popup.options as Array)[0]
	var third_option: Dictionary = (popup.options as Array)[2]
	_expect(int(first_option.option_type) == EloriaProtocol.POPUP_RADIO_OPTION
		and int(first_option.group) == 1 and int(first_option.value) == 0
		and str(first_option.label) == "Weakest first",
		"a radio option carries its group and its wire value")
	_expect(int(third_option.option_type) == EloriaProtocol.POPUP_DISPLAY_TEXT
		and not third_option.has("value"),
		"a display-text option carries no value byte")
	var entry_payload: PackedByteArray = PackedByteArray([7, 0, 0])
	entry_payload.append_array(_sized("Name"))
	entry_payload.append_array(PackedByteArray([0, 1]))
	entry_payload.append_array(_sized("Body"))
	entry_payload.append_array(PackedByteArray([0, 4]))
	entry_payload.append_array(_sized("Your answer"))
	var entry_popup: Dictionary = EloriaProtocol.decode_server(83, entry_payload)
	_expect(entry_popup.type == "popup" and int(entry_popup.popup_id) == 7
		and int((entry_popup.options as Array)[0].option_type)
			== EloriaProtocol.POPUP_TEXT_ENTRY
		and int((entry_popup.options as Array)[0].group) == 4,
		"a text-entry option decodes without a value byte")
	_expect(EloriaProtocol.decode_server(83, PackedByteArray([0, 0, 0, 1, 65])).error
			== "popup_length"
		and EloriaProtocol.decode_server(83,
			PackedByteArray([0, 0, 9, 1, 65, 1, 0, 1, 66])).error == "popup_flags",
		"a truncated popup and a popup with unsupported flags are both rejected")
	var bad_option: PackedByteArray = PackedByteArray([0, 0, 0])
	bad_option.append_array(_sized("T"))
	bad_option.append_array(PackedByteArray([0, 0]))
	bad_option.append_array(_sized("B"))
	bad_option.append_array(PackedByteArray([7, 1]))
	bad_option.append_array(_sized("X"))
	_expect(EloriaProtocol.decode_server(83, bad_option).error == "popup_option_type",
		"an option type the client does not implement is rejected, not guessed")
	_expect_bytes("popup reply fixture",
		EloriaProtocol.popup_reply(0, {1: 2}),
		PackedByteArray([50, 5, 0, 0, 0, 1, 2]))
	_expect_bytes("popup reply text-entry fixture",
		EloriaProtocol.popup_reply(7, {4: "Hi"}),
		PackedByteArray([50, 8, 0, 7, 0, 4, 0, 2, 72, 105]))
	_expect_bytes("popup reply multi-group fixture",
		EloriaProtocol.popup_reply(3, {2: 9, 1: 5}),
		PackedByteArray([50, 7, 0, 3, 0, 1, 5, 2, 9]))
	_expect_bytes("popup reply with no answer fixture",
		EloriaProtocol.popup_reply(3, {}),
		PackedByteArray([50, 3, 0, 3, 0]))

	# The one popup the real server sends today, byte for byte as
	# protocol.summon_behavior_popup() builds it. The reply this client
	# produces for it is fed back into the server's own POPUP_REPLY handler by
	# tests/test_popup_round_trip.py in the server repository.
	var summon_popup: Dictionary = EloriaProtocol.decode_server(83, _hex(
		"0000000f53756d6d6f6e204265686176696f7268013943686f6f736520686f7720796f7572"
		+ "2073756d6d6f6e6564206372656174757265732073686f756c642073656c6563742074617267"
		+ "6574732e09010d446f206e6f742061747461636b0109011241747461636b206d79206f70706f"
		+ "6e656e7400090119446f206e6f742061747461636b206d79206f70706f6e656e740209011e41"
		+ "747461636b206f6e6c792073756d6d6f6e65642063726561747572657303090120446f206e6f"
		+ "742061747461636b2073756d6d6f6e6564206372656174757265730409010e41747461636b20"
		+ "61742077696c6c05"))
	_expect(summon_popup.type == "popup" and int(summon_popup.popup_id) == 0
		and str(summon_popup.title) == "Summon Behavior"
		and (summon_popup.options as Array).size() == 6,
		"the real server's summon-behaviour popup decodes completely")
	var summon_values: Array[int] = []
	var summon_groups: Dictionary = {}
	for raw_summon_option: Variant in summon_popup.options as Array:
		var summon_option: Dictionary = raw_summon_option as Dictionary
		_expect(int(summon_option.option_type) == EloriaProtocol.POPUP_RADIO_OPTION,
			"every summon-behaviour option is a radio option")
		summon_values.append(int(summon_option.value))
		summon_groups[int(summon_option.group)] = true
	_expect(summon_values == [1, 0, 2, 3, 4, 5] and summon_groups.size() == 1,
		"the six behaviour values arrive in the server's order in one group")
	_expect_bytes("summon behaviour reply fixture",
		EloriaProtocol.popup_reply(0, {1: 5}),
		PackedByteArray([50, 5, 0, 0, 0, 1, 5]))

	# Decoded fields must have a consumer or not be decoded at all.
	var idle_actor: Dictionary = EloriaProtocol.decode_server(1, _actor_bytes(
		EloriaProtocol.FRAME_IDLE))
	var fighting_actor: Dictionary = EloriaProtocol.decode_server(1, _actor_bytes(
		EloriaProtocol.FRAME_COMBAT_IDLE))
	_expect(idle_actor.type == "actor_spawn" and not bool(idle_actor.in_combat)
		and fighting_actor.type == "actor_spawn" and bool(fighting_actor.in_combat),
		"the actor frame decides whether an actor arrives already in combat")
	var npc_info: Dictionary = EloriaProtocol.decode_server(33,
		_padded_name("Ferryman", 20) + PackedByteArray([7]))
	_expect(npc_info.type == "npc_info" and str(npc_info.name) == "Ferryman"
		and not npc_info.has("portrait"),
		"the NPC portrait byte is not carried into a DTO with no artwork to render it")
	var owned_sigils: Dictionary = EloriaProtocol.decode_server(42,
		PackedByteArray([0b1001, 0, 0, 0, 0, 0, 0, 0]))
	_expect(owned_sigils.type == "sigils" and owned_sigils.owned == [0, 3]
		and not owned_sigils.has("low_mask") and not owned_sigils.has("high_mask"),
		"sigil ownership is the decoded list, not the list plus its raw masks")
	var inventory_entry: PackedByteArray = PackedByteArray([
		1, 0x12, 0x34, 4, 0, 0, 0, 5, 8])
	var uid_free_inventory: Dictionary = EloriaProtocol.decode_server(19, inventory_entry)
	_expect(uid_free_inventory.type == "inventory"
		and not (uid_free_inventory.items as Array)[0].has("uid"),
		"inventory entries are eight bytes with no UID this server ever sends")
	var uid_entry: PackedByteArray = inventory_entry.duplicate()
	uid_entry.append_array(PackedByteArray([9, 0]))
	_expect(EloriaProtocol.decode_server(19, uid_entry).error == "inventory_length"
		and EloriaProtocol.decode_server(21,
			uid_entry.slice(1)).error == "inventory_update_length",
		"the ten-byte legacy entry is rejected rather than half-decoded")
	var storage_offer: Dictionary = EloriaProtocol.decode_server(35,
		PackedByteArray([3, 0, 4, 0, 0, 0, 2, 1, 0]))
	_expect(int(storage_offer.source_type) == 2,
		"a trade offer states whether it came from the backpack or from storage")
	var cooldown_frame: Dictionary = EloriaProtocol.decode_server(77,
		PackedByteArray([2, 0x2c, 0x01, 0x0e, 0x00]))
	var first_cooldown: Dictionary = (cooldown_frame.cooldowns as Array)[0]
	_expect(int(first_cooldown.maximum_seconds) == 300
		and int(first_cooldown.remaining_seconds) == 14,
		"a cooldown carries the full duration, which is what makes progress drawable")

	print("protocol tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect_bytes(label: String, actual: PackedByteArray, expected: PackedByteArray) -> void:
	_expect(actual == expected, label + ": " + actual.hex_encode())

## The same body as _actor_bytes(), for a caller that cares about the name
## rather than the frame.
func _actor_named(display_name: String, name_colour := 0) -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		5, 0, 10, 0, 12, 0, 0, 0, 0, 0, 3, 0, 20, 0, 20, 0, 3])
	# The colour marker is one raw byte above the ASCII range, not a character
	# that survives a UTF-8 encode.
	if name_colour > 0:
		payload.append(127 + name_colour)
	payload.append_array(_nul_bytes(display_name))
	return payload

## A minimal legacy ADD_NEW_ACTOR body: id, x, y, unused z, rotation, type,
## frame, max health, health, kind, then a NUL-terminated name.
func _actor_bytes(frame: int) -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		5, 0, 10, 0, 12, 0, 0, 0, 0, 0, 3, frame, 20, 0, 20, 0, 3])
	payload.append_array(_nul_bytes("Rat"))
	return payload

## An ADD_NEW_ACTOR_EXTENDED body with a 16-bit actor type, as captured from
## the real server for a Lakeglass Drake.
func _actor_bytes_extended() -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		0x65, 0x00, 0x02, 0x03, 0xe1, 0x01, 0x00, 0x00, 0x00, 0x00,
		0x93, 0x01, 0x07, 0x84, 0x00, 0x84, 0x00, 0x05])
	payload.append_array(_nul_bytes("Lakeglass Drake"))
	return payload

## The legacy length-prefixed string: one count byte then that many bytes.
func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

## The legacy length-prefixed string: one count byte then that many bytes.
func _sized(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	var sized: PackedByteArray = PackedByteArray([bytes.size()])
	sized.append_array(bytes)
	return sized

func _padded_name(value: String, size: int) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	while bytes.size() < size:
		bytes.append(0)
	return bytes.slice(0, size)

func _nul_bytes(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

func _expect(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		push_error(label)
