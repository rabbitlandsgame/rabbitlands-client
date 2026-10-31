# Rounded reference-guided crest

`prepare_rounded_crest.py --output <new ignored stage> [--sex female|male]`
prepares the upper locks from `styles/feathered_mohawk.json`. The profile pins
approved cap and reference hashes. Configure the normal RL head-authoring
inputs through `paths.py`; no private source paths are embedded in the tool.

The new locks use round tapered sections and continuous root-to-tip charts,
with denser sections beside the actual cap. Length and volume use the existing
four grooming targets. Fine/messy locks use the existing vertex-alpha detail
contract. All three LODs inherit the cap skin, head identity target names and
separate Native-fit target. The reviewed cap primitives and binary prefix are
preserved exactly. The crest uses the explicit `rl_hair_clump_crest` material
role so its fibres have a separate texture while cap paint stays unchanged.

Output is an unregistered authoring candidate, not a qualified shipping asset.
`add_rounded_crest_base.py --source <upper stage> --output <new stage>`
authors the continuous lower third, preserving all surviving upper attributes
and targets. The far LOD exchanges subpixel fine locks for that dense base
within the same triangle budget. Contact-only fitting is a separate stage.
Keep their inputs and receipts private. Require independent High identity and
groom checks, actual Native controls/poses, unchanged scalp coverage, client
materials, movement and headwear checks before registration. A hash match or
vertex-only fit does not replace triangle-interior or visual checks.

`conform_crest_base_normals.py --source <fitted stage> --output <new stage>`
is an optional shading-only step for the exposed front of this lower mass.
It blends that range's authored normals toward the actual opaque cap and
transports all corresponding target normals. The cap and upper locks stay
exact, as do every POSITION/index/UV/coverage/skin/target POSITION value.
Reject the result unless matched front/profile views improve. Keep the
original fitted stage and the normal/payload preservation receipt.
