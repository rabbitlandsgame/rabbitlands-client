class_name ActorReducer
extends RefCounted

static func apply_command(actor: Dictionary, actor_command: int) -> Dictionary:
	# A shallow copy. Only top-level keys change here, and nothing writes into
	# the nested appearance and equipment dictionaries in place - every writer
	# replaces them - so sharing them is safe and skips a deep copy per command.
	var next: Dictionary = actor.duplicate(false)
	var step: Vector2i = EloriaProtocol.actor_command_step(actor_command)
	next["x"] = int(next.get("x", 0)) + step.x
	next["y"] = int(next.get("y", 0)) + step.y
	next["command"] = actor_command
	next["command_sequence"] = int(actor.get("command_sequence", 0)) + 1
	# The last command that named a direction, kept apart from the last command
	# of any kind. A frame's packets are reduced to one state before anything
	# renders it, so a turn followed by the swing it was made for - which is
	# every round of every creature fight - left "command" holding the swing,
	# and the facing the turn carried was gone before it was ever read.
	if EloriaProtocol.actor_command_direction(actor_command) != Vector2i.ZERO:
		next["facing_command"] = actor_command
	if actor_command == 13:
		next["sitting"] = true
	elif actor_command == 14:
		next["sitting"] = false
	elif actor_command == 18:
		next["in_combat"] = true
	elif actor_command == 19:
		next["in_combat"] = false
	elif actor_command == 3:
		next["alive"] = false
		next["health"] = 0
	return next
