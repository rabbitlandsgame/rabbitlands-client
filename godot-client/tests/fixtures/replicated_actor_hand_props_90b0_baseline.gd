extends "res://src/actors/replicated_actor_3d.gd"
## Frozen hand-prop visibility boundary from production commit
## 66f575ffe14f23153caa4920b2bfb47ccbc4f219. The actor, equipment loading and
## presentation remain current; only this accessor retains the pre-cache body.

func set_hand_props_visible(enabled: bool) -> void:
	for part: int in [0, 1]:
		for prop: Node in _equipment_nodes.get(part, []):
			if is_instance_valid(prop) and prop is Node3D:
				# Native bow variants are replaced by the string-driven bow in the left hand.
				var weapon := _equipment_model_config(0, int(_equipment_visuals.get(0, 0)))
				(prop as Node3D).visible = enabled and not (part == 0 and weapon.has("rangedAnimationScene"))

# END FROZEN METHOD
