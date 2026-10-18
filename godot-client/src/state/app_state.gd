extends Node

signal state_changed(path: StringName)
signal login_succeeded
signal login_failed(message: String)
signal character_created
signal character_creation_failed(message: String)
signal floating_feedback_requested(feedback: Dictionary)
## Something the server said happened in the world, at an actor and sometimes
## towards another. It is an event rather than state - there is nothing to be
## true a moment later - so it is announced and not stored.
signal special_effect_requested(effect: Dictionary)
## An actor is playing a named animation action - an emote, or anything else
## the server asks for that is not one of the actor commands. An event rather
## than state: it happens once and is over, so nothing keeps it.
signal actor_animation_requested(animation: Dictionary)
## An arrow the server said was loosed, between the two actors it named. Like
## an effect it is an event rather than state: the shot is already resolved by
## the time it arrives, and the damage comes in its own packet.
signal missile_fired(shot: Dictionary)
## An arrow on its way to a tile rather than to an actor - a practice shot, or
## a miss the server placed. Carries the tile because that is where it lands.
signal ground_missile_fired(shot: Dictionary)
## A sound the server placed somewhere on the map, and the music bed it wants
## under the map the player is standing on. Both are events, not state: the
## client owns what is currently sounding.
## The fires the server has placed on this map, keyed by tile. State rather
## than an event: a fire keeps burning, so a client arriving later is told
## about it the same way.
var fires: Dictionary = {}
## The sky over this map, as {"kind": int, "intensity": int}.
var weather: Dictionary = {"kind": 0, "intensity": 0}
## The whole sky from a weather_state_v1 server: {current, target, seconds,
## name, at_msec}; empty while the server speaks only the legacy frames.
var weather_state: Dictionary = {}

## Which quest the NPC is talking about, and which quests have been finished
## this session. `quest_dialogue` is true only while the server has flagged the
## next line and not yet sent it.
var quest_dialogue := false
var current_quest_id := 0
var finished_quests: Array[int] = []

## The player's buddy list, as {name: online}. The server owns the list and
## states all of it at login, so this is a view of what arrived rather than a
## copy the client maintains.
var buddies: Dictionary = {}
## Objects the server placed into this map after it loaded, by object id, and
## the tiles it said are ways off the map.
var world_objects: Dictionary = {}
var teleporters: Array[Vector2i] = []

## A teleport happening at a place. An event: it is over as soon as it is drawn.
signal teleport_seen(teleport: Dictionary)

## One clap of thunder. An event: it happens once and is over.
signal thunder_struck(severity: int)
signal sound_requested(sound: Dictionary)
signal music_requested(track: String)

var connection_state := "disconnected"
var authenticated := false
var local_actor_id := -1
var current_map := ""
## The land neighbours of the current map by the handle their actors' packets
## carry in the stock "z" field (ELORIA_ADJACENT_MAPS); 0 is the current map.
var adjacent_maps: Dictionary = {}
var lantern_tutorial: Dictionary = {}
var actors: Dictionary = {}
## Optional coarse actor-command reducer. The descriptor is generated only by
## the native benchmark build, and this instance exists only for an explicit
## opt-in, so an ordinary source checkout keeps the GDScript path unchanged.
var _native_crowd_reducer: Object
## The ids of actors written since the presentation last read them. Every
## site that writes `actors` records the id here and `take_changed_actors`
## hands the set over, so a frame with one moving creature costs one actor's
## worth of presentation work rather than the whole map's.
var changed_actors: Dictionary = {}
var inventory: Dictionary = {}
## Slot to the name the server calls what is in it, for the same positions
## `inventory` uses. Kept apart from the entries rather than merged into
## them because the two arrive on their own packets and either may land
## first; a consumer that needs a name asks here and copes with not
## finding one, which is also what an older server gets it.
var inventory_names: Dictionary = {}
var inventory_text := ""
var inventory_metadata_dirty := false
var _inventory_text_generation := 0
var inventory_cooldowns: Dictionary = {}
var active_spells: Dictionary = {}
var last_spell_result: Dictionary = {}
signal magic_state_received(data: Dictionary)
var pending_spell_target := ""
var stats: Dictionary = {}
var game_minute := 0
var game_minute_anchor_msec := 0
## How long the server actually takes between two game minutes, measured
## rather than assumed, so the client can carry the clock forward smoothly
## between packets without hard-coding the server's tick.
var game_minute_interval_msec := 0
var server_timestamp := 0
var chat_lines: Array[Dictionary] = []
var active_channels: Array[int] = [0, 0, 0]
var active_channel_index := 0
var selected_actor_id := -1
## The server's technique state (ELORIA_MAGIC_STATE kind "techniques"): the
## rows, the real action points, what is readied and held. Empty until a
## techniques_v1 server says otherwise. `received_msec` dates the cooldowns.
var techniques: Dictionary = {}
## Repeat casting as the server states it (kind "autocast"): `enabled` is the
## player's switch, `active` whether a spell is repeating now and which.
var autocast: Dictionary = {}
## Debuffs shown under a creature's name. Keep in step with
## status_effect_icons.gd NEGATIVE (that script preloads art; this one must not).
const NEGATIVE_STATUSES := ["poison", "cripple", "expose_heat", "expose_cold",
	"expose_magic", "expose_radiation", "stun", "root", "sunder", "mark", "challenge"]
var npc_dialogue: Dictionary = {"open": false, "name": "", "text": "",
	"options": [], "quest": false, "quest_id": 0}
var trade: Dictionary = {"open": false, "partner": "", "storage_available": false,
	"source_inventory": {}, "own_offers": {}, "other_offers": {},
	"own_accepts": 0, "other_accepts": 0}
var storage: Dictionary = {"open": false, "categories": [], "category_id": -1,
	"items": {}, "text": ""}
var ground_bags: Dictionary = {}
var ground_bag: Dictionary = {"open": false, "bag_id": -1, "items": {}}
## What the character is currently reading. The server models a book as
## research: pages remaining tick down and the knowledge bit is set on
## completion, so this is derived from the authoritative statistics rather than
## from a page-turning protocol the server has no content for.
var reading: Dictionary = {"active": false, "index": -1, "pages_read": 0,
	"pages_total": 0}
var known_knowledge: Array[int] = []
var selected_knowledge: int = -1
var knowledge_text: String = ""
## The nine Eloria extension windows. Each is a server-push snapshot: the
## server states the whole window and the client renders it, so none of these
## is merged with a previous value or reconstructed from anything else.
var marketplace: Dictionary = _empty_marketplace_state()
var merchant: Dictionary = {"open": false, "actor_id": -1, "npc_name": "",
	"gold": 0, "carried": 0, "capacity": 0, "items": []}
var quest_journal: Array[Dictionary] = []
## What this character has finished. Held separately from the journal because
## the two answer different questions and arrive in different packets: the
## journal is what is open now, this is the record that outlives the machine.
var quest_archive: Array[Dictionary] = []
## Worn goods, stated two ways because the two wires carry different identity.
## `degraded_item_names` serves every window that knows an item's name; the
## inventory grid knows only an image id, and a worn item shares its artwork
## with the fresh one, so for those slots the server states the answer.
var degraded_item_names: Dictionary = {}
var worn_slots_mask: int = 0
## Everything countable this character has done: the achievement tallies and
## the achievements themselves, which used to exist only as a chat dump.
var achievements_state: Dictionary = {"counters": [], "completed": []}
## The authored achievement catalogue and this character's progress on it, as
## {worn_title, entries}. Every entry carries its own name, description,
## category, progress and threshold: the catalogue is a server config file, so
## a client copy of it would go stale the first time a threshold moved.
var achievements_catalog: Dictionary = {"worn_title": "", "entries": []}
## What each player on this map is calling themselves, {actor_id: title}. Kept
## apart from the actor's display name, which carries a colour byte, the name
## and the guild tag in one string that every client unpicks by hand.
var actor_titles: Dictionary = {}
## What each NPC shown does for a living, {actor_id: occupation}, drawn as a
## second line under the name. Belongs to the actor rather than to the map:
## the server restates it whenever it shows the actor, so a row goes when its
## actor is removed, and a seamless land crossing that keeps the actors keeps
## their rows too.
var actor_occupations: Dictionary = {}
var actor_mounts: Dictionary = {}
## NPCs with a new quest this player can accept, stated by the server.
var quest_offer_actors: Dictionary = {}
## True lifetime experience per skill, keyed by skill name, and what it has
## bought past the level ceiling. Held separately from `stats` because the
## legacy stats packet carries the same numbers through a 32-bit window and
## the two would disagree above four billion - this one is the truth.
var experience64: Dictionary = {}
## How much ground each actor type stands on, as {actor_type: Vector2i(w, d)}.
## Per species rather than per actor, and stated once at login. A type that
## is absent stands on one tile, which is nearly all of them.
##
## This decides where a model is drawn: the tile an actor reports is the
## anchor of its box, and for an even-sized box the anchor is not the centre,
## so without this a two-by-two creature would be drawn half a tile off the
## ground the server has reserved for it.
var actor_footprints: Dictionary = {}

## The footprint of an actor type, defaulting to a single tile.
func mark_actor_changed(actor_id: int) -> void:
	changed_actors[actor_id] = true

func mark_all_actors_changed() -> void:
	for actor_id: Variant in actors:
		changed_actors[actor_id] = true

## The changed set, emptied for the next frame.
func take_changed_actors() -> Dictionary:
	var taken: Dictionary = changed_actors
	changed_actors = {}
	return taken

func footprint_for_actor_type(actor_type: int) -> Vector2i:
	var size: Variant = actor_footprints.get(actor_type)
	return size if size is Vector2i else Vector2i.ONE

func post_cap_points_for(skill: String) -> int:
	var row: Variant = experience64.get(skill)
	return int((row as Dictionary).get("post_cap_points", 0)) if row is Dictionary else 0

func is_degraded_item(name: String) -> bool:
	return degraded_item_names.has(name)

func is_worn_slot(slot: int) -> bool:
	return slot >= 0 and slot < 64 and (worn_slots_mask & (1 << slot)) != 0

## True when the server said this player may do the thing named by `bit`. The
## window asks this rather than comparing ranks, so a threshold that moves on
## the server moves here with it.
func guild_may(bit: int) -> bool:
	return (int(guild.get("permissions", 0)) & bit) != 0
## The party, exactly as the server last stated it. `in_party` false with an
## `invited_by` name is a real state - somebody has been asked to join and has
## not answered - so the two are held together rather than as separate flags
## that could disagree.
var party: Dictionary = {"in_party": false, "members": [],
	"invited_by": "", "invite_seconds": 0}
## The chat channel `#gm` arrives on. Eternal Lands' CHAT_GM, which nothing in
## this client had a tab for until the guild window gave it one. The
## permissions bits that go with the guild packet are on `EloriaProtocol`,
## beside the packet they arrive in.
const GUILD_CHAT_CHANNEL := 2

## The player's guild, exactly as the server last stated it. `in_guild` false
## is a real state and not an empty one: it still carries what founding a
## guild costs and the directory of guilds to apply to, which is everything
## the window needs to be useful to somebody who has none.
var guild: Dictionary = {"in_guild": false, "rank": 0, "permissions": 0,
	"create_cost": 0, "create_level": 0, "join_level": 0, "tag": "", "name": "",
	"owner": "", "motd": "", "description": "", "join_info": "", "url": "",
	"members": [], "applicants": [], "allies": [], "colours": [],
	"pending": [], "directory": [], "palette": []}
var item_detail: Dictionary = {"open": false}
var inventory_state: Dictionary = {"gold": 0, "carried": 0, "capacity": 0,
	"items": []}
var combat_state: Dictionary = {"active": false, "event": 0, "target_id": -1,
	"target_name": "", "player_health": 0, "player_max_health": 0,
	"target_health": 0, "target_max_health": 0, "recent_damage": 0,
	"updated_msec": 0}
var mail: Array[Dictionary] = []
var navigation: Dictionary = {"active": false, "x": 0, "y": 0, "distance": 0,
	"map_id": "", "label": ""}
var special_events: Array[String] = []

## What power each spell effect will be cast at, and the highest the server
## allows, keyed by the server's effect name. Entirely server-stated: the
## client never works a limit out from a level.
var spell_power: Dictionary = {}
## The game date, the special day in force and what it does, and the whole
## catalogue of days the server can roll. Command 238; empty until it arrives.
var almanac: Dictionary = {}

## The player the server last described, in its own words: who was inspected
## and what they have earned. Never assembled from a request the client
## remembers making.
var player_info: Dictionary = {"open": false, "actor_id": -1, "name": "",
	"achievements": []}

## Map markers the server placed, keyed by its marker id. Purely server-stated:
## the client never invents one and never removes one the server still holds.
var map_markers: Dictionary = {}
## Older servers refresh a marker with REMOVE followed by ADD. Allow those
## packets to cross frames without tearing down the marker's live animation.
## A removal with no replacement still takes effect promptly.
const MAP_MARKER_REFRESH_GRACE := 0.25
var _pending_map_marker_removals: Dictionary = {}

## Adds a line the client wrote for itself - a console command's answer, not
## something the server said. Channel 254 keeps it out of the channel tabs and
## marks it as local wherever chat is rendered.
const LOCAL_CHAT_CHANNEL := 254
## How many lines the chat buffer keeps; the console shows all of them.
const CHAT_LINE_LIMIT := 1000

func append_local_line(text: String) -> void:
	chat_lines.append({"channel": LOCAL_CHAT_CHANNEL, "text": text,
		"stamp": Time.get_time_string_from_system()})
	if chat_lines.size() > CHAT_LINE_LIMIT:
		chat_lines.pop_front()
	state_changed.emit(&"chat")

## The game minute carried forward to now. The server states a whole minute at
## a time; this is the same minute plus however far through it the client is,
## measured against the observed interval between two of them, so the sky moves
## instead of stepping once a minute. Falls back to the stated minute until
## two have been seen.
func continuous_game_minute() -> float:
	if game_minute_interval_msec <= 0 or game_minute_anchor_msec <= 0:
		return float(game_minute)
	var elapsed: int = Time.get_ticks_msec() - game_minute_anchor_msec
	var fraction: float = clampf(
		float(elapsed) / float(game_minute_interval_msec), 0.0, 1.0)
	return float(game_minute) + fraction

## Clickable world objects on the current map, keyed by server object id, and
## the authoritative harvesting state. Both are server-declared: nothing here
## is matched by filename or scraped out of chat.
var map_objects: Dictionary = {}
var harvest: Dictionary = {"active": false, "object_id": -1, "resource": ""}

## A server-driven modal question. The server had no way to ask the player
## anything: DISPLAY_POPUP(83) fell through to {"type":"unknown"} and
## POPUP_REPLY(50) had no encoder.
var popup: Dictionary = {"open": false, "popup_id": -1, "title": "", "text": "",
	"options": []}
var _pending_text_popups: Array[Dictionary] = []
var perks: Array[Dictionary] = []
## Every perk that can be bought, as the server prices it, each carrying the
## server's own reason for refusing it where there is one. The client keeps no
## perk table; this is the table, and it arrives again whenever a purchase
## could have changed what is still on offer.
var perk_catalog: Array[Dictionary] = []
## Every attribute a character can buy, in the server's order, with the value
## and the ceiling for each. The legacy stats packet has six attribute slots
## and there are twelve, so the window reads this instead of the packet - and
## reads the names from it too, rather than holding a list that was already
## wrong once.
var attributes: Array[Dictionary] = []
## Lifetime activity totals keyed by the server's own category name, plus the
## order the server listed them in so the window needs no local table.
## How the counters window is arranged, and what fills it: which page each
## total belongs on, what a row opens into, and the achievements with the rung
## each is working towards. All of it the server's - a client grouping
## seventeen totals by a table of its own would be drawing last week's window
## the day a counter moves.
var counter_layout: Dictionary = {
	"categories": [], "breakdowns": {}, "achievements": []}
## The two things the manufacturing window cannot work out for itself: whether
## storage is close enough to mix from, and how a run is going. `served` stays
## false until the first state arrives, which is what tells the window it is
## talking to a server that understands the request at all.
var mix_state: Dictionary = _empty_mix_state()
var activity_counters: Dictionary = {}
var activity_counter_order: Array[String] = []
## Protocol diagnostics. Every undecoded packet and every decode failure used
## to be reduced here and emitted with no listener, so a gap in the client's
## coverage was completely silent. The diagnostics panel reads these.
var unknown_packet_count := 0
var unknown_packets: Dictionary = {}
var recent_protocol_errors: Array[Dictionary] = []
var last_clock_sync_msec := 0
var invasion_assistant: Dictionary = {"open": false}

func _ready() -> void:
	_initialize_native_crowd_reducer()
	Network.connection_state_changed.connect(_on_connection_state_changed)
	Network.packet_received.connect(_on_packet)
	MapSceneCache.set_mismatch_sink(_on_map_digest_mismatch)

func _initialize_native_crowd_reducer() -> void:
	if OS.get_environment("ELORIA_NATIVE_CROWD") != "1":
		return
	if not ClassDB.class_exists(&"NativeCrowdReducer"):
		var extension_path := "res://bin/native_crowd.gdextension"
		if not FileAccess.file_exists(extension_path):
			push_error("ELORIA_NATIVE_CROWD requested but its extension is not built")
			return
		GDExtensionManager.load_extension(extension_path)
	if not ClassDB.class_exists(&"NativeCrowdReducer"):
		push_error("ELORIA_NATIVE_CROWD requested but its extension did not load")
		return
	_native_crowd_reducer = ClassDB.instantiate(&"NativeCrowdReducer")
	if _native_crowd_reducer == null:
		push_error("ELORIA_NATIVE_CROWD could not instantiate its reducer")

func native_crowd_reducer_active() -> bool:
	return _native_crowd_reducer != null

func _try_native_actor_commands(command: int,
		payload: PackedByteArray) -> bool:
	if _native_crowd_reducer == null or command != EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND:
		return false
	var result: Dictionary = _native_crowd_reducer.call(
		"reduce_packet", actors, payload, local_actor_id) as Dictionary
	if str(result.get("status", "fallback")) != "ok":
		return false
	var native_changed_ids: PackedInt32Array = result.get(
		"changed_ids", PackedInt32Array()) as PackedInt32Array
	for actor_id: int in native_changed_ids:
		mark_actor_changed(actor_id)
	state_changed.emit(&"actors")
	return true

## The server said it was built against a different package than the one this
## machine loaded. Said out loud in the console because it is not something the
## client can fix and not something it should hide: nothing about the map is
## trustworthy afterwards, and the symptoms - a door in the wrong place, a
## portal that goes nowhere - look like anything but a stale install.
##
## Installed as a sink rather than checked after the packet, because the two
## halves arrive in either order: the digest can land while the map is still
## being hashed, or minutes after it finished.
func _on_map_digest_mismatch(map_id: String, server: String, local: String) -> void:
	append_local_message(("The %s map here is not the one the server expects "
		+ "(server %s, this install %s). Update the client.") % [
		map_id, server.substr(0, 12), local.substr(0, 12)])

func _on_connection_state_changed(value: String) -> void:
	connection_state = value
	# "reconnecting" is a waiting state between a drop and the next attempt.
	# The world was already cleared by the "disconnected" that preceded it, so
	# it must not clear anything a second time.
	if value == "disconnected":
		authenticated = false
		local_actor_id = -1
		actors.clear()
		inventory.clear()
		inventory_text = ""
		inventory_cooldowns.clear()
		active_spells.clear()
		last_spell_result.clear()
		pending_spell_target = ""
		stats.clear()
		game_minute = 0
		game_minute_anchor_msec = 0
		game_minute_interval_msec = 0
		server_timestamp = 0
		chat_lines.clear()
		active_channels = [0, 0, 0]
		active_channel_index = 0
		current_map = ""
		adjacent_maps.clear()
		lantern_tutorial.clear()
		selected_actor_id = -1
		techniques.clear()
		autocast.clear()
		npc_dialogue = {"open": false, "name": "", "text": "", "options": [],
			"quest": false, "quest_id": 0}
		trade = _empty_trade_state()
		storage = _empty_storage_state()
		ground_bags.clear()
		ground_bag = _empty_ground_bag_state()
		reading = _empty_reading_state()
		known_knowledge.clear()
		selected_knowledge = -1
		knowledge_text = ""
		marketplace = _empty_marketplace_state()
		merchant = _empty_merchant_state()
		quest_journal.clear()
		quest_archive.clear()
		# The catalog half is per-profile and the mask is per-character, so a
		# logout clears both rather than carrying one into the next session.
		degraded_item_names.clear()
		worn_slots_mask = 0
		achievements_state = {"counters": [], "completed": []}
		achievements_catalog = {"worn_title": "", "entries": []}
		actor_titles.clear()
		actor_occupations.clear()
		actor_mounts.clear()
		quest_offer_actors.clear()
		experience64.clear()
		# Per profile rather than per character, but a different server may
		# size its creatures differently, so it is cleared with the rest.
		actor_footprints.clear()
		# Cleared on logout, not on a map change: a party outlives walking
		# through a portal, and the server re-states it at login either way.
		party = _empty_party_state()
		# Cleared with the party and for the same reason: a guild belongs to
		# the character who was logged in, and the server restates it at login.
		guild = _empty_guild_state()
		item_detail = {"open": false}
		almanac = {}
		fires = {}
		weather = {"kind": 0, "intensity": 0}
		weather_state = {}
		quest_dialogue = false
		current_quest_id = 0
		finished_quests = []
		buddies = {}
		world_objects = {}
		teleporters = []
		inventory_names.clear()
		inventory_state = {"gold": 0, "carried": 0, "capacity": 0, "items": []}
		combat_state = _empty_combat_state()
		mail.clear()
		navigation = _empty_navigation_state()
		special_events.clear()
		map_objects.clear()
		map_markers.clear()
		_pending_map_marker_removals.clear()
		player_info = _empty_player_info()
		spell_power.clear()
		harvest = _empty_harvest_state()
		popup = _empty_popup_state()
		_pending_text_popups.clear()
		perks.clear()
		perk_catalog.clear()
		attributes.clear()
		counter_layout = {
			"categories": [], "breakdowns": {}, "achievements": []}
		mix_state = _empty_mix_state()
		activity_counters.clear()
		activity_counter_order.clear()
		invasion_assistant = {"open": false}
	state_changed.emit(&"connection")

func _empty_mix_state() -> Dictionary:
	return {"served": false, "near_storage": false, "running": false,
		"remaining": 0, "made": 0, "output": "", "interrupted": false}

func _queue_map_marker_removal(marker_id: int) -> void:
	# Unknown ids and repeated removes must not create or extend a deadline.
	if not map_markers.has(marker_id) or _pending_map_marker_removals.has(marker_id):
		return
	var timer: SceneTreeTimer = get_tree().create_timer(
		MAP_MARKER_REFRESH_GRACE, true, false, true)
	_pending_map_marker_removals[marker_id] = timer
	timer.timeout.connect(func() -> void:
		# ADD or disconnect cancels this particular removal. A subsequent
		# REMOVE for the same id owns a different timer and its own deadline.
		if _pending_map_marker_removals.get(marker_id) != timer:
			return
		_pending_map_marker_removals.erase(marker_id)
		if map_markers.erase(marker_id):
			state_changed.emit(&"map_markers"), CONNECT_ONE_SHOT)

func _on_packet(command: int, payload: PackedByteArray) -> void:
	var boundary: Dictionary = Network.coordinates.before_packet(command, EloriaProtocol.ServerMessage.CHANGE_MAP)
	if not boundary.ok:
		Network.fail_coordinate_context(boundary.error)
		return
	if command == EloriaProtocol.ServerMessage.ELORIA_COORDINATE_CONTEXT:
		var context: Dictionary = Network.coordinates.receive(payload)
		if not context.ok:
			Network.fail_coordinate_context(context.error)
		elif not Network.coordinates.pending.is_empty():
			Network.clear_coordinate_intents()
		return
	if Network.coordinates.selected and command == EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND and not Network.coordinates.ready():
		Network.fail_coordinate_context("coordinate_no_active_context")
		return
	if _try_native_actor_commands(command, payload):
		return
	var event := EloriaProtocol.decode_server(command, payload, Network.coordinates.selected)
	if event.type == "change_map":
		var committed: Dictionary = Network.coordinates.commit(str(event.map_name))
		if not committed.ok:
			Network.fail_coordinate_context(committed.error)
			return
	var converted: Dictionary = Network.coordinates.convert(event)
	if not converted.ok:
		Network.fail_coordinate_context(converted.error)
		return
	event = converted.event
	match event.type:
		"invasion_assistant":
			var update: Dictionary = (event.state as Dictionary).duplicate(true)
			var kind: String = str(update.get("kind", ""))
			invasion_assistant["open"] = true
			invasion_assistant[kind] = update
			invasion_assistant["last_kind"] = kind
			state_changed.emit(&"invasion_assistant")
		"login_ok":
			authenticated = true
			login_succeeded.emit()
			state_changed.emit(&"authentication")
		"login_error":
			authenticated = false
			login_failed.emit(event.message)
			state_changed.emit(&"authentication")
		"create_character_ok":
			character_created.emit()
		"create_character_error":
			character_creation_failed.emit(event.message)
		"you_are":
			local_actor_id = event.actor_id
			mark_actor_changed(local_actor_id)
			state_changed.emit(&"local_actor")
		"clock_sync":
			server_timestamp = int(event.server_timestamp)
			last_clock_sync_msec = Time.get_ticks_msec()
			state_changed.emit(&"clock")
		"new_minute":
			var minute_arrived_msec: int = Time.get_ticks_msec()
			# Only a minute that follows the last one measures the pace. An
			# invasion master's #set_clock jumps the clock, and the time since
			# the previous minute says nothing about how fast it is running.
			if (game_minute_anchor_msec > 0
					and int(event.minute) == (game_minute + 1) % 360):
				game_minute_interval_msec = (minute_arrived_msec
					- game_minute_anchor_msec)
			game_minute = int(event.minute)
			game_minute_anchor_msec = minute_arrived_msec
			state_changed.emit(&"clock")
		"change_map":
			current_map = event.map_name
			actor_mounts.clear()
			# The new map's objects arrive in their own packet; anything held
			# for the old map is stale the moment the change lands.
			map_objects.clear()
			harvest = _empty_harvest_state()
			marketplace = _empty_marketplace_state()
			merchant = _empty_merchant_state()
			combat_state = _empty_combat_state()
			# Actors are the server's to keep or clear: a teleport sends
			# KILL_ALL_ACTORS ahead of the change, a seamless land crossing keeps
			# every actor the client shows and re-files them on its side. The
			# handles of the old map's neighbours are stale, and named afresh.
			adjacent_maps.clear()
			if Network.coordinates.selected:
				adjacent_maps = Network.coordinates.handles.duplicate()
			selected_actor_id = -1
			npc_dialogue = {"open": false, "name": "", "text": "",
				"options": [], "quest": false, "quest_id": 0}
			pending_spell_target = ""
			trade = _empty_trade_state()
			storage = _empty_storage_state()
			ground_bags.clear()
			ground_bag = _empty_ground_bag_state()
			state_changed.emit(&"map_objects")
			state_changed.emit(&"harvest")
			state_changed.emit(&"marketplace")
			state_changed.emit(&"merchant")
			state_changed.emit(&"combat_state")
			state_changed.emit(&"map")
		"adjacent_maps":
			adjacent_maps = (event.maps as Dictionary).duplicate()
			state_changed.emit(&"adjacent_maps")
		"actor_spawn":
			# Which map the actor stands on: its packet's handle names a neighbour,
			# 0 the map the client stands on. Resolved here, once, so neither a
			# change of map nor a new handle table can re-tag it.
			var map_handle: int = int(event.get("map_handle", 0))
			if not Network.coordinates.selected:
				event["map"] = str(adjacent_maps.get(map_handle, current_map)) if map_handle > 0 else current_map
			actors[event.actor_id] = event
			mark_actor_changed(int(event.actor_id))
			state_changed.emit(&"actors")
		"remove_actor":
			for removed_actor_value: Variant in event.actor_ids:
				var removed_actor_id: int = int(removed_actor_value)
				actors.erase(removed_actor_id)
				actor_occupations.erase(removed_actor_id)
				actor_mounts.erase(removed_actor_id)
				quest_offer_actors.erase(removed_actor_id)
				if selected_actor_id == removed_actor_id:
					selected_actor_id = -1
					state_changed.emit(&"selection")
			state_changed.emit(&"actors")
		"clear_actors":
			Network.coordinate_route_cancelled.emit()
			actors.clear()
			actor_occupations.clear()
			actor_mounts.clear()
			quest_offer_actors.clear()
			state_changed.emit(&"actors")
		"actor_commands":
			for raw_command_event: Variant in event.commands:
				var command_event: Dictionary = raw_command_event as Dictionary
				var actor_id: int = int(command_event.get("actor_id", -1))
				if actors.has(actor_id):
					var actor_command: int = int(command_event.get("command", 0))
					var actor: Dictionary = actors[actor_id]
					actors[actor_id] = ActorReducer.apply_command(actor, actor_command)
					if actor_id == local_actor_id and actor_command == 19:
						combat_state = _empty_combat_state()
						state_changed.emit(&"combat_state")
					mark_actor_changed(actor_id)
			state_changed.emit(&"actors")
		"actor_wear":
			var wear_actor_id: int = int(event.actor_id)
			if actors.has(wear_actor_id):
				var wear_actor: Dictionary = actors[wear_actor_id]
				var wear_visuals: Dictionary = (wear_actor.get("equipment_visuals", {}) as Dictionary).duplicate()
				wear_visuals[int(event.part)] = int(event.visual_id)
				wear_actor["equipment_visuals"] = wear_visuals
				var wear_fallback_parts: Array = (wear_actor.get("equipment_fallback_parts", []) as Array).duplicate()
				if not wear_fallback_parts.has(int(event.part)):
					wear_fallback_parts.append(int(event.part))
				wear_actor["equipment_fallback_parts"] = wear_fallback_parts
				actors[wear_actor_id] = wear_actor
				mark_actor_changed(wear_actor_id)
				state_changed.emit(&"actors")
		"actor_unwear":
			var unwear_actor_id: int = int(event.actor_id)
			if actors.has(unwear_actor_id):
				var unwear_actor: Dictionary = actors[unwear_actor_id]
				var unwear_visuals: Dictionary = (unwear_actor.get("equipment_visuals", {}) as Dictionary).duplicate()
				unwear_visuals.erase(int(event.part))
				unwear_actor["equipment_visuals"] = unwear_visuals
				var unwear_fallback_parts: Array = (unwear_actor.get("equipment_fallback_parts", []) as Array).duplicate()
				unwear_fallback_parts.erase(int(event.part))
				unwear_actor["equipment_fallback_parts"] = unwear_fallback_parts
				actors[unwear_actor_id] = unwear_actor
				mark_actor_changed(unwear_actor_id)
				state_changed.emit(&"actors")
		"actor_damage":
			_apply_actor_health_delta(int(event.actor_id), -int(event.amount))
		"actor_heal":
			_apply_actor_health_delta(int(event.actor_id), int(event.amount))
		"actor_max_health":
			var health_actor_id: int = int(event.actor_id)
			if actors.has(health_actor_id):
				var health_actor: Dictionary = actors[health_actor_id]
				health_actor["max_health"] = int(event.max_health)
				health_actor["health"] = mini(int(health_actor.get("health", 0)),
					int(event.max_health))
				actors[health_actor_id] = health_actor
				mark_actor_changed(health_actor_id)
				state_changed.emit(&"actors")
				if health_actor_id == local_actor_id:
					stats["max_health"] = int(event.max_health)
					stats["health"] = int(health_actor.get("health", 0))
					state_changed.emit(&"stats")
		"stats":
			stats = (event.values as Dictionary).duplicate(true)
			_refresh_reading()
			state_changed.emit(&"stats")
		"partial_stats":
			for stat_key_value: Variant in event.values:
				var stat_key: String = str(stat_key_value)
				var next_value: int = int(event.values[stat_key_value])
				var had_previous: bool = stats.has(stat_key)
				var previous_value: int = int(stats.get(stat_key, next_value))
				stats[stat_key] = next_value
				if had_previous:
					_emit_stat_feedback(stat_key, previous_value, next_value)
			_refresh_reading()
			state_changed.emit(&"stats")
		"inventory":
			inventory_metadata_dirty = true
			var previous_inventory := inventory.duplicate()
			inventory.clear()
			for raw_item: Variant in event.items:
				var item: Dictionary = raw_item as Dictionary
				inventory[int(item.get("slot", -1))] = item
			for slot: Variant in inventory_names.keys():
				if not inventory.has(slot) or int(inventory[slot].get("image_id", -1)) != int(
						(previous_inventory.get(slot, {}) as Dictionary).get("image_id", -2)):
					inventory_names.erase(slot)
			state_changed.emit(&"inventory")
		"inventory_update":
			inventory_metadata_dirty = true
			var updated_item: Dictionary = event.item as Dictionary
			var updated_slot := int(updated_item.get("slot", -1))
			var previous_item: Dictionary = inventory.get(updated_slot, {}) as Dictionary
			if int(previous_item.get("image_id", -1)) != int(updated_item.get("image_id", -2)):
				inventory_names.erase(updated_slot)
			inventory[int(updated_item.get("slot", -1))] = updated_item
			state_changed.emit(&"inventory")
		"inventory_remove":
			inventory_metadata_dirty = true
			for raw_slot: Variant in event.slots:
				inventory.erase(int(raw_slot))
				inventory_names.erase(int(raw_slot))
			state_changed.emit(&"inventory")
		"inventory_text":
			inventory_text = str(event.text)
			_inventory_text_generation += 1
			_expire_inventory_text(_inventory_text_generation)
			state_changed.emit(&"inventory_text")
		"ground_bag":
			var bag: Dictionary = {"bag_id": int(event.bag_id),
				"x": int(event.x), "y": int(event.y)}
			ground_bags[int(event.bag_id)] = bag
			state_changed.emit(&"ground_bags")
		"ground_bags":
			ground_bags.clear()
			for raw_bag: Variant in event.bags:
				var listed_bag: Dictionary = raw_bag as Dictionary
				ground_bags[int(listed_bag.get("bag_id", -1))] = listed_bag.duplicate(true)
			state_changed.emit(&"ground_bags")
		"ground_bag_destroy":
			var destroyed_bag_id: int = int(event.bag_id)
			ground_bags.erase(destroyed_bag_id)
			if int(ground_bag.get("bag_id", -1)) == destroyed_bag_id:
				ground_bag = _empty_ground_bag_state()
				state_changed.emit(&"ground_bag")
			state_changed.emit(&"ground_bags")
		"ground_items":
			var ground_items: Dictionary = {}
			for raw_ground_item: Variant in event.items:
				var ground_item: Dictionary = raw_ground_item as Dictionary
				ground_items[int(ground_item.get("position", -1))] = ground_item
			ground_bag["items"] = ground_items
			ground_bag["open"] = true
			state_changed.emit(&"ground_bag")
		"ground_item":
			var new_ground_item: Dictionary = event.item as Dictionary
			var current_ground_items: Dictionary = (ground_bag.get("items", {}) as Dictionary).duplicate(true)
			current_ground_items[int(new_ground_item.get("position", -1))] = new_ground_item
			ground_bag["items"] = current_ground_items
			ground_bag["open"] = true
			state_changed.emit(&"ground_bag")
		"ground_item_remove":
			var remaining_ground_items: Dictionary = (ground_bag.get("items", {}) as Dictionary).duplicate(true)
			remaining_ground_items.erase(int(event.position))
			ground_bag["items"] = remaining_ground_items
			state_changed.emit(&"ground_bag")
		"ground_bag_close":
			ground_bag = _empty_ground_bag_state()
			state_changed.emit(&"ground_bag")
		"knowledge_list":
			known_knowledge.clear()
			for raw_index: Variant in event.known:
				known_knowledge.append(int(raw_index))
			state_changed.emit(&"knowledge")
			# Spell families are learned from tomes, so the spell windows
			# re-ask what is castable whenever the knowledge list moves.
			state_changed.emit(&"spells")
		"new_knowledge":
			var new_knowledge_index: int = int(event.index)
			if not known_knowledge.has(new_knowledge_index):
				known_knowledge.append(new_knowledge_index)
				known_knowledge.sort()
			state_changed.emit(&"knowledge")
			state_changed.emit(&"spells")
		"knowledge_text":
			knowledge_text = str(event.text)
			state_changed.emit(&"knowledge")
		"trade_partner":
			trade["open"] = true
			trade["partner"] = str(event.name)
			trade["storage_available"] = bool(event.storage_available)
			trade["own_offers"] = {}
			trade["other_offers"] = {}
			trade["own_accepts"] = 0
			trade["other_accepts"] = 0
			state_changed.emit(&"trade")
		"trade_inventory":
			var source_inventory: Dictionary = {}
			for raw_trade_item: Variant in event.items:
				var trade_item: Dictionary = raw_trade_item as Dictionary
				source_inventory[int(trade_item.get("slot", -1))] = trade_item
			trade["source_inventory"] = source_inventory
			trade["open"] = true
			state_changed.emit(&"trade")
		"trade_object":
			var offers_key: String = "other_offers" if bool(event.other) else "own_offers"
			var offers: Dictionary = (trade.get(offers_key, {}) as Dictionary).duplicate(true)
			var offer_slot: int = int(event.slot)
			var prior_quantity: int = 0
			var prior_offer_value: Variant = offers.get(offer_slot)
			if prior_offer_value is Dictionary:
				prior_quantity = int((prior_offer_value as Dictionary).get("quantity", 0))
			offers[offer_slot] = {"image_id": int(event.image_id),
				"quantity": prior_quantity + int(event.quantity),
				"source_type": int(event.source_type), "slot": offer_slot}
			trade[offers_key] = offers
			state_changed.emit(&"trade")
		"trade_remove":
			var remove_key: String = "other_offers" if bool(event.other) else "own_offers"
			var remove_offers: Dictionary = (trade.get(remove_key, {}) as Dictionary).duplicate(true)
			var remove_slot: int = int(event.slot)
			var remove_value: Variant = remove_offers.get(remove_slot)
			if remove_value is Dictionary:
				var remove_offer: Dictionary = (remove_value as Dictionary).duplicate(true)
				var remaining: int = int(remove_offer.get("quantity", 0)) - int(event.quantity)
				if remaining > 0:
					remove_offer["quantity"] = remaining
					remove_offers[remove_slot] = remove_offer
				else:
					remove_offers.erase(remove_slot)
			trade[remove_key] = remove_offers
			state_changed.emit(&"trade")
		"trade_accept":
			# The server reports the phase; the client does not infer it by
			# counting packets. A duplicate or reordered accept therefore
			# cannot leave the two sides disagreeing about the trade.
			var accept_key: String = "other_accepts" if bool(event.other) else "own_accepts"
			trade[accept_key] = clampi(int(event.phase), 0, 2)
			state_changed.emit(&"trade")
		"trade_reject":
			var reject_key: String = "other_accepts" if bool(event.other) else "own_accepts"
			trade[reject_key] = 0
			state_changed.emit(&"trade")
		"trade_exit":
			trade = _empty_trade_state()
			state_changed.emit(&"trade")
		"storage_categories":
			storage["open"] = true
			storage["categories"] = (event.categories as Array).duplicate(true)
			storage["text"] = ""
			# A fresh window: drop descriptions of whatever was open before,
			# so a stale row can never be filtered or sorted into this one.
			storage["described"] = {}
			state_changed.emit(&"storage")
		"storage_items":
			var incoming_category: int = int(event.category_id)
			if incoming_category != int(storage.get("category_id", -1)):
				storage["described"] = {}
			storage["items_category_id"] = incoming_category
			var storage_items: Dictionary = (storage.get("items", {}) as Dictionary).duplicate(true)
			if not bool(event.update):
				storage_items.clear()
			for raw_storage_item: Variant in event.items:
				var storage_item: Dictionary = raw_storage_item as Dictionary
				var storage_position: int = int(storage_item.get("position", -1))
				if int(storage_item.get("quantity", 0)) > 0:
					storage_items[storage_position] = storage_item
				else:
					storage_items.erase(storage_position)
			storage["items"] = storage_items
			storage["category_id"] = int(event.category_id)
			storage["open"] = true
			state_changed.emit(&"storage")
		"storage_state":
			# Keyed by position so it lines up with the stock storage packet.
			# A category the server re-describes replaces its rows outright.
			var described: Dictionary = {}
			for raw_row: Variant in event.rows:
				var row: Dictionary = raw_row as Dictionary
				described[int(row.get("position", -1))] = row
			storage["described"] = described
			storage["described_category_id"] = int(event.category_id)
			storage["category_id"] = int(event.category_id)
			state_changed.emit(&"storage")
		"storage_text":
			storage["text"] = str(event.text)
			state_changed.emit(&"storage")
		"item_cooldowns":
			# The server announces one slot per packet - a fresh cooldown
			# starting, or a reuse attempt while one is still running - and
			# never resends the full active set, so incoming slots must be
			# merged rather than replacing the map: clearing here dropped
			# every other slot's countdown the moment a second item's
			# cooldown was announced.
			var received_msec: int = Time.get_ticks_msec()
			for raw_cooldown: Variant in event.cooldowns:
				var cooldown: Dictionary = raw_cooldown as Dictionary
				var slot: int = int(cooldown.get("slot", -1))
				var maximum_seconds: int = int(cooldown.get("maximum_seconds", 0))
				var remaining_seconds: int = int(cooldown.get("remaining_seconds", 0))
				inventory_cooldowns[slot] = {
					"maximum_msec": maximum_seconds * 1000,
					"end_msec": received_msec + remaining_seconds * 1000}
			state_changed.emit(&"inventory_cooldowns")
		"spell_result":
			last_spell_result = {"status": int(event.status), "spell_id": int(event.spell_id)}
			var spell_action: StringName = &""
			match int(event.status):
				4:
					pending_spell_target = "actor"
					spell_action = &"cast_channel_enter"
				5:
					pending_spell_target = "location"
					spell_action = &"cast_channel_enter"
				_:
					pending_spell_target = ""
					spell_action = SpellPresentation.action_for_spell(int(event.spell_id)) if int(event.status) == 1 else &"cast_exit"
			if int(event.status) == 1 and int(event.get("visual_effect", 255)) != 255:
				var resolved_action := SpellPresentation.action_for_effect(int(event.visual_effect))
				if not resolved_action.is_empty():
					spell_action = resolved_action
			var presentation := {"actor_id": local_actor_id, "action": spell_action}
			if event.has("power"):
				last_spell_result["power"] = int(event.power)
				presentation["power"] = int(event.power)
			if event.has("visual_effect"): presentation["visual_effect"] = int(event.visual_effect)
			actor_animation_requested.emit(presentation)
			state_changed.emit(&"spells")
		"missile":
			# Aiming is state - the shooter is still drawing - and it lives on
			# the actor it describes, so it disappears with them. Loosing is
			# an event, and it ends the aim the server stated before it.
			var shooter_id: int = int(event.source_actor_id)
			if actors.has(shooter_id):
				var shooter: Dictionary = actors[shooter_id] as Dictionary
				shooter["aiming_at"] = (-1 if bool(event.fired)
					else int(event.target_actor_id))
				actors[shooter_id] = shooter
				mark_actor_changed(shooter_id)
				state_changed.emit(&"actors")
			if bool(event.fired):
				missile_fired.emit({"source_actor_id": shooter_id,
					"target_actor_id": int(event.target_actor_id)})
			else:
				actor_animation_requested.emit({"actor_id": shooter_id, "action": "ranged_draw"})
		"world_object":
			if bool(event.replace):
				world_objects.clear()
			for raw_object: Variant in event.objects as Array:
				var placed: Dictionary = raw_object as Dictionary
				world_objects[int(placed.object_id)] = placed.duplicate(true)
			state_changed.emit(&"world_objects")
		"world_object_removed":
			if world_objects.erase(int(event.object_id)):
				state_changed.emit(&"world_objects")
		"teleporters":
			teleporters = (event.tiles as Array[Vector2i]).duplicate()
			state_changed.emit(&"teleporters")
		"teleport":
			teleport_seen.emit({"arriving": bool(event.arriving),
				"x": int(event.x), "y": int(event.y)})
		"buddy":
			var buddy_name: String = str(event.name)
			match str(event.event):
				"added":
					if not buddies.has(buddy_name):
						buddies[buddy_name] = false
				"removed":
					buddies.erase(buddy_name)
				"online":
					buddies[buddy_name] = true
				"offline":
					# Somebody can go offline before this client was told they
					# were on the list at all, if the list arrived in pieces.
					if buddies.has(buddy_name):
						buddies[buddy_name] = false
			state_changed.emit(&"buddies")
		"quest_dialogue_next":
			quest_dialogue = true
			state_changed.emit(&"quest_dialogue")
		"quest_id":
			if bool(event.finished):
				var done: int = int(event.quest_id)
				if not finished_quests.has(done):
					finished_quests.append(done)
				if current_quest_id == done:
					current_quest_id = 0
				state_changed.emit(&"quest_dialogue")
			else:
				current_quest_id = int(event.quest_id)
				state_changed.emit(&"quest_dialogue")
		"weather":
			weather = {"kind": int(event.kind),
				"intensity": int(event.intensity)}
			weather_state = {}
			state_changed.emit(&"weather")
		"weather_state":
			# The legacy pair kept beside it, as a server without the state
			# would have said it: anything falling is rain, a storm if it
			# lightens; cloud and fog are a clear sky to that pair.
			var target: Array = event.target
			var falling: bool = int(target[0]) > 0 and int(target[1]) > 0
			weather = {"kind": (2 if int(target[6]) > 0 else 1) if falling else 0,
				"intensity": int(target[1]) if falling else 0}
			weather_state = {"current": event.current, "target": event.target,
				"seconds": float(event.seconds), "name": str(event.name),
				"at_msec": Time.get_ticks_msec()}
			state_changed.emit(&"weather")
		"rain":
			# The legacy signal. It carries no kind, so it only ever confirms
			# what the sky frame already said or stops the rain outright -
			# it never invents a storm the whole-sky frame did not state.
			if not bool(event.falling):
				weather = {"kind": 0, "intensity": 0}
				state_changed.emit(&"weather")
			elif int(weather.get("kind", 0)) == 0:
				weather = {"kind": 1, "intensity": int(event.intensity)}
				state_changed.emit(&"weather")
		"thunder":
			thunder_struck.emit(int(event.severity))
		"fire":
			var fire_tile := Vector2i(int(event.x), int(event.y))
			if bool(event.burning):
				fires[fire_tile] = int(event.kind)
			else:
				fires.erase(fire_tile)
			state_changed.emit(&"fires")
		"play_sound":
			sound_requested.emit({"name": str(event.name), "x": int(event.x),
				"y": int(event.y), "gain": float(event.gain)})
		"play_music":
			music_requested.emit(str(event.track))
		"ground_missile":
			# Aiming at a place is state on the shooter, the same as aiming at
			# an actor, so it clears the same way and disappears with them.
			var ground_shooter_id: int = int(event.source_actor_id)
			if actors.has(ground_shooter_id):
				var ground_shooter: Dictionary = actors[ground_shooter_id] as Dictionary
				ground_shooter["aiming_at"] = -1
				if bool(event.fired):
					ground_shooter.erase("aiming_at_tile")
				else:
					ground_shooter["aiming_at_tile"] = Vector2i(int(event.x), int(event.y))
				actors[ground_shooter_id] = ground_shooter
				mark_actor_changed(ground_shooter_id)
				state_changed.emit(&"actors")
			if bool(event.fired):
				ground_missile_fired.emit({
					"source_actor_id": ground_shooter_id,
					"x": int(event.x), "y": int(event.y)})
			else:
				actor_animation_requested.emit({"actor_id": ground_shooter_id, "action": "ranged_draw"})
		"actor_animation":
			actor_animation_requested.emit({"actor_id": int(event.actor_id),
				"action": str(event.action)})
		"special_effect":
			special_effect_requested.emit({"effect": int(event.effect),
				"actor_id": int(event.actor_id),
				"target_id": int(event.target_id), "power": int(event.get("power", 1))})
		"actor_buffs":
			# Which visible effects an actor is under, stated per actor. Kept on
			# the actor rather than in a table of its own, so it disappears with
			# the actor it describes.
			var buffed_id: int = int(event.actor_id)
			if actors.has(buffed_id):
				var buffed: Dictionary = actors[buffed_id] as Dictionary
				buffed["buffs"] = int(event.buffs)
				actors[buffed_id] = buffed
				mark_actor_changed(buffed_id)
				state_changed.emit(&"actors")
		"active_spell":
			active_spells[int(event.buff_id)] = {
				"end_msec": Time.get_ticks_msec() + int(event.duration_seconds) * 1000}
			state_changed.emit(&"spells")
		"active_spell_list":
			active_spells.clear()
			for raw_buff: Variant in event.buffs:
				active_spells[int(raw_buff)] = {"end_msec": 0}
			state_changed.emit(&"spells")
		"remove_active_spell":
			active_spells.erase(int(event.buff_id))
			state_changed.emit(&"spells")
		"active_channels":
			active_channels = [0, 0, 0]
			var incoming_channels: Array = event.channels as Array
			for index: int in incoming_channels.size():
				if index < active_channels.size():
					active_channels[index] = int(incoming_channels[index])
				else:
					active_channels.append(int(incoming_channels[index]))
			active_channel_index = clampi(int(event.active_index), 0, 2)
			state_changed.emit(&"channels")
		"chat":
			# The arrival time rides with the line, the way Eternal Lands
			# stamps every chat line as it lands; rendering may show or hide it.
			var slot := int(event.channel) - 5
			var channel_number := int(active_channels[slot]) if slot >= 0 and slot < active_channels.size() else 0
			# A fourth membership shares legacy display slot 7. The server's
			# explicit numeric header is authoritative, not that display slot.
			if int(event.channel) in [5, 6, 7]:
				var text := str(event.text)
				var end := text.find("] ")
				if text.begins_with("[") and end > 1 and text.substr(1, end - 1).is_valid_int():
					channel_number = int(text.substr(1, end - 1))
			chat_lines.append({"channel": event.channel, "channel_number": channel_number, "text": event.text,
				"colour": int(event.get("colour", 0)),
				"stamp": Time.get_time_string_from_system()})
			if chat_lines.size() > CHAT_LINE_LIMIT:
				chat_lines.pop_front()
			state_changed.emit(&"chat")
			# Channel 255 is the server's read-only popup channel. Tutorial
			# lessons arrive here, not through DISPLAY_POPUP's choice packet.
			if int(event.channel) == 255:
				_show_text_popup(str(event.text))
		"npc_info":
			npc_dialogue["open"] = true
			npc_dialogue["name"] = event.name
			state_changed.emit(&"npc_dialogue")
		"npc_text":
			npc_dialogue["open"] = true
			npc_dialogue["text"] = event.text
			# The flag describes exactly one line, so it is spent here rather
			# than left set: the next thing the NPC says is small talk again
			# unless the server flags that too.
			npc_dialogue["quest"] = quest_dialogue
			npc_dialogue["quest_id"] = current_quest_id if quest_dialogue else 0
			quest_dialogue = false
			state_changed.emit(&"npc_dialogue")
		"npc_options":
			npc_dialogue["open"] = true
			npc_dialogue["options"] = event.options
			state_changed.emit(&"npc_dialogue")
		"npc_close":
			npc_dialogue["open"] = false
			npc_dialogue["options"] = []
			state_changed.emit(&"npc_dialogue")
		"quest_archive":
			quest_archive = event.entries
			state_changed.emit(&"quest_archive")
		"degraded_items":
			degraded_item_names.clear()
			for raw_name: Variant in event.names:
				degraded_item_names[str(raw_name)] = true
			state_changed.emit(&"degraded_items")
		"worn_slots":
			worn_slots_mask = int(event.mask)
			state_changed.emit(&"worn_slots")
		"achievements_state":
			achievements_state = {"counters": event.counters,
				"completed": event.completed}
			state_changed.emit(&"achievements_state")
		"achievements_catalog":
			achievements_catalog = {"worn_title": str(event.worn_title),
				"entries": (event.entries as Array).duplicate()}
			state_changed.emit(&"achievements_catalog")
		"actor_titles":
			# An empty title is a real row: it is how somebody who took theirs
			# off stops wearing it here too.
			for raw_title: Variant in event.titles as Array:
				var row: Dictionary = raw_title as Dictionary
				var actor_id: int = int(row.get("actor_id", 0))
				var worn: String = str(row.get("title", ""))
				if worn.is_empty():
					actor_titles.erase(actor_id)
				else:
					actor_titles[actor_id] = worn
			state_changed.emit(&"actor_titles")
		"mount_states":
			if str(event.map) == current_map:
				actor_mounts = (event.states as Dictionary).duplicate(true)
				state_changed.emit(&"mount_states")
		"actor_occupations":
			# An empty row is honoured the way an empty title is: it takes the
			# line off rather than leaving the last one standing.
			for raw_row: Variant in event.occupations as Array:
				var occupation_row: Dictionary = raw_row as Dictionary
				var occupied_id: int = int(occupation_row.get("actor_id", 0))
				var occupation: String = str(occupation_row.get("occupation", "")).strip_edges()
				if occupation.is_empty():
					actor_occupations.erase(occupied_id)
				else:
					actor_occupations[occupied_id] = occupation
			state_changed.emit(&"actor_occupations")
		"quest_offers":
			quest_offer_actors.clear()
			for offered_id: int in event.actor_ids:
				quest_offer_actors[offered_id] = true
			state_changed.emit(&"quest_offers")
		"map_digest":
			# Which package the server was built against. Recorded rather than
			# acted on: the map cache is keyed on the package this machine
			# actually has, so a disagreement here cannot make the cache
			# wrong - it says the install is not the one the server expects,
			# which is a thing to be told, not a thing to work around.
			MapSceneCache.note_server_digest(
				str(event.map_id), str(event.digest))
			state_changed.emit(&"map_digest")
		"experience_state":
			experience64.clear()
			for raw_skill: Variant in event.skills:
				var row: Dictionary = raw_skill as Dictionary
				experience64[str(row.get("skill", ""))] = row
			state_changed.emit(&"experience_state")
		"actor_footprints":
			actor_footprints = event.footprints
			# Every actor is drawn on the ground the table now says it holds.
			mark_all_actors_changed()
			state_changed.emit(&"actor_footprints")
		"party":
			party = {"in_party": bool(event.in_party),
				"members": event.members,
				"invited_by": str(event.invited_by),
				"invite_seconds": int(event.invite_seconds)}
			state_changed.emit(&"party")
		"guild":
			# Taken whole rather than merged: the packet is a complete
			# statement, so a field it no longer carries has stopped being
			# true rather than kept its last value.
			guild = (event as Dictionary).duplicate(true)
			guild.erase("type")
			state_changed.emit(&"guild")
		"marketplace":
			marketplace = (event as Dictionary).duplicate(true)
			marketplace.erase("type")
			marketplace["open"] = true
			state_changed.emit(&"marketplace")
		"merchant":
			merchant = {"open": true, "actor_id": int(event.actor_id),
				"npc_name": str(event.npc_name), "gold": int(event.gold),
				"carried": int(event.carried), "capacity": int(event.capacity),
				"items": (event.items as Array).duplicate(true)}
			state_changed.emit(&"merchant")
		"quest_journal":
			quest_journal.clear()
			for raw_quest: Variant in event.entries:
				quest_journal.append((raw_quest as Dictionary).duplicate(true))
			state_changed.emit(&"quest_journal")
		"tutorial_experience":
			# Overall includes the skill awards. Only float its additional bonus,
			# while leaving the active (possibly borrowed) character's stats alone.
			var skill_total := 0
			for reward: Dictionary in event.rewards:
				if reward.skill != "overall":
					skill_total += int(reward.amount)
			for reward: Dictionary in event.rewards:
				var amount := int(reward.amount)
				if reward.skill == "overall":
					amount -= skill_total
				if amount > 0:
					floating_feedback_requested.emit({"kind":"experience", "skill":reward.skill,
						"amount":amount, "bonus":true, "permanent":event.permanent})
		"lantern_tutorial":
			lantern_tutorial = (event.state as Dictionary).duplicate(true)
			state_changed.emit(&"lantern_tutorial")
		"almanac":
			almanac = (event as Dictionary).duplicate(true)
			almanac.erase("type")
			state_changed.emit(&"almanac")
		"item_detail":
			item_detail = (event as Dictionary).duplicate(true)
			item_detail["open"] = true
			item_detail.erase("type")
			state_changed.emit(&"item_detail")
		"inventory_names":
			inventory_names = (event.names as Dictionary).duplicate()
			# The grid did not change, but what the client can say about it
			# did, so anything reading a slot by identity re-asks.
			state_changed.emit(&"inventory")
		"inventory_state":
			inventory_state = {"gold": int(event.gold),
				"carried": int(event.carried), "capacity": int(event.capacity),
				"items": (event.items as Array).duplicate(true)}
			inventory_names.clear()
			for entry: Dictionary in inventory_state.items:
				inventory_names[int(entry.slot)] = str(entry.name)
			state_changed.emit(&"inventory_state")
		"combat_state":
			# A defeat ends the engagement; every other event refreshes it.
			var defeated: bool = (int(event.event)
				== EloriaProtocol.COMBAT_EVENT_DEFEAT)
			combat_state = {"active": not defeated, "event": int(event.event),
				"target_id": int(event.target_id),
				"target_name": str(event.target_name),
				"player_health": int(event.player_health),
				"player_max_health": int(event.player_max_health),
				"target_health": int(event.target_health),
				"target_max_health": int(event.target_max_health),
				"recent_damage": int(event.recent_damage),
				"updated_msec": Time.get_ticks_msec()}
			state_changed.emit(&"combat_state")
		"mail":
			mail.clear()
			for raw_message: Variant in event.messages:
				mail.append((raw_message as Dictionary).duplicate(true))
			state_changed.emit(&"mail")
		"navigation":
			navigation = {"active": bool(event.active), "x": int(event.x),
				"y": int(event.y), "distance": int(event.distance),
				"map_id": str(event.map_id), "label": str(event.label)}
			state_changed.emit(&"navigation")
		"special_events":
			special_events.clear()
			for raw_line: Variant in event.lines:
				special_events.append(str(raw_line))
			state_changed.emit(&"special_events")
		"magic_state":
			var magic: Dictionary = event.data
			if magic.get("kind") == "techniques":
				techniques = magic.duplicate(true)
				techniques["received_msec"] = Time.get_ticks_msec()
				state_changed.emit(&"techniques")
			elif magic.get("kind") == "autocast":
				autocast = magic.duplicate(true)
				state_changed.emit(&"autocast")
			elif magic.get("kind") in ["creature_status", "actor_status"]:
				var status_actor_id := int(magic.get("actor_id", -1))
				if actors.has(status_actor_id) and magic.get("effects") is Array:
					var status_actor: Dictionary = actors[status_actor_id]
					status_actor["negative_statuses"] = (magic.effects as Array).filter(
						func(effect: Variant) -> bool: return effect in NEGATIVE_STATUSES)
					status_actor["status_effects"] = (magic.effects as Array).duplicate()
					mark_actor_changed(status_actor_id)
					state_changed.emit(&"actors")
			else:
				magic_state_received.emit(magic)
		"spell_power":
			spell_power.clear()
			for raw_effect: Variant in event.effects:
				var described: Dictionary = raw_effect as Dictionary
				spell_power[str(described.get("effect", ""))] = {
					"preferred": int(described.get("preferred", 1)),
					"limit": int(described.get("limit", 1))}
			state_changed.emit(&"spell_power")
		"player_info":
			player_info = {"open": true, "actor_id": int(event.actor_id),
				"name": str(event.name),
				"title": str(event.get("title", "")),
				"achievements": (event.achievements as Array).duplicate()}
			state_changed.emit(&"player_info")
		"map_marker":
			var marker_id: int = int(event.marker_id)
			_pending_map_marker_removals.erase(marker_id)
			var marker: Dictionary = {
				"marker_id": int(event.marker_id), "x": int(event.x),
				"y": int(event.y), "map_id": str(event.map_id),
				"label": str(event.label)}
			if event.has("actor_id"):
				marker["actor_id"] = int(event.actor_id)
			if map_markers.get(marker_id) == marker:
				return
			map_markers[marker_id] = marker
			state_changed.emit(&"map_markers")
		"remove_map_marker":
			_queue_map_marker_removal(int(event.marker_id))
		"map_objects":
			# The list arrives in chunks; only the first clears what was there.
			if bool(event.first):
				map_objects.clear()
			for raw_object: Variant in event.objects:
				var map_object: Dictionary = (raw_object as Dictionary).duplicate(true)
				map_objects[int(map_object.get("object_id", -1))] = map_object
			state_changed.emit(&"map_objects")
		"harvest_state":
			harvest = {"active": bool(event.active),
				"object_id": int(event.object_id), "resource": str(event.resource)}
			state_changed.emit(&"harvest")
		"popup":
			# Only one popup at a time, matching the legacy client's refusal to
			# open a second window for an id it is already showing.
			var same_popup: bool = (bool(popup.get("open", false))
				and int(popup.get("popup_id", -1)) == int(event.popup_id))
			if not same_popup:
				popup = {"open": true, "popup_id": int(event.popup_id),
					"title": str(event.title), "text": str(event.text),
					"options": (event.options as Array).duplicate(true)}
				state_changed.emit(&"popup")
		"perks":
			perks.clear()
			for raw_perk: Variant in event.perks:
				perks.append((raw_perk as Dictionary).duplicate(true))
			state_changed.emit(&"perks")
		"perk_catalog":
			perk_catalog.clear()
			for raw_perk: Variant in event.perks:
				perk_catalog.append((raw_perk as Dictionary).duplicate(true))
			state_changed.emit(&"perk_catalog")
		"attribute_state":
			attributes.clear()
			for raw_attribute: Variant in event.attributes:
				attributes.append((raw_attribute as Dictionary).duplicate(true))
			state_changed.emit(&"attributes")
		"mix_state":
			# A finished run keeps the name of what it was making and the
			# count that came out; the queue reads both before deciding
			# whether to send the next batch, and does not send one at all
			# when another action interrupted this one.
			mix_state = {
				"served": true,
				"near_storage": bool(event.get("near_storage", false)),
				"running": bool(event.get("running", false)),
				"remaining": int(event.get("remaining", 0)),
				"made": int(event.get("made", 0)),
				"output": str(event.get("output", "")),
				"interrupted": bool(event.get("interrupted", false)),
			}
			state_changed.emit(&"mix_state")
		"counter_layout":
			counter_layout = {
				"categories": event.get("categories", []),
				"breakdowns": event.get("breakdowns", {}),
				"achievements": event.get("achievements", [])}
			state_changed.emit(&"counters")
		"activity_counters":
			if bool(event.full):
				activity_counters.clear()
				activity_counter_order.clear()
			for raw_counter: Variant in event.counters:
				var counter: Dictionary = raw_counter as Dictionary
				var counter_name: String = str(counter.get("name", ""))
				if counter_name.is_empty():
					continue
				if not activity_counters.has(counter_name):
					activity_counter_order.append(counter_name)
				activity_counters[counter_name] = int(counter.get("total", 0))
			state_changed.emit(&"counters")
		"ping_request":
			Network.send_frame(EloriaProtocol.encode(EloriaProtocol.ClientMessage.PING_RESPONSE))
		"invalid":
			recent_protocol_errors.append({"command": command,
				"error": str(event.error), "size": payload.size(),
				"msec": Time.get_ticks_msec()})
			if recent_protocol_errors.size() > 50:
				recent_protocol_errors.pop_front()
			state_changed.emit(&"protocol_errors")
		"unknown":
			unknown_packet_count += 1
			var record: Dictionary = unknown_packets.get(command,
				{"count": 0, "size": 0, "msec": 0})
			record["count"] = int(record.get("count", 0)) + 1
			record["size"] = payload.size()
			record["msec"] = Time.get_ticks_msec()
			unknown_packets[command] = record
			state_changed.emit(&"protocol_unknown")

func append_local_message(text: String, channel: int = 255) -> void:
	chat_lines.append({"channel": channel, "text": text, "colour": 0,
		"stamp": Time.get_time_string_from_system()})
	if chat_lines.size() > CHAT_LINE_LIMIT:
		chat_lines.pop_front()
	state_changed.emit(&"chat")

func active_channel_number() -> int:
	if active_channel_index < 0 or active_channel_index >= active_channels.size():
		return 0
	return active_channels[active_channel_index]

func select_actor(actor_id: int) -> void:
	selected_actor_id = actor_id if actors.has(actor_id) else -1
	state_changed.emit(&"selection")

func _apply_actor_health_delta(actor_id: int, amount: int) -> void:
	if not actors.has(actor_id):
		return
	var actor: Dictionary = actors[actor_id]
	var maximum: int = maxi(0, int(actor.get("max_health", 0)))
	var health: int = clampi(int(actor.get("health", 0)) + amount, 0, maximum)
	actor["health"] = health
	actor["alive"] = health > 0
	actors[actor_id] = actor
	mark_actor_changed(actor_id)
	state_changed.emit(&"actors")
	if actor_id == local_actor_id:
		stats["health"] = health
		state_changed.emit(&"stats")

func _emit_stat_feedback(stat_key: String, previous_value: int,
		next_value: int) -> void:
	if next_value <= previous_value:
		return
	if stat_key.ends_with("_exp_next"):
		return
	if stat_key.ends_with("_exp"):
		var skill_key: String = stat_key.trim_suffix("_exp")
		floating_feedback_requested.emit({
			"kind": "experience", "skill": skill_key,
			"amount": next_value - previous_value, "value": next_value})
	elif stat_key.ends_with("_base"):
		var skill_key: String = stat_key.trim_suffix("_base")
		if not skill_key in ["attack", "defense", "harvesting", "alchemy",
				"magic", "potion", "summoning", "manufacturing", "crafting",
				"engineering", "tailoring", "ranging", "overall"]:
			return
		floating_feedback_requested.emit({
			"kind": "level", "skill": skill_key, "level": next_value})

## The popup is closed by the client once its answer is on the wire, or when
## the player dismisses it. The server does not send a close packet.
func close_popup() -> void:
	popup = (_pending_text_popups.pop_front() if not _pending_text_popups.is_empty()
		else _empty_popup_state())
	state_changed.emit(&"popup")

func _show_text_popup(message: String) -> void:
	message = message.strip_edges()
	if message.is_empty():
		return
	var split_at: int = message.find("\n")
	var incoming: Dictionary = {"open": true, "popup_id": -1, "options": [],
		"title": message.substr(0, split_at).strip_edges() if split_at >= 0 else "Quest progress",
		"text": message.substr(split_at + 1).strip_edges() if split_at >= 0 else message}
	# A notification must not swallow a question awaiting the player's reply.
	if bool(popup.get("open", false)) and int(popup.get("popup_id", -1)) >= 0:
		_pending_text_popups.append(incoming)
		return
	popup = incoming
	state_changed.emit(&"popup")

## The reading slice is a typed reduction of the three research statistics, so
## the window never re-reads raw slot numbers. Index 1024 is the server's
## "reading nothing" value.
func _refresh_reading() -> void:
	var index: int = int(stats.get("researching", 1024))
	var total: int = maxi(0, int(stats.get("research_total", 0)))
	var completed: int = clampi(int(stats.get("research_completed", 0)), 0, total)
	var next_reading: Dictionary = {
		"active": index >= 0 and index < 1024 and total > 0,
		"index": index, "pages_read": completed, "pages_total": total}
	if next_reading == reading:
		return
	reading = next_reading
	state_changed.emit(&"reading")

func _empty_reading_state() -> Dictionary:
	return {"active": false, "index": -1, "pages_read": 0, "pages_total": 0}

func close_marketplace() -> void:
	marketplace = _empty_marketplace_state()
	state_changed.emit(&"marketplace")

func close_merchant() -> void:
	merchant = _empty_merchant_state()
	state_changed.emit(&"merchant")

func _expire_inventory_text(generation: int) -> void:
	await get_tree().create_timer(8.0).timeout
	if generation == _inventory_text_generation:
		inventory_text = ""
		state_changed.emit(&"inventory_text")

func close_item_detail() -> void:
	item_detail = {"open": false}
	state_changed.emit(&"item_detail")

func close_player_info() -> void:
	player_info = _empty_player_info()
	state_changed.emit(&"player_info")

func _empty_player_info() -> Dictionary:
	return {"open": false, "actor_id": -1, "name": "", "title": "",
		"achievements": []}

func _empty_party_state() -> Dictionary:
	return {"in_party": false, "members": [], "invited_by": "",
		"invite_seconds": 0}

func _empty_guild_state() -> Dictionary:
	return {"in_guild": false, "rank": 0, "permissions": 0, "create_cost": 0,
		"create_level": 0, "join_level": 0, "tag": "", "name": "", "owner": "",
		"motd": "", "description": "", "join_info": "", "url": "",
		"members": [], "applicants": [], "allies": [], "colours": [],
		"pending": [], "directory": [], "palette": []}

func _empty_marketplace_state() -> Dictionary:
	return {"open": false, "gold": 0, "returned_items": 0, "listings": [],
		"view": 0, "version": 1, "offset": 0, "total": 0, "page_size": 0,
		"query": "", "notice": "", "notice_kind": 0, "returns": []}

func _empty_merchant_state() -> Dictionary:
	return {"open": false, "actor_id": -1, "npc_name": "", "gold": 0,
		"carried": 0, "capacity": 0, "items": []}

func _empty_combat_state() -> Dictionary:
	return {"active": false, "event": 0, "target_id": -1, "target_name": "",
		"player_health": 0, "player_max_health": 0, "target_health": 0,
		"target_max_health": 0, "recent_damage": 0, "updated_msec": 0}

func _empty_navigation_state() -> Dictionary:
	return {"active": false, "x": 0, "y": 0, "distance": 0, "map_id": "",
		"label": ""}

func _empty_harvest_state() -> Dictionary:
	return {"active": false, "object_id": -1, "resource": ""}

func _empty_popup_state() -> Dictionary:
	return {"open": false, "popup_id": -1, "title": "", "text": "", "options": []}

func close_dialogue() -> void:
	npc_dialogue["open"] = false
	npc_dialogue["options"] = []
	state_changed.emit(&"npc_dialogue")

func _empty_trade_state() -> Dictionary:
	return {"open": false, "partner": "", "storage_available": false,
		"source_inventory": {}, "own_offers": {}, "other_offers": {},
		"own_accepts": 0, "other_accepts": 0}

func close_storage() -> void:
	storage = _empty_storage_state()
	state_changed.emit(&"storage")

func _empty_storage_state() -> Dictionary:
	return {"open": false, "categories": [], "category_id": -1,
		"items": {}, "described": {}, "text": ""}

func begin_ground_bag_inspection(bag_id: int) -> void:
	ground_bag["bag_id"] = bag_id
	ground_bag["open"] = false
	ground_bag["items"] = {}
	state_changed.emit(&"ground_bag")

func close_ground_bag() -> void:
	ground_bag = _empty_ground_bag_state()
	state_changed.emit(&"ground_bag")

func _empty_ground_bag_state() -> Dictionary:
	return {"open": false, "bag_id": -1, "items": {}}

func select_knowledge(index: int) -> void:
	selected_knowledge = index
	knowledge_text = ""
	state_changed.emit(&"knowledge")
