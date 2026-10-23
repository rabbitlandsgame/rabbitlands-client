class_name EloriaProtocol
extends RefCounted

const HEADER_SIZE := 3
# Actor animation frames. Only the two resting frames are meaningful in an
# actor packet; the rest are transient states the server does not spawn into.
const FRAME_IDLE := 7
const FRAME_COMBAT_IDLE := 15
## The only actor-buff bit this server sets: doubled movement speed.
const ACTOR_BUFF_DOUBLE_SPEED := 1024
const MAX_PAYLOAD := 65532
# Reserved raw codecs only; do not advertise before runtime integration.
const MAP_STORAGE_COORDS_CAPABILITY := "map_storage_coords_v1"
const CoordinateTransport = preload("res://src/network/coordinate_transport.gd")
const InterestProtocol := preload("res://src/network/interest_protocol.gd")

## The guild packet's permissions field: what the server says this reader may
## do. They live here, with the packet they arrive in, and the rank each power
## starts at is deliberately not here at all - the server keeps that, and the
## window asks these bits instead of comparing a number.
const GUILD_CAN_CHAT := 1 << 0
const GUILD_CAN_ROSTER := 1 << 1
const GUILD_CAN_INTERGUILD := 1 << 2
const GUILD_CAN_TEXT := 1 << 3
const GUILD_CAN_ACCEPT := 1 << 4
const GUILD_CAN_ALLY := 1 << 5
const GUILD_CAN_RANK := 1 << 6
const GUILD_CAN_OWN := 1 << 7
const GUILD_CAN_LEAVE := 1 << 8

enum ClientMessage {
	RAW_TEXT = 0, MOVE_TO = 1, SEND_PM = 2, GET_PLAYER_INFO = 5, RUN_TO = 6,
	SIT_DOWN = 7, SEND_ME_MY_ACTORS = 8, SEND_OPENING_SCREEN = 9, SEND_VERSION = 10,
	TURN_LEFT = 11, TURN_RIGHT = 12,
	PING = 13, HEART_BEAT = 14, LOCATE_ME = 15, USE_MAP_OBJECT = 16,
	SEND_MY_STATS = 17, SEND_MY_INVENTORY = 18, LOOK_AT_INVENTORY_ITEM = 19,
	MOVE_INVENTORY_ITEM = 20, HARVEST = 21, DROP_ITEM = 22, PICK_UP_ITEM = 23,
	LOOK_AT_GROUND_ITEM = 24, INSPECT_BAG = 25, CLOSE_BAG = 26, LOOK_AT_MAP_OBJECT = 27, TOUCH_PLAYER = 28,
	RESPOND_TO_NPC = 29, MANUFACTURE_THIS = 30, USE_INVENTORY_ITEM = 31,
	TRADE_WITH = 32, ACCEPT_TRADE = 33, REJECT_TRADE = 34, EXIT_TRADE = 35,
	PUT_OBJECT_ON_TRADE = 36, REMOVE_OBJECT_FROM_TRADE = 37,
	LOOK_AT_TRADE_ITEM = 38, CAST_SPELL = 39, ATTACK_SOMEONE = 40,
	GET_KNOWLEDGE_INFO = 41,
	# Client-to-server; 42 and 70 are also server-to-client numbers, the way
	# the storage commands below share 44-46. The direction tells them apart.
	ITEM_ON_ITEM = 42, DO_EMOTE = 70, FIRE_MISSILE_AT_OBJECT = 51,
	WHAT_QUEST_IS_THIS_ID = 63,
	GET_STORAGE_CATEGORY = 44, DEPOSIT_ITEM = 45,
	WITHDRAW_ITEM = 46, LOOK_AT_STORAGE_ITEM = 47, POPUP_REPLY = 50,
	PING_RESPONSE = 60, SET_ACTIVE_CHANNEL = 61, LOG_IN = 140,
	CREATE_CHAR = 141, GET_DATE = 230, GET_TIME = 231,
	# Eternal Lands spoke for everything below 200, so what this client asks
	# for that Eternal Lands never had is numbered from there up.
	ELORIA_MIX_REQUEST = 200, ELORIA_TOOL_REQUEST = 201, ELORIA_TUTORIAL_UI = 203,
	ELORIA_MAP_COMMAND = 204, ELORIA_CLIENT_RELEASE = 205,
	# Use a combat technique: {"op": "use", "key", "target_id"}. Carries only
	# an actor id, so it is never coordinate-framed. The state comes back on
	# ELORIA_MAGIC_STATE as kind "techniques".
	ELORIA_TECHNIQUE_REQUEST = 220,
	# The keyboard direction held (keyboard_intent_v1): epoch, direction 0-7
	# in the server's order (N, NE, E, SE, S, SW, W, NW) or 255 for a
	# release, flags. A direction carries no coordinates, so it is never
	# coordinate-framed; the epoch ties it to a map instead. The same number
	# as ServerMessage.ELORIA_MOVE_INTENT, as 230/231 are shared.
	ELORIA_MOVE_INTENT = 254
}

enum ServerMessage {
	RAW_TEXT = 0, ADD_NEW_ACTOR = 1, ADD_ACTOR_COMMAND = 2, YOU_ARE = 3,
	SYNC_CLOCK = 4, NEW_MINUTE = 5, REMOVE_ACTOR = 6, CHANGE_MAP = 7,
	COMBAT_MODE = 8, KILL_ALL_ACTORS = 9, PONG = 11, HERE_YOUR_STATS = 18,
	HERE_YOUR_INVENTORY = 19, INVENTORY_ITEM_TEXT = 20,
	GET_NEW_INVENTORY_ITEM = 21, REMOVE_ITEM_FROM_INVENTORY = 22,
	HERE_YOUR_GROUND_ITEMS = 23, GET_NEW_GROUND_ITEM = 24,
	REMOVE_ITEM_FROM_GROUND = 25, CLOSE_BAG = 26,
	GET_NEW_BAG = 27, GET_BAGS_LIST = 28, DESTROY_BAG = 29, NPC_TEXT = 30,
	NPC_OPTIONS_LIST = 31, CLOSE_NPC_MENU = 32, SEND_NPC_INFO = 33,
	GET_TRADE_OBJECT = 35, GET_TRADE_ACCEPT = 36, GET_TRADE_REJECT = 37,
	GET_TRADE_EXIT = 38, REMOVE_TRADE_OBJECT = 39, GET_YOUR_TRADEOBJECTS = 40,
	GET_TRADE_PARTNER_NAME = 41,
	GET_YOUR_SIGILS = 42, GET_ACTIVE_SPELL = 44,
	GET_ACTIVE_SPELL_LIST = 45, REMOVE_ACTIVE_SPELL = 46,
	GET_ACTOR_DAMAGE = 47, GET_ACTOR_HEAL = 48, SEND_PARTIAL_STAT = 49,
	ADD_NEW_ENHANCED_ACTOR = 51, ACTOR_WEAR_ITEM = 52, ACTOR_UNWEAR_ITEM = 53,
	GET_KNOWLEDGE_LIST = 55, GET_NEW_KNOWLEDGE = 56, GET_KNOWLEDGE_TEXT = 57,
	STORAGE_LIST = 67, STORAGE_ITEMS = 68, STORAGE_TEXT = 69,
	PING_REQUEST = 60, SPELL_CAST = 70, GET_ACTIVE_CHANNELS = 71, GET_ACTOR_HEALTH = 73,
	GET_ITEMS_COOLDOWN = 77, SEND_BUFFS = 78, SEND_SPECIAL_EFFECT = 79,
	MISSILE_AIM_A_AT_B = 84, MISSILE_FIRE_A_TO_B = 86,
	MISSILE_AIM_A_AT_XYZ = 85, MISSILE_FIRE_A_TO_XYZ = 87,
	PLAY_SOUND = 14, PLAY_MUSIC = 54,
	START_RAIN = 15, STOP_RAIN = 16, THUNDER = 17,
	FIRE_PARTICLES = 61, REMOVE_FIRE_AT = 62, SEND_WEATHER = 100,
	NEXT_NPC_MESSAGE_IS_QUEST = 92, HERE_IS_QUEST_ID = 93, QUEST_FINISHED = 94,
	BUDDY_EVENT = 59,
	GET_TELEPORTERS_LIST = 10, TELEPORT_IN = 12, TELEPORT_OUT = 13,
	GET_3D_OBJ_LIST = 74, GET_3D_OBJ = 75, REMOVE_3D_OBJ = 76,
	DISPLAY_POPUP = 83, SEND_MAP_MARKER = 90, REMOVE_MAP_MARKER = 91,
	SEND_ACHIEVEMENTS = 95, ADD_NEW_ACTOR_EXTENDED = 247,
	ELORIA_INVASION_ASSISTANT_STATE = 233,
	ELORIA_PERKS = 234, ELORIA_ACTIVITY_COUNTERS = 235,
	ELORIA_MAP_OBJECTS = 236, ELORIA_HARVEST_STATE = 237,
	ELORIA_MARKETPLACE_STATE = 222, ELORIA_MERCHANT_STATE = 223,
	ELORIA_QUEST_JOURNAL_STATE = 224, ELORIA_ITEM_DETAIL = 225,
	ELORIA_INVENTORY_STATE = 226, ELORIA_COMBAT_STATE = 227,
	ELORIA_MAIL_STATE = 229, ELORIA_NAVIGATION_STATE = 230,
	ELORIA_SPECIAL_EVENT_STATE = 232, ELORIA_PLAYER_INFO = 228,
	ELORIA_SPELL_POWER = 231,
	ELORIA_MAGIC_STATE = 212,
	ELORIA_ALMANAC_STATE = 238, ELORIA_STORAGE_STATE = 239,
	ELORIA_PARTY_STATE = 240, ELORIA_QUEST_ARCHIVE_STATE = 241,
	ELORIA_DEGRADED_ITEMS = 242, ELORIA_WORN_SLOTS = 243,
	ELORIA_ACHIEVEMENTS_STATE = 244, ELORIA_EXPERIENCE_STATE = 245,
	ELORIA_ACTOR_FOOTPRINTS = 246, ELORIA_INVENTORY_NAMES = 248,
	# 222-247 are full - 247 is ADD_NEW_ACTOR_EXTENDED above - so the
	# extensions continue in the run below the stock commands instead.
	# 216-219 are free. NOTE 248 above is REDEFINE_YOUR_COLORS in stock
	# Eternal Lands, as 249-253 are YOU_DONT_EXIST and the log-in replies.
	ELORIA_PERK_CATALOG = 215, ELORIA_ATTRIBUTE_STATE = 216,
	ELORIA_COUNTER_LAYOUT = 217,
	ELORIA_MIX_STATE = 218,
	ELORIA_GUILD_STATE = 213,
	ELORIA_ACHIEVEMENTS_CATALOG = 219,
	## The whole sky as it looks and as it is becoming (weather_state_v1).
	## 220 is ClientMessage.ELORIA_TECHNIQUE_REQUEST: the ids are one pool.
	ELORIA_WEATHER_STATE = 221,
	# The worn titles of everyone on a map. Down here in the low run the
	# extensions overflowed into rather than beside 244, because 219 was the
	# last free number of the 215-219 block and this run continues downwards.
	ELORIA_ACTOR_TITLES = 211,
	# What the NPCs just shown do for a living, the line under their names.
	# The free number between the map digest (209) and the titles (211).
	ELORIA_ACTOR_OCCUPATIONS = 210,
	ELORIA_MOUNT_STATES = 198,
	ELORIA_QUEST_OFFERS = 199,
	# Player interest (interest_protocol.gd), continuing the run down from the
	# riding table: the dots of the players beyond the area of interest, the
	# server's clock for the packets that follow it, and riding-table deltas.
	ELORIA_PRESENCE = 197, ELORIA_SERVER_TIME = 196, ELORIA_MOUNT_DELTAS = 195,
	ELORIA_LEADERBOARD_STATE = 194,
	ELORIA_GAUNTLET_READY_STATE = 193,
	ELORIA_GAUNTLET_LOOT_STATE = 192,
	# Which map package the server was built against. Continues the same
	# downward run below 211.
	ELORIA_MAP_DIGEST = 209,
	ELORIA_COORDINATE_CONTEXT = 208,
	ELORIA_LANTERN_STATE = 207,
	ELORIA_CLIENT_UPDATE = 206,
	# The land neighbours of the map the client stands on, with the handle each
	# one's actors carry in the stock "z" field of the actor packets (0 is the
	# client's own map). The next free number of the downward run.
	ELORIA_ADJACENT_MAPS = 214,
	# Whether the server steps a held keyboard direction (keyboard_intent_v1),
	# the epoch intents must carry (it changes with every map change) and the
	# keep-alive and idle timings. 254 was the last free number.
	ELORIA_MOVE_INTENT = 254,
	ADD_ACTOR_ANIMATION = 89,
	LOG_IN_OK = 250, LOG_IN_NOT_OK = 251,
	CREATE_CHAR_OK = 252, CREATE_CHAR_NOT_OK = 253
}

static func encode(command: int, payload := PackedByteArray()) -> PackedByteArray:
	assert(command >= 0 and command <= 255)
	assert(payload.size() <= MAX_PAYLOAD)
	var frame := PackedByteArray([command])
	var wire_length := payload.size() + 1
	frame.append(wire_length & 0xff)
	frame.append((wire_length >> 8) & 0xff)
	frame.append_array(payload)
	return frame

static func coordinate_context(context: Dictionary) -> Dictionary:
	var result := CoordinateTransport.encode_context(context)
	if result.ok:
		result["frame"] = encode(ServerMessage.ELORIA_COORDINATE_CONTEXT, result.payload)
	return result

static func decode_coordinate_context(payload: PackedByteArray, expected_profiles: Dictionary) -> Dictionary:
	return CoordinateTransport.decode_context(payload, expected_profiles)

static func map_command(epoch: Variant, command: Variant, payload: PackedByteArray) -> Dictionary:
	var result := CoordinateTransport.encode_map_command(epoch, command, payload)
	if result.ok:
		result["frame"] = encode(ClientMessage.ELORIA_MAP_COMMAND, result.payload)
	return result

static func decode_map_command(payload: PackedByteArray) -> Dictionary:
	return CoordinateTransport.decode_map_command(payload)

## Decodes the packet that starts at `offset`. Reading in place lets a caller
## drain a burst of packets from one receive buffer without re-slicing the
## remainder after each of them. `consumed` stays relative to `offset`.
static func try_decode(buffer: PackedByteArray, offset := 0) -> Dictionary:
	var available := buffer.size() - offset
	if available < HEADER_SIZE:
		return {"status": "incomplete"}
	var wire_length := u16(buffer, offset + 1)
	if wire_length < 1 or wire_length - 1 > MAX_PAYLOAD:
		return {"status": "error", "error": "invalid_packet_length"}
	var total := wire_length + 2
	if available < total:
		return {"status": "incomplete"}
	return {"status": "ok", "command": int(buffer[offset]),
		"payload": buffer.slice(offset + HEADER_SIZE, offset + total),
		"consumed": total}

static func login(username: String, password: String) -> PackedByteArray:
	# Legacy send_login_info(): "username password\0".
	var payload := (username + " " + password).to_utf8_buffer()
	payload.append(0)
	return encode(ClientMessage.LOG_IN, payload)

static func create_character(username: String, password: String, appearance: Dictionary,
		class_id := 0) -> PackedByteArray:
	var payload := (username + " " + password).to_utf8_buffer()
	payload.append(0)
	# Exact legacy order: skin, hair, shirt, pants, boots, actor type, head, eyes.
	var wire := appearance.duplicate()
	var hair := int(appearance.get("hair", 0))
	wire["head"] = AppearanceVariants.hair_wire_head(hair, int(appearance.get("head", 0)))
	wire["hair"] = hair & 0xff
	for key in ["skin", "hair", "shirt", "pants", "boots", "actor_type", "head", "eyes"]:
		payload.append(clampi(int(wire.get(key, 0)), 0, 255))
	# Eloria extension: a ninth byte selects a server-owned starter kit. Legacy
	# servers ignore trailing create bytes; updated servers default an absent
	# byte to Vanguard, so old clients and servers remain wire-compatible.
	payload.append(clampi(class_id, 0, 255))
	return encode(ClientMessage.CREATE_CHAR, payload)

static func version(protocol_major: int, protocol_minor: int,
		client_version: PackedByteArray, host := PackedByteArray([0, 0, 0, 0]),
		port := 0) -> PackedByteArray:
	assert(client_version.size() == 4)
	assert(host.size() == 4)
	var payload := PackedByteArray([
		protocol_major & 0xff, (protocol_major >> 8) & 0xff,
		protocol_minor & 0xff, (protocol_minor >> 8) & 0xff])
	payload.append_array(client_version)
	payload.append_array(host)
	# Legacy wire order for this field is network byte order.
	payload.append((port >> 8) & 0xff)
	payload.append(port & 0xff)
	return encode(ClientMessage.SEND_VERSION, payload)

static func move_to(x: int, y: int, run := false) -> PackedByteArray:
	return encode(ClientMessage.RUN_TO if run else ClientMessage.MOVE_TO,
		PackedByteArray([x & 0xff, (x >> 8) & 0xff, y & 0xff, (y >> 8) & 0xff]))

## The server's eight tile directions in the order ELORIA_MOVE_INTENT numbers them.
const INTENT_DIRECTIONS: Array[Vector2i] = [Vector2i(0, 1), Vector2i(1, 1), Vector2i(1, 0),
	Vector2i(1, -1), Vector2i(0, -1), Vector2i(-1, -1), Vector2i(-1, 0), Vector2i(-1, 1)]
const INTENT_RELEASE := 255

## A held keyboard direction (one of INTENT_DIRECTIONS) or Vector2i.ZERO for a
## release. Flags bit 0: the run key is held.
static func move_intent(epoch: int, direction: Vector2i, run := false) -> PackedByteArray:
	var index: int = INTENT_DIRECTIONS.find(direction)
	return encode(ClientMessage.ELORIA_MOVE_INTENT,
		PackedByteArray([epoch & 0xff, INTENT_RELEASE if index < 0 else index, 1 if run else 0]))

static func set_sitting(sitting: bool) -> PackedByteArray:
	return encode(ClientMessage.SIT_DOWN, PackedByteArray([1 if sitting else 0]))

## One 45 degree facing step. The command carries no payload; the server
## answers with the matching CMD_TURN_* actor command, which is what actually
## changes the rendered facing for every client including this one.
static func turn(left: bool) -> PackedByteArray:
	return encode(ClientMessage.TURN_LEFT if left else ClientMessage.TURN_RIGHT)

## Extensions this client actually implements, sent to the server on login as
## `#clientcaps a,b,c`. The server withholds each Eloria extension packet from
## a client that has not claimed it and falls back to legacy dialogue or raw
## text instead, so an inaccurate list here is worse than a short one: claiming
## a capability the client cannot decode turns a working dialogue into a packet
## that lands in the protocol diagnostics panel and nowhere else.
##
## Grow this list in the same commit that lands the window which decodes the
## packet, never before.
const CLIENT_CAPABILITIES: Array[String] = [
	"death_state_v1",
	"music_program_v1",
	"lantern_tutorial_v1",
	"tutorial_rewards_v1",
	"second_bell_v1",
	"borrowed_sky_v1",
	"spell_ring_v1",
	"followup_tutorials_v1",
	"field_dispatch_v1",
	"signed_ashore_v1",
	"actor16_v1",
	"adjacent_actors_v1",
	# Players within 80 tiles as actors, the rest as ELORIA_PRESENCE dots, and
	# a cap on the actors shown, which the client lowers with the
	# `actor_cap:<N>` token `client_capabilities` adds (interest_protocol.gd).
	"player_interest_v1",
	# ELORIA_SERVER_TIME stamps; remote steps are paced by when they happened.
	"server_time_v1",
	"almanac_v1",
	"seasons_v1",
	"combat_hud_v1",
	"inventory_names_v1",
	"inventory_window_v1",
	"item_detail_v1",
	"mail_window_v1",
	"map_digest_v1",
	"mix_window_v1",
	"market_window_v1",
	"market_window_v2",
	"market_window_v3",
	"merchant_window_v1",
	"merchant_weights_v1",
	"merchant_descriptions_v1",
	"merchant_lots_v1",
	"navigation_hud_v1",
	"map_marker_actor_v1",
	"party_window_v1",
	"gauntlet_ready_v1",
	"gauntlet_loot_v1",
	"perk_catalog_v3",
	"player_info_v1",
	"achievements_window_v1",
	"achievements_catalog_v1",
	"leaderboards_v1",
	"actor_titles_v1",
	"actor_occupations_v1",
	"mounts_v1",
	"mount_selection_v1",
	"crystalback_mount_v1",
	"rabbit_mount_v1",
	"raptor_mount_v1",
	# ELORIA_MOUNT_DELTAS: changed riders only, countdowns as server-time
	# deadlines (mount_delta_state.gd).
	"mount_deltas_v1",
	"quest_offers_v1",
	"actor_footprints_v1",
	"actor_wardrobe_v1",
	"weather_state_v1",
	"attribute_state_v1",
	"counter_layout_v1",
	"degraded_items_v1",
	"experience64_v1",
	"guild_window_v1",
	"quest_archive_v1",
	"quest_journal_v1",
	"spell_power_v1",
	"magic_book_v2",
	"spell_visuals_v1",
	"spell_impacts_v1",
	"creature_status_v1",
	"actor_status_v1",
	"special_events_v1",
	"storage_window_v1",
	# Draws the continent-v2 maps (registry status continent-v2-served: the
	# isles' chunk-streamed packages). The server sends CHANGE_MAP onto one only
	# to a client that claims this, and moves a client that does not off it.
	"continent_v2_maps_v1",
	"landfall_underground_v1",
	# The Techniques window and the real action-point pool, sent as
	# ELORIA_MAGIC_STATE kind "techniques".
	"techniques_v1",
	"technique_effects_v1",
	# Repeat casting: whether it is on and running, ELORIA_MAGIC_STATE kind
	# "autocast"; switched with magic_request {"op": "autocast"}.
	"magic_autocast_v1",
	# The character is held off the screen until its ground is loaded and then
	# reported with `#arrived <map>`; the server keeps it out of every fight
	# until then (main.gd `_report_arrival`).
	"arrival_ready_v1",
	# Hold a keyboard direction instead of re-sending MOVE_TO every 360 ms:
	# ELORIA_MOVE_INTENT both ways, used only once the server says it takes them.
	"keyboard_intent_v1",
]

## `#clientcaps` is an ordinary chat command; the server parses it out of
## RAW_TEXT and stores the set on the session. A positive `actor_cap` adds the
## player's cap as a value token after the list, which stays a list of names.
static func client_capabilities(actor_cap := 0) -> PackedByteArray:
	var declared := PackedStringArray(CLIENT_CAPABILITIES)
	if actor_cap > 0:
		declared.append(InterestProtocol.actor_cap_token(actor_cap))
	return chat("#clientcaps " + ",".join(declared))

## Ask the server to use a combat technique. The server checks everything -
## manual, level, gear, cooldown, action points - and answers in chat and with
## a fresh technique state.
static func technique_request(data: Dictionary) -> PackedByteArray:
	return encode(ClientMessage.ELORIA_TECHNIQUE_REQUEST, JSON.stringify(data).to_utf8_buffer())

## Ask the server to play an emote. The name rather than a legacy numeric id:
## this server has no such id namespace, and mirroring one here would be a
## second copy of a list the server owns.
## Loose an arrow at a place rather than at somebody. The server decides
## whether the shot is allowed and what it costs.
static func fire_missile_at_object(x: int, y: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u16(0, x)
	payload.encode_u16(2, y)
	return encode(ClientMessage.FIRE_MISSILE_AT_OBJECT, payload)

## Ask the server what a quest id is. The client never invents a title for an
## id it has not been told about.
static func what_quest_is_this_id(quest_id: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(2)
	payload.encode_u16(0, quest_id)
	return encode(ClientMessage.WHAT_QUEST_IS_THIS_ID, payload)

static func do_emote(name: String) -> PackedByteArray:
	var payload: PackedByteArray = name.to_utf8_buffer()
	payload.append(0)
	return encode(ClientMessage.DO_EMOTE, payload)

## Put one carried item onto another. The server decides what, if anything,
## comes of it.
static func item_on_item(source_slot: int, target_slot: int) -> PackedByteArray:
	return encode(ClientMessage.ITEM_ON_ITEM,
		PackedByteArray([source_slot & 0xFF, target_slot & 0xFF]))

static func chat(text: String) -> PackedByteArray:
	var payload: PackedByteArray = text.to_utf8_buffer()
	payload.append(0)
	return encode(ClientMessage.RAW_TEXT, payload)

static func set_active_channel(slot: int) -> PackedByteArray:
	assert(slot >= 0 and slot < 3)
	# The legacy wire values CHAT_CHANNEL1..3 are 5..7. The server keeps the
	# selected public channel behind those three stable UI slots.
	return encode(ClientMessage.SET_ACTIVE_CHANNEL, PackedByteArray([5 + slot]))

static func locate_me() -> PackedByteArray:
	return encode(ClientMessage.LOCATE_ME)

static func get_date() -> PackedByteArray:
	return encode(ClientMessage.GET_DATE)

static func get_time() -> PackedByteArray:
	return encode(ClientMessage.GET_TIME)

static func private_message(text: String) -> PackedByteArray:
	# Legacy send_input_text_line() removes exactly one leading slash before
	# SEND_PM. Callers provide "name message" or "/message" for reply-last.
	var payload: PackedByteArray = text.to_utf8_buffer()
	payload.append(0)
	return encode(ClientMessage.SEND_PM, payload)

static func touch_actor(actor_id: int) -> PackedByteArray:
	return encode(ClientMessage.TOUCH_PLAYER, PackedByteArray([
		actor_id & 0xff, (actor_id >> 8) & 0xff,
		(actor_id >> 16) & 0xff, (actor_id >> 24) & 0xff]))

static func npc_response(actor_id: int, response_id: int) -> PackedByteArray:
	return encode(ClientMessage.RESPOND_TO_NPC, PackedByteArray([
		actor_id & 0xff, (actor_id >> 8) & 0xff,
		response_id & 0xff, (response_id >> 8) & 0xff]))

static func look_at_inventory_item(slot: int) -> PackedByteArray:
	return encode(ClientMessage.LOOK_AT_INVENTORY_ITEM,
		PackedByteArray([clampi(slot, 0, 255)]))

static func use_inventory_item(slot: int) -> PackedByteArray:
	return encode(ClientMessage.USE_INVENTORY_ITEM,
		PackedByteArray([clampi(slot, 0, 255)]))

static func move_inventory_item(source: int, destination: int) -> PackedByteArray:
	return encode(ClientMessage.MOVE_INVENTORY_ITEM, PackedByteArray([
		clampi(source, 0, 255), clampi(destination, 0, 255)]))

## Casts a spell by its sigils. A power of zero leaves the byte off entirely,
## which is the legacy frame; anything else appends the fork's trailing power
## byte, and the server decides whether that power is allowed.
static func cast_spell(sigils: Array[int], power: int = 0) -> PackedByteArray:
	assert(sigils.size() >= 2 and sigils.size() <= 6)
	var payload: PackedByteArray = PackedByteArray([sigils.size()])
	for sigil_id: int in sigils:
		assert(sigil_id >= 0 and sigil_id <= 63)
		payload.append(sigil_id)
	if power > 0:
		payload.append(mini(power, 255))
	return encode(ClientMessage.CAST_SPELL, payload)

## Answers a server popup. `answers` maps a group id to either an integer
## option value or a string typed into a text entry; the legacy layout is
## `popup_id:u16le` then, per answered group, `group:u8 | value:u8` for a
## choice or `group:u8 | 0:u8 | length:u8 | text` for an entry. A group the
## player left unanswered is simply absent, which is how the legacy client
## reports "no selection" too.
static func popup_reply(popup_id: int, answers: Dictionary) -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		popup_id & 0xff, (popup_id >> 8) & 0xff])
	var groups: Array = answers.keys()
	groups.sort()
	for raw_group: Variant in groups:
		var group: int = int(raw_group)
		assert(group >= 0 and group <= 255)
		var answer: Variant = answers[raw_group]
		if answer is String:
			var text: PackedByteArray = (answer as String).to_utf8_buffer().slice(0, 255)
			payload.append(group)
			payload.append(0)
			payload.append(text.size())
			payload.append_array(text)
		else:
			payload.append(group)
			payload.append(int(answer) & 0xff)
	return encode(ClientMessage.POPUP_REPLY, payload)

## Starts, or stops, harvesting one world object. The command is a toggle: the
## server cancels a run already in progress for the same request.
static func harvest(object_id: int) -> PackedByteArray:
	return encode(ClientMessage.HARVEST, PackedByteArray([
		object_id & 0xff, (object_id >> 8) & 0xff]))

## Asks the server to describe an item lying in the open bag. The bag packet
## carries an image id, a quantity and a slot and nothing else, so this is the
## only way to learn what is on the ground.
static func look_at_ground_item(slot: int) -> PackedByteArray:
	return encode(ClientMessage.LOOK_AT_GROUND_ITEM,
		PackedByteArray([slot & 0xff]))

## Asks the server to describe another player. The reply is command 228 for a
## client with `player_info_v1`, and the legacy text plus `SEND_ACHIEVEMENTS`
## for one without.
static func look_at_player(actor_id: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u32(0, actor_id)
	return encode(ClientMessage.GET_PLAYER_INFO, payload)

## Uses a world object - a waygate, a storage cache, a crafting station. The
## legacy width for both map-object commands is 32 bits.
static func use_map_object(object_id: int) -> PackedByteArray:
	return encode(ClientMessage.USE_MAP_OBJECT, PackedByteArray([
		object_id & 0xff, (object_id >> 8) & 0xff,
		(object_id >> 16) & 0xff, (object_id >> 24) & 0xff]))

static func look_at_map_object(object_id: int) -> PackedByteArray:
	return encode(ClientMessage.LOOK_AT_MAP_OBJECT, PackedByteArray([
		object_id & 0xff, (object_id >> 8) & 0xff,
		(object_id >> 16) & 0xff, (object_id >> 24) & 0xff]))

static func attack_actor(actor_id: int) -> PackedByteArray:
	return encode(ClientMessage.ATTACK_SOMEONE, PackedByteArray([
		actor_id & 0xff, (actor_id >> 8) & 0xff,
		(actor_id >> 16) & 0xff, (actor_id >> 24) & 0xff]))

static func trade_with(actor_id: int) -> PackedByteArray:
	return encode(ClientMessage.TRADE_WITH, PackedByteArray([
		actor_id & 0xff, (actor_id >> 8) & 0xff,
		(actor_id >> 16) & 0xff, (actor_id >> 24) & 0xff]))

static func put_inventory_on_trade(source_slot: int, quantity: int) -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		1, clampi(source_slot, 0, 255),
		quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff])
	return encode(ClientMessage.PUT_OBJECT_ON_TRADE, payload)

static func remove_trade_item(offer_slot: int, quantity: int) -> PackedByteArray:
	var payload: PackedByteArray = PackedByteArray([
		clampi(offer_slot, 0, 15), quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff])
	return encode(ClientMessage.REMOVE_OBJECT_FROM_TRADE, payload)

static func accept_trade(destinations: PackedByteArray = PackedByteArray()) -> PackedByteArray:
	var payload: PackedByteArray = destinations.slice(0, 16)
	while payload.size() < 16:
		payload.append(1)
	for index: int in range(payload.size()):
		payload[index] = 2 if int(payload[index]) == 2 else 1
	return encode(ClientMessage.ACCEPT_TRADE, payload)

static func reject_trade() -> PackedByteArray:
	return encode(ClientMessage.REJECT_TRADE)

static func exit_trade() -> PackedByteArray:
	return encode(ClientMessage.EXIT_TRADE)

static func look_at_trade_item(offer_slot: int, other: bool) -> PackedByteArray:
	return encode(ClientMessage.LOOK_AT_TRADE_ITEM,
		PackedByteArray([clampi(offer_slot, 0, 15), 1 if other else 0]))

static func get_storage_category(category_id: int) -> PackedByteArray:
	return encode(ClientMessage.GET_STORAGE_CATEGORY,
		PackedByteArray([clampi(category_id, 0, 255)]))

static func deposit_storage(inventory_slot: int, quantity: int) -> PackedByteArray:
	return encode(ClientMessage.DEPOSIT_ITEM, PackedByteArray([
		clampi(inventory_slot, 0, 255), quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff]))

static func withdraw_storage(position: int, quantity: int) -> PackedByteArray:
	return encode(ClientMessage.WITHDRAW_ITEM, PackedByteArray([
		position & 0xff, (position >> 8) & 0xff,
		quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff]))

static func look_at_storage_item(position: int) -> PackedByteArray:
	return encode(ClientMessage.LOOK_AT_STORAGE_ITEM,
		PackedByteArray([position & 0xff, (position >> 8) & 0xff]))

static func inspect_bag(bag_id: int) -> PackedByteArray:
	return encode(ClientMessage.INSPECT_BAG,
		PackedByteArray([clampi(bag_id, 0, 255)]))

static func close_bag() -> PackedByteArray:
	return encode(ClientMessage.CLOSE_BAG)

static func pick_up_ground_item(position: int, quantity: int) -> PackedByteArray:
	return encode(ClientMessage.PICK_UP_ITEM, PackedByteArray([
		clampi(position, 0, 255), quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff]))

static func drop_inventory_item(slot: int, quantity: int) -> PackedByteArray:
	return encode(ClientMessage.DROP_ITEM, PackedByteArray([
		clampi(slot, 0, 255), quantity & 0xff, (quantity >> 8) & 0xff,
		(quantity >> 16) & 0xff, (quantity >> 24) & 0xff]))

static func get_knowledge_info(index: int) -> PackedByteArray:
	return encode(ClientMessage.GET_KNOWLEDGE_INFO,
		PackedByteArray([index & 0xff, (index >> 8) & 0xff]))

## Mix by recipe rather than by the inventory positions the ingredients sit
## in. `MANUFACTURE_THIS` can only name positions, which makes mixing out of
## storage unsayable in it: the materials are not in any inventory position.
static func mix_request(recipe_index: int, wanted: int,
		from_storage: bool) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(5)
	payload.encode_u16(0, maxi(0, recipe_index))
	payload.encode_u16(2, clampi(wanted, 1, 65535))
	payload[4] = 1 if from_storage else 0
	return encode(ClientMessage.ELORIA_MIX_REQUEST, payload)

## Take one of a recipe's tools out of storage. Named rather than pointed at,
## because the window knows a tool by name and never opens storage to learn
## which slot it is in. Tools wear out, so this is the difference between
## replacing a hatchet and leaving the window to go and find one.
static func tool_request(name: String) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append_array(name.to_utf8_buffer())
	payload.append(0)
	return encode(ClientMessage.ELORIA_TOOL_REQUEST, payload)

static func manufacture(ingredients: Array[Dictionary], wanted: int = 1) -> PackedByteArray:
	# Legacy mix_handler(): count:u8, repeated slot:u8 + quantity:u16le,
	# then wanted:u8. The six-entry cap is the legacy manufacture tray size.
	assert(ingredients.size() >= 1 and ingredients.size() <= 6)
	assert(wanted >= 1 and wanted <= 255)
	var payload: PackedByteArray = PackedByteArray([ingredients.size()])
	for ingredient: Dictionary in ingredients:
		var slot: int = int(ingredient.get("slot", -1))
		var quantity: int = int(ingredient.get("quantity", 0))
		assert(slot >= 0 and slot <= 35)
		assert(quantity >= 1 and quantity <= 0xffff)
		payload.append(slot)
		payload.append(quantity & 0xff)
		payload.append((quantity >> 8) & 0xff)
	payload.append(wanted)
	return encode(ClientMessage.MANUFACTURE_THIS, payload)

static func actor_command_step(command: int) -> Vector2i:
	# Server movement frames are the authoritative one-tile updates used by the
	# legacy client. Walk and run use the same tile delta; timing differs.
	var direction: int = command
	if command >= 30 and command <= 37:
		direction = command - 10
	match direction:
		20: return Vector2i(0, 1)
		21: return Vector2i(1, 1)
		22: return Vector2i(1, 0)
		23: return Vector2i(1, -1)
		24: return Vector2i(0, -1)
		25: return Vector2i(-1, -1)
		26: return Vector2i(-1, 0)
		27: return Vector2i(-1, 1)
		_: return Vector2i.ZERO

## True for the eight CMD_TURN_* facing commands. A turn command is the
## server's confirmation of a local turn prediction.
static func is_turn_command(command: int) -> bool:
	return command >= 38 and command <= 45

static func actor_command_direction(command: int) -> Vector2i:
	var direction: int = command
	if command >= 30 and command <= 37:
		direction = command - 10
	elif command >= 38 and command <= 45:
		direction = command - 18
	match direction:
		20: return Vector2i(0, 1)
		21: return Vector2i(1, 1)
		22: return Vector2i(1, 0)
		23: return Vector2i(1, -1)
		24: return Vector2i(0, -1)
		25: return Vector2i(-1, -1)
		26: return Vector2i(-1, 0)
		27: return Vector2i(-1, 1)
		_: return Vector2i.ZERO

static func decode_leaderboard_state(payload: PackedByteArray) -> Dictionary:
	return preload("res://src/network/leaderboard_codec.gd").decode(payload)

static func decode_server(command: int, payload: PackedByteArray, logical_coordinates := false) -> Dictionary:
	match command:
		ServerMessage.ELORIA_INVASION_ASSISTANT_STATE:
			var parsed: Variant = JSON.parse_string(payload.get_string_from_utf8())
			if not parsed is Dictionary:
				return {"type": "invalid", "error": "invasion_assistant_json"}
			return {"type": "invasion_assistant", "state": parsed}
		ServerMessage.LOG_IN_OK:
			return {"type": "login_ok"}
		ServerMessage.LOG_IN_NOT_OK:
			return {"type": "login_error", "message": nul_string(payload)}
		ServerMessage.CREATE_CHAR_OK:
			return {"type": "create_character_ok"}
		ServerMessage.CREATE_CHAR_NOT_OK:
			return {"type": "create_character_error", "message": nul_string(payload)}
		ServerMessage.YOU_ARE:
			return {"type": "you_are", "actor_id": u16(payload)} if payload.size() >= 2 else {"type": "invalid", "error": "short_payload"}
		ServerMessage.SYNC_CLOCK:
			return {"type": "clock_sync", "server_timestamp": u32(payload)} if payload.size() >= 4 else {"type": "invalid", "error": "clock_sync_length"}
		ServerMessage.NEW_MINUTE:
			return {"type": "new_minute", "minute": u16(payload) % 360} if payload.size() >= 2 else {"type": "invalid", "error": "new_minute_length"}
		ServerMessage.CHANGE_MAP:
			return {"type": "change_map", "map_name": nul_string(payload)}
		ServerMessage.REMOVE_ACTOR:
			# The server batches every actor that left view into one packet -
			# a pack of creatures dying together, or a whole screen of them
			# falling out of visibility range at once. Reading only the first
			# id left the rest standing on the map for good, because the
			# server considers them gone and never repeats the removal.
			if payload.size() < 2:
				return {"type": "invalid", "error": "short_payload"}
			var removed_actor_ids: Array[int] = []
			for offset: int in range(0, payload.size() - 1, 2):
				removed_actor_ids.append(u16(payload, offset))
			return {"type": "remove_actor", "actor_ids": removed_actor_ids}
		ServerMessage.KILL_ALL_ACTORS:
			return {"type": "clear_actors"}
		ServerMessage.ADD_ACTOR_COMMAND:
			if payload.size() % 3 != 0:
				return {"type": "invalid", "error": "actor_command_length"}
			var commands: Array[Dictionary] = []
			for offset in range(0, payload.size(), 3):
				commands.append({"actor_id": u16(payload, offset), "command": int(payload[offset + 2])})
			return {"type": "actor_commands", "commands": commands}
		ServerMessage.ADD_NEW_ACTOR:
			return decode_actor(payload, false)
		ServerMessage.ADD_NEW_ACTOR_EXTENDED:
			return decode_actor(payload, false, true)
		ServerMessage.ADD_NEW_ENHANCED_ACTOR:
			return decode_actor(payload, true)
		ServerMessage.HERE_YOUR_STATS:
			return decode_stats(payload)
		ServerMessage.SEND_PARTIAL_STAT:
			return decode_partial_stats(payload)
		ServerMessage.HERE_YOUR_INVENTORY:
			return decode_inventory(payload)
		ServerMessage.GET_NEW_INVENTORY_ITEM:
			return decode_inventory_update(payload)
		ServerMessage.REMOVE_ITEM_FROM_INVENTORY:
			if payload.is_empty():
				return {"type": "invalid", "error": "inventory_remove_length"}
			var removed_slots: Array[int] = []
			for slot_value: int in payload:
				removed_slots.append(slot_value)
			return {"type": "inventory_remove", "slots": removed_slots}
		ServerMessage.INVENTORY_ITEM_TEXT:
			if payload.is_empty():
				return {"type": "invalid", "error": "inventory_text_length"}
			return {"type": "inventory_text", "color": int(payload[0]),
				"text": nul_string(payload.slice(1))}
		ServerMessage.GET_NEW_BAG:
			return decode_ground_bag(payload)
		ServerMessage.GET_BAGS_LIST:
			return decode_ground_bags(payload)
		ServerMessage.DESTROY_BAG:
			if payload.size() != 1:
				return {"type": "invalid", "error": "ground_bag_destroy_length"}
			return {"type": "ground_bag_destroy", "bag_id": int(payload[0])}
		ServerMessage.HERE_YOUR_GROUND_ITEMS:
			return decode_ground_items(payload)
		ServerMessage.GET_NEW_GROUND_ITEM:
			if payload.size() != 7:
				return {"type": "invalid", "error": "ground_item_length"}
			return {"type": "ground_item", "item": decode_ground_item(payload)}
		ServerMessage.REMOVE_ITEM_FROM_GROUND:
			if payload.size() != 1:
				return {"type": "invalid", "error": "ground_item_remove_length"}
			return {"type": "ground_item_remove", "position": int(payload[0])}
		ServerMessage.CLOSE_BAG:
			if not payload.is_empty():
				return {"type": "invalid", "error": "ground_bag_close_length"}
			return {"type": "ground_bag_close"}
		ServerMessage.GET_KNOWLEDGE_LIST:
			var known: Array[int] = []
			for byte_index: int in range(payload.size()):
				for bit_index: int in range(8):
					if (int(payload[byte_index]) & (1 << bit_index)) != 0:
						known.append(byte_index * 8 + bit_index)
			return {"type": "knowledge_list", "known": known,
				"capacity": payload.size() * 8}
		ServerMessage.GET_NEW_KNOWLEDGE:
			if payload.size() != 2:
				return {"type": "invalid", "error": "new_knowledge_length"}
			return {"type": "new_knowledge", "index": u16(payload)}
		ServerMessage.GET_KNOWLEDGE_TEXT:
			if payload.is_empty():
				return {"type": "invalid", "error": "knowledge_text_length"}
			return {"type": "knowledge_text", "text": nul_string(payload)}
		ServerMessage.GET_ITEMS_COOLDOWN:
			return decode_item_cooldowns(payload)
		ServerMessage.GET_TRADE_PARTNER_NAME:
			if payload.size() < 2:
				return {"type": "invalid", "error": "trade_partner_length"}
			return {"type": "trade_partner", "storage_available": bool(payload[0]),
				"name": nul_string(payload.slice(1))}
		ServerMessage.GET_YOUR_TRADEOBJECTS:
			var trade_inventory: Dictionary = decode_inventory(payload)
			if trade_inventory.get("type", "") == "inventory":
				trade_inventory["type"] = "trade_inventory"
			return trade_inventory
		ServerMessage.GET_TRADE_OBJECT:
			if payload.size() != 9:
				return {"type": "invalid", "error": "trade_object_length"}
			return {"type": "trade_object", "image_id": u16(payload),
				"quantity": u32(payload, 2), "source_type": int(payload[6]),
				"slot": int(payload[7]), "other": bool(payload[8])}
		ServerMessage.REMOVE_TRADE_OBJECT:
			if payload.size() != 6:
				return {"type": "invalid", "error": "trade_remove_length"}
			return {"type": "trade_remove", "quantity": u32(payload),
				"slot": int(payload[4]), "other": bool(payload[5])}
		ServerMessage.GET_TRADE_ACCEPT:
			# The phase is on the wire. Counting accept packets desynchronised
			# the two-phase state machine from the server's view of the trade
			# the moment one was duplicated, dropped or reordered.
			if payload.size() != 2:
				return {"type": "invalid", "error": "trade_accept_length"}
			if int(payload[1]) > 2:
				return {"type": "invalid", "error": "trade_accept_phase"}
			return {"type": "trade_accept", "other": bool(payload[0]),
				"phase": int(payload[1])}
		ServerMessage.GET_TRADE_REJECT:
			if payload.size() != 1:
				return {"type": "invalid", "error": "trade_reject_length"}
			return {"type": "trade_reject", "other": bool(payload[0])}
		ServerMessage.GET_TRADE_EXIT:
			if not payload.is_empty():
				return {"type": "invalid", "error": "trade_exit_length"}
			return {"type": "trade_exit"}
		ServerMessage.STORAGE_LIST:
			return decode_storage_categories(payload)
		ServerMessage.STORAGE_ITEMS:
			return decode_storage_items(payload)
		ServerMessage.ELORIA_STORAGE_STATE:
			return decode_storage_state(payload)
		ServerMessage.STORAGE_TEXT:
			if payload.is_empty():
				return {"type": "invalid", "error": "storage_text_length"}
			return {"type": "storage_text", "color": int(payload[0]),
				"text": nul_string(payload.slice(1))}
		ServerMessage.GET_YOUR_SIGILS:
			if payload.size() != 8:
				return {"type": "invalid", "error": "sigils_length"}
			var owned_sigils: Array[int] = []
			for sigil_id: int in range(64):
				var mask_offset: int = 0 if sigil_id < 32 else 4
				var mask_bit: int = sigil_id if sigil_id < 32 else sigil_id - 32
				if (u32(payload, mask_offset) & (1 << mask_bit)) != 0:
					owned_sigils.append(sigil_id)
			# The two raw masks are the wire form of `owned`; carrying both
			# invites two sources of truth for the same fact.
			return {"type": "sigils", "owned": owned_sigils}
		ServerMessage.SPELL_CAST:
			if payload.size() not in [2, 4] or int(payload[0]) < 1 or int(payload[0]) > 6:
				return {"type": "invalid", "error": "spell_result_length"}
			var result := {"type": "spell_result", "status": int(payload[0]),
				"spell_id": int(payload[1])}
			if payload.size() == 4:
				if int(payload[2]) < 1 or int(payload[2]) > 10:
					return {"type": "invalid", "error": "spell_result_power"}
				result["power"] = int(payload[2])
				result["visual_effect"] = int(payload[3])
			return result
		ServerMessage.MISSILE_AIM_A_AT_B, ServerMessage.MISSILE_FIRE_A_TO_B:
			# Both carry the same pair: who is shooting and what at. The
			# server sends an aim before every shot and a fire when it looses,
			# so the two together are the whole engagement.
			if payload.size() != 4:
				return {"type": "invalid", "error": "missile_length"}
			return {"type": "missile",
				"fired": command == ServerMessage.MISSILE_FIRE_A_TO_B,
				"source_actor_id": u16(payload),
				"target_actor_id": u16(payload, 2)}
		ServerMessage.GET_3D_OBJ:
			# An object placed into a map that is already being played in.
			# Everything the client knew about a map used to arrive with the
			# map, so nothing could change while anybody was looking at it.
			var placed: Dictionary = _world_object_at(payload, 0)
			if placed.is_empty() or int(placed.offset) != payload.size():
				return {"type": "invalid", "error": "world_object"}
			return {"type": "world_object", "objects": [placed.value],
				"replace": false}
		ServerMessage.GET_3D_OBJ_LIST:
			if payload.size() < 2:
				return {"type": "invalid", "error": "world_object_list_length"}
			var wanted: int = u16(payload)
			var listed: Array[Dictionary] = []
			var at: int = 2
			for _index: int in range(wanted):
				var entry: Dictionary = _world_object_at(payload, at)
				if entry.is_empty():
					return {"type": "invalid", "error": "world_object_list"}
				listed.append(entry.value as Dictionary)
				at = int(entry.offset)
			if at != payload.size():
				return {"type": "invalid", "error": "world_object_list_trailing"}
			# A list is the whole truth about a map, so it replaces what was
			# there rather than adding to it.
			return {"type": "world_object", "objects": listed, "replace": true}
		ServerMessage.REMOVE_3D_OBJ:
			if payload.size() != 2:
				return {"type": "invalid", "error": "remove_world_object"}
			return {"type": "world_object_removed", "object_id": u16(payload)}
		ServerMessage.GET_TELEPORTERS_LIST:
			if payload.size() < 2:
				return {"type": "invalid", "error": "teleporters_length"}
			var teleporter_count: int = u16(payload)
			if payload.size() != 2 + teleporter_count * 4:
				return {"type": "invalid", "error": "teleporters_trailing"}
			var tiles: Array[Vector2i] = []
			for index: int in range(teleporter_count):
				tiles.append(Vector2i(u16(payload, 2 + index * 4),
					u16(payload, 4 + index * 4)))
			return {"type": "teleporters", "tiles": tiles}
		ServerMessage.TELEPORT_IN, ServerMessage.TELEPORT_OUT:
			if payload.size() != 4:
				return {"type": "invalid", "error": "teleport_length"}
			return {"type": "teleport", "arriving":
				command == ServerMessage.TELEPORT_IN,
				"x": u16(payload), "y": u16(payload, 2)}
		ServerMessage.BUDDY_EVENT:
			# What happened, and to whom. The name travels with the event
			# because a client that had to keep its own list to read one would
			# be keeping a second copy of a list the server owns.
			if payload.size() < 2:
				return {"type": "invalid", "error": "buddy_length"}
			if int(payload[0]) >= BUDDY_EVENTS.size():
				return {"type": "invalid", "error": "buddy_event"}
			var buddy_field: Dictionary = _nul_at(payload, 1)
			if buddy_field.is_empty():
				return {"type": "invalid", "error": "buddy_text"}
			if int(buddy_field.offset) != payload.size():
				return {"type": "invalid", "error": "buddy_trailing"}
			if str(buddy_field.value).is_empty():
				return {"type": "invalid", "error": "buddy_empty"}
			return {"type": "buddy", "event": BUDDY_EVENTS[int(payload[0])],
				"name": str(buddy_field.value)}
		ServerMessage.NEXT_NPC_MESSAGE_IS_QUEST:
			# A flag with no payload: the NPC text after it is quest dialogue
			# rather than small talk. It comes first because it describes what
			# follows it.
			if payload.size() != 0:
				return {"type": "invalid", "error": "quest_flag_trailing"}
			return {"type": "quest_dialogue_next"}
		ServerMessage.HERE_IS_QUEST_ID, ServerMessage.QUEST_FINISHED:
			if payload.size() != 2:
				return {"type": "invalid", "error": "quest_id_length"}
			return {"type": "quest_id", "quest_id": u16(payload),
				"finished": command == ServerMessage.QUEST_FINISHED}
		ServerMessage.SEND_WEATHER:
			# The whole sky in one frame. Weather is the server's because two
			# players standing together have to see the same one.
			if payload.size() != 2:
				return {"type": "invalid", "error": "weather_length"}
			if int(payload[1]) > 100:
				return {"type": "invalid", "error": "weather_intensity"}
			return {"type": "weather", "kind": int(payload[0]),
				"intensity": int(payload[1])}
		ServerMessage.START_RAIN, ServerMessage.STOP_RAIN:
			# The legacy client's own rain signals, sent alongside the sky
			# frame. This client reads the sky frame and takes these as
			# confirmation, so an older server that sends only these still
			# makes it rain.
			var starting: bool = command == ServerMessage.START_RAIN
			if starting and payload.size() != 1:
				return {"type": "invalid", "error": "rain_length"}
			if not starting and payload.size() != 0:
				return {"type": "invalid", "error": "rain_trailing"}
			return {"type": "rain", "falling": starting,
				"intensity": int(payload[0]) if starting else 0}
		ServerMessage.THUNDER:
			if payload.size() != 1:
				return {"type": "invalid", "error": "thunder_length"}
			return {"type": "thunder", "severity": int(payload[0])}
		ServerMessage.FIRE_PARTICLES:
			if payload.size() != 5:
				return {"type": "invalid", "error": "fire_length"}
			return {"type": "fire", "x": u16(payload), "y": u16(payload, 2),
				"kind": int(payload[4]), "burning": true}
		ServerMessage.REMOVE_FIRE_AT:
			if payload.size() != 4:
				return {"type": "invalid", "error": "remove_fire_length"}
			return {"type": "fire", "x": u16(payload), "y": u16(payload, 2),
				"kind": -1, "burning": false}
		ServerMessage.PLAY_SOUND:
			# A sound the client could not have worked out for itself: what
			# somebody else is doing. It is named rather than numbered, so
			# there is no id table to keep in step, and a name this client has
			# no sound for is simply not heard.
			if payload.size() < 6:
				return {"type": "invalid", "error": "play_sound_length"}
			var sound_field: Dictionary = _nul_at(payload, 5)
			if sound_field.is_empty():
				return {"type": "invalid", "error": "play_sound_text"}
			if int(sound_field.offset) != payload.size():
				return {"type": "invalid", "error": "play_sound_trailing"}
			if str(sound_field.value).is_empty():
				return {"type": "invalid", "error": "play_sound_empty"}
			return {"type": "play_sound", "name": str(sound_field.value),
				"x": u16(payload), "y": u16(payload, 2),
				"gain": float(int(payload[4])) / 100.0}
		ServerMessage.PLAY_MUSIC:
			# An empty track name is the server saying "nothing here", which is
			# an answer rather than an omission.
			var track_field: Dictionary = _nul_at(payload, 0)
			if track_field.is_empty():
				return {"type": "invalid", "error": "play_music_text"}
			if int(track_field.offset) != payload.size():
				return {"type": "invalid", "error": "play_music_trailing"}
			return {"type": "play_music", "track": str(track_field.value)}
		ServerMessage.MISSILE_AIM_A_AT_XYZ, ServerMessage.MISSILE_FIRE_A_TO_XYZ:
			# An arrow going to a place rather than into somebody: a practice
			# shot, or a miss. The server decides where it lands, because the
			# server decided it was a miss - a client inventing its own
			# scatter would draw something that never happened.
			if payload.size() != 6:
				return {"type": "invalid", "error": "ground_missile_length"}
			return {"type": "ground_missile",
				"fired": command == ServerMessage.MISSILE_FIRE_A_TO_XYZ,
				"source_actor_id": u16(payload),
				"x": u16(payload, 2), "y": u16(payload, 4)}
		ServerMessage.SEND_SPECIAL_EFFECT:
			# spell_visuals_v1 appends the resolved power byte to either legacy shape.
			if payload.size() not in [3, 4, 5, 6]:
				return {"type": "invalid", "error": "special_effect_length"}
			var power := int(payload[-1]) if payload.size() in [4, 6] else 1
			if power < 1 or power > 10:
				return {"type": "invalid", "error": "special_effect_power"}
			return {"type": "special_effect", "effect": int(payload[0]),
				"actor_id": u16(payload, 1),
				"target_id": u16(payload, 3) if payload.size() >= 5 else -1,
				"power": power}
		ServerMessage.SEND_BUFFS:
			if payload.size() != 6:
				return {"type": "invalid", "error": "actor_buffs_length"}
			return {"type": "actor_buffs", "actor_id": u16(payload),
				"buffs": u32(payload, 2)}
		ServerMessage.GET_ACTIVE_SPELL:
			if payload.size() != 2:
				return {"type": "invalid", "error": "active_spell_length"}
			return {"type": "active_spell", "buff_id": int(payload[0]),
				"duration_seconds": int(payload[1])}
		ServerMessage.GET_ACTIVE_SPELL_LIST:
			if payload.size() != 10:
				return {"type": "invalid", "error": "active_spell_list_length"}
			var active_buffs: Array[int] = []
			for buff_id: int in payload:
				if buff_id != 255:
					active_buffs.append(buff_id)
			return {"type": "active_spell_list", "buffs": active_buffs}
		ServerMessage.REMOVE_ACTIVE_SPELL:
			if payload.size() != 1:
				return {"type": "invalid", "error": "remove_active_spell_length"}
			return {"type": "remove_active_spell", "buff_id": int(payload[0])}
		ServerMessage.ACTOR_WEAR_ITEM:
			if payload.size() != 4:
				return {"type": "invalid", "error": "actor_wear_length"}
			return {"type": "actor_wear", "actor_id": u16(payload),
				"part": int(payload[2]), "visual_id": int(payload[3])}
		ServerMessage.ACTOR_UNWEAR_ITEM:
			if payload.size() != 3:
				return {"type": "invalid", "error": "actor_unwear_length"}
			return {"type": "actor_unwear", "actor_id": u16(payload),
				"part": int(payload[2])}
		ServerMessage.GET_ACTOR_DAMAGE:
			if payload.size() != 4:
				return {"type": "invalid", "error": "actor_damage_length"}
			return {"type": "actor_damage", "actor_id": u16(payload),
				"amount": u16(payload, 2)}
		ServerMessage.GET_ACTOR_HEAL:
			if payload.size() != 4:
				return {"type": "invalid", "error": "actor_heal_length"}
			return {"type": "actor_heal", "actor_id": u16(payload),
				"amount": u16(payload, 2)}
		ServerMessage.GET_ACTOR_HEALTH:
			if payload.size() != 4:
				return {"type": "invalid", "error": "actor_health_length"}
			return {"type": "actor_max_health", "actor_id": u16(payload),
				"max_health": u16(payload, 2)}
		ServerMessage.GET_ACTIVE_CHANNELS:
			if payload.is_empty() or (payload.size() - 1) % 4 != 0:
				return {"type": "invalid", "error": "active_channels_length"}
			var active_channels: Array[int] = []
			for offset: int in range(1, payload.size(), 4):
				active_channels.append(u32(payload, offset))
			return {"type": "active_channels", "active_index": int(payload[0]),
				"channels": active_channels}
		ServerMessage.RAW_TEXT:
			if payload.is_empty():
				return {"type": "invalid", "error": "chat_length"}
			# One copy of the line, read twice. The payload was sliced once to
			# strip the colour markers out of it and again to read the first of
			# them, so every chat line was copied twice to be read once.
			var chat_bytes: PackedByteArray = payload.slice(1)
			return {"type": "chat", "channel": int(payload[0]),
				"text": legacy_colored_string(chat_bytes),
				"colour": leading_text_colour(chat_bytes)}
		ServerMessage.SEND_NPC_INFO:
			# The trailing byte is the legacy portrait index. Eloria has no
			# portrait art and cannot convert the Eternal Lands set, so the
			# field is deliberately not carried into the DTO rather than being
			# decoded and ignored. Add it back with the artwork, not before.
			if payload.size() < 20:
				return {"type": "invalid", "error": "npc_info_length"}
			return {"type": "npc_info", "name": nul_string(payload.slice(0, 20))}
		ServerMessage.NPC_TEXT:
			return {"type": "npc_text", "text": nul_string(payload)}
		ServerMessage.NPC_OPTIONS_LIST:
			return decode_npc_options(payload)
		ServerMessage.CLOSE_NPC_MENU:
			return {"type": "npc_close"}
		ServerMessage.DISPLAY_POPUP:
			return decode_popup(payload)
		ServerMessage.ELORIA_MAGIC_STATE:
			var magic: Variant = JSON.parse_string(payload.get_string_from_utf8())
			if magic is Dictionary:
				return {"type": "magic_state", "data": magic}
			return {"type": "invalid", "error": "magic_state_json"}
		ServerMessage.ELORIA_LEADERBOARD_STATE:
			return decode_leaderboard_state(payload)
		ServerMessage.ELORIA_SPELL_POWER:
			return decode_spell_power(payload)
		ServerMessage.ELORIA_ALMANAC_STATE:
			return decode_almanac(payload)
		ServerMessage.ADD_ACTOR_ANIMATION:
			return decode_actor_animation(payload)
		ServerMessage.ELORIA_PLAYER_INFO:
			return decode_player_info(payload)
		ServerMessage.SEND_MAP_MARKER:
			return decode_map_marker(payload)
		ServerMessage.REMOVE_MAP_MARKER:
			if payload.size() != 2:
				return {"type": "invalid", "error": "remove_map_marker_length"}
			return {"type": "remove_map_marker", "marker_id": u16(payload)}
		ServerMessage.ELORIA_PARTY_STATE:
			return decode_party(payload)
		ServerMessage.ELORIA_GUILD_STATE:
			return decode_guild(payload)
		ServerMessage.ELORIA_QUEST_ARCHIVE_STATE:
			return decode_quest_archive(payload)
		ServerMessage.ELORIA_DEGRADED_ITEMS:
			return decode_degraded_items(payload)
		ServerMessage.ELORIA_ACHIEVEMENTS_STATE:
			return decode_achievements_state(payload)
		ServerMessage.ELORIA_ACHIEVEMENTS_CATALOG:
			return decode_achievements_catalog(payload)
		ServerMessage.ELORIA_WEATHER_STATE:
			return decode_weather_state(payload)
		ServerMessage.ELORIA_ACTOR_TITLES:
			return decode_actor_titles(payload)
		ServerMessage.ELORIA_ACTOR_OCCUPATIONS:
			return decode_actor_occupations(payload)
		ServerMessage.ELORIA_MOUNT_STATES:
			return preload("res://src/mounts/mount_protocol.gd").decode(payload)
		ServerMessage.ELORIA_MOUNT_DELTAS:
			return InterestProtocol.decode_mount_deltas(payload)
		ServerMessage.ELORIA_PRESENCE:
			return InterestProtocol.decode_presence(payload)
		ServerMessage.ELORIA_SERVER_TIME:
			return InterestProtocol.decode_server_time(payload)
		ServerMessage.ELORIA_QUEST_OFFERS:
			if payload.size() < 2 or payload.size() != 2 + u16(payload) * 2:
				return {"type": "invalid", "error": "quest_offers_length"}
			var offered_ids: Array[int] = []
			for index: int in range(u16(payload)):
				offered_ids.append(u16(payload, 2 + index * 2))
			return {"type": "quest_offers", "actor_ids": offered_ids}
		ServerMessage.ELORIA_ADJACENT_MAPS:
			return decode_adjacent_maps(payload)
		ServerMessage.ELORIA_MAP_DIGEST:
			return decode_map_digest(payload)
		ServerMessage.ELORIA_CLIENT_UPDATE:
			var notice: Variant = JSON.parse_string(payload.get_string_from_utf8())
			if not notice is Dictionary or notice.get("schema") != 1:
				return {"type": "invalid", "error": "client_update_shape"}
			return {"type": "client_update", "notice": notice}
		ServerMessage.ELORIA_GAUNTLET_READY_STATE:
			return decode_gauntlet_ready(payload)
		ServerMessage.ELORIA_GAUNTLET_LOOT_STATE:
			return decode_gauntlet_loot(payload)
		ServerMessage.ELORIA_LANTERN_STATE:
			return decode_lantern(payload, logical_coordinates)
		ServerMessage.ELORIA_EXPERIENCE_STATE:
			return decode_experience_state(payload)
		ServerMessage.ELORIA_INVENTORY_NAMES:
			return decode_inventory_names(payload)
		ServerMessage.ELORIA_ACTOR_FOOTPRINTS:
			return decode_actor_footprints(payload)
		ServerMessage.ELORIA_ATTRIBUTE_STATE:
			return decode_attribute_state(payload)
		ServerMessage.ELORIA_COUNTER_LAYOUT:
			return decode_counter_layout(payload)
		ServerMessage.ELORIA_MIX_STATE:
			return decode_mix_state(payload)
		ServerMessage.ELORIA_PERK_CATALOG:
			return decode_perk_catalog(payload)
		ServerMessage.ELORIA_WORN_SLOTS:
			if payload.size() != 8:
				return {"type": "invalid", "error": "worn_slots_length"}
			var mask: int = 0
			for index: int in range(8):
				mask |= int(payload[index]) << (index * 8)
			return {"type": "worn_slots", "mask": mask}
		ServerMessage.ELORIA_MARKETPLACE_STATE:
			return decode_marketplace(payload)
		ServerMessage.ELORIA_MERCHANT_STATE:
			return decode_merchant(payload)
		ServerMessage.ELORIA_QUEST_JOURNAL_STATE:
			return decode_quest_journal(payload)
		ServerMessage.ELORIA_ITEM_DETAIL:
			return decode_item_detail(payload)
		ServerMessage.ELORIA_INVENTORY_STATE:
			return decode_inventory_state(payload)
		ServerMessage.ELORIA_COMBAT_STATE:
			return decode_combat_state(payload)
		ServerMessage.ELORIA_MAIL_STATE:
			return decode_mail(payload)
		ServerMessage.ELORIA_NAVIGATION_STATE:
			return decode_navigation(payload)
		ServerMessage.ELORIA_MOVE_INTENT:
			return decode_move_intent(payload)
		ServerMessage.ELORIA_SPECIAL_EVENT_STATE:
			return decode_special_events(payload)
		ServerMessage.ELORIA_MAP_OBJECTS:
			return decode_map_objects(payload)
		ServerMessage.ELORIA_HARVEST_STATE:
			return decode_harvest_state(payload)
		ServerMessage.ELORIA_PERKS:
			return decode_perks(payload)
		ServerMessage.ELORIA_ACTIVITY_COUNTERS:
			return decode_activity_counters(payload)
		ServerMessage.PING_REQUEST:
			return {"type": "ping_request"}
		_:
			return {"type": "unknown", "command": command, "payload": payload}

## --- Eloria extension windows -----------------------------------------------
##
## Nine server-push state packets, each driving one window. They are the fork's
## own additions rather than upstream Eternal Lands, and the server withholds
## every one of them from a client that has not claimed the matching capability
## in `#clientcaps` - which is why this client saw none of them until Phase 1.
##
## Every one of these is a snapshot: the server states the whole window, the
## client renders it. None of them is merged with a previous value.

## A NUL-terminated UTF-8 string at `offset`. Returns the value and the offset
## just past the terminator, or an empty dictionary when the payload does not
## contain one.
static func _nul_at(payload: PackedByteArray, offset: int) -> Dictionary:
	if offset >= payload.size():
		return {}
	var end: int = payload.find(0, offset)
	if end < 0:
		return {}
	return {"value": payload.slice(offset, end).get_string_from_utf8(),
		"offset": end + 1}

## Reads `count` NUL-terminated strings in order. Returns the values and the
## offset past the last terminator, or an empty dictionary on a short payload.
static func _nul_run(payload: PackedByteArray, offset: int,
		count: int) -> Dictionary:
	var values: Array[String] = []
	for _index: int in range(count):
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {}
		values.append(str(field.value))
		offset = int(field.offset)
	return {"values": values, "offset": offset}

## Command 245. A skill's true lifetime experience, in 64 bits.
##
## The legacy stats packet carries experience in a 32-bit field at a fixed
## offset, so a total past four billion shows as four billion there. This is
## the same number without that ceiling, plus what it has bought since the
## skill stopped levelling. GDScript integers are signed 64-bit, which covers
## every value this can carry short of the top bit.
static func decode_experience_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "experience_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var skills: Array[Dictionary] = []
	for _index: int in range(count):
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {"type": "invalid", "error": "experience_skill_text"}
		offset = int(field.offset)
		if offset + 20 > payload.size():
			return {"type": "invalid", "error": "experience_skill_values"}
		skills.append({
			"skill": str(field.value),
			"experience": u64(payload, offset),
			"next_level": u64(payload, offset + 8),
			"post_cap_points": u32(payload, offset + 16)})
		offset += 20
	if offset != payload.size():
		return {"type": "invalid", "error": "experience_trailing"}
	return {"type": "experience_state", "skills": skills}

## Command 217. How the counters window is arranged, and what fills it.
##
## Three tables in one packet: which page each total belongs on, what a row
## opens into, and the achievements with the rung each is working towards.
## None of the arrangement is decided here - a client grouping seventeen
## totals by a table of its own would be drawing last week's window the day
## a counter moves.
## What the manufacturing window cannot work out for itself.
##
## Whether storage is close enough to mix from is a distance to an actor the
## client is never told the role of, so the window would have to guess, and a
## guess greys the control out in the one place a player wanted it.
##
## The rest describes a run. While one is going `running` is set and
## `remaining` counts down; when it stops, one last state arrives with
## `running` false, the name of what was being made, and how many actually
## came out. That last part is what a queue moves on: "the run stopped" alone
## cannot tell six torches from two, and a run that ends early for want of
## materials ends silently as far as a watched inventory is concerned.
##
## A run another action stopped - a harvest - says so in one byte after the
## name's terminator. A queue stops there rather than send its next batch,
## which would only stop that action in turn. Older clients stop reading at
## the terminator and never see it; an older server never sends it, and no
## byte reads as "not interrupted".
static func decode_mix_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 7:
		return {"type": "invalid", "error": "mix_state_length"}
	var output := ""
	var after_name: int = payload.size()
	for index: int in range(6, payload.size()):
		if payload[index] == 0:
			after_name = index + 1
			break
		output += char(payload[index])
	return {
		"type": "mix_state",
		"near_storage": payload[0] != 0,
		"running": payload[1] != 0,
		"remaining": payload.decode_u16(2),
		"made": payload.decode_u16(4),
		"output": output,
		"interrupted": after_name < payload.size() and payload[after_name] != 0,
	}

static func decode_counter_layout(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 3:
		return {"type": "invalid", "error": "counter_layout_length"}
	var category_count: int = int(payload[0])
	var breakdown_count: int = int(payload[1])
	var achievement_count: int = int(payload[2])
	var offset: int = 3

	var categories: Array[Dictionary] = []
	for _index: int in range(category_count):
		if offset >= payload.size():
			return {"type": "invalid", "error": "counter_layout_category"}
		var member_count: int = int(payload[offset])
		offset += 1
		var names: Dictionary = _nul_run(payload, offset, member_count + 1)
		if names.is_empty():
			return {"type": "invalid", "error": "counter_layout_members"}
		offset = int(names.offset)
		var values: Array = names.values
		var members: Array[String] = []
		for index: int in range(1, values.size()):
			members.append(str(values[index]))
		categories.append({"name": str(values[0]), "counters": members})

	var breakdowns: Dictionary = {}
	for _index: int in range(breakdown_count):
		if offset >= payload.size():
			return {"type": "invalid", "error": "counter_layout_breakdown"}
		var row_count: int = int(payload[offset])
		offset += 1
		var owner: Dictionary = _nul_at(payload, offset)
		if owner.is_empty():
			return {"type": "invalid", "error": "counter_layout_owner"}
		offset = int(owner.offset)
		var rows: Array[Dictionary] = []
		for _row: int in range(row_count):
			if offset + 4 > payload.size():
				return {"type": "invalid", "error": "counter_layout_row"}
			var value: int = u32(payload, offset)
			offset += 4
			var label: Dictionary = _nul_at(payload, offset)
			if label.is_empty():
				return {"type": "invalid", "error": "counter_layout_label"}
			offset = int(label.offset)
			rows.append({"label": str(label.value), "value": value})
		breakdowns[str(owner.value)] = rows

	var achievements: Array[Dictionary] = []
	for _index: int in range(achievement_count):
		if offset + 9 > payload.size():
			return {"type": "invalid", "error": "counter_layout_achievement"}
		var progress: int = u32(payload, offset)
		var target: int = u32(payload, offset + 4)
		var done: bool = int(payload[offset + 8]) != 0
		offset += 9
		var text: Dictionary = _nul_run(payload, offset, 2)
		if text.is_empty():
			return {"type": "invalid", "error": "counter_layout_achievement_text"}
		offset = int(text.offset)
		var parts: Array = text.values
		achievements.append({"title": str(parts[0]), "category": str(parts[1]),
			"progress": progress, "target": max(1, target), "done": done})

	if offset != payload.size():
		return {"type": "invalid", "error": "counter_layout_trailing"}
	return {"type": "counter_layout", "categories": categories,
		"breakdowns": breakdowns, "achievements": achievements}

## Command 216. Every attribute a character can buy, and its ceiling.
##
## The legacy stats packet has room for six attributes at fixed offsets and
## there are twelve, so it shows the first six and this carries the set. The
## names travel with the values on purpose: which attributes exist is a design
## decision that has already changed once - they used to be six base
## attributes with these derived from them - and a client holding its own copy
## of the list would be confidently wrong the next time it moves.
static func decode_attribute_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "attributes_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var rows: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 4 > payload.size():
			return {"type": "invalid", "error": "attributes_values"}
		var value: int = s16(payload, offset)
		var maximum: int = s16(payload, offset + 2)
		offset += 4
		var names: Dictionary = _nul_run(payload, offset, 2)
		if names.is_empty():
			return {"type": "invalid", "error": "attributes_names"}
		offset = int(names.offset)
		var pair: Array = names.values
		rows.append({"key": str(pair[0]), "label": str(pair[1]),
			"value": value, "maximum": maximum})
	if offset != payload.size():
		return {"type": "invalid", "error": "attributes_trailing"}
	return {"type": "attribute_state", "attributes": rows}

## Command 246. Which actor types stand on more than one tile.
##
## Sent once at login, because a footprint belongs to the species rather than
## to the individual. The client needs it to place a model: the tile an actor
## reports is the anchor of its box, and for an even-sized box the anchor is
## not the middle of it, so a two-by-two creature drawn on its anchor sits
## half a tile off the ground it is actually standing on.
##
## A type that is not listed is one tile, which is most of them.
static func decode_actor_footprints(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "footprints_length"}
	var count: int = u16(payload)
	if payload.size() != 2 + count * 4:
		return {"type": "invalid", "error": "footprints_count"}
	var sizes: Dictionary = {}
	for index: int in range(count):
		var offset: int = 2 + index * 4
		var width: int = int(payload[offset + 2])
		var depth: int = int(payload[offset + 3])
		if width < 1 or depth < 1:
			return {"type": "invalid", "error": "footprints_size"}
		sizes[u16(payload, offset)] = Vector2i(width, depth)
	return {"type": "actor_footprints", "footprints": sizes}

## Command 244. Every countable thing this character has done.
##
## These numbers were always tracked and the only way to read them was a chat
## command that printed a dozen lines and scrolled away.
static func decode_achievements_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 4:
		return {"type": "invalid", "error": "achievements_length"}
	var counter_count: int = u16(payload)
	var name_count: int = u16(payload, 2)
	var offset: int = 4
	var counters: Array[Dictionary] = []
	for _index: int in range(counter_count):
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {"type": "invalid", "error": "achievements_counter_text"}
		offset = int(field.offset)
		if offset + 4 > payload.size():
			return {"type": "invalid", "error": "achievements_counter_value"}
		counters.append({"label": str(field.value), "value": u32(payload, offset)})
		offset += 4
	var completed: Array[String] = []
	for _index: int in range(name_count):
		var name_field: Dictionary = _nul_at(payload, offset)
		if name_field.is_empty():
			return {"type": "invalid", "error": "achievements_name_text"}
		completed.append(str(name_field.value))
		offset = int(name_field.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "achievements_trailing"}
	return {"type": "achievements_state", "counters": counters,
		"completed": completed}

## Command 219. The whole achievement catalogue, with this character's
## progress on it and the title they are wearing.
##
## Everything the window draws travels here, descriptions included, for the
## same reason the perk catalogue and the counter layout carry theirs: the
## catalogue is written in a server config file precisely so that a threshold
## can move, and a client holding its own copy would be drawing last week's
## list the day one did.
##
## `ELORIA_ACHIEVEMENTS_STATE(244)` still arrives and still feeds the Counters
## tab. It is a different, older model - labelled counters plus finished names
## - and this sits beside it rather than replacing it.
## The whole sky (weather_state_v1): version 1, the look the sky has now and
## the look it is becoming (seven bytes each: what falls - 0 none, 1 rain,
## 2 snow, 3 ash, 4 sand - then precipitation, clouds, fog, darkness, wind and
## lightning, 0-100), the real seconds left until it gets there in tenths
## (u16 LE), and the state's name. The client draws the numbers, not the
## name, so a sky the server adds needs no new client.
static func decode_weather_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 18 or int(payload[0]) != 1:
		return {"type": "invalid", "error": "weather_state_length"}
	var current: Array[int] = []
	var target: Array[int] = []
	for index: int in 7:
		current.append(int(payload[1 + index]))
		target.append(int(payload[8 + index]))
	for look: Array[int] in [current, target]:
		for index: int in range(1, 7):
			if look[index] > 100:
				return {"type": "invalid", "error": "weather_state_amount"}
	var length: int = int(payload[17])
	if payload.size() < 18 + length:
		return {"type": "invalid", "error": "weather_state_name"}
	return {"type": "weather_state", "current": current, "target": target,
		"seconds": float(payload.decode_u16(15)) / 10.0,
		"name": payload.slice(18, 18 + length).get_string_from_ascii()}

static func decode_achievements_catalog(payload: PackedByteArray) -> Dictionary:
	var worn: Dictionary = _nul_at(payload, 0)
	if worn.is_empty():
		return {"type": "invalid", "error": "achievements_catalog_title"}
	var offset: int = int(worn.offset)
	if offset + 2 > payload.size():
		return {"type": "invalid", "error": "achievements_catalog_length"}
	var count: int = u16(payload, offset)
	offset += 2
	var entries: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 9 > payload.size():
			return {"type": "invalid", "error": "achievements_catalog_entry"}
		var progress: int = u32(payload, offset)
		var threshold: int = u32(payload, offset + 4)
		var done: bool = int(payload[offset + 8]) != 0
		offset += 9
		var text: Dictionary = _nul_run(payload, offset, 5)
		if text.is_empty():
			return {"type": "invalid", "error": "achievements_catalog_text"}
		offset = int(text.offset)
		var parts: Array = text.values
		entries.append({"key": str(parts[0]), "name": str(parts[1]),
			"category": str(parts[2]), "description": str(parts[3]),
			"title": str(parts[4]), "progress": progress,
			"target": maxi(1, threshold), "done": done})
	if offset != payload.size():
		return {"type": "invalid", "error": "achievements_catalog_trailing"}
	return {"type": "achievements_catalog", "worn_title": str(worn.value),
		"entries": entries}

## Command 211. What each player on this map is calling themselves.
##
## A packet of its own rather than a field on the actor: the stock display
## name carries a colour byte, the name and the guild tag in one string, and
## the decoder above unpicks all three by hand. A fourth field there would
## have broken that for every server that does not send one.
##
## One frame carries a whole map on arrival and one row when somebody changes
## theirs, so there is one code path. An empty title is a real row - it is how
## somebody who took theirs off stops wearing it on everyone's screen.
static func decode_actor_titles(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "actor_titles_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var titles: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "actor_titles_entry"}
		var actor_id: int = u16(payload, offset)
		offset += 2
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {"type": "invalid", "error": "actor_titles_text"}
		offset = int(field.offset)
		titles.append({"actor_id": actor_id, "title": str(field.value)})
	if offset != payload.size():
		return {"type": "invalid", "error": "actor_titles_trailing"}
	return {"type": "actor_titles", "titles": titles}

## Command 210. What the NPCs the server has just shown do for a living, drawn
## as a second, smaller line under the name ("<Grove-Keeper>").
##
## The same shape as the titles above and for the same reason: the stock
## display name packs a colour byte, the name and the guild tag into one
## string, so the occupation rides its own packet. The server sends it after
## the actor packets it describes, every time it shows those people, so the
## client forgets a row along with its actor.
static func decode_actor_occupations(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "actor_occupations_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var rows: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "actor_occupations_entry"}
		var actor_id: int = u16(payload, offset)
		offset += 2
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {"type": "invalid", "error": "actor_occupations_text"}
		offset = int(field.offset)
		rows.append({"actor_id": actor_id, "occupation": str(field.value)})
	if offset != payload.size():
		return {"type": "invalid", "error": "actor_occupations_trailing"}
	return {"type": "actor_occupations", "occupations": rows}

## Command 209. Which map package the server was built against.
##
## Map id then digest, both NUL-terminated. The digest is the sha256
## `MapSceneCache.package_digest()` computes over the package's own bytes, so
## the client can hash what it has and compare like for like.
##
## Sent at login for the map the player is on, and after every map change. It
## is a statement, not an instruction: the client's map cache is keyed on the
## package this machine actually has, so a mismatch cannot make the cache
## wrong. It means the install is not the one this server was built against,
## and the only right response is to say so where somebody will read it.
static func decode_map_digest(payload: PackedByteArray) -> Dictionary:
	var fields: Dictionary = _nul_run(payload, 0, 2)
	if fields.is_empty():
		return {"type": "invalid", "error": "map_digest_fields"}
	if int(fields.offset) != payload.size():
		return {"type": "invalid", "error": "map_digest_trailing"}
	var values: Array = fields.values as Array
	return {"type": "map_digest", "map_id": str(values[0]),
		"digest": str(values[1])}

## Command 242. Which item names exist only because something wore out.
##
## Sent once at login. An empty list is a real answer: it means this profile
## authors no degradation chains, not that the packet went missing.
## Command 248. What is in each of the player's own slots, by name.
##
## The stock inventory packet carries an image id and no name, and in this
## profile plenty of items share their artwork - five pelts draw as one
## picture. A window that has to choose an item by identity rather than by
## the player pointing at it cannot do so from a picture, which is why six
## recipes could not be mixed at all. Positions are the stock packet's own,
## equipment slots included.
static func decode_inventory_names(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "inventory_names_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var names: Dictionary = {}
	for _index: int in range(count):
		if offset >= payload.size():
			return {"type": "invalid", "error": "inventory_names_slot"}
		var slot: int = int(payload[offset])
		var field: Dictionary = _nul_at(payload, offset + 1)
		if field.is_empty():
			return {"type": "invalid", "error": "inventory_names_text"}
		names[slot] = str(field.value)
		offset = int(field.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "inventory_names_trailing"}
	return {"type": "inventory_names", "names": names}

static func decode_degraded_items(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "degraded_items_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var names: Array[String] = []
	for _index: int in range(count):
		var field: Dictionary = _nul_at(payload, offset)
		if field.is_empty():
			return {"type": "invalid", "error": "degraded_items_text"}
		names.append(str(field.value))
		offset = int(field.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "degraded_items_trailing"}
	return {"type": "degraded_items", "names": names}

## Command 241. What this character has finished.
##
## The journal says what is open; this says what is done. It is server-held, so
## it survives a reinstall and a new machine - which is the whole reason it
## exists rather than being read out of a local log.
static func decode_quest_archive(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "quest_archive_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var entries: Array[Dictionary] = []
	for _index: int in range(count):
		var text: Dictionary = _nul_run(payload, offset, 3)
		if text.is_empty():
			return {"type": "invalid", "error": "quest_archive_entry_text"}
		var values: Array = text.values as Array
		entries.append({"title": values[0], "location": values[1],
			"detail": values[2]})
		offset = int(text.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "quest_archive_trailing"}
	return {"type": "quest_archive", "entries": entries}

## Command 193. A shared selection and each party member's explicit consent.
static func decode_gauntlet_ready(payload: PackedByteArray) -> Dictionary:
	var state: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not state is Dictionary or state.get("version") != 1 or not state.get("open") is bool:
		return {"type": "invalid", "error": "gauntlet_ready_shape"}
	if state.open:
		for key: String in ["check_id", "route", "difficulty"]:
			if not state.get(key) is String or str(state[key]).is_empty():
				return {"type": "invalid", "error": "gauntlet_ready_text"}
		if not state.get("members") is Array or state.members.is_empty() or state.members.size() > 8:
			return {"type": "invalid", "error": "gauntlet_ready_members"}
		if not (state.get("level") is float or state.get("level") is int):
			return {"type": "invalid", "error": "gauntlet_ready_level"}
		for key: String in ["is_leader", "can_start", "in_party"]:
			if not state.get(key) is bool:
				return {"type": "invalid", "error": "gauntlet_ready_flags"}
		for member: Variant in state.members:
			if not member is Dictionary or not member.get("name") is String or not member.get("status") is String:
				return {"type": "invalid", "error": "gauntlet_ready_member"}
			for key: String in ["self", "leader", "ready"]:
				if not member.get(key) is bool:
					return {"type": "invalid", "error": "gauntlet_ready_member_flags"}
			if member.has("bot"):
				if not member.bot is bool:
					return {"type": "invalid", "error": "gauntlet_ready_bot"}
				if member.bot and (not member.get("id") is String or str(member.id).is_empty()
						or not (member.get("class_id") is float or member.get("class_id") is int)
						or float(member.class_id) != float(int(member.class_id))
						or int(member.class_id) < 0 or int(member.class_id) > 3):
					return {"type": "invalid", "error": "gauntlet_ready_bot"}
	return {"type": "gauntlet_ready", "data": state}

## A bounded page of the authoritative escrow ledger; quantities are integers.
static func decode_gauntlet_loot(payload: PackedByteArray) -> Dictionary:
	var state: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not state is Dictionary or state.get("version") != 1:
		return {"type": "invalid", "error": "gauntlet_loot_shape"}
	if state.has("error") and not state.error is String:
		return {"type": "invalid", "error": "gauntlet_loot_error"}
	for key: String in ["run_id", "route", "phase", "leader", "reason", "announcement"]:
		if not state.get(key) is String:
			return {"type": "invalid", "error": "gauntlet_loot_text"}
	if state.phase not in ["active", "complete", "ended", "sent"]:
		return {"type": "invalid", "error": "gauntlet_loot_phase"}
	for key: String in ["open", "is_leader", "can_send"]:
		if not state.get(key) is bool:
			return {"type": "invalid", "error": "gauntlet_loot_flag"}
	for key: String in ["revision", "assigned", "total", "page", "pages", "announcement_id"]:
		if not _loot_integer(state.get(key)):
			return {"type": "invalid", "error": "gauntlet_loot_number"}
	if not state.get("members") is Array or state.members.is_empty() or state.members.size() > 8:
		return {"type": "invalid", "error": "gauntlet_loot_members"}
	var names: Array[String] = []
	for member: Variant in state.members:
		if not member is Dictionary or not member.get("username") is String or not member.get("name") is String:
			return {"type": "invalid", "error": "gauntlet_loot_member"}
		if names.has(member.username) or not member.get("online") is bool or not member.get("portrait") is Dictionary:
			return {"type": "invalid", "error": "gauntlet_loot_member_fields"}
		names.append(member.username)
		if not _loot_integer(member.get("charge_gold")) or not _loot_integer(member.get("rebate_gold")) or not _loot_integer(member.get("sale_share_gold")) or not member.get("payment_ready") is bool:
			return {"type": "invalid", "error": "gauntlet_loot_payment"}
		if not member.get("self") is bool or not member.get("payment_approved") is bool:
			return {"type": "invalid", "error": "gauntlet_loot_payment_approval"}
		if not member.get("preview") is Array or member.preview.size() > 8 or not _loot_integer(member.get("more")):
			return {"type": "invalid", "error": "gauntlet_loot_preview"}
		for item: Variant in member.preview:
			if not item is Dictionary or not item.get("name") is String or not _loot_integer(item.get("quantity")) or not _loot_integer(item.get("image_id"), -1):
				return {"type": "invalid", "error": "gauntlet_loot_preview_item"}
	if not state.get("rows") is Array or state.rows.size() > 24 or int(state.pages) < 1 or int(state.page) >= int(state.pages):
		return {"type": "invalid", "error": "gauntlet_loot_rows"}
	var ids: Array[String] = []
	for row: Variant in state.rows:
		if not row is Dictionary or not row.get("id") is String or ids.has(row.id) or not row.get("name") is String or not row.get("owner") is String or not row.get("rare") is bool or not row.get("allocations") is Dictionary:
			return {"type": "invalid", "error": "gauntlet_loot_row"}
		ids.append(row.id)
		if not _loot_integer(row.get("price_gold")) or not row.get("locked") is bool or row.get("source") not in ["creature", "cache", "compensation", "npc_sales"]:
			return {"type": "invalid", "error": "gauntlet_loot_price"}
		for key: String in ["sell_quantity", "available_quantity", "npc_gold", "sale_proceeds"]:
			if not _loot_integer(row.get(key)):
				return {"type": "invalid", "error": "gauntlet_loot_sale"}
		if not _loot_integer(row.get("exchange_quantity", 0)) or not _loot_integer(row.get("exchange_price", 0)):
			return {"type": "invalid", "error": "gauntlet_loot_exchange_quantity"}
		if not _loot_integer(row.get("npc_bundle"), 1) or int(row.available_quantity) + int(row.sell_quantity) + int(row.get("exchange_quantity", 0)) != int(row.quantity):
			return {"type": "invalid", "error": "gauntlet_loot_sale_quantity"}
		if not _loot_integer(row.get("quantity"), 1) or not _loot_integer(row.get("image_id"), -1):
			return {"type": "invalid", "error": "gauntlet_loot_quantity"}
		var allocated := 0
		for recipient: String in row.allocations:
			if not names.has(recipient) or not _loot_integer(row.allocations[recipient]):
				return {"type": "invalid", "error": "gauntlet_loot_recipient"}
			allocated += int(row.allocations[recipient])
		if allocated > int(row.available_quantity) or not row.owner.is_empty() and not names.has(row.owner):
			return {"type": "invalid", "error": "gauntlet_loot_overallocation"}
	if state.has("exchange_enabled"):
		if not state.exchange_enabled is bool or not state.get("exchange") is Array or state.exchange.size() > 24:
			return {"type": "invalid", "error": "party_exchange_shape"}
		for key: String in ["exchange_total", "exchange_page", "exchange_pages", "ledger_page", "ledger_pages", "exchange_plan_types", "exchange_plan_quantity", "exchange_plan_gold"]:
			if not _loot_integer(state.get(key)):
				return {"type": "invalid", "error": "party_exchange_page"}
		if int(state.exchange_pages) < 1 or int(state.exchange_page) >= int(state.exchange_pages) or int(state.ledger_pages) < 1 or int(state.ledger_page) >= int(state.ledger_pages):
			return {"type": "invalid", "error": "party_exchange_page_range"}
		if not state.get("ledgers") is Array or state.ledgers.size() > 24:
			return {"type": "invalid", "error": "party_exchange_ledgers"}
		for ledger: Variant in state.ledgers:
			if not ledger is Dictionary or not ledger.get("run_id") is String or not ledger.get("route") is String or ledger.get("phase") not in ["active", "complete", "ended", "sent"]:
				return {"type": "invalid", "error": "party_exchange_ledger"}
		var listing_ids: Array[int] = []
		for listing: Variant in state.exchange:
			if not listing is Dictionary:
				return {"type": "invalid", "error": "party_exchange_listing"}
			for key: String in ["listing_id", "quantity", "original_quantity", "price_gold", "gold_sold", "request_id", "deadline"]:
				if not _loot_integer(listing.get(key)):
					return {"type": "invalid", "error": "party_exchange_number"}
			if int(listing.listing_id) < 1 or listing_ids.has(int(listing.listing_id)) or not _loot_integer(listing.get("image_id"), -1) or not listing.get("name") is String or not listing.get("withdrawal_run_id") is String:
				return {"type": "invalid", "error": "party_exchange_fields"}
			listing_ids.append(int(listing.listing_id))
			if int(listing.original_quantity) < 1 or int(listing.price_gold) < 1 or int(listing.quantity) > int(listing.original_quantity):
				return {"type": "invalid", "error": "party_exchange_quantity"}
			if listing.get("state") not in ["active", "sold", "withdrawn"] or listing.get("vote_state") not in ["none", "open", "approved", "rejected", "sold"] or listing.get("own_vote") not in ["none", "yes", "no", "abstain"]:
				return {"type": "invalid", "error": "party_exchange_status"}
			if not listing.get("votes") is Array or listing.votes.size() != names.size() or not listing.get("payouts") is Array or listing.payouts.size() > names.size():
				return {"type": "invalid", "error": "party_exchange_roster"}
			var voters: Array[String] = []
			for voter: Variant in listing.votes:
				if not voter is Dictionary or not voter.get("username") is String or not names.has(voter.username) or voters.has(voter.username) or not voter.get("name") is String or voter.get("vote") not in ["none", "yes", "no", "abstain"]:
					return {"type": "invalid", "error": "party_exchange_vote"}
				voters.append(voter.username)
			var payees: Array[String] = []
			for payout: Variant in listing.payouts:
				if not payout is Dictionary or not payout.get("username") is String or not names.has(payout.username) or payees.has(payout.username) or not _loot_integer(payout.get("gold")) or not _loot_integer(payout.get("pending_gold")):
					return {"type": "invalid", "error": "party_exchange_payout"}
				payees.append(payout.username)
	return {"type": "gauntlet_loot", "data": state}

static func _loot_integer(value: Variant, minimum := 0) -> bool:
	return (value is float or value is int) and is_finite(float(value)) and float(value) == floor(float(value)) and float(value) >= minimum and float(value) <= 2147483647

## Command 240. Who is in the party, how they are doing, and where they are.
## Offline members keep their rows so their absence remains visible.
static func decode_party(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 5:
		return {"type": "invalid", "error": "party_length"}
	var in_party: bool = payload[0] != 0
	var count: int = int(payload[1])
	var offset: int = 2
	var members: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 13 > payload.size():
			return {"type": "invalid", "error": "party_entry_length"}
		var flags: int = int(payload[offset])
		var member: Dictionary = {
			"online": (flags & 1) != 0,
			"leader": (flags & 2) != 0,
			"is_self": (flags & 4) != 0,
			"is_bot": (flags & 8) != 0,
			"class_id": (flags >> 4) & 3,
			"health": u16(payload, offset + 1),
			"max_health": u16(payload, offset + 3),
			"ether": u16(payload, offset + 5),
			"max_ether": u16(payload, offset + 7),
			"x": u16(payload, offset + 9),
			"y": u16(payload, offset + 11)}
		offset += 13
		var text: Dictionary = _nul_run(payload, offset, 2)
		if text.is_empty():
			return {"type": "invalid", "error": "party_entry_text"}
		member["name"] = (text.values as Array)[0]
		member["map_id"] = (text.values as Array)[1]
		offset = int(text.offset)
		members.append(member)
	var invite: Dictionary = _nul_at(payload, offset)
	if invite.is_empty():
		return {"type": "invalid", "error": "party_invite_text"}
	offset = int(invite.offset)
	if offset + 2 != payload.size():
		return {"type": "invalid", "error": "party_trailing"}
	return {"type": "party", "in_party": in_party, "members": members,
		"invited_by": str(invite.value), "invite_seconds": u16(payload, offset)}

## Command 213. The whole of a guild, as it looks to the one person reading it.
##
## Guilds were in the server long before anything drew them: the roster was a
## column of chat that scrolled away, and `#join_guild` wanted a long name the
## client had no way to learn. Everything here is the server's answer, down to
## what this reader is allowed to do - the window offers a button because the
## permissions field says so, never because it worked a rank out for itself.
##
## No guild is a state rather than a missing packet: `in_guild` false still
## carries the price of founding one, the guilds this player has applied to,
## and the directory they would pick from.
static func decode_guild(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 11:
		return {"type": "invalid", "error": "guild_length"}
	var flags: int = int(payload[1])
	var state: Dictionary = {
		"type": "guild", "version": int(payload[0]),
		"in_guild": (flags & 1) != 0, "rank": int(payload[2]),
		"permissions": u16(payload, 3), "create_cost": u32(payload, 5),
		"create_level": int(payload[9]), "join_level": int(payload[10])}
	var text: Dictionary = _nul_run(payload, 11, 7)
	if text.is_empty():
		return {"type": "invalid", "error": "guild_text"}
	var fields: Array = text.values as Array
	var field_names: Array[String] = ["tag", "name", "owner", "motd",
		"description", "join_info", "url"]
	for index: int in range(field_names.size()):
		state[field_names[index]] = fields[index]
	var offset: int = int(text.offset)

	# The seven counted sections, in the order the server writes them. Each one
	# is read whole before the next begins, so a section that runs off the end
	# refuses the frame instead of reading the next section's bytes as its own.
	var section: Dictionary = _guild_section(payload, offset, 2, 1, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_members"}
	var members: Array[Dictionary] = []
	for raw: Variant in section.rows as Array:
		var row: Dictionary = raw as Dictionary
		var member_flags: int = int((row.head as PackedByteArray)[1])
		members.append({
			"rank": int((row.head as PackedByteArray)[0]),
			"online": (member_flags & 1) != 0,
			"is_self": (member_flags & 2) != 0,
			"owner": (member_flags & 4) != 0,
			"name": str((row.text as Array)[0])})
	state["members"] = members
	offset = int(section.offset)

	section = _guild_section(payload, offset, 0, 1, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_applicants"}
	state["applicants"] = _guild_names(section)
	offset = int(section.offset)

	section = _guild_section(payload, offset, 0, 2, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_allies"}
	var allies: Array[Dictionary] = []
	for raw: Variant in section.rows as Array:
		var row: Array = (raw as Dictionary).text as Array
		allies.append({"tag": str(row[0]), "name": str(row[1])})
	state["allies"] = allies
	offset = int(section.offset)

	section = _guild_section(payload, offset, 1, 1, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_colours"}
	var colours: Array[Dictionary] = []
	for raw: Variant in section.rows as Array:
		var row: Dictionary = raw as Dictionary
		colours.append({"colour": int((row.head as PackedByteArray)[0]),
			"tag": str((row.text as Array)[0])})
	state["colours"] = colours
	offset = int(section.offset)

	section = _guild_section(payload, offset, 0, 1, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_pending"}
	state["pending"] = _guild_names(section)
	offset = int(section.offset)

	section = _guild_section(payload, offset, 0, 2, 2)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_directory"}
	var directory: Array[Dictionary] = []
	for raw: Variant in section.rows as Array:
		var row: Dictionary = raw as Dictionary
		var names: Array = row.text as Array
		directory.append({"tag": str(names[0]), "name": str(names[1]),
			"members": u16(row.tail as PackedByteArray)})
	state["directory"] = directory
	offset = int(section.offset)

	section = _guild_section(payload, offset, 1, 1, 0)
	if section.is_empty():
		return {"type": "invalid", "error": "guild_palette"}
	var palette: Array[Dictionary] = []
	for raw: Variant in section.rows as Array:
		var row: Dictionary = raw as Dictionary
		palette.append({"colour": int((row.head as PackedByteArray)[0]),
			"name": str((row.text as Array)[0])})
	state["palette"] = palette
	offset = int(section.offset)

	if offset != payload.size():
		return {"type": "invalid", "error": "guild_trailing"}
	return state

## One u16-counted section of the guild packet: `lead` raw bytes, then
## `strings` NUL-terminated strings, then `trail` raw bytes, per row. The raw
## runs come back unread so the caller names their fields; an empty dictionary
## means the payload ended inside the section.
static func _guild_section(payload: PackedByteArray, offset: int, lead: int,
		strings: int, trail: int) -> Dictionary:
	if offset + 2 > payload.size():
		return {}
	var count: int = u16(payload, offset)
	offset += 2
	var rows: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + lead > payload.size():
			return {}
		var head: PackedByteArray = payload.slice(offset, offset + lead)
		offset += lead
		var text: Dictionary = _nul_run(payload, offset, strings)
		if text.is_empty():
			return {}
		offset = int(text.offset)
		if offset + trail > payload.size():
			return {}
		rows.append({"head": head, "text": text.values,
			"tail": payload.slice(offset, offset + trail)})
		offset += trail
	return {"rows": rows, "offset": offset}

## The first string of every row in a section, which is all three of the
## packet's name lists carry.
static func _guild_names(section: Dictionary) -> Array[String]:
	var names: Array[String] = []
	for raw: Variant in section.rows as Array:
		names.append(str(((raw as Dictionary).text as Array)[0]))
	return names

## Reasons an item sits in return escrow, as `market_window_v2` numbers them.
const MARKET_RETURN_REASONS: Array[String] = ["returned", "expired", "cancelled"]
const MARKET_NOTICE_NONE := 0
const MARKET_NOTICE_DONE := 1
const MARKET_NOTICE_REFUSED := 2

## Command 222. The Nymara Exchange: the player's gold, how many items are
## waiting in escrow, and the listings on offer.
##
## A server that heard `market_window_v2` follows the listings with the page:
## where it starts in the whole list, how long that list is, the search it
## answers, how the last request went, which rows are the player's own, and
## what is waiting in return escrow and why. An older server sends none of it,
## and the state says `version` 1 so the window does not offer paging it
## cannot serve.
static func decode_marketplace(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 11:
		return {"type": "invalid", "error": "marketplace_length"}
	var view: int = int(payload[0])
	var gold: int = u32(payload, 1)
	var returned_items: int = u32(payload, 5)
	var count: int = u16(payload, 9)
	var offset: int = 11
	var listings: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 18 > payload.size():
			return {"type": "invalid", "error": "marketplace_entry_length"}
		var listing: Dictionary = {
			"listing_id": u32(payload, offset),
			"quantity": u32(payload, offset + 4),
			"unit_price": u32(payload, offset + 8),
			"seconds_left": u32(payload, offset + 12),
			"image_id": u16(payload, offset + 16)}
		offset += 18
		var text: Dictionary = _nul_run(payload, offset, 2)
		if text.is_empty():
			return {"type": "invalid", "error": "marketplace_entry_text"}
		listing["item_name"] = (text.values as Array)[0]
		listing["seller"] = (text.values as Array)[1]
		listing["own"] = view == 1
		offset = int(text.offset)
		listings.append(listing)
	var state: Dictionary = {"type": "marketplace", "view": view, "gold": gold,
		"returned_items": returned_items, "listings": listings, "version": 1,
		"offset": 0, "total": listings.size(), "page_size": listings.size(),
		"query": "", "notice": "", "notice_kind": MARKET_NOTICE_NONE,
		"returns": []}
	if offset == payload.size():
		return state
	# The version-2 trailer.
	if offset + 9 > payload.size():
		return {"type": "invalid", "error": "marketplace_page_length"}
	state.version = 2
	state.offset = u32(payload, offset)
	state.total = u32(payload, offset + 4)
	state.page_size = int(payload[offset + 8])
	offset += 9
	var query: Dictionary = _nul_at(payload, offset)
	if query.is_empty() or int(query.offset) >= payload.size():
		return {"type": "invalid", "error": "marketplace_query"}
	state.query = str(query.value)
	offset = int(query.offset)
	state.notice_kind = int(payload[offset])
	var notice: Dictionary = _nul_at(payload, offset + 1)
	if notice.is_empty():
		return {"type": "invalid", "error": "marketplace_notice"}
	state.notice = str(notice.value)
	offset = int(notice.offset)
	if offset + listings.size() + 2 > payload.size():
		return {"type": "invalid", "error": "marketplace_flags"}
	for listing: Dictionary in listings:
		listing["own"] = (int(payload[offset]) & 1) != 0
		listing["party_owned"] = (int(payload[offset]) & 2) != 0
		offset += 1
	var return_count: int = u16(payload, offset)
	offset += 2
	var returns: Array[Dictionary] = []
	for _index: int in range(return_count):
		if offset + 7 > payload.size():
			return {"type": "invalid", "error": "marketplace_return_length"}
		var reason: int = int(payload[offset + 6])
		var item: Dictionary = _nul_at(payload, offset + 7)
		if item.is_empty():
			return {"type": "invalid", "error": "marketplace_return_text"}
		returns.append({"quantity": u32(payload, offset),
			"image_id": u16(payload, offset + 4),
			"reason": MARKET_RETURN_REASONS[reason]
				if reason < MARKET_RETURN_REASONS.size() else "returned",
			"item_name": str(item.value)})
		offset = int(item.offset)
	state.returns = returns
	if offset < payload.size():
		var extension: Dictionary = _nul_at(payload, offset)
		if extension.is_empty() or int(extension.offset) != payload.size():
			return {"type": "invalid", "error": "marketplace_trailing"}
		var details: Variant = JSON.parse_string(str(extension.value))
		if not details is Dictionary or not details.get("filters") is Dictionary \
				or not details.get("history") is Array or not details.get("categories") is Array \
				or not details.get("types") is Array \
				or str(details.get("view", "")) not in ["browse", "mine", "history"]:
			return {"type": "invalid", "error": "marketplace_details"}
		for sale: Variant in details.history:
			if not sale is Dictionary:
				return {"type": "invalid", "error": "marketplace_sale"}
		state.version = 3
		state["market_view"] = str(details.view)
		state["filters"] = details.filters
		state["history"] = details.history
		state["categories"] = details.categories
		state["types"] = details.types
	return state

## Command 223. One NPC merchant's stock, with the prices in both directions
## and how many of each the player already carries.
static func decode_merchant(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 16:
		return {"type": "invalid", "error": "merchant_length"}
	var actor_id: int = u16(payload)
	var gold: int = u32(payload, 2)
	var carried: int = u32(payload, 6)
	var capacity: int = u32(payload, 10)
	var count: int = u16(payload, 14)
	var name_field: Dictionary = _nul_at(payload, 16)
	if name_field.is_empty():
		return {"type": "invalid", "error": "merchant_name"}
	var offset: int = int(name_field.offset)
	var items: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 16 > payload.size():
			return {"type": "invalid", "error": "merchant_entry_length"}
		var entry: Dictionary = {
			"index": u16(payload, offset),
			"buy_price": u32(payload, offset + 2),
			"sell_price": u32(payload, offset + 6),
			"owned": u32(payload, offset + 10),
			"image_id": u16(payload, offset + 14)}
		offset += 16
		var entry_name: Dictionary = _nul_at(payload, offset)
		if entry_name.is_empty():
			return {"type": "invalid", "error": "merchant_entry_name"}
		entry["name"] = str(entry_name.value)
		offset = int(entry_name.offset)
		items.append(entry)
	# Negotiated merchant_weights_v1 trailer, in the same order as the rows.
	if offset < payload.size():
		if offset + 2 > payload.size() or u16(payload, offset) != items.size():
			return {"type": "invalid", "error": "merchant_weights_count"}
		offset += 2
		if offset + items.size() * 4 > payload.size():
			return {"type": "invalid", "error": "merchant_weights_length"}
		for entry: Dictionary in items:
			entry["emu"] = u32(payload, offset)
			offset += 4
	# Negotiated merchant_descriptions_v1 follows the weights in row order.
	if offset < payload.size():
		if offset + 2 > payload.size() or u16(payload, offset) != items.size():
			return {"type": "invalid", "error": "merchant_descriptions_count"}
		offset += 2
		for entry: Dictionary in items:
			var description: Dictionary = _nul_at(payload, offset)
			if description.is_empty():
				return {"type": "invalid", "error": "merchant_description"}
			entry["description"] = str(description.value)
			offset = int(description.offset)
	# Exact sale bundles allow prices such as two flowers for one gold.
	if offset < payload.size():
		if offset + 2 > payload.size() or u16(payload, offset) != items.size():
			return {"type": "invalid", "error": "merchant_lots_count"}
		offset += 2
		if offset + items.size() * 2 != payload.size():
			return {"type": "invalid", "error": "merchant_lots_length"}
		for entry: Dictionary in items:
			entry["sell_quantity"] = u16(payload, offset)
			if int(entry.sell_quantity) < 1:
				return {"type": "invalid", "error": "merchant_lot_zero"}
			offset += 2
	if offset != payload.size():
		return {"type": "invalid", "error": "merchant_trailing"}
	return {"type": "merchant", "actor_id": actor_id, "npc_name": str(name_field.value),
		"gold": gold, "carried": carried, "capacity": capacity, "items": items}

## Command 224. Active quest objectives with their progress.
static func decode_quest_journal(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "quest_journal_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var entries: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 9 > payload.size():
			return {"type": "invalid", "error": "quest_entry_length"}
		var entry: Dictionary = {
			"ready": int(payload[offset]) != 0,
			"current": u32(payload, offset + 1),
			"target": u32(payload, offset + 5)}
		offset += 9
		var text: Dictionary = _nul_run(payload, offset, 3)
		if text.is_empty():
			return {"type": "invalid", "error": "quest_entry_text"}
		entry["title"] = (text.values as Array)[0]
		entry["objective"] = (text.values as Array)[1]
		entry["location"] = (text.values as Array)[2]
		offset = int(text.offset)
		entries.append(entry)
	if offset != payload.size():
		return {"type": "invalid", "error": "quest_journal_trailing"}
	return {"type": "quest_journal", "entries": entries}

## Command 225. One inspected item, and the equipped item it would replace.
static func decode_item_detail(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 7:
		return {"type": "invalid", "error": "item_detail_length"}
	var text: Dictionary = _nul_run(payload, 7, 7)
	if text.is_empty():
		return {"type": "invalid", "error": "item_detail_text"}
	if int(text.offset) != payload.size():
		return {"type": "invalid", "error": "item_detail_trailing"}
	var values: Array = text.values
	return {"type": "item_detail", "image_id": u16(payload),
		"quantity": u32(payload, 2), "equipped": int(payload[6]) != 0,
		"name": values[0], "category": values[1], "equip_type": values[2],
		"description": values[3], "stats": values[4],
		"comparison_name": values[5], "comparison": values[6]}

## Command 226. The server's own view of the backpack, with the item names,
## categories and per-item weight the ordinary inventory packet cannot carry.
static func decode_inventory_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 14:
		return {"type": "invalid", "error": "inventory_state_length"}
	var count: int = u16(payload, 12)
	var offset: int = 14
	var items: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 12 > payload.size():
			return {"type": "invalid", "error": "inventory_state_entry_length"}
		var entry: Dictionary = {
			"slot": int(payload[offset]), "image_id": u16(payload, offset + 1),
			"quantity": u32(payload, offset + 3), "emu": u32(payload, offset + 7),
			"flags": int(payload[offset + 11])}
		offset += 12
		var text: Dictionary = _nul_run(payload, offset, 2)
		if text.is_empty():
			return {"type": "invalid", "error": "inventory_state_entry_text"}
		entry["name"] = (text.values as Array)[0]
		entry["category"] = (text.values as Array)[1]
		offset = int(text.offset)
		items.append(entry)
	if offset != payload.size():
		return {"type": "invalid", "error": "inventory_state_trailing"}
	return {"type": "inventory_state", "gold": u32(payload),
		"carried": u32(payload, 4), "capacity": u32(payload, 8), "items": items}

## Command 227. The combat HUD: both health bars and the most recent outcome.
## Event 0 is a state refresh; the rest name what just happened.
const COMBAT_EVENT_STATE := 0
const COMBAT_EVENT_HIT := 1
const COMBAT_EVENT_MISS := 2
const COMBAT_EVENT_INCOMING := 3
const COMBAT_EVENT_DODGE := 4
const COMBAT_EVENT_DEFEAT := 5

static func decode_combat_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 14:
		return {"type": "invalid", "error": "combat_state_length"}
	var name_field: Dictionary = _nul_at(payload, 13)
	if name_field.is_empty() or int(name_field.offset) != payload.size():
		return {"type": "invalid", "error": "combat_state_name"}
	return {"type": "combat_state", "event": int(payload[0]),
		"target_id": u16(payload, 1), "player_health": u16(payload, 3),
		"player_max_health": u16(payload, 5), "target_health": u16(payload, 7),
		"target_max_health": u16(payload, 9), "recent_damage": u16(payload, 11),
		"target_name": str(name_field.value)}

## Command 229. The persistent mail inbox.
static func decode_mail(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "mail_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var messages: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 9 > payload.size():
			return {"type": "invalid", "error": "mail_entry_length"}
		var message: Dictionary = {
			"mail_id": u32(payload, offset),
			"created_at": u32(payload, offset + 4),
			"read": int(payload[offset + 8]) != 0}
		offset += 9
		var text: Dictionary = _nul_run(payload, offset, 3)
		if text.is_empty():
			return {"type": "invalid", "error": "mail_entry_text"}
		message["sender"] = (text.values as Array)[0]
		message["subject"] = (text.values as Array)[1]
		message["body"] = (text.values as Array)[2]
		offset = int(text.offset)
		messages.append(message)
	if offset != payload.size():
		return {"type": "invalid", "error": "mail_trailing"}
	return {"type": "mail", "messages": messages}

## Command 230. The waypoint HUD. `active` false means no waypoint is set, and
## the remaining fields are then meaningless rather than stale.
static func decode_navigation(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 7:
		return {"type": "invalid", "error": "navigation_length"}
	var text: Dictionary = _nul_run(payload, 7, 2)
	if text.is_empty():
		return {"type": "invalid", "error": "navigation_text"}
	if int(text.offset) != payload.size():
		return {"type": "invalid", "error": "navigation_trailing"}
	return {"type": "navigation", "active": int(payload[0]) != 0,
		"x": u16(payload, 1), "y": u16(payload, 3), "distance": u16(payload, 5),
		"map_id": (text.values as Array)[0], "label": (text.values as Array)[1]}

## Command 254, version 1: whether the server steps held keyboard directions,
## the epoch they must carry, and the keep-alive and idle timings.
static func decode_move_intent(payload: PackedByteArray) -> Dictionary:
	if payload.size() != 7:
		return {"type": "invalid", "error": "move_intent_length"}
	if payload[0] != 1:
		return {"type": "invalid", "error": "move_intent_version"}
	return {"type": "move_intent", "enabled": payload[1] != 0, "epoch": int(payload[2]),
		"keepalive_msec": u16(payload, 3), "idle_msec": u16(payload, 5)}

## Command 232. Free text lines for the specialty-event panel, NUL delimited.
static func decode_special_events(payload: PackedByteArray) -> Dictionary:
	if payload.is_empty() or payload[payload.size() - 1] != 0:
		return {"type": "invalid", "error": "special_events_terminator"}
	var lines: Array[String] = []
	var start: int = 0
	for index: int in range(payload.size()):
		if payload[index] != 0:
			continue
		lines.append(payload.slice(start, index).get_string_from_utf8())
		start = index + 1
	# A single empty line is how the server clears the panel.
	if lines.size() == 1 and lines[0].is_empty():
		lines.clear()
	return {"type": "special_events", "lines": lines}

## Clickable world objects on the current map. The client cannot infer any of
## this: a world package renders harvestable props and buildings as ordinary
## geometry, and the legacy client matched object basenames against a lowercase
## harvestable list, a lookup that never matched anything because the packs
## wrote relative paths. Object identity is server state.
const MAP_OBJECT_HARVEST := 1
const MAP_OBJECT_INTERACTIVE := 2
## A way off the map that nothing else marks - a march with no waygate, a
## door into an interior, the way out of one. The server states it from its
## portal tiles; it is not clickable, and the maps draw it.
const MAP_OBJECT_EXIT := 3

static func decode_map_objects(payload: PackedByteArray) -> Dictionary:
	# A busy map has thousands of harvest nodes, which does not fit in one
	# frame, so the list arrives in chunks. The leading flag says whether a
	# chunk begins a new list or continues the one already being built.
	if payload.size() < 3:
		return {"type": "invalid", "error": "map_objects_length"}
	var first: bool = int(payload[0]) != 0
	var count: int = u16(payload, 1)
	var offset: int = 3
	var objects: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 7 > payload.size():
			return {"type": "invalid", "error": "map_object_entry_length"}
		var object_id: int = u16(payload, offset)
		var kind: int = int(payload[offset + 2])
		var x: int = u16(payload, offset + 3)
		var y: int = u16(payload, offset + 5)
		offset += 7
		var label_end: int = payload.find(0, offset)
		if label_end < 0:
			return {"type": "invalid", "error": "map_object_label"}
		var label: String = payload.slice(offset, label_end).get_string_from_utf8()
		offset = label_end + 1
		var detail_end: int = payload.find(0, offset)
		if detail_end < 0:
			return {"type": "invalid", "error": "map_object_detail"}
		var detail: String = payload.slice(offset, detail_end).get_string_from_utf8()
		offset = detail_end + 1
		if kind not in [MAP_OBJECT_HARVEST, MAP_OBJECT_INTERACTIVE, MAP_OBJECT_EXIT]:
			return {"type": "invalid", "error": "map_object_kind"}
		objects.append({"object_id": object_id, "kind": kind, "x": x, "y": y,
			"label": label, "detail": detail})
	if offset != payload.size():
		return {"type": "invalid", "error": "map_objects_trailing"}
	return {"type": "map_objects", "first": first, "objects": objects}

## Whether the player is harvesting, and what. The stock client matched an
## exact English phrase out of the chat stream to drive this, which breaks on
## any rewording and on any translation.
static func decode_harvest_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 4:
		return {"type": "invalid", "error": "harvest_state_length"}
	var terminator: int = payload.find(0, 3)
	if terminator < 0 or terminator != payload.size() - 1:
		return {"type": "invalid", "error": "harvest_state_resource"}
	return {"type": "harvest_state", "active": int(payload[0]) != 0,
		"object_id": u16(payload, 1),
		"resource": payload.slice(3, terminator).get_string_from_utf8()}

## A server-driven modal question. Option types are the legacy popup contract:
## 0 text entry, 1 display text, 8 text option (a button that answers at once),
## 9 radio option (a choice confirmed with the popup's send button). Options
## carry a group id; one answer is returned per group.
const POPUP_TEXT_ENTRY := 0
const POPUP_DISPLAY_TEXT := 1
const POPUP_TEXT_OPTION := 8
const POPUP_RADIO_OPTION := 9

## Command 231. What power each spell effect will be cast at, and the highest
## the player's Magic level and nexus allow.
##
## Both numbers are the server's: `#sp` reports them as chat text, which a
## client must not parse, and working them out from a levels table would mean
## keeping a second copy of the server's progression rules.
static func decode_spell_power(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "spell_power_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var effects: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "spell_power_entry_length"}
		var preferred: int = int(payload[offset])
		var limit: int = int(payload[offset + 1])
		var field: Dictionary = _nul_at(payload, offset + 2)
		if field.is_empty():
			return {"type": "invalid", "error": "spell_power_entry_text"}
		effects.append({"effect": str(field.value), "preferred": preferred,
			"limit": limit})
		offset = int(field.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "spell_power_trailing"}
	return {"type": "spell_power", "effects": effects}

## Command 89. An actor is playing a named animation action.
##
## The action is a name, not a clip: which piece of art plays is this client's
## to decide from its own animation map, and an action it has no clip for is
## simply not played. The server sends the words separately and always, so an
## emote reaches the player either way.
static func decode_actor_animation(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 3:
		return {"type": "invalid", "error": "actor_animation_length"}
	var field: Dictionary = _nul_at(payload, 2)
	if field.is_empty():
		return {"type": "invalid", "error": "actor_animation_text"}
	if int(field.offset) != payload.size():
		return {"type": "invalid", "error": "actor_animation_trailing"}
	var action: String = str(field.value)
	if action.is_empty():
		return {"type": "invalid", "error": "actor_animation_empty"}
	return {"type": "actor_animation", "actor_id": u16(payload),
		"action": action}

## One object out of a placement frame: id, tile, facing and model name.
static func _world_object_at(payload: PackedByteArray, offset: int) -> Dictionary:
	if offset + 8 > payload.size():
		return {}
	var field: Dictionary = _nul_at(payload, offset + 8)
	if field.is_empty() or str(field.value).is_empty():
		return {}
	return {"value": {"object_id": u16(payload, offset),
		"x": u16(payload, offset + 2), "y": u16(payload, offset + 4),
		"rotation": u16(payload, offset + 6), "model": str(field.value)},
		"offset": int(field.offset)}

## What a buddy event says happened, in the order the server numbers them.
const BUDDY_EVENTS: Array[String] = ["offline", "online", "added", "removed"]

## The four kinds a day can be, in the order the server numbers them.
const ALMANAC_KINDS: Array[String] = ["ordinary", "good", "neutral", "bad"]

## Command 238. The game date, the day in force and what it does, and the whole
## catalogue of days this server can roll.
##
## Both halves used to be chat lines - a `GET_DATE` reply and a broadcast
## announcement - so showing either meant reading prose off the chat stream.
## The catalogue arrives with them because which days exist is the server's to
## decide; a copy shipped here would be a second source of truth.
static func decode_almanac(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 7:
		return {"type": "invalid", "error": "almanac_length"}
	var kind_index: int = int(payload[4])
	if kind_index >= ALMANAC_KINDS.size():
		return {"type": "invalid", "error": "almanac_kind"}
	var names: Dictionary = _nul_run(payload, 7, 2)
	if names.is_empty():
		return {"type": "invalid", "error": "almanac_text"}
	var offset: int = int(names.offset)
	var texts: Array = names.values as Array

	if offset >= payload.size():
		return {"type": "invalid", "error": "almanac_effect_count"}
	var effect_count: int = int(payload[offset])
	var effect_fields: Dictionary = _nul_run(payload, offset + 1, effect_count)
	if effect_fields.is_empty() and effect_count > 0:
		return {"type": "invalid", "error": "almanac_effects"}
	offset = int(effect_fields.offset) if effect_count > 0 else offset + 1
	var effects: Array[String] = []
	if effect_count > 0:
		for value: Variant in effect_fields.values as Array:
			effects.append(str(value))

	if offset >= payload.size():
		return {"type": "invalid", "error": "almanac_multiplier_count"}
	var multiplier_count: int = int(payload[offset])
	offset += 1
	var multipliers: Dictionary = {}
	for _index: int in range(multiplier_count):
		var skill: Dictionary = _nul_at(payload, offset)
		if skill.is_empty() or int(skill.offset) + 2 > payload.size():
			return {"type": "invalid", "error": "almanac_multiplier"}
		offset = int(skill.offset)
		multipliers[str(skill.value)] = float(u16(payload, offset)) / 100.0
		offset += 2

	if offset + 2 > payload.size():
		return {"type": "invalid", "error": "almanac_catalogue_count"}
	var catalogue_count: int = u16(payload, offset)
	offset += 2
	var catalogue: Array[Dictionary] = []
	for _index: int in range(catalogue_count):
		if offset >= payload.size():
			return {"type": "invalid", "error": "almanac_catalogue_kind"}
		var entry_kind: int = int(payload[offset])
		if entry_kind >= ALMANAC_KINDS.size():
			return {"type": "invalid", "error": "almanac_catalogue_kind"}
		var entry: Dictionary = _nul_run(payload, offset + 1, 2)
		if entry.is_empty():
			return {"type": "invalid", "error": "almanac_catalogue_text"}
		offset = int(entry.offset)
		var entry_values: Array = entry.values as Array
		catalogue.append({"kind": ALMANAC_KINDS[entry_kind],
			"name": str(entry_values[0]), "description": str(entry_values[1])})
	var season: Dictionary = {}
	if offset < payload.size():
		# Only seasons_v1 clients are sent this optional five-byte trailer.
		if payload.size() - offset != 5 or int(payload[offset]) >= 4:
			return {"type": "invalid", "error": "almanac_season"}
		season = {"index": int(payload[offset]), "next_change": u32(payload, offset + 1)}
	return {"type": "almanac",
		"day": int(payload[0]), "month": int(payload[1]), "year": u16(payload, 2),
		"kind": ALMANAC_KINDS[kind_index],
		"experience_bonus": float(u16(payload, 5)) / 100.0,
		"name": str(texts[0]), "description": str(texts[1]),
		"effects": effects, "multipliers": multipliers, "catalogue": catalogue,
		"season": season}

## Command 228. Who the player just looked at, and what they have earned.
##
## The legacy reply is a "You see: <name>" chat line plus `SEND_ACHIEVEMENTS`,
## a bare 160-bit set with no actor id and no names: a client had to pair the
## bitset with its own outstanding request and carry a second copy of the
## server's achievement catalog to read it. This states all three.
static func decode_player_info(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 4:
		return {"type": "invalid", "error": "player_info_length"}
	var count: int = u16(payload, 2)
	var fields: Dictionary = _nul_run(payload, 4, count + 1)
	if fields.is_empty():
		return {"type": "invalid", "error": "player_info_text"}
	var offset: int = int(fields.offset)
	# The worn title, when there is one. Appended rather than slotted in, so
	# a server that predates titles sends the frame this always read and the
	# field simply is not there - which is why its absence is not an error.
	var title: String = ""
	if offset < payload.size():
		var worn: Dictionary = _nul_at(payload, offset)
		if worn.is_empty():
			return {"type": "invalid", "error": "player_info_title"}
		title = str(worn.value)
		offset = int(worn.offset)
	if offset != payload.size():
		return {"type": "invalid", "error": "player_info_trailing"}
	var values: Array = fields.values as Array
	var achievements: Array[String] = []
	for index: int in range(count):
		achievements.append(str(values[index + 1]))
	return {"type": "player_info", "actor_id": u16(payload),
		"name": str(values[0]), "achievements": achievements, "title": title}

## Command 90. One map marker the server placed: a waypoint, a quest target or
## a tutorial pointer. The map arrives as the server's own file reference, which
## is still an Eternal Lands map path (`./maps/four_gates.elm`); the marker
## belongs to that map and no other.
## map_marker_actor_v1 adds a uint16 actor id after the two NUL-terminated
## strings so a creature beacon can follow rendered motion between packets.
static func decode_map_marker(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 6:
		return {"type": "invalid", "error": "map_marker_length"}
	var text: Dictionary = _nul_run(payload, 6, 2)
	if text.is_empty():
		return {"type": "invalid", "error": "map_marker_text"}
	var remaining: int = payload.size() - int(text.offset)
	if remaining != 0 and remaining != 2:
		return {"type": "invalid", "error": "map_marker_trailing"}
	var values: Array = text.values as Array
	var marker := {"type": "map_marker", "marker_id": u16(payload),
		"x": u16(payload, 2), "y": u16(payload, 4),
		"map_id": map_id_from_reference(str(values[0])), "map_reference": str(values[0]), "label": str(values[1])}
	if remaining == 2:
		marker["actor_id"] = u16(payload, int(text.offset))
	return marker

## `./maps/four_gates.elm` is the map id `four_gates`. The server names its own
## maps this way in every marker; matching on the reference itself would tie the
## client to a path layout, and to a file format, that have nothing to do with
## what it renders.
static func map_id_from_reference(reference: String) -> String:
	return reference.get_file().get_basename()

static func decode_popup(payload: PackedByteArray) -> Dictionary:
	# The legacy client rejects anything too short to hold a one-character
	# title and a one-character body.
	if payload.size() <= 5:
		return {"type": "invalid", "error": "popup_length"}
	if int(payload[2]) != 0:
		return {"type": "invalid", "error": "popup_flags"}
	var popup_id: int = u16(payload)
	var offset: int = 3
	var title_result: Dictionary = _sized_string(payload, offset)
	if title_result.is_empty():
		return {"type": "invalid", "error": "popup_title"}
	offset = int(title_result.offset)
	if offset + 2 > payload.size():
		return {"type": "invalid", "error": "popup_size_hint"}
	var size_hint: int = u16(payload, offset)
	offset += 2
	var text_result: Dictionary = _sized_string(payload, offset)
	if text_result.is_empty():
		return {"type": "invalid", "error": "popup_text"}
	offset = int(text_result.offset)
	var options: Array[Dictionary] = []
	while offset < payload.size():
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "popup_option_header"}
		var option_type: int = int(payload[offset])
		var group: int = int(payload[offset + 1])
		offset += 2
		if option_type not in [POPUP_TEXT_ENTRY, POPUP_DISPLAY_TEXT,
				POPUP_TEXT_OPTION, POPUP_RADIO_OPTION]:
			return {"type": "invalid", "error": "popup_option_type"}
		var label_result: Dictionary = _sized_string(payload, offset)
		if label_result.is_empty():
			return {"type": "invalid", "error": "popup_option_label"}
		offset = int(label_result.offset)
		var option: Dictionary = {"option_type": option_type, "group": group,
			"label": str(label_result.value)}
		if option_type in [POPUP_TEXT_OPTION, POPUP_RADIO_OPTION]:
			if offset >= payload.size():
				return {"type": "invalid", "error": "popup_option_value"}
			option["value"] = int(payload[offset])
			offset += 1
		options.append(option)
	return {"type": "popup", "popup_id": popup_id, "title": str(title_result.value),
		"size_hint": size_hint, "text": str(text_result.value), "options": options}

## A length-prefixed string: one count byte then that many bytes. Returns the
## decoded value and the offset just past it, or an empty dictionary if the
## payload cannot hold it.
static func _sized_string(payload: PackedByteArray, offset: int) -> Dictionary:
	if offset >= payload.size():
		return {}
	var length: int = int(payload[offset])
	if offset + 1 + length > payload.size():
		return {}
	return {"value": payload.slice(offset + 1, offset + 1 + length).get_string_from_utf8(),
		"offset": offset + 1 + length}

## The player's perks as server state. Names and descriptions are on the wire,
## so the client keeps no perk table: the previous implementation asked
## `#list_perks` and pattern-matched the chat reply against a hardcoded
## 33-name array inside an 8-second window, which dropped every renamed, added
## or reworded perk and dropped all of them on a slow server.
static func decode_perks(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "perks_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var perks: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 3 > payload.size():
			return {"type": "invalid", "error": "perks_entry_length"}
		var from_gear: bool = int(payload[offset]) != 0
		var pickpoints: int = s16(payload, offset + 1)
		offset += 3
		var name_end: int = payload.find(0, offset)
		if name_end < 0:
			return {"type": "invalid", "error": "perks_name_terminator"}
		var perk_name: String = payload.slice(offset, name_end).get_string_from_utf8()
		offset = name_end + 1
		var description_end: int = payload.find(0, offset)
		if description_end < 0:
			return {"type": "invalid", "error": "perks_description_terminator"}
		var description: String = payload.slice(offset, description_end).get_string_from_utf8()
		offset = description_end + 1
		perks.append({"name": perk_name, "description": description,
			"pickpoints": pickpoints, "from_gear": from_gear})
	if offset != payload.size():
		return {"type": "invalid", "error": "perks_trailing"}
	return {"type": "perks", "perks": perks}

## Every perk that can be bought, what it costs, and the server's own reason
## for refusing it where there is one. The perks packet says what a character
## has; this says what is on offer, so the statistics window can price a perk
## and grey out what would be refused without keeping a perk table of its own.
static func decode_perk_catalog(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "perk_catalog_length"}
	var count: int = u16(payload)
	var offset: int = 2
	var perks: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 6 > payload.size():
			return {"type": "invalid", "error": "perk_catalog_entry_length"}
		var pickpoints: int = s16(payload, offset)
		var gold: int = u32(payload, offset + 2)
		offset += 6
		# A perk is bought in up to three tiers, and what is priced above is
		# the next one. The two bytes say which: how many tiers this
		# character owns, and how many there are to own.
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "perk_catalog_entry_tier"}
		var owned: int = int(payload[offset])
		var maximum: int = int(payload[offset + 1])
		offset += 2
		# Four strings now: the fourth is which tab of the perk window this
		# belongs on. Which the client is told rather than working out, for
		# the same reason it is told the names - how the shelf is divided is
		# the server's to say, and a table here would sort last week's shelf.
		var text: Dictionary = _nul_run(payload, offset, 4)
		if text.is_empty():
			return {"type": "invalid", "error": "perk_catalog_entry_text"}
		var values: Array = text.values
		offset = int(text.offset)
		perks.append({"name": values[0], "description": values[1],
			"pickpoints": pickpoints, "gold": gold, "blocker": values[2],
			"tier": owned, "max_tier": max(1, maximum),
			"category": values[3]})
	if offset != payload.size():
		return {"type": "invalid", "error": "perk_catalog_trailing"}
	return {"type": "perk_catalog", "perks": perks}

## Lifetime activity totals. `full` marks a complete snapshot; otherwise the
## packet carries only the categories that just changed. The category name
## travels with its total, so the client keeps no parallel table and the totals
## are the server's confirmed events rather than client-side guesses made when
## a request was sent.
static func decode_activity_counters(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2:
		return {"type": "invalid", "error": "activity_counters_length"}
	var full: bool = int(payload[0]) != 0
	var count: int = int(payload[1])
	var offset: int = 2
	var counters: Array[Dictionary] = []
	for _index: int in range(count):
		if offset + 4 > payload.size():
			return {"type": "invalid", "error": "activity_counter_entry_length"}
		var total: int = u32(payload, offset)
		offset += 4
		var name_end: int = payload.find(0, offset)
		if name_end < 0:
			return {"type": "invalid", "error": "activity_counter_terminator"}
		counters.append({"name": payload.slice(offset, name_end).get_string_from_utf8(),
			"total": total})
		offset = name_end + 1
	if offset != payload.size():
		return {"type": "invalid", "error": "activity_counters_trailing"}
	return {"type": "activity_counters", "full": full, "counters": counters}

static func decode_npc_options(payload: PackedByteArray) -> Dictionary:
	var options: Array[Dictionary] = []
	var offset: int = 0
	while offset < payload.size():
		if offset + 2 > payload.size():
			return {"type": "invalid", "error": "npc_option_size"}
		var text_size: int = u16(payload, offset)
		offset += 2
		if text_size < 1 or offset + text_size + 4 > payload.size():
			return {"type": "invalid", "error": "npc_option_length"}
		var label: String = nul_string(payload.slice(offset, offset + text_size))
		offset += text_size
		var response_id: int = u16(payload, offset)
		var actor_id: int = u16(payload, offset + 2)
		offset += 4
		options.append({"label": label, "response_id": response_id, "actor_id": actor_id})
	return {"type": "npc_options", "options": options}

static func decode_storage_categories(payload: PackedByteArray) -> Dictionary:
	if payload.is_empty():
		return {"type": "invalid", "error": "storage_categories_length"}
	var categories: Array[Dictionary] = []
	var offset: int = 1
	for _index: int in range(int(payload[0])):
		if offset >= payload.size():
			return {"type": "invalid", "error": "storage_category_length"}
		var category_id: int = int(payload[offset])
		offset += 1
		var terminator: int = payload.find(0, offset)
		if terminator < 0:
			return {"type": "invalid", "error": "storage_category_name"}
		categories.append({"id": category_id,
			"name": payload.slice(offset, terminator).get_string_from_utf8()})
		offset = terminator + 1
	if offset != payload.size():
		return {"type": "invalid", "error": "storage_categories_trailing"}
	return {"type": "storage_categories", "categories": categories}

static func decode_ground_bag(payload: PackedByteArray) -> Dictionary:
	if payload.size() != 5:
		return {"type": "invalid", "error": "ground_bag_length"}
	return {"type": "ground_bag", "x": u16(payload), "y": u16(payload, 2),
		"bag_id": int(payload[4])}

static func decode_ground_bags(payload: PackedByteArray) -> Dictionary:
	if payload.is_empty() or payload.size() != 1 + int(payload[0]) * 5:
		return {"type": "invalid", "error": "ground_bags_length"}
	var bags: Array[Dictionary] = []
	for index: int in range(int(payload[0])):
		var offset: int = 1 + index * 5
		bags.append({"x": u16(payload, offset), "y": u16(payload, offset + 2),
			"bag_id": int(payload[offset + 4])})
	return {"type": "ground_bags", "bags": bags}

static func decode_ground_items(payload: PackedByteArray) -> Dictionary:
	if payload.is_empty() or payload.size() != 1 + int(payload[0]) * 7:
		return {"type": "invalid", "error": "ground_items_length"}
	var items: Array[Dictionary] = []
	for index: int in range(int(payload[0])):
		items.append(decode_ground_item(payload, 1 + index * 7))
	return {"type": "ground_items", "items": items}

static func decode_ground_item(payload: PackedByteArray, offset: int = 0) -> Dictionary:
	return {"image_id": u16(payload, offset), "quantity": u32(payload, offset + 2),
		"position": int(payload[offset + 6])}

static func decode_storage_items(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 2 or (payload.size() - 2) % 8 != 0:
		return {"type": "invalid", "error": "storage_items_length"}
	var update: bool = int(payload[0]) == 255
	if int(payload[0]) not in [0, 255]:
		return {"type": "invalid", "error": "storage_items_mode"}
	var items: Array[Dictionary] = []
	for offset: int in range(2, payload.size(), 8):
		items.append({"image_id": u16(payload, offset),
			"quantity": u32(payload, offset + 2),
			"position": u16(payload, offset + 6)})
	return {"type": "storage_items", "category_id": int(payload[1]),
		"update": update, "items": items}

## The Eloria organizer packet: what each stored position actually is, so the
## window can filter a category by type and sort it by name, strength, or
## rarity. Positions match the stock STORAGE_ITEMS packet exactly.
static func decode_storage_state(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 3:
		return {"type": "invalid", "error": "storage_state_length"}
	var count: int = u16(payload, 1)
	var rows: Array[Dictionary] = []
	var offset: int = 3
	for _index: int in range(count):
		if offset + 13 > payload.size():
			return {"type": "invalid", "error": "storage_state_row"}
		var row: Dictionary = {
			"position": u16(payload, offset),
			"image_id": u16(payload, offset + 2),
			"quantity": u32(payload, offset + 4),
			"strength": s32(payload, offset + 8),
			"rarity": int(payload[offset + 12])}
		offset += 13
		for key: String in ["name", "subtype"]:
			var terminator: int = payload.find(0, offset)
			if terminator < 0:
				return {"type": "invalid", "error": "storage_state_text"}
			row[key] = payload.slice(offset, terminator).get_string_from_utf8()
			offset = terminator + 1
		rows.append(row)
	if offset != payload.size():
		return {"type": "invalid", "error": "storage_state_trailing"}
	return {"type": "storage_state", "category_id": int(payload[0]), "rows": rows}

## Where the full statistics packet keeps each thing, in its own word offsets.
## Constants for the same reason `STAT_SLOT_KEYS` is one: they never change,
## and building them inside the decoder built them again for every packet - the
## resource list was rebuilt once per resource, to be searched for the index
## the loop already had.
const STATS_ATTRIBUTE_NAMES := [
	"physique", "coordination", "reasoning", "will", "instinct", "vitality",
	"human_nexus", "animal_nexus", "vegetal_nexus", "inorganic_nexus",
	"artificial_nexus", "magic_nexus"]
const STATS_SKILL_LEVEL_SLOTS := {
	"manufacturing": 24, "harvesting": 26, "alchemy": 28, "overall": 30,
	"attack": 32, "defense": 34, "magic": 36, "potion": 38,
	"summoning": 83, "crafting": 89, "engineering": 95,
	"tailoring": 101, "ranging": 107}
const STATS_EXPERIENCE_SLOTS := {
	"manufacturing": 49, "harvesting": 53, "alchemy": 57,
	"overall": 61, "attack": 65, "defense": 69, "magic": 73,
	"potion": 77, "summoning": 85, "crafting": 91,
	"engineering": 97, "tailoring": 103, "ranging": 109}
const STATS_RESOURCE_NAMES := [
	"carried", "capacity", "health", "max_health", "ether", "max_ether"]

static func decode_stats(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 230:
		return {"type": "invalid", "error": "stats_length"}
	var values: Dictionary = {}
	for index: int in range(STATS_ATTRIBUTE_NAMES.size()):
		var key: String = str(STATS_ATTRIBUTE_NAMES[index])
		values[key] = s16(payload, index * 4)
		values[key + "_base"] = s16(payload, index * 4 + 2)
	for skill_name: String in STATS_SKILL_LEVEL_SLOTS:
		var level_slot: int = int(STATS_SKILL_LEVEL_SLOTS[skill_name])
		values[skill_name] = s16(payload, level_slot * 2)
		values[skill_name + "_base"] = s16(payload, (level_slot + 1) * 2)
	# Eloria sends spent pickpoints in the current half of the legacy overall
	# pair and the actual overall level in the base half.
	values["overall_level"] = values["overall_base"]
	for skill_name: String in STATS_EXPERIENCE_SLOTS:
		var experience_slot: int = int(STATS_EXPERIENCE_SLOTS[skill_name])
		values[skill_name + "_exp"] = u32(payload, experience_slot * 2)
		values[skill_name + "_exp_next"] = u32(payload, (experience_slot + 2) * 2)
	for resource_index: int in range(STATS_RESOURCE_NAMES.size()):
		values[str(STATS_RESOURCE_NAMES[resource_index])] = s16(
			payload, (40 + resource_index) * 2)
	values["food"] = s16(payload, 46 * 2)
	values["research_completed"] = s16(payload, 47 * 2)
	values["researching"] = s16(payload, 81 * 2)
	values["research_total"] = s16(payload, 82 * 2)
	values["action_points"] = s16(payload, 113 * 2)
	values["max_action_points"] = s16(payload, 114 * 2)
	# Eloria's current server also uses these legacy tail slots for pickpoint
	# accounting. Keep the action-point aliases for older servers/HUD meters.
	values["pickpoints_spent"] = values["action_points"]
	values["pickpoints_earned"] = values["max_action_points"]
	return {"type": "stats", "values": values}

static func decode_partial_stats(payload: PackedByteArray) -> Dictionary:
	if payload.size() % 5 != 0:
		return {"type": "invalid", "error": "partial_stats_length"}
	var values: Dictionary = {}
	for offset: int in range(0, payload.size(), 5):
		var slot: int = int(payload[offset])
		var value: int = s32(payload, offset + 1)
		values[stat_key(slot)] = value
		if slot == 31 or slot == 114:
			values["overall_level"] = value
		if slot == 113:
			values["pickpoints_spent"] = value
		elif slot == 114:
			values["pickpoints_earned"] = value
	return {"type": "partial_stats", "values": values}

## Inventory entries are eight bytes. The optional legacy ten-byte form carried
## a per-item UID that this server does not emit, so decoding it produced a
## `uid` field nothing could ever contain or read. PROTOCOL.md, not
## client_serv.h, is the specification: when unique item identity goes on the
## wire it will be added deliberately, with a consumer.
static func decode_inventory(payload: PackedByteArray) -> Dictionary:
	if payload.is_empty():
		return {"type": "invalid", "error": "inventory_length"}
	var count: int = int(payload[0])
	if payload.size() != 1 + count * 8:
		return {"type": "invalid", "error": "inventory_length"}
	var items: Array[Dictionary] = []
	for index: int in range(count):
		items.append(decode_inventory_item(payload, 1 + index * 8))
	return {"type": "inventory", "items": items}

static func decode_inventory_update(payload: PackedByteArray) -> Dictionary:
	if payload.size() != 8:
		return {"type": "invalid", "error": "inventory_update_length"}
	return {"type": "inventory_update", "item": decode_inventory_item(payload, 0)}

static func decode_inventory_item(payload: PackedByteArray,
		offset: int) -> Dictionary:
	var flags: int = int(payload[offset + 7])
	var item: Dictionary = {
		"image_id": u16(payload, offset), "quantity": u32(payload, offset + 2),
		"slot": int(payload[offset + 6]), "flags": flags,
		"reagent": (flags & 1) != 0, "resource": (flags & 2) != 0,
		"stackable": (flags & 4) != 0, "inventory_usable": (flags & 8) != 0,
		"tile_usable": (flags & 16) != 0, "player_usable": (flags & 32) != 0,
		"object_usable": (flags & 64) != 0, "on_off": (flags & 128) != 0}
	return item

static func decode_item_cooldowns(payload: PackedByteArray) -> Dictionary:
	if payload.size() % 5 != 0:
		return {"type": "invalid", "error": "item_cooldown_length"}
	var cooldowns: Array[Dictionary] = []
	for offset: int in range(0, payload.size(), 5):
		cooldowns.append({"slot": int(payload[offset]),
			"maximum_seconds": u16(payload, offset + 1),
			"remaining_seconds": u16(payload, offset + 3)})
	return {"type": "item_cooldowns", "cooldowns": cooldowns}

## Partial-statistic slot numbers. These are the legacy incremental-update
## identifiers and are a different namespace from the word offsets in the full
## statistics packet: research is 47/65/66 here and 47/81/82 there, and the
## server writes both from the same character fields.
## Attack levels precede defense (32-35), but their partial XP identifiers
## have the opposite order (defense 57/58, attack 59/60).
## Which stat each slot of a partial-stat packet carries.
##
## A constant, not a table built inside `stat_key`. Every health, food, mana
## and experience tick arrives as a partial-stat packet and every stat in one
## asked for this name, so a ninety-entry dictionary was allocated, filled and
## thrown away several times per packet: 41 microseconds a packet, which is
## most of what a partial stat cost to decode at all.
const STAT_SLOT_KEYS := {
	0: "physique", 1: "physique_base", 2: "coordination",
	3: "coordination_base", 4: "reasoning", 5: "reasoning_base",
	6: "will", 7: "will_base", 8: "instinct", 9: "instinct_base",
	10: "vitality", 11: "vitality_base", 12: "human_nexus",
	13: "human_nexus_base", 14: "animal_nexus", 15: "animal_nexus_base",
	16: "vegetal_nexus", 17: "vegetal_nexus_base", 18: "inorganic_nexus",
	19: "inorganic_nexus_base", 20: "artificial_nexus",
	21: "artificial_nexus_base", 22: "magic_nexus", 23: "magic_nexus_base",
	24: "manufacturing", 25: "manufacturing_base", 26: "harvesting",
	27: "harvesting_base", 28: "alchemy", 29: "alchemy_base",
	30: "overall", 31: "overall_base", 32: "attack", 33: "attack_base",
	34: "defense", 35: "defense_base", 36: "magic", 37: "magic_base",
	38: "potion", 39: "potion_base", 40: "carried", 41: "capacity",
	42: "health", 43: "max_health", 44: "ether", 45: "max_ether",
	46: "food", 47: "researching", 49: "manufacturing_exp",
	50: "manufacturing_exp_next", 51: "harvesting_exp",
	52: "harvesting_exp_next", 53: "alchemy_exp", 54: "alchemy_exp_next",
	55: "overall_exp", 56: "overall_exp_next", 57: "defense_exp",
	58: "defense_exp_next", 59: "attack_exp", 60: "attack_exp_next",
	61: "magic_exp", 62: "magic_exp_next", 63: "potion_exp",
	64: "potion_exp_next", 65: "research_completed", 66: "research_total",
	67: "summoning_exp", 68: "summoning_exp_next", 69: "summoning",
	70: "summoning_base", 71: "crafting_exp", 72: "crafting_exp_next",
	73: "crafting", 74: "crafting_base", 75: "engineering_exp",
	76: "engineering_exp_next", 77: "engineering", 78: "engineering_base",
	79: "ranging_exp", 80: "ranging_exp_next", 81: "ranging",
	82: "ranging_base", 83: "tailoring_exp", 84: "tailoring_exp_next",
	85: "tailoring", 86: "tailoring_base", 87: "action_points",
	88: "max_action_points", 113: "action_points", 114: "max_action_points"}

static func stat_key(slot: int) -> String:
	if STAT_SLOT_KEYS.has(slot):
		return str(STAT_SLOT_KEYS[slot])
	return "slot_%d" % slot

## How the actor packets encode a model scale: an unsigned 16-bit field
## holding the base-two logarithm of the scale in 1/2048ths of an octave,
## offset so 0x8000 is life size.
##
## Logarithmic because scale is multiplicative and the range wanted of it
## is fourteen octaves - 128x down to 1/128 - which a linear field would
## hold to half a percent at the top and fifty percent at the bottom.
## Every power of two lands exactly.
##
## Must match the server's `protocol.ACTOR_SCALE_ZERO` and steps, or every
## scaled creature is drawn at the wrong size.
const ACTOR_SCALE_ZERO := 32768.0
const ACTOR_SCALE_STEPS_PER_OCTAVE := 2048.0

## The scale an actor packet's 16-bit field asks for.
static func decode_actor_scale(value: int) -> float:
	return pow(2.0, (float(value) - ACTOR_SCALE_ZERO) / ACTOR_SCALE_STEPS_PER_OCTAVE)

## The land neighbours of the map the client stands on: handle -> server map
## name. Actor packets carry the handle in their stock "z" field; 0 is never
## listed and means the client's own map.
static func decode_adjacent_maps(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 1:
		return {"type": "invalid", "error": "adjacent_maps_length"}
	var maps: Dictionary = {}
	var offset: int = 1
	for _index in range(int(payload[0])):
		if payload.size() < offset + 3:
			return {"type": "invalid", "error": "adjacent_maps_length"}
		var handle: int = u16(payload, offset)
		var end: int = payload.find(0, offset + 2)
		if end < 0:
			return {"type": "invalid", "error": "adjacent_maps_name"}
		maps[handle] = payload.slice(offset + 2, end).get_string_from_ascii()
		offset = end + 1
	return {"type": "adjacent_maps", "maps": maps}

static func decode_actor(payload: PackedByteArray, enhanced: bool, extended := false) -> Dictionary:
	var minimum := 31 if enhanced else (19 if extended else 18)
	if payload.size() < minimum:
		return {"type": "invalid", "error": "actor_length"}
	var shift := 1 if extended else 0
	var actor := {
		"type": "actor_spawn", "enhanced": enhanced, "actor_id": u16(payload),
		"x": u16(payload, 2) & 0x7ff, "y": u16(payload, 4) & 0x7ff,
		"rotation": s16(payload, 8),
		# The stock "z" field, which no client read: the handle of the neighbour
		# map the actor stands on (ELORIA_ADJACENT_MAPS names it), 0 for our own.
		"map_handle": u16(payload, 6),
		"actor_type": u16(payload, 10) if extended else int(payload[10]),
		"scale": 1.0}
	if enhanced:
		actor["appearance"] = {
			"skin": int(payload[12]), "hair": AppearanceVariants.hair_from_wire(int(payload[13]), int(payload[17])), "shirt": int(payload[14]),
			"pants": int(payload[15]), "boots": int(payload[16]), "head": int(payload[17]),
			"eyes": 0,
			"shield": int(payload[18]), "weapon": int(payload[19]),
			"cape": int(payload[20]), "helmet": int(payload[21])}
		actor["equipment_visuals"] = {
			0: int(payload[19]), 1: int(payload[18]), 2: int(payload[20]),
			3: int(payload[21]), 4: int(payload[15]), 5: int(payload[14]),
			6: int(payload[16])}
		actor["equipment_fallback_parts"] = []
		actor["frame"] = int(payload[22])
		actor["max_health"] = u16(payload, 23)
		actor["health"] = u16(payload, 25)
		actor["kind"] = int(payload[27])
		var name_end: int = payload.find(0, 28)
		if name_end < 0:
			name_end = min(payload.size(), 58)
		actor.merge(decode_actor_name(payload.slice(28, name_end)))
		# The enhanced-actor trailer follows the variable-length name: model
		# scale, the attachment sentinel, eye style, and neck visual. Preserve
		# eye choices across the real server round trip instead of silently
		# reverting to 0.
		#
		# The first two bytes were read as an attached actor id, which they
		# never were - the server writes a scale there, and 255 at +2 is the
		# no-attachment sentinel. Nothing read either field, so the mistake
		# was invisible until a scale other than life size was sent.
		var trailer_offset: int = name_end + 1
		if payload.size() >= trailer_offset + 5:
			actor["scale"] = decode_actor_scale(u16(payload, trailer_offset))
			actor["attachment_type"] = int(payload[trailer_offset + 2])
			var appearance: Dictionary = actor["appearance"] as Dictionary
			appearance["eyes"] = int(payload[trailer_offset + 3])
			var neck_visual: int = int(payload[trailer_offset + 4])
			if neck_visual > 0:
				var equipment_visuals: Dictionary = actor["equipment_visuals"] as Dictionary
				equipment_visuals[7] = neck_visual
			# Opt-in wardrobe trailer: WA, version 1, shirt/pants/boots dyes,
			# then a mask of clothing parts whose legacy bytes really are gear.
			var wardrobe_offset := trailer_offset + 5
			if payload.size() >= wardrobe_offset + 7 and payload.slice(
					wardrobe_offset, wardrobe_offset + 3) == PackedByteArray([87, 65, 1]):
				var clothing_visuals: Dictionary = actor["equipment_visuals"] as Dictionary
				var worn_mask := int(payload[wardrobe_offset + 6])
				for index: int in range(3):
					var key: String = ["shirt", "pants", "boots"][index]
					var part: int = [5, 4, 6][index]
					appearance[key] = int(payload[wardrobe_offset + 3 + index])
					if (worn_mask & (1 << part)) == 0:
						clothing_visuals.erase(part)
	else:
		actor["frame"] = int(payload[11 + shift])
		actor["max_health"] = u16(payload, 12 + shift)
		actor["health"] = u16(payload, 14 + shift)
		actor["kind"] = int(payload[16 + shift])
		var plain_name: PackedByteArray = payload.slice(
			17 + shift, min(payload.size(), 47 + shift))
		var plain_end: int = plain_name.find(0)
		# A plain actor packet is a creature or a scenery NPC. Neither has a
		# guild, and their names routinely contain spaces.
		actor.merge(decode_actor_name(plain_name if plain_end < 0
			else plain_name.slice(0, plain_end), false))
		# A creature's scale rides after the name's terminator and only when
		# it is not life size, so its offset depends on how long the name
		# was. No terminator means no trailer to find.
		if plain_end >= 0:
			var scale_offset: int = 17 + shift + plain_end + 1
			if payload.size() >= scale_offset + 2:
				actor["scale"] = decode_actor_scale(u16(payload, scale_offset))
	actor["alive"] = int(actor.get("health", 0)) > 0
	# The frame byte is the actor's current animation state. FRAME_COMBAT_IDLE
	# is the only value that carries gameplay meaning at spawn: an actor
	# already fighting when it comes into view must not be presented as idle
	# until the next enter-combat command, which may never arrive.
	actor["in_combat"] = int(actor.get("frame", FRAME_IDLE)) == FRAME_COMBAT_IDLE
	return actor

## Eternal Lands' text palette (colors.c), in the server's own index order:
## the four shades of a hue are 7 apart, not adjacent. Only the first of each
## entry's four shades is a text colour, so only that one is kept here.
##
## Index 0 is EL's c_red1, but a colour reaches us as the byte `127 + index`
## and a leading 127 is not read as a marker, so 0 never arrives from the wire
## and doubles as "the server chose no colour for this name".
const EL_TEXT_COLOURS: Array[Color] = [
	Color("ffb3c1"), Color("f7c49f"), Color("fbfabe"), Color("c9fecb"),
	Color("a9effa"), Color("d2b4fb"), Color("ffffff"),
	Color("fa5a5a"), Color("fc7a3a"), Color("fcec38"), Color("05fa9b"),
	Color("7697f8"), Color("d95df4"), Color("999999"),
	Color("dd0202"), Color("bf6610"), Color("e7ae14"), Color("25c400"),
	Color("4448d2"), Color("8254f6"), Color("9e9e9e"),
	Color("7e0303"), Color("833003"), Color("826f06"), Color("149504"),
	Color("0f0fba"), Color("6a01ac"), Color("282828"),
]

## The colour a decoded `name_colour` or `guild_colour` asks for. Returns
## `fallback` for 0 - the server named no colour - and for anything outside the
## palette, so an unknown index degrades to the plain nameplate rather than to
## black.
static func el_text_colour(colour_index: int, fallback := Color.WHITE) -> Color:
	if colour_index <= 0 or colour_index >= EL_TEXT_COLOURS.size():
		return fallback
	return EL_TEXT_COLOURS[colour_index]

## Splits the display name an actor packet carries into the parts it is really
## made of: the name, the colour the server chose for it, and the guild tag
## with its own colour.
##
## The server builds one string - an optional colour byte, the name, then a
## space, an optional colour byte and the guild tag - and a client that takes
## the whole thing as a name renders the colour bytes as mojibake and the tag
## as part of the player's name. Both colours are the server's choice, so they
## are decoded rather than dropped, and neither is ever chosen here.
static func decode_actor_name(bytes: PackedByteArray,
		space_separates_tag := true) -> Dictionary:
	var name_colour: int = 0
	var body: PackedByteArray = bytes
	if not body.is_empty() and body[0] > 127:
		name_colour = int(body[0]) - 127
		body = body.slice(1)
	var guild_colour: int = 0
	var guild_tag: String = ""
	# The tag's own colour marker is the reliable separator, because it cannot
	# occur inside a name. The trailing space is only a fallback for a server
	# that sent an uncoloured tag, and it is never used for a creature or NPC:
	# "Mirrorfin Otter" is one name, and splitting it on the space turns every
	# two-word creature into "Mirrorfin [Otter]".
	var marker: int = -1
	for offset: int in range(body.size()):
		if body[offset] > 127:
			marker = offset
			break
	var space: int = marker - 1 if marker > 0 else (
		body.rfind(32) if space_separates_tag else -1)
	if space > 0 and body[space] == 32:
		var tag_bytes: PackedByteArray = body.slice(space + 1)
		if not tag_bytes.is_empty():
			if tag_bytes[0] > 127:
				guild_colour = int(tag_bytes[0]) - 127
				tag_bytes = tag_bytes.slice(1)
			guild_tag = tag_bytes.get_string_from_ascii()
			body = body.slice(0, space)
	return {"name": body.get_string_from_ascii(), "name_colour": name_colour,
		"guild_tag": guild_tag, "guild_colour": guild_colour}

static func nul_string(bytes: PackedByteArray) -> String:
	var end := bytes.find(0)
	var clean := bytes if end < 0 else bytes.slice(0, end)
	return clean.get_string_from_utf8()

## The palette index of the colour byte a chat line opens with, or 0 when the
## server led with plain text. Only the leading byte is read: mid-line colour
## changes are stripped by `legacy_colored_string`, so a line renders in the
## one colour the server chose for it.
static func leading_text_colour(bytes: PackedByteArray) -> int:
	if bytes.is_empty():
		return 0
	var index: int = int(bytes[0]) - 127
	if index <= 0 or index >= EL_TEXT_COLOURS.size():
		return 0
	return index

static func legacy_colored_string(bytes: PackedByteArray) -> String:
	# EL color markers occupy the C1-control range. Preserve bytes in valid
	# UTF-8 multibyte sequences so non-ASCII chat is not damaged while removing
	# standalone presentation controls from the text DTO.
	var end: int = bytes.find(0)
	var source: PackedByteArray = bytes if end < 0 else bytes.slice(0, end)
	var clean: PackedByteArray = PackedByteArray()
	var continuation_bytes: int = 0
	for byte_value: int in source:
		if continuation_bytes > 0:
			if byte_value >= 0x80 and byte_value <= 0xbf:
				clean.append(byte_value)
				continuation_bytes -= 1
				continue
			continuation_bytes = 0
		if byte_value >= 0x7f and byte_value <= 0x9f:
			continue
		clean.append(byte_value)
		if byte_value >= 0xc2 and byte_value <= 0xdf:
			continuation_bytes = 1
		elif byte_value >= 0xe0 and byte_value <= 0xef:
			continuation_bytes = 2
		elif byte_value >= 0xf0 and byte_value <= 0xf4:
			continuation_bytes = 3
	return clean.get_string_from_utf8()

static func u16(bytes: PackedByteArray, offset := 0) -> int:
	return int(bytes[offset]) | (int(bytes[offset + 1]) << 8)

static func s16(bytes: PackedByteArray, offset := 0) -> int:
	var value := u16(bytes, offset)
	return value - 65536 if value >= 32768 else value

## Little-endian 64-bit. Read as two 32-bit halves because shifting a byte to
## bit 56 in one expression is where a signed-integer surprise would hide.
static func u64(bytes: PackedByteArray, offset := 0) -> int:
	return u32(bytes, offset) | (u32(bytes, offset + 4) << 32)

static func u32(bytes: PackedByteArray, offset := 0) -> int:
	return (int(bytes[offset]) | (int(bytes[offset + 1]) << 8)
		| (int(bytes[offset + 2]) << 16) | (int(bytes[offset + 3]) << 24))

static func s32(bytes: PackedByteArray, offset := 0) -> int:
	var value: int = u32(bytes, offset)
	return value - 4294967296 if value >= 2147483648 else value


static func decode_lantern(payload: PackedByteArray, logical_coordinates := false) -> Dictionary:
	if payload.is_empty() or payload.size() > 8192:
		return {"type":"invalid", "error":"lantern_length"}
	var json := JSON.new()
	if json.parse(payload.get_string_from_utf8()) != OK:
		return {"type":"invalid", "error":"lantern_json"}
	var parsed: Variant = json.data
	if not parsed is Dictionary:
		return {"type":"invalid", "error":"lantern_json"}
	var value: Dictionary = parsed
	if value.has("event"):
		return decode_tutorial_experience(value)
	if typeof(value.get("version")) not in [TYPE_INT, TYPE_FLOAT] or value.version != 1 or not value.get("active") is bool:
		return {"type":"invalid", "error":"lantern_version"}
	if value.has("ring_training") and not value.ring_training is bool:
		return {"type":"invalid", "error":"ring_training"}
	if value.has("tutorial") and value.tutorial not in ["second_bell", "borrowed_sky", "followup", "signed_ashore", "watchpost", "field_dispatch"]:
		return {"type":"invalid", "error":"tutorial_kind"}
	# Signed Ashore, the landing isle's chapter: its four countersigns
	# (grove/temple/gate/light) stand in for the Lantern's flags below. The
	# type test comes first: != between a String and a number, array,
	# dictionary or bool is a script error, not false.
	if value.get("tutorial", "") == "signed_ashore" and bool(value.active) and not (value.get("chapter") is String and value.chapter == "SIGNED ASHORE"):
		return {"type":"invalid", "error":"signed_ashore_chapter"}
	if value.get("tutorial", "") == "watchpost" and bool(value.active):
		if not (value.get("chapter") is String and value.chapter == "HELP FOR THE WATCHPOST") or not value.get("paused") is bool:
			return {"type":"invalid", "error":"watchpost_state"}
	if value.get("tutorial", "") == "followup" and bool(value.active):
		for key in ["adventure", "guide"]:
			if not value.get(key) is String:
				return {"type":"invalid", "error":"adventure_text"}
	if value.get("tutorial", "") in ["second_bell", "borrowed_sky"] and bool(value.active):
		if not (value.get("chapter") is String and value.chapter == ("THE BORROWED SKY" if value.tutorial == "borrowed_sky" else "THE SECOND BELL")) or not value.get("pending") is bool or not value.get("assisted") is bool:
			return {"type":"invalid", "error":"bell_state"}
		var remaining: Variant = value.get("remaining")
		if typeof(remaining) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(remaining)) or remaining < 0 or remaining > 500 or int(remaining) != remaining:
			return {"type":"invalid", "error":"bell_remaining"}
		if not value.get("flags") is Dictionary:
			return {"type":"invalid", "error":"bell_flags"}
		for key in ["north", "east", "south", "west", "rung"]:
			if not value.flags.get(key) is bool:
				return {"type":"invalid", "error":"bell_flags"}
	if bool(value.active):
		for key in ["stage","total","scene","count","required"]:
			var number: Variant = value.get(key)
			if typeof(number) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(number)) or int(number)!=number or number<0 or number>65535:
				return {"type":"invalid", "error":"lantern_number"}
		for key in ["key","title","hint","control","item","map","target_id"]:
			if not value.get(key) is String:
				return {"type":"invalid", "error":"lantern_text"}
		if int(value.get("stage",0)) < 1 or int(value.get("stage",0)) > int(value.get("total",0)):
			return {"type":"invalid", "error":"lantern_stage"}
		if not value.get("flags") is Dictionary or not value.get("target") is Array:
			return {"type":"invalid", "error":"lantern_target"}
		if value.target.size() != 2:
			return {"type":"invalid", "error":"lantern_target"}
		for coordinate: Variant in value.target:
			if typeof(coordinate) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(coordinate)) or coordinate < (-2147483648 if logical_coordinates else 0) or coordinate > (2147483647 if logical_coordinates else 65535) or int(coordinate)!=coordinate:
				return {"type":"invalid", "error":"lantern_target"}
		if value.has("route"):
			if not value.route is Array or value.route.size() > 513:
				return {"type": "invalid", "error": "tutorial_route"}
			for point: Variant in value.route:
				if not point is Array or point.size() != 2:
					return {"type": "invalid", "error": "tutorial_route"}
				for coordinate: Variant in point:
					if typeof(coordinate) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(coordinate)) \
							or int(coordinate) != coordinate or coordinate < (-2147483648 if logical_coordinates else 0) \
							or coordinate > (2147483647 if logical_coordinates else 65535):
						return {"type": "invalid", "error": "tutorial_route"}
		var required_flags: Array = ["north","east","south","west"] if value.get("tutorial", "") == "followup" \
			else ["grove","temple","gate","light"] if value.get("tutorial", "") == "signed_ashore" \
			else ["crafted","prepared","repaired","lit"]
		for key in required_flags:
			if not value.flags.get(key) is bool:
				return {"type":"invalid", "error":"lantern_flags"}
		for key in ["forge_lit", "sword_ready", "pump_repaired", "order_ready",
				"caravan_north_open", "caravan_east_home", "caravan_south_home", "caravan_west_home"]:
			if value.flags.has(key) and not value.flags[key] is bool:
				return {"type":"invalid", "error":"lantern_flags"}
	return {"type":"lantern_tutorial", "state":value}

static func decode_tutorial_experience(value: Dictionary) -> Dictionary:
	if typeof(value.get("version")) not in [TYPE_INT, TYPE_FLOAT] or value.version != 1 \
			or not value.get("event") is String or value.event != "experience" \
			or not value.get("permanent") is bool or not value.get("rewards") is Array:
		return {"type":"invalid", "error":"tutorial_experience"}
	var rewards: Array = value.rewards
	if rewards.is_empty() or rewards.size() > 13:
		return {"type":"invalid", "error":"tutorial_experience_rewards"}
	var seen: Dictionary = {}
	for reward: Variant in rewards:
		if not reward is Dictionary or reward.get("skill") not in [
				"manufacturing", "harvesting", "alchemy", "overall", "attack", "defense",
				"magic", "potion", "summoning", "crafting", "engineering", "ranging", "tailoring"]:
			return {"type":"invalid", "error":"tutorial_experience_skill"}
		var amount: Variant = reward.get("amount")
		if typeof(amount) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(amount)) \
				or amount <= 0 or amount > 4294967295 or int(amount) != amount or seen.has(reward.skill):
			return {"type":"invalid", "error":"tutorial_experience_amount"}
		seen[reward.skill] = true
	return {"type":"tutorial_experience", "rewards":rewards, "permanent":value.permanent}
