# Human NPC faces

Named Human NPCs use individual identities from the updated 36-face library.
The current selection covers 92 names and 94 name/type combinations, including
the Landfall town cast, regional services, quest workers and the rescue family.
NPCs of the other Eloria peoples retain their existing models and appearances.

At High graphics, the head uses the selected identity's complete controls,
including shapes that the player sliders cannot express exactly. Low and
Medium keep the existing native heads, with the corresponding supported face
controls. This selection follows the normal renderer, distance and quality
policy; it does not force detailed heads onto lower settings.

Wardrobe dyes, skin and eye colours, equipment, body proportions and gameplay
state remain the existing character's choices. A few previously unstyled NPCs
receive a named hairstyle while retaining the incoming hair colour. Cosmetic
skin-age and greying amounts distinguish seasoned characters. The rescue
daughter retains her existing child scale, with both aging amounts at zero.

## Authoring

`godot-client/data/actors/npc_human_faces.json` selects a face for each exact
NPC name and actor type. Each name holds a list because a recurring character
can have different wire IDs in older tutorial scenes. `wireNames` records the
server's shortened 29-byte display spelling for longer names.

The profile's `archetype` refers to
`godot-client/data/actors/rl_head_archetypes.json` and its matching entry in
`rl_head_presets.json`. Keep its `model` consistent with that head's sex and the
character's existing full outfit. `skin_age` and `hair_grey` are cosmetic amounts
from 0 to 100, not ages in years. Optional `hairStyle` selects an existing native
style; it does not copy the archetype's colour or garment choices.

`NpcCharacterLooks.face` requires NPC kind, name and actor type to agree. The
presentation pass adds head fields to a separate appearance dictionary. It
never edits replicated actor state or player records. Existing named outfit
selections continue to take precedence over shared generic model IDs.

The presentation-only `npc_face` key preserves the exact High identity while
the ordinary appearance fields provide the native fallback. It is not a new
network field, player customization option or laboratory `rl_head` override.
Head, body, hair and animation files remain the currently shipped assets.

Enhanced NPC packets preserve full names containing spaces. Only player names
use an uncoloured trailing word as a guild-tag fallback; coloured player tags
continue to use their existing marker. This keeps the family and gathering
crew identities intact through normal packet decoding.

## Checks

`tests/test_npc_human_faces.py` checks profile coverage, head/body compatibility
and unambiguous wire identities. `tests/test_npc_human_faces.gd` exercises Main's
production selection, exact face controls, wardrobe/state isolation and the
enhanced NPC name decoder. Existing NPC, rescue and protocol checks remain
applicable.

`tests/integration/npc_human_face_review.gd` builds the real actors at High,
checks their outfits, captures front views and representative side/walking
views, then checks switching down to both native tiers. Set
`ELORIA_NPC_FACE_INPUTS` to an ignored JSON file keyed by lowercase name plus
`:<actor type>`. Each value is a DTO or an actual server spawn's
`{opcode, payload}` hex record. `ELORIA_NPC_FACE_REVIEW` selects the private
capture directory, and `ELORIA_NPC_FACE_NAMES` optionally limits the cast.
Keep screenshots, source audits and native packet inputs in ignored task
storage.
