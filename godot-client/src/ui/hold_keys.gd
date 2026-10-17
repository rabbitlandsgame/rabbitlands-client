extends RefCounted
## Held keys that open a ring (the spell ring, the technique ring) are input
## actions like every other key, so they can be rebound and saved in keys.ini.
## A ring watches the press and the release itself, so it asks whether an
## event is its key rather than using `is_action_pressed`: that would also
## match the key with modifiers held, and Left Shift must not be Right Shift.

## Whether this key event is the key bound to `action`, ignoring modifiers.
static func matches(action: String, event: InputEvent) -> bool:
	if not event is InputEventKey or not InputMap.has_action(action):
		return false
	var key := event as InputEventKey
	var code := key.physical_keycode if key.physical_keycode != 0 else key.keycode
	for bound: InputEvent in InputMap.action_get_events(action):
		if not bound is InputEventKey:
			continue
		var wanted := bound as InputEventKey
		var wanted_code := wanted.physical_keycode if wanted.physical_keycode != 0 else wanted.keycode
		if wanted_code == code and (wanted.location == KEY_LOCATION_UNSPECIFIED
				or wanted.location == key.location):
			return true
	return false
