# Optional rigid Native pose queries

`RigidNativePoseUnion(manifest, sex, case_names=None, quality=0,
carrier_bone='Head', horizontal_slice_proof=False)` supplies exact authoring
constraints for a hair part carried rigidly by one evaluated bone. Callers must
verify that skinning contract; this is not an adapter for a part influenced by
multiple bones or simulated joints.

`signed(bind_points)` carries points through each fixture's recorded bone
transform, queries the complete fixture in its original world coordinates,
then returns minimum signed distances and the matching closest points/normals
in bind coordinates. It retains the fixture's original outside-proof axes.
Nonrigid or reflected carriers, absent requested poses and High identity
weights fail closed. The optional horizontal proof is forwarded explicitly;
no existing authoring or runtime default changes.

Explicit `case_names` can select `neutral` plus the four `idle-*` and four
`walk-*` samples for lower-curtain fitting. Omit the selection to include every
matching case. The `source` receipt contains fixture/carrier hashes and pose
labels, without private filesystem paths.

This performs no fitting and makes no qualification claim. Keep the separate
full Native traversal, High controls, coverage, actual poses and appearance
checks after authoring. Existing 14 mm exterior bounds remain the caller's
constraint; this tool does not change them.
