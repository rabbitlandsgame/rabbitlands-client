# Creature animation contract

Every standard creature delivery contains exactly these seven base clips unless a documented asset profile adds a deliberate supplement:

| Clip | Playback | Intent |
| --- | --- | --- |
| `Idle_A` | loop | neutral breathing or body-specific idle |
| `Fighting_Idle` | loop | alert combat-ready idle |
| `Walk` | loop | body-specific slow locomotion |
| `Jog` | loop | body-specific fast locomotion |
| `Sword_Attack` | one-shot | shared primary-attack slot; never implies a sword |
| `Hit_Chest` | one-shot | readable hit reaction |
| `Death_A` | one-shot, hold end | complete death/fall response |

`Walk` and `Jog` mean the appropriate locomotion for the body: walking, hopping, swimming, slithering, crawling, or hovering. Add `Fly` only for a deliberate flight-capable profile. Dedicated takeoff and landing are separate work, not implied by `Fly`.

The seven clips are Eloria's base compatibility contract. Do not import another project's default turn, strafe, or flavor clips. Add turns, strafes, takeoff/landing, casting, or other actions only when Eloria's current actor/controller data requires them, then document their events and mappings separately.

## Motion rules

- Existing creature batches face `-Y` with `+Z` up; verify each source rather than assuming.
- Keep loop locomotion in place. No accumulated root translation or yaw.
- The planted contact point must move backward relative to the body during the stance phase. A foot moving forward while planted is a common sliding failure.
- Feet/paws remain flat enough for the anatomy and meet the authored floor without penetration or hovering.
- Attack motion must read from anticipation through impact and recovery while support contacts remain credible.
- Define attack release/contact and recovery in seconds and frames. Count time intervals, not the number of included samples: `duration = (last_frame - first_frame) / fps`. Preserve the contact fraction when uniformly retiming an approved action.
- `Sword_Attack` must use the creature's anatomy; do not add a sword.
- Death ends in a stable pose suitable for a held final frame.
- Faces, hands, horns, hair, feathers, cloth, wing panels, and detached rigid pieces remain attached to the correct control throughout every clip.

## Gameplay readability and polish

- Judge important poses at normal speed from the intended gameplay camera and unit size. Close-ups diagnose deformation but do not prove gameplay readability.
- Establish preparation, release/contact, and recovery before secondary motion. The attacking limb and direction must separate clearly from the body silhouette.
- Keep grounded contacts and rigid attachments stable. Add delayed tail, hair, cloth, or flexible-appendage response only when it supports the leading mass.
- Overshoot must not cross the target before the authoritative contact event. Hitstop is a separate engine decision, not hidden extra time inside the animation.
- Keep recovery short enough for the intended interruption/chaining rules. Corpse lifetime belongs to gameplay, not the `Death_A` clip.
- Preserve a baseline and compare candidate revisions with the same camera, scale, duration, and playback speed.

## Sampling and reduction

Bake at 24 keys per second as the standard delivery representation, but sample more densely during solving and validation when needed. Reduce curves using measured error; a useful starting tolerance is approximately 0.5 degrees rotation and 2 mm translation, adjusted for scale and silhouette. Always evaluate original keys and between-key midpoints after reduction.

Do not apply historical speed-up factors a second time to already revised assets. Read the asset's animation profile and revision report before changing timing.
