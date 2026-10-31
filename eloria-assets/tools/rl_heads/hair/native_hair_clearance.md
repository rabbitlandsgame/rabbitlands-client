# Native Human bind-space contact guard

`NativeHeadSurface.from_current_head(head)` loads the exact native body named
by the current RL head's body-cut receipt, verifies its SHA, and retains only
the native upper-head body triangles and scalp. Every primitive is scoped by
its own used triangle indices. Unexpected node transforms fail closed.

`push_out(P, margin=0.0028, max_shift_mm=14)` corrects contacting vertices only,
with a strict displacement limit and an explicit before/after clearance
receipt. Already-clear points remain exact. It does not smooth or expand the
whole exterior, touch UVs/paint/topology, or update a source file. Normals and
geometry at changed areas still need the owning builder's visual review.

This is a conservative closest-normal check on unposed native bind geometry.
Actual native face controls, body proportions, Idle/Walk poses and Low/Medium
actors need separate client evidence. It does not authorize a `native_head`
runtime capability, replace the RL head's identity/coverage gate, or qualify a
hairstyle by itself. Preserve failures and use only an optional new-profile
authoring hook until both head representations pass.
