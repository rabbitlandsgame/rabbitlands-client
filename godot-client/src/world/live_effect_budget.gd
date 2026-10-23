extends RefCounted
## How many short-lived combat visuals may be alive at once. A big fight sends
## a spell, an arrow or a number for every exchange of every fighter in view,
## and each one is nodes, particles and a material for a second or two: at a
## hundred fighters the client drew several hundred at once and fell to 17 FPS,
## at five hundred it passed four thousand and stopped presenting at all.
##
## The fight is unchanged - every hit, miss and death still arrives and is
## applied - only how many of its visuals are drawn at once is bounded. What
## involves the player, their target or their selection is always drawn, over
## the limit if it has to be; the rest is drawn while there is room and simply
## skipped while there is not. Nothing already drawn is cut short.

## Live visuals of each kind before the rest are skipped. `spell` is spells,
## impacts, bursts and portal flashes (WorldEffect3D), `missile` arrows and
## bolts, `technique` melee technique visuals, `number` floating health changes.
const LIMITS := {&"spell": 48, &"missile": 48, &"technique": 32, &"number": 24}

var enabled := true
var quality := 2
var _live: Dictionary = {}
var _skipped: Dictionary = {}
var _admitted: Dictionary = {}

## Whether a new visual of `kind` may be drawn. `priority` visuals always may.
func admit(kind: StringName, priority: bool) -> bool:
	if priority or not enabled or live(kind) < limit(kind):
		_admitted[kind] = int(_admitted.get(kind, 0)) + 1
		return true
	_skipped[kind] = int(_skipped.get(kind, 0)) + 1
	return false

func limit(kind: StringName) -> int:
	var scale: float = [0.5, 0.75, 1.0][clampi(quality, 0, 2)]
	return maxi(1, int(int(LIMITS.get(kind, 1 << 30)) * scale))

## Counts `node` as live until it leaves the tree.
func track(node: Node, kind: StringName) -> void:
	if node == null:
		return
	_live[kind] = live(kind) + 1
	node.tree_exited.connect(_release.bind(kind), CONNECT_ONE_SHOT)

func _release(kind: StringName) -> void:
	_live[kind] = maxi(0, live(kind) - 1)

func live(kind: StringName) -> int:
	return int(_live.get(kind, 0))

func describe() -> Dictionary:
	var limits := {}
	for kind: StringName in LIMITS:
		limits[kind] = limit(kind)
	return {"enabled": enabled, "limits": limits, "live": _live.duplicate(),
		"admitted": _admitted.duplicate(), "skipped": _skipped.duplicate()}
