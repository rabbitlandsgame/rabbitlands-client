# Cape fitting sources

`approved-v100/` is the portable, approved on-foot fit and motion source. The
mounted driver uses those same surfaces, materials, UVs, topology and eight
weight slots. It writes the existing twelve cape bones; it does not replace
body animations or modify the sixty-five body bones.

Mounted presentation adds a separate attachment adapter and material/contact
projection in `godot-client/src/actors/cape_mounted_*.gd`. The adapter rebases a
mounted-only mesh and Skin from a deterministic canonical reference. This keeps
the reference rendered fit while separating torso support from neck motion.
The spine slot retains its torso support and the other four body slots follow
the neck. All three cape roots use a reference-normalized half blend of those
supports. Sharing support across the yoke keeps the nape with
the wearer while limiting shoulder shear.
A smooth mounted-only shoulder adjustment adds 8 mm posterior clearance to the
wardrobe fit, and 20 mm posterior plus 20 mm upward clearance to the armour fit.
The adjustment leaves the central neckline and lower panel in their approved
reference positions. The adapter reports the exact
reference rebase and this deliberate adjustment separately; normals and tangents
follow the adjustment's analytic derivatives.
The original mesh and Skin references are restored on dismount. The frozen
on-foot catalog's mounted-state description records its original delivery;
the mounted implementation is qualified separately.

`mounted-fit-contexts.json` and the generated runtime
`mounted-support-edges.json` record the initial material-edge ordering recipe
and its limits. The runtime checks the approved fit hash and vertex indices
before using them, then includes movable source edges above 5 mm throughout
the panel. Original approved material lengths remain the strain denominator;
rebasing the mesh does not redefine the cloth's length. Three root controls
follow anatomical support and nine lower controls provide drape and flow.
Animated mount envelopes and the actual skinned torso's posterior surface
supply contact constraints. Triangle-interior samples average the actual
rendered corner positions and weights separately, preserving the skin's
position/weight cross terms. Every sufficiently movable triangle contributes
an interior sample, regardless of its original height. Contact samples also
cover the one-third and two-third points of source edges longer than 6 cm;
edges longer than 12 cm also include their quarter points and midpoint.
These use the same exact rendered-corner arithmetic. Clear posterior body
planes remain unilateral barriers, and newly penetrating samples activate
after material correction. When a point reaches a different body region, a
clear inactive plane with no stored correction is replaced by the newly
penetrated surface plane. The next checked sweep clears the current surface
instead of exhausting the iteration budget against stale support. The script
fallback follows the same contact policy. The internal source-edge target is 1.79; independent
posed-mesh checks retain the 1.8 acceptance limit. Near-immovable edges retain
the solver's numerical cutoff and are still included in the independent audit.
After the first two ordinary sweeps, a source-limited pose also revisits the
last measured worst material edge with its retained metric correction. Full
contact and source-edge checks follow the extra visit. This changes scheduling
within the same projection objective, rather than discarding corrections or
relaxing fit/clearance limits. The script fallback uses the same ordering.
The convergence target is a 6 mm residual against the body's 8 mm posterior
guard. This retains 2 mm outside the sampled body surface without spending the full
iteration budget on an unnecessary additional gap. Independent physical checks
retain their 6 mm tolerance; they measure finite surfaces separately from the
conservative posterior envelope.
The wardrobe defensive cast turns the left shoulder control by up to 34 degrees
about its clasp as the upper-body action blends in. Bow actions use an 18 degree
turn with the continuous grip blend through draw, hold and release. Direct
action changes carry the outgoing turn through the body's captured pose blend.
These clear the folded shoulder without moving the clasp or editing the
character's body animation.

The optional client runtime extension accelerates body-surface sampling and
material projection with the same arithmetic. Its descriptor and library
checksums are verified before loading. Missing or incompatible payloads use
the complete script implementation. `RABBITLANDS_CAPE_MATH=gdscript` explicitly
selects that implementation without changing other runtime modes.
Exact per-batch query caches and persistent numeric workers accelerate frozen
contact queries, exact residual skin points and finite strain maxima. Body
sampling retains its sorted coarse candidates and uses bounded, conservative
fine buckets in dense cells; posed world normals are cached per triangle.
These arithmetic optimizations preserve the reference results. Workers read immutable numeric surfaces after ownership is
validated; the owning thread retains all scene, bone and sequential projection
writes. The pool reserves two logical cores, uses at most six workers, falls
back to the owning thread on small machines, and joins on extension shutdown.

At reduced animation quality, the driver fits a conservative seated pose when
its context changes, then applies the twelve held controls with gradual lower
carry and current shoulder support. It resumes simulation from that held pose
when the quality budget allows it. Quality transitions ramp their target drape
before contact projection; only valid fits replace the displayed held pose.
Universal body-animation defaults omit cape helpers so they cannot overwrite
the cape owner's held pose. Reusable geometry and metric data are cached;
per-character motion histories remain separate.

Rabbit and Lantern Stag profiles blend mount gait changes over 180 ms before
sampling the saddle, rider and cape. Their collision surfaces therefore follow
the same visible transition. Other mount profiles keep their existing timing.

Reproduce the support data with NumPy:

```powershell
python eloria-assets/tools/prepare_mounted_cape_support_edges.py --check
```

The sparse edge certificate is sampled coverage, not a clearance proof. Native
runtime checks in `godot-client/tests/test_mounted_approved_cape.gd` cover actual
equipment, mounting, dismounting, supported upper-body actions and all mount
profiles. The manual `godot-client/tests/test_mounted_cape_native_math.gd`
regression compares reference and parallel residual arithmetic byte for byte
through gaits and upper actions, including rejected-batch history checks.
It reports an explicit skip without a compatible optional payload;
`RL_MOUNT_REQUIRE_NATIVE=1` requires that payload and its current capabilities.
Local review videos and full-resolution skin witnesses belong in ignored
authoring output, not in the source package.
