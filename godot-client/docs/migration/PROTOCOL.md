# Protocol compatibility specification (baseline)

Authoritative sources: server `eloria/protocol.py`, server protocol tests, legacy client `client_serv.h`, `connection.cpp`, and `multiplayer.c` at the audited revisions.

## Transport and framing

TCP stream. Each frame is `command:u8 | wire_length:u16le | payload`. `wire_length` includes the command byte, so total bytes on the wire are `wire_length + 2`. Valid payload length is 0–65,532. Reads may be fragmented or contain multiple frames.

Strings are message-specific. Legacy authentication uses NUL-terminated byte strings; server-facing text commonly uses UTF-8, while actor names and legacy login fields require Latin-1-compatible bytes. Integer fields are little-endian unless a packet-specific audit proves otherwise.

## Connection baseline

Endpoint is configurable (legacy `servers.lst` behavior will become a data resource). States are disconnected, connecting, connected, authenticating, loading_world, in_world, and reconnecting. Password frames and credentials are always redacted. Invalid lengths terminate the connection safely.

## Verified identifiers

Client: RAW_TEXT 0, MOVE_TO 1, SEND_PM 2, GET_PLAYER_INFO 5, RUN_TO 6, SIT_DOWN 7, SEND_ME_MY_ACTORS 8, SEND_VERSION 10, TURN_LEFT 11, TURN_RIGHT 12, PING 13, HEART_BEAT 14, LOCATE_ME 15, USE_MAP_OBJECT 16, stats 17, inventory 18, harvest 21, drop 22, pickup 23, inspect bag 25, NPC response 29, manufacture 30, item use 31, trade 32–38, cast 39, attack 40, storage 44–47, login 140, create 141, date/time 230/231.

Server: RAW_TEXT 0, actor spawn 1/51, actor command 2, YOU_ARE 3, clock 4/5, actor removal 6, map change 7, combat mode 8, clear actors 9, stats 18, inventory 19–22, ground/bags 23–29, NPC 30–33, trade 35–41, equipment 52/53, ping 60, storage 67–69, spell 70, channels 71, actor health 73, cooldowns 77, buffs 78, effects 79, popup 83, map markers 90/91, achievements 95, login results 250/251, creation results 252/253.

## Authentication

LOG_IN(140) is username, one ASCII space, password, then NUL. This matches legacy send_login_info() and server _credentials(). On connection the client first sends SEND_VERSION with protocol 10.31, application 1.9.7.0, IPv4 bytes, and a network-order port, followed by SEND_OPENING_SCREEN. Password-containing frames are always redacted.

## Coordinate baseline

Movement payload is `x:u16le, y:u16le`. Actor packets use 11-bit tile coordinates in server serialization. Godot conversion is centralized and will be finalized from map/client inspection; no scene may implement its own conversion.

An actor packet's `frame` byte is its current animation state. Only
`FRAME_COMBAT_IDLE`(15) carries gameplay meaning at spawn: it marks an actor
that is already fighting when it comes into view, which must not be presented
as idle until an enter-combat command that may never arrive.

Partial statistic slots are the legacy incremental-update identifiers and are a
different namespace from the word offsets in the full statistics packet:
research progress is 47/65/66 (index, pages read, total pages) in a partial
update and 47/81/82 (pages read, index, total pages) in the full packet. The
server writes both from the same character fields.

Actor movement is advanced by server `ADD_ACTOR_COMMAND` frames: commands 20–27
are one-tile walk steps and 30–37 are the equivalent run steps. `SIT_DOWN(7)`
carries one desired-state byte (`1` sit, `0` stand); the server broadcasts actor
commands 13/14 after accepting the state change. The legacy default is Alt+S.

Facing is server-owned. `TURN_LEFT(11)` and `TURN_RIGHT(12)` carry no payload
and each request one 45° step; left is counter-clockwise seen from above. The
server rotates the character and broadcasts the matching turn actor command
38–45 (`CMD_TURN_N` … `CMD_TURN_NW`, clockwise from north) to everyone on the
map, so a turn is visible to other players. A turn command changes facing
without moving the actor. The same facing is stored in the actor packet's
signed 16-bit `rotation` field as `direction_index × 8192`, wrapped into
−32768…32767, so a client that spawns the actor later sees the direction a
client that watched the turn sees. Walking also updates that field from the
step direction. A seated player does not turn; the server ignores the request,
because the turn animation would break the seated pose. The client may render
one predicted step while the reply is in flight, but the reply replaces it.

Chat sends `RAW_TEXT(0)` as UTF-8 plus NUL. A private message sends
`SEND_PM(2)` as `recipient ASCII-space message NUL`, omitting the leading slash
typed in the legacy input line; payloads beginning with `/` implement the
legacy `// message` reply-to-last-sender shortcut. Incoming private messages
are normal `RAW_TEXT(0)` frames on channel 1. Local, personal, server, and the
three rendered channel tabs use channel IDs 0, 1, 3, and 5–7 respectively.
Standalone legacy color-control bytes are presentation metadata and are
removed from DTO text without removing valid UTF-8 continuation bytes.
NPC activation sends
`TOUCH_PLAYER(28)` with `actor_id:u32le`. Dialogue uses `SEND_NPC_INFO(33)`,
`NPC_TEXT(30)`, and a repeated `NPC_OPTIONS_LIST(31)` entry layout of
`text_size:u16le | NUL text | response_id:u16le | actor_id:u16le`; replies send
`RESPOND_TO_NPC(29)` as `actor_id:u16le | response_id:u16le`. `SEND_NPC_INFO`
carries a trailing legacy portrait index after the 20-byte name; Eloria has no
portrait artwork and will not convert the Eternal Lands set, so that byte is
deliberately not carried into the dialogue DTO.

Inventory snapshots use `HERE_YOUR_INVENTORY(19)` with a count byte followed
by `image_id:u16le | quantity:u32le | slot:u8 | flags:u8` entries. Entries are
eight bytes; the optional legacy ten-byte form carrying `uid:u16le` is not
emitted by this server and is rejected rather than half-decoded. When unique
item identity goes on the wire it will be added with a consumer. Incremental updates
use the same entry in `GET_NEW_INVENTORY_ITEM(21)`; removals are one or more
slot bytes in `REMOVE_ITEM_FROM_INVENTORY(22)`. Inspect and use send one slot
byte with commands 19 and 31. Moving/equipping sends
`MOVE_INVENTORY_ITEM(20)` as `source_slot:u8 | destination_slot:u8`; inventory
positions are 0–35 and the eight generic wear positions are 36–43. Cooldown
command 77 repeats `slot:u8 | maximum_seconds:u16le | remaining_seconds:u16le`.

Actor equipment changes are server commands 52/53. Wear is
`actor_id:u16le | part:u8 | visual_id:u8`; unwear omits the visual byte. Parts
0–7 mean right hand, left hand, cape, helmet, legs, body, boots, and neck. These
part IDs are distinct from the eight generic inventory wear positions. Part 1
carries a shield below visual 160 and a weapon held in the off hand at 160 and
above, which is how a player with Two Handed Wielding is drawn holding two; the
server sends what each part is drawing now rather than what each item is, so
wearing the second weapon moves it to part 1 without disturbing the first.

Spell casting sends `CAST_SPELL(39)` as `count:u8 | sigil_id:u8[count]`; the
ordered sigil sequence, not the local spell ID, identifies the spell. The
server publishes ownership with `GET_YOUR_SIGILS(42)` as two `u32le` masks (the client's DTO carries the
decoded ownership list only, not the list and its raw masks) and
returns `SPELL_CAST(70)` as `status:u8 | spell_id:u8`. Status 1 succeeds, 2
fails validation or the cast roll, 3 rejects an invalid/unknown spell, 4 asks
for an actor selected through `TOUCH_PLAYER(28)`, and 5 asks for a location
submitted through the normal movement packet. `GET_ACTIVE_SPELL(44)` carries
`buff_id:u8 | duration_seconds:u8`.

The book is twenty-two spells now, ids 0-21, which is what the twelve-slot
quickbar and the spell window were built for; `data/spells/catalog.json`
mirrors `dev-server config/eloria/spells.xml` and the server test
`tests/test_spellbook.py` fails if the two disagree on any id, name, level,
mana, icon, sigil sequence or reagent. Seven of the twelve ask for an actor
(status 4) and none of the new ones asks for a location. Four of the new
spells - Swiftwend, Duskveil, Glassgaze and Thriceward - name effects that
`spells_window.gd`'s `EFFECT_GROUPS` does not, so they draw under General.
Eternal Lands also keeps haste, invisibility and true sight there;
`element_ward` belongs under Defense and wants a row in that table.

Melee targeting sends `ATTACK_SOMEONE(40)` as `actor_id:u32le`. The server may
approach the target before broadcasting actor command 18 (enter combat), 46
(primary attack), and 19 (leave combat); command 3 is death. Actor damage and
heal messages 47/48 carry `actor_id:u16le | amount:u16le`, while command 73
carries `actor_id:u16le | max_health:u16le`. Creature and PvP range, PK-area,
Peace Day, already-in-combat, death, and flee validation remain server-owned.

Player trade begins with `TRADE_WITH(32)` carrying `actor_id:u32le`; the target
accepts the 30-second request by sending the reciprocal command while within a
four-tile Chebyshev radius. `GET_TRADE_PARTNER_NAME(41)` carries
`storage_available:u8 | name[0..19] | NUL`, followed by
`GET_YOUR_TRADEOBJECTS(40)` using the normal inventory snapshot body. Inventory
offers send `PUT_OBJECT_ON_TRADE(36)` as
`source_type=1:u8 | source_slot:u8 | quantity:u32le`; the server immediately
removes the accepted quantity from inventory and broadcasts `GET_TRADE_OBJECT`
(35) as `image_id:u16le | quantity:u32le | source_type:u8 | offer_slot:u8 |
other:u8`. Removal sends `REMOVE_OBJECT_FROM_TRADE(37)` as
`offer_slot:u8 | quantity:u32le`; server command 39 returns
`quantity:u32le | offer_slot:u8 | other:u8`. `ACCEPT_TRADE(33)` carries sixteen
destination bytes (1 inventory, or 2 storage where allowed). Acceptance is a
server-authoritative two-phase sequence reported by `GET_TRADE_ACCEPT(36)` as
`other:u8 | phase:u8`. Phase 0 is not accepted, 1 is the first stage, and 2 is
the second stage that completes the trade; `other` names the side the phase
belongs to. The client reads the phase and never infers it by counting accept
packets, because a duplicated, dropped or reordered accept would otherwise
desynchronise the two-phase state machine from the server. The server clamps
the phase to 0-2 and the client rejects any other value. Command 37 resets the
indicated side, and command 38 closes the trade. `REJECT_TRADE(34)` only
resets acceptance. `EXIT_TRADE(35)` cancels and restores all offers.

Storage is opened only through a nearby storage NPC dialogue response. Server
command `STORAGE_LIST(67)` carries `count:u8` followed by repeated
`category_id:u8 | NUL name`; `GET_STORAGE_CATEGORY(44)` selects one category by
its `u8` identifier. `STORAGE_ITEMS(68)` starts with
`mode:u8 | category_id:u8`; mode 0 is a full snapshot and mode 255 is one
incremental entry. Each entry is `image_id:u16le | quantity:u32le |
position:u16le`. Deposits use `DEPOSIT_ITEM(45)` as
`inventory_slot:u8 | quantity:u32le`. Withdrawals use `WITHDRAW_ITEM(46)` as
`storage_position:u16le | quantity:u32le`. Inspection uses
`LOOK_AT_STORAGE_ITEM(47)` with a `u16le` position and receives
`STORAGE_TEXT(69)` as `color:u8 | NUL text`. The server validates NPC range,
category/session state, quantities, inventory slots, and carry capacity.

Ground bags are map-authoritative. `GET_NEW_BAG(27)` carries
`x:u16le | y:u16le | bag_id:u8`; `GET_BAGS_LIST(28)` prefixes repeated entries
with a count byte, and `DESTROY_BAG(29)` carries the map-local bag ID. Inspect
sends `INSPECT_BAG(25)` with that ID. The server approaches the bag when
needed, then `HERE_YOUR_GROUND_ITEMS(23)` sends `count:u8` plus repeated
`image_id:u16le | quantity:u32le | position:u8` entries. Incremental add and
remove commands are 24 and 25; command 26 closes the view. Pickup sends
`PICK_UP_ITEM(23)` as `position:u8 | quantity:u32le`; dropping sends
`DROP_ITEM(22)` as `inventory_slot:u8 | quantity:u32le`. The server owns bag
creation/destruction, interaction range, carry capacity, quantities, and the
resulting inventory snapshots.

Knowledge ownership is sent by `GET_KNOWLEDGE_LIST(55)` as a little-endian
bitset: bit `index % 8` of byte `index / 8` marks one catalog entry as read.
`GET_NEW_KNOWLEDGE(56)` carries a newly completed `index:u16le`. Selecting an
entry sends `GET_KNOWLEDGE_INFO(41)` with `index:u16le`, and the server replies
with `GET_KNOWLEDGE_TEXT(57)` as NUL-terminated UTF-8. Index-to-name mapping is
the insertion-ordered result of the server's `load_books` catalog, excluding
repeatable big books; the checked-in Godot catalog records the exact source
configuration hashes used to generate it. Reading itself remains initiated by
using a server-recognized book from inventory, and the server owns progress,
completion, recipe gating, and rejection messages.

Manufacturing sends `MANUFACTURE_THIS(30)` as `count:u8`, followed by `count`
entries of `inventory_slot:u8 | quantity:u16le`, and a trailing `wanted:u8`.
The legacy tray and imported server catalog both cap ingredient entries at six.
`wanted=1` requests one attempt and `wanted=255` requests the legacy mix-all
loop. The server matches authoritative item names and quantities to one exact
recipe; validates knowledge, tools, skills, food, ethereal points, combat,
special days, nexus, and carry capacity; then reports outcomes through the
existing inventory text (20), raw text (0), inventory (19/21/22), and
partial/full statistics (49/18) messages. The checked-in recipe catalog is
generated from the unmodified server's recipes, items, and books configuration
and records all three source hashes. Recipes whose distinct item names share a
legacy image ID are shown but automatic mixing remains disabled, because the
default inventory wire format transmits neither an item name nor UID.

## Open verification items

Full field tables for every identifier; version sequence and capability behavior; keepalive cadence; map-change filename encoding; enhanced actor optional tail; storage-backed trade positions and storage lifecycle; reconnect policy. These remain explicit blockers in traceability rather than assumed behavior.

## Eloria extension packets

Perks are server state, not chat. `ELORIA_PERKS(234)` carries `count:u16le`
followed by `count` entries of
`from_gear:u8 | pickpoints:i16le | name NUL | description NUL`, all UTF-8. The
`from_gear` flag marks a perk granted by equipped gear rather than a permanent
one, and `pickpoints` is signed because negative perks give pick points back.
Names and descriptions are on the wire so the client keeps no perk table: the
previous client asked `#list_perks` and pattern-matched the chat reply against
a hardcoded 33-name array inside an eight-second window, which silently dropped
every renamed, added or reworded perk and dropped all of them on a slow server.
The server pushes the packet at login and whenever the effective perk set
changes: a perk purchase, a removal stone, a quest reward, and any equipment
change, because a cape can carry a perk. The client never requests it.

`ELORIA_ACTIVITY_COUNTERS(235)` carries lifetime activity totals as
`full:u8 | count:u8` followed by `count` entries of `total:u32le | name NUL`.
`full` marks a complete snapshot, sent once at login and listing all seventeen
categories; otherwise the packet is a delta carrying only the categories that
just changed. Totals saturate at `0xffffffff` rather than wrapping. The
category name travels with its total so the client keeps no parallel table.
The seventeen categories are Kills, Deaths, Breakages, Crit Fails, Used Items,
Events, Harvests, Alchemy, Crafting, Manufacturing, Potions, Spells, Summons,
Engineering, Tailoring, Storage and Drops. Every increment is made after the
server has committed the outcome, never when a request arrives, so a rejected
deposit or a failed mix does not count. The client presents the totals and
derives its "this session" column as a difference against the totals as they
stood when the session started; it increments nothing.

Combat techniques (the server's `eloria/techniques.py`) use one new number in
each direction's spirit but only one on the wire. The client asks with
`ELORIA_TECHNIQUE_REQUEST(220)`, client to server, a UTF-8 JSON body
`{"op": "use", "key": <technique>, "target_id": <actor id, optional>}` or
`{"op": "state"}`. It names at most an actor, never a tile, so it is sent
unframed even when coordinates are selected. The answer rides the existing
JSON channel `ELORIA_MAGIC_STATE(212)` as kind `"techniques"`, sent only to a
client that declares `techniques_v1`: the real action-point pool (the legacy
stats slots 113/114 carry pick points on this server), what is readied and
held, and one row per technique with its cost, cooldown, `ready_in` seconds,
whether it is known, and the server's refusal text. The client draws the rows
and never decides a technique is usable. Stun, root, sunder, mark, challenge,
brace, riposte, war_cry and intercept arrive as ordinary actor status names.

Repeat casting rides the same JSON pair. The client switches it with
`magic_request {"op": "autocast", "enabled": bool}` and is told the switch and
whether a spell is repeating as `ELORIA_MAGIC_STATE` kind `"autocast"`
(`enabled`, `active`, `spell_id`, `target_id`), only when it declares
`magic_autocast_v1`. Escape sends the ordinary `{"op": "cancel"}`, which stops
a repeat. Target spells are always aimed by a click: no client path sends a
cast at the selected actor without one.

## Capability handshake

On login the client sends `#clientcaps a,b,c` as an ordinary `RAW_TEXT(0)`
chat command; the server parses it out and stores the set on the session. Every
Eloria extension window is gated on its capability, and a client that has not
claimed one is served a legacy fallback instead - raw text for the quest
journal, NPC dialogue menus for the merchant and the marketplace, a plain item
description instead of the item-detail packet - or, for the navigation and
combat HUDs, nothing at all. Those fallbacks are the only way a client without
the windows can use those features, so they are load-bearing until the windows
exist.

The client advertises only capabilities whose packets it actually decodes
(`EloriaProtocol.CLIENT_CAPABILITIES`). Claiming one it cannot decode is worse
than claiming nothing: it replaces a working dialogue with a packet that lands
in the protocol diagnostics panel and nowhere else. The list grows in the same
commit that lands each window.

The client advertises thirteen capabilities: `actor16_v1`, `combat_hud_v1`,
`inventory_window_v1`, `item_detail_v1`, `mail_window_v1`, `market_window_v1`,
`merchant_window_v1`, `navigation_hud_v1`, `player_info_v1`,
`quest_journal_v1`, `spell_power_v1` and `special_events_v1`. `tests/test_protocol.gd` decodes a real payload behind
each one, so the list cannot outrun the decoders.

`actor16_v1` does **not** gate the 16-bit actor packet. Measured against the
real server: `actor_packet()` selects `ADD_NEW_ACTOR_EXTENDED(247)` purely from
`actor_type > 0xFF`, with no capability check anywhere, so a creature with a
type of 401 arrives on the extended packet for a client that has advertised
nothing at all. The capability is advertised because the client does implement
the packet, not because anything is withheld without it.

## Audio

Nothing about audio is on the wire. Every sound the client plays is answered to
a packet that already exists - the harvest state, the inventory snapshot, the
combat state, `SEND_SPECIAL_EFFECT` - or to the player's own click. A snapshot
that restates what was already true is not a new event and is silent, which is
the same rule the rest of the client follows for a restated state.

## World effects

`SEND_SPECIAL_EFFECT(79)` is `effect:u8 | actor_id:u16`, with a second
`target_id:u16` when the effect travelled between two actors. It is an event,
not state - there is nothing to still be true a moment later - so the client
announces it and stores nothing.

The effect ids are a legacy namespace with no names on the wire. This server
uses 17 for a harvest interrupted by bees, 14 for a lucky harvest, and a
spell-to-effect table for the rest, four of which (0, 1, 2, 10) carry a second
actor. The client draws an abstract generated burst - a ring, and a beam when
the server named a second actor - rather than inventing a distinct piece of
art per id, which would be inventing meaning the server never sent. An effect
at an actor the client has not been told about is not drawn at all rather than
placed at a guess.

## Player names, colours and guild tags

An actor packet carries one display-name string, not three fields: an optional
name-colour byte, the name, then - for a player in a guild - a space, an
optional tag-colour byte and the tag. Both colour bytes are `chr(127 + colour)`
and the tag colour is chosen per viewer, so the same player can arrive with
different tag colours for different clients. `decode_actor_name` splits all
four parts; a client that does not is showing the colour byte as mojibake and
the tag as part of the player's name.

There is **no buddy list** on this server: no table, no command, no
notification and nothing on the wire. Guilds are the social structure it has.

## Looking at things

`LOOK_AT_INVENTORY_ITEM(19)`, `LOOK_AT_STORAGE_ITEM(47)`, `LOOK_AT_TRADE_ITEM(38)`
and `LOOK_AT_GROUND_ITEM(24)` all take a single slot byte and are answered the
same way: the fork's `ELORIA_ITEM_DETAIL(225)` for a client with
`item_detail_v1`, and `INVENTORY_ITEM_TEXT(20)` for any other. The ground-item
case had no handler at all until 2.7; the bag packet carries an image id, a
quantity and a slot, so nothing else could say what an item on the ground was.

`ITEM_ON_ITEM(42)` and `DO_EMOTE(70)` are **not implemented on either side and
have no concept behind them**: no client-command constant, no dispatch branch,
no item-on-item combination in the world model and no emote catalog, state or
broadcast. An encoder for either would put bytes on the wire that nothing
reads.

## Spell power

`CAST_SPELL(39)` is `count:u8 | sigil...`, and the fork accepts an optional
trailing `power:u8`. Without that byte the frame is exactly the legacy one and
the server uses the stored preference; with it, the server sets the preference
to that power and casts at it, refusing anything above the limit.

Command 231 states both numbers per standardized effect, because both are the
server's: the preference is stored on the character and the limit comes from
its Magic level and nexus. An effect the character cannot cast at all is left
out rather than sent with a limit of zero. The client's stepper is bounded by
the highest stated limit and each cast is clamped to the limit stated for that
effect, so no progression rule is duplicated client-side.

**Content defect:** no NPC in the Eloria roster sells a sigil - the roster
format has no column for it - so `buy_sigil` can never find a seller and
`CAST_SPELL(39)` always answers "you do not have these sigils". The client's
spell quickbar is therefore unusable against this content profile, and the
standardized `#cast` framework is the only working route.

## Active effects

`GET_ACTIVE_SPELL(44)` is `buff_id:u8 | seconds:u8`, `REMOVE_ACTIVE_SPELL(46)`
is `buff_id:u8`, and `GET_ACTIVE_SPELL_LIST(45)` is ten buff ids with 255 for
an empty slot. All three share their command numbers with client-to-server
storage commands; the direction tells them apart.

Two server defects sat behind this and are fixed in 2.3. `protocol.active_spell`
referenced a `GET_ACTIVE_SPELL` constant that was never defined, so every
buff-granting cast raised `NameError` inside the connection handler and killed
that client's connection silently. And nothing announced an expiry: `has_buff`
drops an expired effect the next time something asks, so the server was right
and the client was never told. A two-second sweep now sends
`REMOVE_ACTIVE_SPELL` when one runs out.

The buff id namespace is the server's; the names are not on the wire. The
client's spell catalog carries a name and an icon per buff id, the same way it
already carries spell names and sigil art. Ids this server sets: 0 shield, 1
magic protection, 3 invisibility, 7 haste, 11 magic immunity, 17/23 cold
protection, 18/24 heat protection, 19/25 radiation protection, 22 true sight -
the duplicate pairs are the potion and the spell routes to the same
protection. Seven and eleven were in the server's duration table with no spell
to set them until Swiftwend and Null Mantle; a hasted player also carries the
`BUFF_DOUBLE_SPEED` bit in `SEND_BUFFS(78)`, which is what makes the client
choose its running frames.

`SEND_BUFFS(78)` is `actor_id:u16 | buffs:u32`, the visible effects on one
actor. The only bit this server sets is 1024, doubled movement speed, and it
states the whole mask each time rather than a change.

## Map markers

`SEND_MAP_MARKER(90)` is `marker_id:u16 | x:u16 | y:u16 | map_reference |
label`, and `REMOVE_MAP_MARKER(91)` is `marker_id:u16`. The map reference is
the server's own file name for the map (`./maps/four_gates.elm`); the client
reduces it to the map id it already knows rather than matching a path it never
renders from.

The server owns markers completely. It places the waypoint marker (id 490) when
`#waypoint` sets one and removes that id when the waypoint is cleared, and it
maintains the tutorial and quest markers (ids 500-506) by clearing the whole
range and re-sending what still applies. A marker for another map is kept
rather than dropped, because the server does not withdraw one when the player
walks away; the client draws only the markers whose map is the one it is
standing on.

## Keepalive, idle eviction and resync

The client sends `HEART_BEAT(14)` - a zero-payload frame - every 25 seconds
while connected, matching the legacy cadence. The server records the arrival
time of every inbound packet and closes a *logged-in* connection that has sent
nothing for `client_idle_timeout_seconds` (default 90, zero disables the
sweep). A connection that has not authenticated is not swept.

This exists because a client that vanishes without closing its socket produces
no FIN: its character would otherwise stay in the server's logged-in set and
its actor in the world until the kernel gave up, and the player could not
reconnect to their own character in the meantime. Eviction releases both, so a
re-login succeeds immediately.

Resync is `SEND_ME_MY_ACTORS(8)`, `SEND_MY_STATS(17)` and
`SEND_MY_INVENTORY(18)`, which return `ADD_NEW_ENHANCED_ACTOR(51)` for every
visible actor, `HERE_YOUR_STATS(18)` and `HERE_YOUR_INVENTORY(19)`. Everything
else the client holds is derived from those three, so they are what a
connection of doubtful continuity asks for. The client sends all three after
re-authenticating following a dropped socket.

Reconnection is client-side only and never involves stored credentials. An
unexpected drop schedules a socket reconnect with backoff (1s, 2s, 4s, 8s,
15s, then it stops); a disconnect the player asked for schedules nothing. The
password is cleared from the client the moment it is sent and is never
retained, so a recovered socket returns the player to the login panel with
their username preserved rather than signing in on their behalf.

## Server popups

`DISPLAY_POPUP(83)` is a modal question. Its payload is
`popup_id:u16le | flags:u8 | title | size_hint:u16le | text` followed by zero
or more options, where each string is length-prefixed: one count byte then that
many UTF-8 bytes. `flags` must be zero; the client rejects anything else rather
than guessing. Each option is `option_type:u8 | group:u8 | label`, and the two
selectable types carry a trailing `value:u8`:

| Type | Meaning | Value byte |
|---|---|---|
| 0 | text entry - a field the player types into | no |
| 1 | display text - a static line | no |
| 8 | text option - a button that answers immediately | yes |
| 9 | radio option - a choice confirmed with the send button | yes |

Options are grouped by `group`, and exactly one answer is returned per group.
A popup containing a radio option or a text entry gets a send button and
answers when it is pressed; a popup built only from text options answers the
moment one is clicked, because each option *is* the action. That is the legacy
rule (`popup.c` sets `has_send_button` when a radio option or text entry is
added) and the Godot client follows it.

`POPUP_REPLY(50)` carries `popup_id:u16le` then, per answered group,
`group:u8 | value:u8` for a choice or `group:u8 | 0:u8 | length:u8 | text` for
an entry. A group the player left unanswered is absent. Dismissing a popup
sends nothing at all: declining to answer is a legitimate outcome and must not
be reported as a choice. The server does not send a close packet - the client
closes the window once its answer is on the wire, and keeps it open if the
send failed.

Only one popup is shown at a time; a repeat of an id already on screen is
ignored, matching the legacy client's refusal to open a second window for it.

## World objects and harvesting

The client cannot tell which rendered prop is a resource. A world package draws
harvestable props and buildings as ordinary geometry, and the legacy client
matched object basenames against a lowercase `harvestable.lst` while the packs
wrote relative paths, so nothing ever matched and no object was harvestable in
the C client either. Object identity is therefore server state.

`ELORIA_MAP_OBJECTS(236)` lists the clickable objects on the player's current
map. It is sent unasked at login and again on every map change, and it is
chunked because a busy map has thousands of harvest nodes: each frame is
`first:u8 | count:u16le` followed by `count` entries of
`object_id:u16le | kind:u8 | x:u16le | y:u16le | label NUL | detail NUL`. Only
the frame with `first` set begins a new list; the rest continue it. Kind 1 is a
harvest node, kind 2 is an interactive and kind 3 is a map exit; any other
kind is rejected. `label` is the resource name, the interactive's role, or the
exit's destination, and `detail` is the harvesting level and tool requirement,
the interactive's text, or a sentence naming where the exit leads - so a
requirement is stated rather than discovered by failing. An exit is a way off
the map that nothing else marks - a march with no waygate, a door into an
interior, the way out of one - derived by the server from its own portal
tiles, one per doorway; it is not clickable, and both maps draw it as a red X
named for its destination, beside the cyan P a waygate gets.

`HARVEST(21)` carries `object_id:u16le` and is a toggle: sending it for the
node already being harvested stops the run. `USE_MAP_OBJECT(16)` and
`LOOK_AT_MAP_OBJECT(27)` both carry `object_id:u32le`, the legacy widths.

`ELORIA_HARVEST_STATE(237)` is `active:u8 | object_id:u16le | resource NUL`,
sent when a run starts and on every path that ends one - the player moving, a
full backpack, entering combat, a map change, or the toggle. The stock client
matched an exact English phrase out of the chat stream to drive this state,
which is not a contract: it breaks on any rewording and on any translation.
The client renders the indicator from this packet only.

## Books and reading

The Eloria server models a book as **research**, not as pages of text. Using a
book from the backpack consumes it and sets `reading_book`, `reading_pages` and
`reading_total`; pages tick down while the character has food, and the
knowledge bit is set on completion with `GET_NEW_KNOWLEDGE(56)`. Progress is
reported through ordinary partial statistics: slot 47 is the knowledge index
being read (1024 means nothing), 65 is pages completed and 66 is the total.
The full statistics packet carries the same three facts at word offsets 47, 81
and 82.

`OPEN_BOOK(64)`, `READ_BOOK(65)`, `CLOSE_BOOK(66)` and `SEND_BOOK(43)` are the
legacy page-content protocol and are **deliberately not implemented**. This
server has no book text: `config/books.txt` is a two-setting tuning file, and
`load_books` derives a `BookDefinition` from each book *item* with a page count
and nothing else. Implementing a page-turning window against it would be a
window with nothing behind it. If page content is ever wanted, the server needs
book text first, and those four opcodes become the way to carry it.

Reading is presented from the three statistics above plus the client's hashed
knowledge catalog for the title. There is no command to stop reading; hiding
the window does not interrupt it, and the client does not pretend otherwise.

## The nine Eloria extension windows

Fork additions rather than upstream Eternal Lands. Each is a server-push
snapshot driving one window: the server states the whole window and the client
renders it, so none of them is merged with a previous value. Every one is
withheld from a client that has not claimed the matching capability in
`#clientcaps`, and the server falls back to legacy dialogue or raw text
instead. All integers are little-endian and all strings are NUL-terminated
UTF-8.

| Cmd | Window | Payload |
|---|---|---|
| 222 | Marketplace | `view:u8 \| gold:u32 \| returned_items:u32 \| count:u16`, then per listing `listing_id:u32 \| quantity:u32 \| unit_price:u32 \| seconds_left:u32 \| image_id:u16 \| item_name \| seller`. With `market_window_v2`, then `offset:u32 \| total:u32 \| page_size:u8 \| query \| notice_kind:u8 \| notice`, one `flags:u8` per listing (bit 0: the player's own), `returns:u16`, and per item in return escrow `quantity:u32 \| image_id:u16 \| reason:u8 \| item_name` (reason 0 returned, 1 expired, 2 cancelled; notice kind 0 none, 1 done, 2 refused) |
| 223 | Merchant | `actor_id:u16 \| gold:u32 \| carried:u32 \| capacity:u32 \| count:u16 \| npc_name`, then per row `index:u16 \| buy_price:u32 \| sell_price:u32 \| owned:u32 \| image_id:u16 \| name` |
| 224 | Quest journal | `count:u16`, then per entry `ready:u8 \| current:u32 \| target:u32 \| title \| objective \| location` |
| 225 | Item detail | `image_id:u16 \| quantity:u32 \| equipped:u8 \| name \| category \| equip_type \| description \| stats \| comparison_name \| comparison` |
| 226 | Inventory state | `gold:u32 \| carried:u32 \| capacity:u32 \| count:u16`, then per row `slot:u8 \| image_id:u16 \| quantity:u32 \| emu:u32 \| flags:u8 \| name \| category` |
| 227 | Combat HUD | `event:u8 \| target_id:u16 \| player_health:u16 \| player_max:u16 \| target_health:u16 \| target_max:u16 \| recent_damage:u16 \| target_name` |
| 228 | Player info | `actor_id:u16 \| count:u16 \| name`, then one achievement name per row |
| 231 | Spell power | `count:u16`, then per effect `preferred:u8 \| limit:u8 \| effect_name` |
| 229 | Mail | `count:u16`, then per message `mail_id:u32 \| created_at:u32 \| read:u8 \| sender \| subject \| body` |
| 230 | Navigation HUD | `active:u8 \| x:u16 \| y:u16 \| distance:u16 \| map_id \| label` |
| 232 | Special events | NUL-delimited text lines, always NUL-terminated |
| 74 | World object list | `count:u16`, then per object `object_id:u16 \| x:u16 \| y:u16 \| rotation:u16 \| model_name` |
| 75 | World object | one object, same body as a list row |
| 76 | World object removed | `object_id:u16` |
| 10 | Teleporters | `count:u16`, then `x:u16 \| y:u16` per portal |
| 12 | Teleport in | `x:u16 \| y:u16` |
| 13 | Teleport out | `x:u16 \| y:u16` |
| 59 | Buddy event | `event:u8 \| name` - event indexes `offline, online, added, removed` |
| 92 | Next NPC message is a quest | empty; describes the frame after it |
| 93 | Here is the quest id | `quest_id:u16` |
| 94 | Quest finished | `quest_id:u16` |
| 100 | Weather | `kind:u8 \| intensity:u8` - kind indexes `clear, rain, storm`, intensity 0-100 |
| 15 | Start rain | `intensity:u8` - the legacy signal, sent alongside |
| 16 | Stop rain | empty |
| 17 | Thunder | `severity:u8`, 1-5 |
| 61 | Fire | `x:u16 \| y:u16 \| kind:u8` - hearth, forge or pyre |
| 62 | Fire removed | `x:u16 \| y:u16` |
| 14 | Play a sound | `x:u16 \| y:u16 \| gain:u8 \| sound_name` - gain is a percentage, 0-200 |
| 54 | Play music | `track_name`, empty for silence |
| 85 | Missile aim at a place | `actor_id:u16 \| x:u16 \| y:u16` |
| 87 | Missile loosed at a place | `actor_id:u16 \| x:u16 \| y:u16` |
| 89 | Actor animation | `actor_id:u16 \| action` - an action name, never a clip |
| 238 | Almanac | `day:u8 \| month:u8 \| year:u16 \| kind:u8 \| experience_bonus:u16 \| name \| description \| effect_count:u8` then that many effect tags, `multiplier_count:u8` then that many `skill \| multiplier:u16`, `catalogue_count:u16` then that many `kind:u8 \| name \| description` |

Commands 74, 75 and 76 put objects into a map that is already being played in.
Everything the client knew about a map used to arrive with the map, so nothing
could raise a totem in the square while somebody was standing in it. A list is
the whole truth about a map and replaces what was there; a single placement
adds to it. The model is a name rather than a file - which art a client draws
is its own business, and a name it does not know is drawn as a plain marker,
because an object that is there should be visible even when its appearance is
not.

Commands 10, 12 and 13 are the portals. The client could see a portal's art
without any idea it was one, so it could not mark one or say where a road went.
An empty list is an answer: this map has no way out. The two effects carry
tiles rather than actors, because the actor packets already say who moved and
the part a client cannot work out is where the ends were - by the time it hears
about an arrival, the departure has already gone.

`MAP_SET_OBJECTS(220)` and `MAP_STATE_OBJECTS(221)` stay unallocated as
server-to-client commands (220 client-to-server is the technique request
above; the directions are separate spaces). They are
superseded rather than missing: `ELORIA_MAP_OBJECTS(236)` already states every
clickable object on a map with its kind and its name, which is strictly more
than the legacy pair carried. Mines - `REMOVE_MINE(80)`, `GET_NEW_MINE(81)`,
`GET_MINES_LIST(82)` - stay unallocated because nothing on this server places a
trap, triggers one, or makes one.

Command 59 carries the buddy list. The server owns the list and states all of
it at login, so no client keeps a copy, and the name travels with every event
because a client that had to consult its own list to read one would be keeping
a second copy of a list it does not own.

Adding somebody is a bookmark, not a friendship: it does not tell them, does
not need their agreement, and gives no way to reach a person who has not asked
to hear from you. `#add_buddy`, `#remove_buddy` and `#buddies` drive it.

Commands 92, 93 and 94 say which quest a piece of NPC dialogue belongs to. The
fork's own journal already carried what a player was doing, but nothing marked
a line of dialogue as part of a quest, so it could not be told from small talk.
The flag comes first because it describes the frame after it, and it describes
exactly one line: the next thing an NPC says is small talk again unless the
server flags that too. A quest with no id sends nothing rather than zero.

`WHAT_QUEST_IS_THIS_ID(63)` asks for a quest's name. An id the server does not
know is answered with a plain refusal rather than silence, so a client is never
left waiting on a reply that is not coming.

Command 100 carries the whole sky in one frame, with 15, 16 and 17 as the
legacy signals sent alongside it so an older client still sees weather. The sky
has to be the server's: two players standing together must see the same one,
and a client rolling its own would drift from everyone else's within a minute.
It rolls once per game day, so weather moves at the pace of the day the world
already has. A map that declares no climate is always clear - it has no weather
rather than a default it never asked for.

Commands 61 and 62 place and remove fires. A fire is content the client cannot
invent, so each is named by tile and kind; what a hearth, a forge or a pyre
looks like is the client's to decide, and a kind it does not know is still
drawn, because a fire that is there should be visible even if its flavour is
not.

Commands 14 and 54 carry the audio a client cannot work out for itself. This
client answers its own harvest, its own combat and its own pick-ups from state
it already has, so the server never sends a sound for those - the client that
caused a sound is left out of the broadcast, or it would hear everything twice.
What is left is what somebody else is doing, and what a map sounds like.

Both name rather than number. A numeric table would have to be mirrored in the
client and would go stale the first time a sound was added; a name the client
has no sound for is simply not heard, and an empty music track is the server
saying the map is quiet, which is an answer rather than an omission.

Commands 85 and 87 draw an arrow going to a place rather than into somebody.
Two things use them: a practice shot at a tile, sent by the client as
`FIRE_MISSILE_AT_OBJECT(51)`, and a **miss**. A miss used to be drawn as a shot
at the target it missed - the shot was broadcast before the hit was rolled, so
every miss looked exactly like a hit. Where a stray arrow lands is the server's
decision, computed from the two positions rather than rolled, so two clients
watching one shot draw the same arrow instead of each inventing a scatter.
`MISSILE_FIRE_XYZ_TO_B(88)` stays unallocated: nothing on this server shoots at
an actor from a place.

Command 89 asks an actor to play a named animation action - an emote, or
anything else that is not one of the actor commands. It carries an action name
rather than a clip: which piece of art plays is the client's to decide from its
own animation map, and an action the client has no clip for is simply not
played. An emote's two text lines are sent separately and always, so an emote
that cannot be animated still reaches everyone as words.

`DO_EMOTE(70)` and `ITEM_ON_ITEM(42)` are the client commands behind it. Both
share a number with a server-to-client command, the way the storage commands
share 44-46; the direction tells them apart. `DO_EMOTE` carries the emote's
name rather than a numeric id, because this server has no legacy emote id
namespace and mirroring one in the client would be a second copy of a list the
server owns. `ITEM_ON_ITEM` carries two inventory slots and means one thing:
mix the recipe whose ingredients are exactly those two items.

Command 238 replaces two chat lines. The game date was only ever a `GET_DATE`
reply reading "Game Date 4/7/132", and the special day in force was only ever a
broadcast announcement, so a client that wanted to show either had to parse
prose off the chat stream. Both are numbers here. `kind` is an index into
`ordinary, good, neutral, bad`; `experience_bonus` and each skill `multiplier`
are hundredths, so 200 is a doubling and 123 is the 1.23 that Scholars Day
rolls at random and no client could derive.

The catalogue of every day the world can bring travels with the packet rather
than being shipped inside the client. Which days exist and what each one does
is the server's to decide, and a copy in the client is a second source of truth
that goes stale without anyone noticing. Both chat lines still go out unchanged
for the legacy client.

Command 228 replaces a reply a client could not read on its own. The legacy
answer to `GET_PLAYER_INFO(5)` is a `You see: <name>` chat line plus
`SEND_ACHIEVEMENTS(95)`, a 160-bit set with no actor id and no names: a client
had to pair the bitset with a request it remembered making, and keep its own
copy of the server's achievement catalog to name the bits. 228 states the
actor, the name and the achievements together, so the client does neither. A
client without `player_info_v1` still gets the chat line and the bitset.

`COMBAT_MODE(8)` is defined on both sides and **sent by nothing**: the Eloria
server has no call site for it. The client does not decode it, because combat
presentation is already driven by two things the server does send - the actor
frame, which says whether an actor arrives already in combat, and command 227,
which states both health bars and the outcome of each exchange.

Command 226 is **enrichment, not inventory**. The authoritative inventory
packet still owns which slot holds what and how much; 226 adds only the names,
categories and per-unit weights that packet has no room for, and the client
uses it for nothing else. Where the two disagree about a quantity, the
authoritative packet wins - the client never adopts 226's number - so the
enrichment cannot become a second, contradictory source of inventory truth.
The server sends it only in answer to `#inventory`.

A client advertising `merchant_window_v1` sends the legacy shop response ids
(`3100 + index` to choose an item, `3300 + n` or `3309` to choose a quantity)
without the dialogue ever being drawn, so no new client-to-server command
exists for shop trade. The server answers those ids with a refreshed command
223 rather than the NPC text and options menu a legacy client gets, including
when it refuses the trade.

Combat event 0 is a state refresh; 1 hit, 2 miss, 3 dodge, 4 defeat. A defeat
ends the engagement, so the client clears the HUD on it rather than leaving the
last frame on screen. Navigation `active` false means no waypoint is set and
the remaining fields are meaningless rather than stale. A special-event payload
of a single NUL clears the panel.

Each decoder rejects a truncated payload and any trailing bytes rather than
half-decoding, so a layout change on the server surfaces in the protocol
diagnostics panel instead of producing a half-filled window.
