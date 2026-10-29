# Continent road surfaces

The 17 served continent-v2 exterior territories draw ordinary roads in existing
ground materials at four coverage pixels per metre. Saved authoring controls
remain intact. Published chunks omit ordinary road meshes and collision faces;
bridges and other structural walks retain their geometry and materials.

Each affected leaf declares `roadGround`: schema
`rabbitlands-road-terrain-blend-v1`, local `roads.json`, its SHA256 and resolution.
Metadata names retained ground targets, the source frame, road styles, coverage
mips, a triangle ID grid and a compact affine coefficient table. Its `resources`
map hashes every field and shared style image. The affine table reconstructs
authored texture coordinates and gradients instead of baking road colour into
a new continent-wide albedo image.

The loader verifies and decodes fields before cache lookup. Background work owns
private resources; main publication revalidates them and binds materials. Native
geometry snapshots omit per-load bindings. Live look changes reuse retained
fields. Ground patches preserve their alpha contract; roads add no visual node
or material pass. Terrain footsteps and grass query the same coverage and style;
bridge hits keep the bridge's surface classification. Missing or changed required
fields fail loading and packaging. Legacy maps without `roadGround` are unchanged.

## Runtime shader reuse

Road composition shares immutable shader programs and uniform layouts across
chunks with identical base headers, road shaders, surface/paint sources and look
mode. Lookup happens before source rewriting and shader reflection. The cache
holds at most 64 weak entries; active materials and seasonal replacements retain
their programs for their existing lifetime. Each chunk still owns its materials,
texture bindings, colours and field parameters. Shared shader identity also lets
the existing seasonal shader cache reuse its work across those chunks.

`ELORIA_ROAD_SHADER_CACHE=0` reconstructs the same shader bytes through the
uncached path for matched measurements. Compare fresh processes with the same
content, renderer, texture tier and preparation. OS and driver caches remain
uncontrolled. This reuse changes no saved geometry, field data or cache format.

## Publishing

Publish a complete territory through the normal continent-v2 authoring publisher.
`publish_finish.py` bakes roads after image, precision and exact-vertex processing,
promotes portable fields, then restates geometry and field memory figures. Mixed
partial publication with new ribbons beside stripped chunks is rejected: overlap
and gutters require the complete original territory. Re-finishing unchanged,
fully converted territories verifies their fields and leaves them intact.

Stages and recovery inputs belong in ignored `client/.local/` and
`.local/road-ground-recovery/` folders, excluded from package walks. Keep the saved
road controls. Rebuild collision, crossings and server publication in the normal
continent publication order. The exporter declares `terrain-road-surface-v1`:
ordinary roads use terrain floors; bridges retain authored walk faces. Parent
collision blocks and regional collision receipts travel with their grids. Keep
leaf collision declarations lightweight; never copy parent binaries, hashes or
export statistics into them.

Regenerate both regional map images. The cartography reader renders verified
fields on retained ground and depth-tests water, props and bridges. Its source
digest includes the road closure; changing a fingerprint alone does not qualify
an old image. Geometry-cache policy 2 and scene-cache format 9 invalidate older
snapshots; see [geometry cache preparation](client-map-geometry-cache.md).

## Costs and limits

The conversion removes 434 ordinary road meshes from 287 of 1,276 exterior chunks.
All 220 retained walk nodes, including 33 authored bridges, match their previous
expanded attributes, materials and transforms. Fields occupy about 30 MB. Leaf
packages are about 62 MB smaller than the consolidated geometry version, before
map-image changes. Shared style images are reused.

For those 287 changed leaf packages, ZIP level 6 shrinks from 81.93 MB to
78.99 MB: about 2.95 MB saved in transfer versus 62.13 MB in loose file bytes.
The format adds 3,230 small files; installer copy and filesystem overhead are
separate from the byte counts above.

Coverage samples are 25 cm apart, so close road edges can differ slightly.
Ordinary collision loses the former 5.5 cm lift and follows terrain; retained
ground artwork sits about 6 mm above it. Five server tiles close at existing
steep ground or solid intersections, without disconnecting additional areas.
Spawn, harvest, NPC, ferry, boat and crossing approaches pass; all 15,820 portal
rows remain unchanged.

Hashing, decoding and sampling add work and memory. Streaming estimates include
decoded CPU/GPU field costs separately from shared images and prototypes. The
current shader supports up to two styles per chunk sharing image contents and
samplers. Incompatible new content fails explicitly and needs a format/shader
extension.

Eight foreground Suncoil component runs used two chunks and matching camera
routes. GPU medians were about 0.48 ms for fields versus 0.69 ms for consolidated
ribbons. The final isolated pair rendered about 514,000 versus 744,000 primitives.
Frame-time tails varied; this is a scene measurement, not a whole-game FPS
guarantee. Qualification covered all three looks, OpenGL compatibility, actual
grass and consumption of prepared native geometry. Captures, profiles, timing
records and recoveries stay in ignored local evidence folders.
