# Style and 3D-input contract

## Eloria / Oldcraft visual language

- Stylized fantasy with broad, chunky, low-frequency forms.
- Strong silhouette and exaggerated but internally consistent proportions.
- Hand-painted, matte color treatment with restrained highlights and readable material grouping.
- Simplified planes and purposeful detail rather than photorealism, microtexture, or procedural noise.
- Warm, storybook color relationships with enough value separation to read during gameplay.
- Personality comes from shape language, posture, and proportion—not from busy accessories.

This is a direction, not permission to copy a reference asset. Preserve the requested Eloria identity and use references to calibrate rendering, proportion, and detail density.

## Exploration versus faithful recreation

- In **exploration**, style and shape-language cues may deliberately produce alternatives. Change one or two decisions per variant so results can be compared.
- In **faithful recreation**, lead with the accepted design and explicitly preserve silhouette, proportions, palette, outfit structure, anatomy, and signature features. Heavy style keywords can override identity; use only the minimum Eloria style direction needed.
- Prefer one or two strong signature features over many small accessories. When a design becomes noisy, simplify secondary detail before weakening the primary silhouette.
- A 60/30/10 palette split can clarify dominant, secondary, and accent regions, but use it as a prompt aid rather than a mandatory formula.

## Camera modes

- **Strict-front master:** dead-front orthographic-like camera, equal left/right exposure, no body twist, no contrapposto, A-pose for humanoids. Required for modular parts and fitting references.
- **Single-image volume view:** restrained front three-quarter view with limited perspective. Useful for simple whole-object Image-to-3D when it exposes depth without hiding appendages.
- **Support views:** exact side and back projections generated after the master. Preserve identity and pose; reject halfway three-quarter drift.
- **Hero illustration:** valid for marketing or mood only. Never substitute it for production reference without generating a neutral modeling view.

## Construction rules by body plan

- **Humanoid:** use a strict-front neutral A-pose for modular/reference-pack work; hands visible and separated from hips, legs separated, face forward, palms consistently oriented, and hair, capes, and garments clear of important joints.
- **Quadruped:** standing neutral; all four feet visible or clearly inferable; legs do not overlap; tail attachment and underside are readable.
- **Flyer:** wings relaxed enough to fit the image but separated from the torso; shoulder roots, membrane/feather span, legs, and tail remain visible.
- **Serpent or aquatic:** straight or gently curved neutral body; clear head-to-tail centerline; fins and tentacles separated; never invent legs.
- **Multi-limbed or unusual anatomy:** explicitly state exact appendage counts and attachment locations. Favor a view that proves them.
- **Wearable/equipment:** isolate the object; show openings, straps, thickness, and how it attaches. Avoid posing it on a body unless fit is the decision being communicated.

## Negative constraints

Exclude cinematic action, extreme foreshortening, motion blur, depth-of-field blur, harsh rim light, transparent/glass anatomy, complex scenery, floor plinths, contact shadows that hide feet, labels, typography, borders, collages, duplicate subjects, detached floating decorations, and anatomy hidden behind effects.

## Review questions

1. Could a modeler count every major appendage from this image?
2. Are front/back and left/right relationships clear enough to resolve unseen surfaces conservatively?
3. Can each joint deform without intersecting neighboring geometry?
4. Are thin parts thick enough to survive meshing, skinning, and gameplay distance?
5. Does the palette separate skin, cloth, leather, metal, fur, feather, horn, and magic where relevant?
6. Does the design still read without the background and lighting?

If any answer is no, revise the concept before model generation.

For orthographic packs, also verify equal shoulder/hip widths in the front view, exact side or back orientation in support views, consistent equipment placement, and unchanged color/material boundaries. Inspect every accepted image rather than trusting the prompt.
