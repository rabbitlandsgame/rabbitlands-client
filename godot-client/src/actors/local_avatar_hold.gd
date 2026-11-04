extends RefCounted
## The player's own body, kept across a map change that is not a seamless
## crossing (AW-02, wave-2 avatar-worker plan section 3.1).
##
## A door, a teleport, a gauntlet entry or a same-map relocation used to free
## the local avatar with every other actor (KILL_ALL_ACTORS, then CHANGE_MAP)
## and rebuild it for the ADD_NEW_ACTOR that follows the server's YOU_ARE. The
## actor id is per character, so that ADD names the same actor: Main holds the
## body here instead and wears it again through the path a parked crowd body
## takes back (main.gd `_hold_local_avatar` / `_adopt_local_avatar`).
##
## Main owns the node and every call; this owns the one slot, its expiry and
## its counters:
## - **Held.** Out of Main's `actor_nodes`, so nothing that walks the table -
##   stale removal, the animation gate, the arrival hold, the camera follow -
##   sees it, but still under Main's `world_root`, so it never leaves the tree
##   (no `_exit_tree` side effects such as the RL head releases). Hidden, not
##   processing and not pickable, as a parked crowd body is.
## - **Adopted** only by the ADD for the same actor id, the same identity key
##   (CrowdPresentation.identity_key: type, kind, name, guild tag, name colour)
##   and the same model id.
## - **Released** (freed): on an ADD for the player that does not match,
##   HOLD_MSEC after the hold, when the player's actor id changes, and at
##   session end or client close.

## How long a held body waits for its ADD. A map change sends it within the
## same burst as the CHANGE_MAP; a cold arrival behind the curtain can take a
## few seconds more before Main builds the player.
const HOLD_MSEC := 15000

var _holding := false
var _node: Variant = null
var _actor_id := -1
var _identity := ""
var _model := ""
var _held_at := 0
var _until := 0
## Bodies held, bodies worn again, and why the others were let go.
var holds := 0
var adoptions := 0
var releases: Dictionary = {}
## How long the last adopted body waited for its ADD, in milliseconds.
var last_wait_msec := -1
## Why a body was not held (Main's eligibility, `refuse`).
var refusals: Dictionary = {}

func holding() -> bool:
	return _holding

## The actor id of the held body, or -1.
func held_id() -> int:
	return _actor_id if _holding else -1

## The held body itself, or null (also once something else freed it).
func node() -> Node3D:
	return _node as Node3D if _holding and is_instance_valid(_node) else null

## Takes `node` out of view for the ADD that should follow. False (and nothing
## changed) for a node that is gone or being freed. A body already held is let
## go first: there is one player.
func hold(node: Node3D, actor_id: int, identity: String, model: String, now: int) -> bool:
	if not is_instance_valid(node) or node.is_queued_for_deletion():
		return false
	if _holding and _node != node:
		release("replaced")
	node.visible = false
	node.process_mode = Node.PROCESS_MODE_DISABLED
	if node is CollisionObject3D:
		(node as CollisionObject3D).collision_layer = 0
	_holding = true
	_node = node
	_actor_id = actor_id
	_identity = identity
	_model = model
	_held_at = now
	_until = now + HOLD_MSEC
	holds += 1
	return true

## Whether the held body is the one an ADD with these values asks for.
func matches(actor_id: int, identity: String, model: String) -> bool:
	return _holding and is_instance_valid(_node) and actor_id == _actor_id \
		and identity == _identity and model == _model

## The held body for this ADD, visible and processing again, or null. A held
## body that does not match is freed: the ADD builds a new one.
func take(actor_id: int, identity: String, model: String) -> Node3D:
	if not _holding:
		return null
	if not is_instance_valid(_node):
		_forget("lost")
		return null
	if not matches(actor_id, identity, model):
		release("mismatch")
		return null
	var node := _node as Node3D
	last_wait_msec = Time.get_ticks_msec() - _held_at
	_forget("")
	node.visible = true
	node.process_mode = Node.PROCESS_MODE_INHERIT
	adoptions += 1
	return node

## Lets the held body go once HOLD_MSEC has passed or the player is someone
## else now. Main calls it every frame; with nothing held it is one test.
func expire(now: int, local_actor_id: int) -> bool:
	if not _holding:
		return false
	if not is_instance_valid(_node):
		_forget("lost")
		return true
	if local_actor_id != _actor_id:
		release("actor_changed")
		return true
	if now >= _until:
		release("expired")
		return true
	return false

## Frees the held body, counting `reason`.
func release(reason: String) -> void:
	if not _holding:
		return
	if is_instance_valid(_node) and not (_node as Node).is_queued_for_deletion():
		(_node as Node).queue_free()
	_forget(reason)

## Counts a body Main chose not to hold (`reason` names the rule).
func refuse(reason: String) -> void:
	refusals[reason] = int(refusals.get(reason, 0)) + 1

func _forget(reason: String) -> void:
	_holding = false
	_node = null
	_actor_id = -1
	_identity = ""
	_model = ""
	if not reason.is_empty():
		releases[reason] = int(releases.get(reason, 0)) + 1

## Diagnostics (main.gd `client_diagnostic_snapshot`, `local_avatar_hold`).
## Counts and times only: the release log records no player data, so the
## held character's actor id stays out of it.
func snapshot(now: int = -1) -> Dictionary:
	var at := Time.get_ticks_msec() if now < 0 else now
	return {"held": _holding,
		"heldForMsec": (at - _held_at) if _holding else 0,
		"holds": holds, "adoptions": adoptions, "lastWaitMsec": last_wait_msec,
		"releases": releases.duplicate(), "refusals": refusals.duplicate()}
