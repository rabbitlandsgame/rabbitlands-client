# Cape motion

The accepted cape keeps the neck and shoulder attachment in place, follows a closer idle profile, and restores the fuller walk/run billow. The user approved both reference outfits and all five review videos on 2026-10-31. Exact source and review-media hashes are recorded in the [authoring approval receipt](approved-authoring-2026-10-31.json).

Runtime integration is **qualified** against the final fit and motion data. The [integration receipt](runtime-integration.json) links the frozen payload hashes to the [runtime qualification results](runtime-qualification-2026-10-31.json). Develop publication and primary-checkout import maintenance are recorded separately by the integration owner.

## Source and delivery

- [Portable approved sources](../../../eloria-assets/source/capes/approved-v100/source-catalog.json) bind the two fitted meshes and source motion to the accepted hashes.
- [Reproducible preparation tool](../../../eloria-assets/tools/prepare_approved_cape_motion.py) prepares the runtime fit and motion data.
- [Runtime catalogue](../../../godot-client/data/actors/cape_motion/catalog.json) identifies `wardrobe-fit.bin`, `armour-fit.bin` and `motion.bin`.

The reference outfits use `luminous_male` with the Gray Cape. The armour review uses Bark Jerkin, Bark Legguards, Warded Boots, sword and shield; the other review uses the default wardrobe. The delivery extends the shared cape geometry across its 39 styles and 16 canonical rigs while preserving native Base/Trim/Detail materials, tints and emblems. Rig-rest compatibility and visual clearance for every equipment combination remain separate checks.

## Runtime contract

The adapter drives the twelve existing cape bones and retains the 65 body bones, body rest, skin and original body clips. Fitted cape skins retain up to eight influences, including the body-owned neckline. Offline cloth is an authoring reference; the delivered motion uses bones.

Steady locomotion uses closed, phase-averaged loops mapped to the actual body clip's seconds and playback rate. Intrinsic attack motion excludes the review episode's incoming run history; transitions carry the actor's actual outgoing cape state. This preserves the accepted shape and motion character without claiming exact playback of every three-second authoring episode at every native phase.

Body and equipment collision guards apply outside the complete reviewed reference kit, including weapon/shield and cross-profile changes. Unsupported and native cinematic clips use the bridged legacy Verlet writer on the approved fit. Mounted actors use the original legacy geometry, skin and solver; approved geometry returns on dismount or failed mount setup. Inactive quality and crowd tiers hold the approved idle cheaply.

## Qualification

The installed actor suite passed 1362 checks across eight reference cases covering male/female bodies, Luminous/Human heads and both outfits. It checks body-rest ownership, attachment, material/weight preservation, body-clip timing, loop boundaries, transitions, guards and fallback roundtrips. All 16 canonical rigs have compatible native global rests. The mounted regression suite passed all 47 checks using the legacy mounted geometry and solver.

Actual native idle geometry agrees with the independently evaluated v100 source within 0.131 mm without armour and 0.110 mm with armour, including native vertex and weight packing. Eight native graphics captures cover idle/run, side/quarter views and both fits without script, resource or rendering errors. Modifier-only debug timings and capture hashes are in the qualification results.

The reviewed free panel had no skin, leg or boot intersections; small upper-back garment seam contacts remain in the authoring reference. These checks do not certify every equipment combination as collision-free. The old manual idle and frozen-reference suites also contain baseline failures: baseline replay reproduces eight after-walk idle failures and 4216 obsolete golden-reference mismatches, while direct current-versus-baseline legacy solver parity passes. Their references were preserved.
