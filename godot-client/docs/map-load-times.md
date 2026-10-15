# Map load times

What a region costs to load, phase by phase, what was done about it, and what
is left. Companion to `runtime-performance.md`, which covers the frame rather
than the load.

The client loads a region by handing Godot's runtime glTF importer an absolute
path to a 19-33 MB `world.glb`, then walking the result: material passes,
declared collision, walk surfaces, navigation polygons and static batching.
`WorldLoader.load_world()` does all of it on the main thread, so a load is a
freeze, and the freeze was up to eight seconds.

## Measuring

`WorldLoader` times its own steps into `load_phases`, a microsecond per phase
in the order it runs them. `tests/integration/map_load_phases.gd` reads that
over every region and writes the table below as JSON:

```
Godot --headless --path . --script res://tests/integration/map_load_phases.gd
```

`ELORIA_PHASE_REGIONS` picks regions, `ELORIA_PHASE_REPEATS` sets how many
loads the median is taken over (3 by default), `ELORIA_ARTIFACT_DIR` says where
the JSON goes.

Three traps, all of which cost time here before they were understood:

* **Headless frames are padded** to `OS.low_processor_usage_mode_sleep_usec`,
  6.9 ms by default, because no window can draw. Every script in this file
  sets it to 1 and `Engine.max_fps` to 0. `sunmane_performance.gd` still
  reports 6.90 ms a frame for exactly this reason; its frame column is not a
  measurement.
* **This machine is shared** with about a dozen other agent sessions. A single
  load's wall time moves by a tenth either way, and the glTF parse column below
  moved 15% between two runs of the same code. Everything here is a median of
  three, and a difference under 10% is not a difference.
* **`GLTFState.HANDLE_BINARY_DISCARD_TEXTURES` does not skip decoding.** It
  drops the texture after Godot has decoded the image, so parsing with it is
  within noise of parsing without it, and it cannot be used to price the
  embedded PNGs. Pulling the image buffers out of the container and decoding
  them by hand can, and does: see the texture row in the options table.

## Where a load went

Median of three loads per region, headless, milliseconds, before this pass.
`manifest` is reading and validating `world.json`; `parse` is
`GLTFDocument.append_from_file`; `mipmaps` is the mip chain the loader rebuilds
over the imported images; `generateScene` is Godot's own scene builder;
`attach` is `add_child`; `index` is the single walk of the import; the rest are
the loader's own passes.

| region | manifest | parse | mipmaps | generateScene | attach | index | materials | collision | walkSurfaces | batching | **total** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| four_gates | 21.7 | 403.8 | 61.3 | 127.3 | 8.3 | 3.8 | 4.3 | 5.0 | 300.1 | 31.5 | **970** |
| mirrorhold | 27.9 | 405.7 | 47.7 | 173.4 | 11.6 | 3.7 | 2.1 | 64.3 | 495.2 | 19.4 | **1 263** |
| crownwater | 29.4 | 453.4 | 46.9 | 98.9 | 12.0 | 3.0 | 1.1 | 11.8 | 514.4 | 10.0 | **1 158** |
| whitehorn_range | 26.5 | 333.9 | 31.3 | 139.5 | 16.5 | 6.6 | 3.6 | 28.1 | 501.9 | 33.6 | **1 119** |
| amethyst_barrens | 28.3 | 309.4 | 31.1 | 79.6 | 4.7 | 1.5 | 1.0 | 14.5 | 465.2 | 14.3 | **955** |
| sunmane_steppe | 25.0 | 170.0 | 15.7 | 90.0 | 6.0 | 1.2 | 1.2 | 72.8 | 131.8 | 7.7 | **528** |
| amberwood | 25.3 | 434.9 | 46.3 | 3 437.8 | 17.7 | 11.7 | 8.5 | 229.6 | 428.4 | 39.9 | **4 675** |
| grey_moors | 18.4 | 420.4 | 46.6 | 2 220.1 | 18.8 | 9.3 | 5.8 | 88.1 | 492.6 | 29.2 | **3 348** |
| westhaven | 18.2 | 393.4 | 47.2 | 188.0 | 9.2 | 5.1 | 3.0 | 82.5 | 443.6 | 24.3 | **1 215** |
| verdant_stair | 24.6 | 620.4 | 46.7 | 6 144.5 | 34.1 | 23.1 | 12.6 | 13.2 | 705.6 | 60.1 | **7 926** |
| ssarathi_ruins | 23.7 | 496.1 | 61.4 | 202.4 | 12.5 | 11.5 | 5.5 | 6.7 | 669.7 | 41.3 | **1 545** |
| manymouth_delta | 27.3 | 652.3 | 55.9 | 1 845.3 | 19.8 | 18.6 | 10.0 | 7.6 | 739.6 | 66.6 | **3 405** |
| **twelve regions** | **296** | **5 094** | **538** | **14 747** | **171** | **99** | **59** | **624** | **5 888** | **378** | **28 106** |

Navigation polygons are 0.7 ms across all twelve: no shipped region declares
any, and the walk surfaces do that job.

The first frame drawn with the region in the tree is 3-8 ms, so texture upload
and the initial cull are not where the load is. Reading the glb off disk into a
buffer is 15-36 ms, so neither is I/O; the page cache is warm on every run here
and a cold first read on a slow disk is not measured.

And what a region is made of. `widest` is the largest sibling list in the
built tree, which turns out to be the column that matters:

| region | glb MB | nodes | mesh nodes | widest | batches | bodies | images | decoded MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| four_gates | 23.2 | 4 255 | 3 028 | 1 276 | 241 | 456 | 95 | 60.0 |
| mirrorhold | 21.4 | 2 838 | 2 342 | 1 736 | 63 | 137 | 109 | 52.0 |
| crownwater | 31.9 | 2 437 | 1 402 | 440 | 29 | 217 | 89 | 44.0 |
| whitehorn_range | 18.6 | 4 970 | 3 813 | 1 951 | 164 | 41 | 86 | 40.6 |
| amethyst_barrens | 24.7 | 1 209 | 851 | 405 | 44 | 65 | 87 | 40.0 |
| sunmane_steppe | 18.4 | 1 625 | 1 050 | 1 106 | 44 | 259 | 30 | 10.4 |
| amberwood | 32.8 | 11 545 | 9 106 | 7 935 | 321 | 897 | 114 | 56.5 |
| grey_moors | 29.6 | 7 930 | 7 524 | 6 748 | 118 | 65 | 106 | 55.2 |
| westhaven | 28.5 | 4 235 | 3 526 | 1 816 | 167 | 66 | 106 | 55.0 |
| verdant_stair | 28.8 | 15 818 | 12 243 | 9 449 | 284 | 432 | 103 | 49.7 |
| ssarathi_ruins | 23.7 | 7 724 | 5 256 | 2 370 | 182 | 55 | 104 | 51.5 |
| manymouth_delta | 31.6 | 12 668 | 9 347 | 5 874 | 314 | 253 | 107 | 53.9 |

## What generate_scene was doing

`generate_scene` was 52% of the twelve-region load and effectively all of the
two worst regions. The third pass wrote it off as Godot's own code and not
addressable from here. It is addressable, and it is not the geometry.

`GLTFDocument` adds every node in the package with a readable name.
`Node.add_child(node, true)` checks the proposed name against the children the
parent already holds, so building a sibling list of *n* nodes costs the square
of *n*. The regions are built wide, and the cost tracks the width and nothing
else:

| region | widest sibling list | mesh nodes | generateScene |
| --- | ---: | ---: | ---: |
| four_gates | 1 276 | 3 028 | 127 ms |
| grey_moors | 6 748 | 7 524 | 2 220 ms |
| manymouth_delta | 5 874 | 9 347 | 1 845 ms |
| amberwood | 7 935 | 9 106 | 3 438 ms |
| verdant_stair | 9 449 | 12 243 | 6 145 ms |

Verdant Stair has four times Four Gates' nodes and forty-eight times its scene
build. Bucketing the wide list under empty grouping nodes and building the same
package again, in a scratch probe over `GLTFState` before `generate_scene`:

| bucket size | groups added | generateScene, Amberwood | geometry |
| --- | ---: | ---: | --- |
| as shipped | 0 | 3 755 ms | - |
| 512 | 18 | 294 ms | identical |
| 256 | 34 | 230 ms | identical |
| 128 | 67 | 204 ms | identical |
| 64 | 136 | 177 ms | identical |
| 32 | 271 | 172 ms | identical |

"Identical" is a hash over every mesh instance's name, mesh, surface count,
world transform and visibility. The regrouping itself was 8-15 ms.

## What landed

**`WorldLoader` buckets an over-wide sibling list before the scene is built.**
Any list wider than `MAX_SIBLINGS` (512) - the scene roots included, which is
the shape Sunmane Steppe has, with a thousand props and no parent among them -
is split into buckets of about sqrt(n) empty `Node3D` groups, so neither the
buckets nor the list of them is left wide. The groups carry an identity
transform and no geometry.

A mesh keeps its name, its mesh, its materials, its layers, its shadow casting
and its world placement - the last to the bit, because a grouping node's
transform is exactly the identity and multiplying by it changes none. Only its
depth in the tree changes, and every pass in the loader and every consumer of
the loaded world - the batching, the occluder fade, the interior cutaway, the
secret sections, the collision declarations - reaches nodes by a recursive
search or by name. `rendering.regroupWideSiblings` in a world manifest turns it
off, beside `batchStaticInstances`, and `rendering.maxSiblings` moves the
limit. A package carrying a skin or a skeleton is skipped whatever the manifest
says, because Godot places a `Skeleton3D` from where its joints sit among their
siblings; none of the 56 shipped packages has one.

### What does change on screen: 245 pixels in 7.4 million

Not nothing, and it is worth being exact about. A scratch probe renders
Amberwood through the loader from eight fixed cameras with nothing in the shot
that moves, so two runs can be compared pixel for pixel. Two runs of the same
build are byte-identical in all eight views, so the probe measures the change
and not the weather. With the manifest switch off it is byte-identical to the
loader as it was before this pass, in all eight views. With it on, **245 pixels
of 7 372 800 differ - 0.0033%**.

They are single pixels and pairs of pixels, scattered, always inside dense
alpha-scissored autumn foliage, where two leaf surfaces meet the camera at the
same depth. Which one wins a depth tie is decided by the order the two are
drawn, and the draw order follows the shape of the tree. Crop the worst of them
at twelve times and the two images are indistinguishable.

Nor is the order the package happens to ship any more correct than the one the
pass produces. Bucketing at 128, 256 and 512 gives three byte-identical
renders - the widest list is split the same way by all three - while bucketing
at 2048 flips a different 190 pixels again. There is no right answer to a depth
tie; there is only which surface got there first.

So: the geometry, the materials and the placements are identical to the last
bit, and 0.0033% of the pixels of a foliage-heavy region resolve a coplanar tie
the other way. If a reviewer wants even that not to move, the manifest switch
is per map.

Median of three loads per region, headless, milliseconds:

| region | before | after | | generateScene before | after |
| --- | ---: | ---: | ---: | ---: | ---: |
| four_gates | 970 | 770 | -21% | 127 | 57 |
| mirrorhold | 1 263 | 921 | -27% | 173 | 53 |
| crownwater | 1 158 | 1 011 | -13% | 99 | 80 |
| whitehorn_range | 1 119 | 919 | -18% | 140 | 61 |
| amethyst_barrens | 955 | 970 | +2% | 80 | 78 |
| sunmane_steppe | 528 | 510 | -3% | 90 | 56 |
| amberwood | 4 675 | 1 363 | **-71%** | 3 438 | 160 |
| grey_moors | 3 348 | 1 184 | **-65%** | 2 220 | 127 |
| westhaven | 1 215 | 1 100 | -9% | 188 | 92 |
| verdant_stair | 7 926 | 1 186 | **-85%** | 6 145 | 164 |
| ssarathi_ruins | 1 545 | 1 011 | -35% | 202 | 91 |
| manymouth_delta | 3 405 | 1 309 | **-62%** | 1 845 | 144 |
| **twelve regions** | **28 106** | **12 255** | **-56%** | **14 747** | **1 161** |

Crownwater and Amethyst Barrens are the two the pass leaves alone: their widest
lists are 440 and 405, under the limit, and their movement is this machine's
noise. The worst region in the game went from 7.9 s to 1.2 s, and by the
loader's own clock no region is now over 1.4 s.

The regrouping costs 15.6 ms on Amberwood and adds 113 nodes to an 11 545-node
import; across the twelve it is 158 ms and about 700 nodes.

Where the twelve-region load stands afterwards:

| | before | after |
| --- | ---: | ---: |
| generate_scene | 14 747 | 1 161 |
| walk surfaces | 5 888 | 4 765 |
| glTF parse | 5 094 | 4 309 |
| declared collision | 624 | 581 |
| mip chains | 538 | 417 |
| static batching | 378 | 317 |
| manifest | 296 | 311 |
| regrouping | - | 158 |
| everything else | 541 | 236 |
| **total** | **28 106** | **12 255** |

The parse and walk-surface columns did not move for any reason of this pass;
the differences there are the two runs, on a machine a dozen sessions share.

**The other instrument says the same, and windowed says more.**
`tests/integration/client_benchmarks.gd` times a load from the outside - from
the call to `world_root` appearing - and its own median of three puts the
twelve at 12 955 ms. It also says the memory story did not change: eleven of
the twelve give back everything they took (the three that do not are 0.7 to
4.8 MB of allocator high-water mark), the process keeps 11.7 MB across the
whole tour, and a return to Four Gates after it costs 729 ms against the 742 ms
it cost first, giving back 0.14 MB more than it took. Read its `staticBytes`
column against other headless runs only: with no GPU to hand the images to,
headless keeps them in process memory, which is why Amberwood reads 259 MB here
and 177 MB in the third pass's windowed table.

Windowed, on the RTX 5080 the third pass used, four regions against that pass's
own numbers:

| region | third pass | now | | mip chains | first frame |
| --- | ---: | ---: | ---: | ---: | ---: |
| amberwood | 3 941 | 1 580 | -60% | 310 ms | 153 ms |
| verdant_stair | 4 366 | 1 544 | -65% | 262 ms | 153 ms |
| four_gates | 1 037 | 943 | -9% | 248 ms | 93 ms |
| sunmane_steppe | 525 | 532 | +1% | 78 ms | 156 ms |

Two things only a windowed run shows. The mip chains are 250-310 ms rather than
the 31-46 ms of the headless table, because `ImageTexture.set_image()` hands the
rebuilt image to the GPU; and the first frame is 93-156 ms rather than 3-8 ms,
which is the upload and the pipelines. Both are real costs of a real load and
neither is in the headless totals above.

**Guards.** `tests/test_runtime_performance.gd` checks the pass on a synthetic
`GLTFState`: no sibling list wider than the limit survives, every node keeps
its ancestor and its order among its siblings, a group is an empty identity
transform, and a map that switches the pass off or a package that carries a
skin is left untouched. `tests/integration/map_regrouping.gd` proves the
picture: it loads Four Gates and Sunmane Steppe through the production loader,
rebuilds the same packages straight through `GLTFDocument` with no regrouping,
and compares - the same 3 028 and 1 050 mesh instances, sharing the same 184
and 258 meshes, each with the same name, mesh, surface count, layers, shadow
casting and world transform. The transform comparison is exact float equality
rather than a tolerance, and it holds: 9 106 of Amberwood's 9 106 mesh
instances come out of the regrouped tree bit-for-bit where they came out of
the shipped one.

## What landed: the cache

The first visit to a region packs the tree `WorldLoader` built into a
`PackedScene` and writes it to the player's own disk. Every visit after that
instantiates it instead of parsing the package again. Nothing ships in the
repository; the cache is built on the machine that plays the game, out of the
package that machine has.

Median of three loads per region, headless, milliseconds. **build** is the
loader with the cache switched off, which is the column the tables above are
in. **first visit** is one load with the cache on: a build plus the package
hash. **write** is packing and saving the entry, which happens three frames
after the load rather than during it. **warm** is every visit after that.

| region | build | first visit | write | warm | | on disk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| four_gates | 800 | 1 037 | 929 | **639** | -20% | 32.9 MB |
| mirrorhold | 1 270 | 1 256 | 844 | **771** | -39% | 35.0 MB |
| crownwater | 1 275 | 1 148 | 618 | **706** | -45% | 29.3 MB |
| whitehorn_range | 1 099 | 979 | 644 | **601** | -45% | 28.6 MB |
| amethyst_barrens | 922 | 890 | 541 | **639** | -31% | 30.3 MB |
| sunmane_steppe | 557 | 472 | 293 | **257** | -54% | 14.3 MB |
| amberwood | 1 537 | 1 655 | 1 167 | **904** | -41% | 42.1 MB |
| grey_moors | 1 380 | 1 858 | 1 225 | **861** | -38% | 39.7 MB |
| westhaven | 1 264 | 1 283 | 872 | **813** | -36% | 34.4 MB |
| verdant_stair | 1 422 | 1 598 | 1 321 | **734** | -48% | 34.4 MB |
| ssarathi_ruins | 972 | 982 | 695 | **590** | -39% | 28.2 MB |
| manymouth_delta | 1 595 | 1 430 | 980 | **777** | -51% | 33.9 MB |
| **twelve regions** | **14 094** | **14 589** | **10 129** | **8 292** | **-41%** | **383 MB** |

**Read the columns against each other, not against the tables higher up this
page.** This run was taken while another session had a core of this machine;
an earlier run of the same code, on a quiet one, built the twelve in 11 749 ms
and warmed them in 6 901 ms. Both runs give **-41%**, and both give 383 MB,
which is the point: the ratio is a property of the change and the absolutes
are a property of the afternoon. The same noise is why Four Gates reads -20%
and Sunmane Steppe -54% here where the quieter run had them at -43% and -47%;
per-region figures at this spread say "about two fifths", not more.

**The first visit costs the package hash and nothing else.** That is 58-147 ms
a region, 1 228 ms across the twelve, and it is the only work the cache adds
to a load. The measured first-visit column is +3.5% over twelve regions, which
is the hash plus the same noise as everything else. The write is not on the
load - it lands three frames later - and is discussed below.

And where a warm load goes:

| region | hash | read | instantiate | relink | **warm** |
| --- | ---: | ---: | ---: | ---: | ---: |
| four_gates | 105 | 396 | 130 | 5 | **639** |
| sunmane_steppe | 58 | 128 | 65 | 1 | **257** |
| amberwood | 114 | 494 | 282 | 10 | **904** |
| verdant_stair | 115 | 394 | 232 | 15 | **734** |
| **twelve regions** | **1 228** | **4 573** | **2 259** | **76** | **8 292** |

The hash is 15% of a warm load and it buys the whole invalidation contract, so
it is not a candidate for removal. A size-and-mtime key would be nearly free
and would be wrong the first time somebody's file system rounded a timestamp -
and it could not be the number the server publishes, which the sha256 can be.

### Where it lives, and what makes an entry stale

`user://map-cache/<map id>-<key>.scn` - on Windows,
`%APPDATA%/Godot/app_userdata/Eloria/map-cache`.

The key is `sha256(PACKAGE_DIGEST_VERSION + glb sha256 + manifest sha256)`,
folded together with `WorldLoader.CACHE_FORMAT_VERSION`. The glb is hashed
exactly as it sits; the manifest is folded to LF first, because it is a text
file that git and Python both rewrite the line endings of and the same digest
has to come out of any checkout - that is also what lets the server publish it
(below). All of it lives in `src/world/map_scene_cache.gd`.

So the two ways an entry goes stale are one mechanism:

* **the package changed** - a client update, a regenerated region - and the
  digest moves;
* **the loader changed** - a new pass, a different name, a different layer -
  and `CACHE_FORMAT_VERSION` moves.

Either way the name the loader looks for is not a name on disk, the region is
built from the package, and the stale entry for that map is deleted when the
new one lands. A player never has two builds of one map, and never has to be
told to clear anything.

**The failure mode this leaves is a loader change with no version bump**, which
would leave every player holding the tree the previous version built, with
nothing in the log. That is the thing to remember when editing `WorldLoader`:
if a change would make it build a different tree from the same package, raise
`CACHE_FORMAT_VERSION` in the same commit.

### Everything in the table above is in the entry

Collision bodies, walk surfaces and their layers, the shared trimesh shapes
(a `PackedScene` stores a sub-resource once and references it, so the sharing
survives), navigation collision, the static batches and their multimeshes, the
material passes, the rebuilt mip chains, visibility ranges, node names,
visibility, and the batch links. `tests/test_map_cache.gd` compares a cached
region against a built one on every one of those, plus a hash over the name,
world transform, layers, shadow casting, visibility range, visibility and
override state of every mesh instance in the tree.

Two things are **not** in it, and both are re-derived after instantiating:

* **The batch links.** `WorldLoader` stamps every mesh a batch swallowed with
  the `MultiMeshInstance3D` now drawing it, and `OccluderFade` reaches through
  that to lift one instance out of the multimesh while it fades. A `Node` in
  node metadata does not survive a pack - and not as null, which would at least
  be checkable: after a round trip the key is not in `get_meta_list()` at all.
  So the link is written twice, as the object and as a `NodePath` from the
  imported root, and `_resolve_batch_links()` turns the path back into the
  object on the way in. Four Gates relinks 1 531 of them in 3 ms.
* **`manifest.warnings`.** A cached load does not run the collision pass, so it
  does not re-report `collision node not found: X` for a package that declares
  a node it does not have. Nothing reads those warnings, and the first visit
  reports them, but it is a real difference and this is where it is written
  down.

### The write is off the load, but it is not free, and it is not threaded

The write runs three frames after `load_completed`. Not during the load, and
not deferred by one frame either, which would land it inside the frame that
first draws the region - the frame the player is actually waiting on. Three
frames puts it in the arrival, where the transition is still resolving and the
wait is already expected. It costs **293-1 321 ms** on the frame it lands on
(24-542 ms of packing, 247-944 ms of saving), once per region for the life of
an install. The entry is written under a temporary name and renamed into place,
so a write that does not finish leaves no half a region behind.

**The save was on a worker thread first, and that was a bug.** It is the larger
half of the write and appears to touch nothing but the `PackedScene`, which
holds its own reference to every mesh, material and image in it - so a map
change while it runs cannot pull them away. It worked, for every region, every
time. Then the client was asked to quit while one was in flight, and it never
quit again.

`ResourceSaver.save` of a scene full of imported `ArrayMesh`es reaches the
rendering server for their surface arrays, and off the main thread that is a
synchronous request the main thread has to serve. At shutdown the main thread
stops serving: the worker stops inside `ResourceSaver.save`, the
`wait_to_finish()` in `_exit_tree` waits for it forever, and the process hangs
with the engine half torn down. A probe that loads Sunmane Steppe and quits
five frames later hung on every run; with prints in both places, the worker
enters the save and never leaves it and the join is entered and never left.

So **`ResourceSaver.save` on a scene of imported meshes is not safe on a worker
thread in Godot 4.7**, however well it behaves while the main thread is still
pumping. Two consolations: the main-thread save is *faster* than the threaded
one was, because it makes no cross-thread round trips at all - Sunmane Steppe
is 247 ms here against 313 on the worker - and there is now no thread to join,
so a map change simply drops a queued write and the region is built again next
time, which is where it started.

Three frames is long enough for the rest of the client to have had the tree,
and it does things to it: `InteriorCutaway` hides a wall the camera is looking
through, `SecretSections` hides an undiscovered section, and `OccluderFade`
hangs a duplicated translucent material on whatever stands between the camera
and the player and makes a batched prop's own node visible so the fade can be
seen. Packed in, any of those would be permanent - a rock made of glass, for
the players whose cache happened to be written on a frame where the camera was
in the wrong place. So `_snapshot_for_cache` records visibility and surface
override materials while nothing but the loader has touched the tree, puts them
back for the length of the pack, and restores whatever the client had
afterwards; the snapshot costs 5 ms on Four Gates and is only taken on a miss.
Nodes a consumer *adds* need no handling at all: `PackedScene.pack` stores only
what the packed root owns, the owners are set from that same list, and anything
else is left out for free.

`test_map_cache.gd` does exactly what those three consumers do to a real
region, then reads it back and proves none of it survived. With the restore
removed, all three of its assertions fail.

### Compression: on, and it is not close

Measured on Four Gates, packing once and saving both ways:

| | size | save | read |
| --- | ---: | ---: | ---: |
| `FLAG_COMPRESS` | 32.9 MB | 600 ms | 285 ms |
| uncompressed | 87.8 MB | 74 ms | 136 ms |

Two things to weigh, not one, now that the save is on the main thread.
Uncompressed reads 150 ms faster on every warm load *and* writes about eight
times faster, so it would take the write hitch from 293-1 321 ms down to
roughly 70-630 ms. Against that it is 2.7x the disk: 1.02 GB across the twelve
regions rather than 383 MB, and something like 3.2 GB rather than 1.2 GB if a
player visits all 53 packages.

Compressed, because disk is the resource the player did not agree to spend and
there is no eviction policy to spend it against, while the write it pays for is
one hitch per region for the life of an install. It is the closest call in this
document, and `WorldLoader.CACHE_COMPRESS` is one constant: nothing else has to
change, because an entry written either way is read by the same call.

### What it draws

`tests/integration/map_cache_render.gd` is the eight-camera probe, and it took
two corrections before it said anything true.

**Byte-identity between two loads is not achievable and never was.** Two loads
of the same package, through the same code, in the same process, move pixels:
each load builds its own meshes and materials, the renderer sorts opaque draws
by the RIDs those got, and where two surfaces meet the camera at the same depth
the tie falls to whichever sorted first. It is the same phenomenon as the 245
pixels the regrouping moved. So the probe measures its own floor on every run,
photographing the region twice the slow way before once from the cache.

**And the first time a region is drawn in a process is not like the times
after.** The probe's first reference was a first load, and it is not a
reference: Amberwood's first eight views differ from its second eight by 22 000
pixels and its second from its third by 613, because the renderer is still
building pipelines and settling textures on the way through the first one. The
probe now throws the first set away.

With both corrected, and taken in one run over the three regions:

| region | two builds | built vs cached |
| --- | ---: | ---: |
| four_gates | 564 | **528** |
| verdant_stair | 4 110 | **1 132** |
| amberwood | 24 303 | **30 621** |

Of 4 147 200 pixels across eight views. Two of the three move *less* between a
build and the cache than between two builds.

Amberwood is the interesting one, and a separate probe took it apart. Its
residue is real, it is small, and it is perfectly repeatable:

* two loads **from the cache** are byte-identical to each other - zero pixels;
* two warm builds, back to back, are 613 pixels apart;
* a cached load against a warm build is **6 700-6 900 pixels, 1.6 per mille**,
  the same number twice;
* and the region's own build-to-build variation over a longer session, with
  other regions loaded in between, is 24 303.

So the cache's own contribution to the picture is a sixth of the variation the
region already has between two builds of itself, and it is scattered
single-pixel and pair-pixel differences inside dense alpha-scissored foliage,
mean channel delta 16 of 255. Everything structural was checked and is
identical: 11 658 nodes, 9 106 mesh instances, 429 meshes, 321 batches with
byte-identical multimesh buffers and AABBs, 897 collision bodies, 35 walk
surfaces, 3 019 hidden meshes, 3 019 resolved batch links, 46 materials with
the same filters, transparency modes, cull modes and alpha-scissor thresholds,
and 41 albedo textures all with their mip chains.

That leaves resource-allocation order as the only candidate, which is the
regrouping's finding again: there is no right answer to a depth tie, only which
surface got there first.

This is the weaker of the two guarantees and is deliberately not the
load-bearing one. The structural comparison in `test_map_cache.gd` is: it is
exact and deterministic, and it is what catches a baked-in fade or a wall left
hidden. The probe's budget is 5 per mille or three times the run's own floor,
whichever is larger, because what it exists to catch - three thousand batched
props that failed to relink - is percent-scale.

### The settings row

Graphics tab: **Keep built maps on disk**, the size the cache is using, and
**Clear map cache**. It gets a row rather than a bare toggle because it is the
only setting in that window that spends the player's disk. The switch persists
in `user://eloria_hud.cfg` under `graphics/map_cache`, written by
`MapSceneCache` itself, so no part of this needed a line in `main.gd`.

`--no-map-cache` on the command line and `ELORIA_NO_MAP_CACHE=1` in the
environment turn it off for a run without touching the setting.
`map_regrouping.gd`, `client_benchmarks.gd` and `sunmane_performance.gd` set
the environment switch themselves: each of them measures or tests the
*building* of a region, and a warm load would answer a different question in a
column that does not say so.

### The server says which package it expects

The maps ship with the client, so the server cannot supply one; what it can do
is say which it was built against. `config/eloria/client_content_manifest.json`
now carries a `packageSha256` per map - the same digest, over the same bytes,
in the same order - written by
`eloria-assets/tools/sync_package_content.py --digests --apply`, which is in
the client repository because that is where the packages are. The server sends
`ELORIA_MAP_DIGEST` (209, capability `map_digest_v1`): map id NUL, hex digest
NUL, at login and after every `CHANGE_MAP`.

The client compares it with the hash it computed for the package it actually
loaded, and on a mismatch says so in the console and in the settings row. It
does nothing else, and must not: the cache is keyed on the local package, so a
mismatch cannot make the cache wrong. It means the install is not the one the
server expects, which is worth being told - the symptoms of a stale map, a door
in the wrong place or a portal that goes nowhere, look like anything but a
stale install.

The manifest's map list is 12 entries and the client registry knows 53
packages, so **digests are published for those twelve only**. That is not a
gap: the twelve are the server's own maps, so they are the only ones it could
ever send a digest for. The tool hashes all 53 and reports the count.

## The options, measured

Everything below was measured on this base after the regrouping landed, except
where it says estimated.

| option | saving | cost | risk | on screen |
| --- | --- | --- | --- | --- |
| **Regroup wide sibling lists** (landed) | 15.9 s of 28.1 s across twelve; 6.7 s off Verdant Stair | ~40 lines in `WorldLoader`, 158 ms and 700 nodes across twelve | low - the tree is deeper by one level | 245 pixels of 7.4 million, all coplanar ties inside foliage |
| **Parse and build on a worker thread** | hides 400-610 ms of a 500-1 400 ms load; total unchanged | a thread, a deferred attach, and a decision about what the client shows meanwhile | medium - `GLTFDocument` off-thread is unsupported territory, though it worked in every probe | nothing, if the loading screen already covers the freeze |
| **Cache the built region as a PackedScene** (landed) | 41% of every visit after the first | first visit +58 to +147 ms, the package hash, plus a 293-1 321 ms write three frames later; 383 MB for the twelve; an invalidation contract | medium-high - a cached tree can drift from what the loader would build | 1.6 per mille on the worst region, a sixth of the variation it has between two builds of itself |
| **Cheaper walk-surface collision** | up to 4.8 s across twelve, the largest item left | unknown; the shapes are two thirds of it and they are the grounding contract | high - this is what holds the player up | nothing, if the shapes are the same |
| **Fewer nodes at build time** | little: Sunmane's own LOD2 package has 318 mesh instances against 1 050 and loads in 380 ms against 459 | a toolkit change and a regeneration of every package | low | LOD2 is a different, coarser map; a MultiMesh bake would not be |
| **Compressed textures at build time** | ~180 ms a region headless (150-175 ms of PNG decode, ~30 ms of mip building), 400-480 ms windowed, where the mip pass is also an upload | `KHR_texture_basisu` in the toolkit, and a decision about quality | low | **yes** - compression artefacts, and the mip chain would come from the package rather than from the loader |
| **Load the region in cells** | perceived only; the player's cell could appear in a fraction of the time | the loader, the collision passes, the batching and every fixture that waits on `world_root` | high | **yes** - the far side of the region arrives late |

### (a) Threaded loading

Feasible, and cheap. A scratch probe ran `append_from_file`, the regrouping and
`generate_scene` on a `Thread` while the main thread served frames:

| region | on the worker | main-thread frames served | slowest main-thread frame | `add_child` on the main thread | nodes |
| --- | ---: | ---: | ---: | ---: | ---: |
| four_gates | 397 ms | 129 240 | 0.97 ms | 6.1 ms | 3 137 |
| amberwood | 607 ms | 194 244 | 0.83 ms | 15.1 ms | 9 543 |
| verdant_stair | 597 ms | 187 858 | 1.22 ms | 21.2 ms | 14 767 |

The main thread never blocked and attaching a fifteen-thousand-node tree is
21 ms. Godot 4 allows building nodes off the tree on a worker and adding them
on the main thread, and the mesh and texture resources the parse creates go
through the rendering server's own command queue.

What would still be on the main thread is the material passes, the collision,
the walk surfaces and the batching - about 500 ms of Amberwood's 1 363 - because
`Node3D.global_transform` needs the node to be in the tree and the batching
reads it. Moving those too means computing the transforms by hand and attaching
last, which is a larger change than this one.

Every fixture already polls `loader.world_root` in an `await process_frame`
loop rather than assuming the tree is there when `load_world` returns
(`rendered_crownwater`, `rendered_day_night`, `rendered_ground_markers`,
`rendered_interiors`, `rendered_map_transition`, `rendered_sunmane_steppe`,
`sunmane_caves`, `sunmane_grounding`, `sunmane_minimap`,
`sunmane_performance`, `client_benchmarks`, and the rest), so the seam is
already the right one. This was **not landed**: it hides a freeze rather than
shortening it, the freeze is now 0.5-1.4 s rather than up to 8 s, and it wants
a decision about what the client shows while the worker runs.

### (b) Fewer nodes before the parse

The reason for this option was `generate_scene`, and that reason is gone. What
is left to win is the parse, which is proportional to the buffers rather than
the nodes: Sunmane Steppe's own LOD2 package has 318 mesh instances against
1 050 - a 70% cut - and loads in 380 ms against 459 ms, a 17% cut. Baking
repeats into MultiMesh at build time would not help the parse at all and would
lose the per-instance nodes the manifest, the occluder fade and the tooling all
reach for.

### (c) A cached native scene - landed

*This is the study that was written before the cache existed. It is kept
because its two warnings were both right and both cost work to answer; what
actually landed, and what the numbers turned out to be, is under "What landed:
the cache" above. The one thing this section got wrong is the shape of the
bargain: the first visit does not cost +640 to +960 ms, because the pack does
not happen on the load.*

Measured end to end in a scratch probe: load the region through `WorldLoader`,
set the owners, `PackedScene.pack()`, `ResourceSaver.save()` with
`FLAG_COMPRESS`, then read it back and instantiate it.

| region | fresh load | own | pack | save | cache file | read | instantiate | **warm load** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| four_gates | 735 ms | 3.0 | 79.6 | 556.5 | 32.9 MB | 275.7 | 100.2 | **376 ms** |
| amberwood | 1 318 ms | 8.6 | 252.5 | 702.9 | 42.0 MB | 439.4 | 224.3 | **664 ms** |
| verdant_stair | 1 244 ms | 11.9 | 347.3 | 639.4 | 34.4 MB | 364.9 | 202.4 | **567 ms** |
| sunmane_steppe | 490 ms | 1.3 | 50.4 | 204.9 | 14.3 MB | 131.8 | 59.2 | **191 ms** |

The geometry round-trips exactly - the probe compared every mesh instance's
name, mesh, surface count, world origin and visibility - and a `PackedScene`
instantiates with `_add_child_nocheck`, so it never pays the name check the
regrouping is about. Two things a landed version would have to deal with:

* **The batch links do not survive.** `WorldLoader` stamps every batched mesh
  with a `static_batch` metadata entry naming the `MultiMeshInstance3D` that
  now draws it, and `OccluderFade` reads it to lift one instance back out while
  it fades. Metadata is stored in a scene, but a `Node` in it is not a
  `Resource` and comes back null, silently, so `OccluderFade` would fade a mesh
  that is not the one being drawn. The probe worked around it by taking the
  links off before packing; a landed version would have to write them as node
  paths and re-resolve them after instantiating.
* **The key.** The cache is only correct while the package, the manifest and
  every pass in the loader are the ones that built it. A size-and-mtime key
  over both files plus a format version in the loader is the obvious contract,
  and the failure mode when someone forgets to raise the version is a map that
  is subtly wrong with nothing in the log.

Worth doing if a second visit to a region has to be instant. Not worth doing
for another 600 ms once the worst region is 1.4 s.

*Both warnings held. The metadata does not come back null - it does not come
back at all - and the key is the whole feature rather than a detail of it. The
size-and-mtime key this section proposed was replaced by a sha256 over the
bytes: it costs 53-91 ms a load, and it is the same number the server can
publish, which a size and an mtime could never be.*

### (d) Cells and streaming

The batching already sorts instances into 180 m cells, but it does that after
the whole package is parsed and built, which is the part that costs. Streaming
would mean splitting the package itself, which is a build-time change to every
region, a rewrite of the loader's passes (collision and walk surfaces are
declared per node name over the whole map), and a new contract for every
fixture that waits for `world_root` and then looks for a node by name. It is
the largest change here and the only one that changes what the player sees.

### (e) Textures

Embedded textures are decoded during the parse and there is no flag that avoids
it. Pulled out of the container and decoded by hand:

| region | images | PNG MB | decode | decoded MB | mip build |
| --- | ---: | ---: | ---: | ---: | ---: |
| four_gates | 95 | 11.9 | 174 ms | 60.0 | 32 ms |
| amberwood | 114 | 12.3 | 175 ms | 56.5 | 32 ms |
| verdant_stair | 103 | 9.3 | 150 ms | 49.7 | 30 ms |
| sunmane_steppe | 30 | 3.7 | 42 ms | 10.4 | 5 ms |

So about 180 ms a region headless, or 2.2 s across the twelve, of the 12.3 s
that is left. Windowed it is worth more than that: the mip pass is 250-310 ms
rather than 30, because `ImageTexture.set_image()` hands every rebuilt image
back to the GPU, so a region that arrived with its mip chains already in it
would skip an upload as well as a decode.

Shipping the textures VRAM-compressed and pre-mipped would take most of it and
would also cut the texture memory a region holds (14-80 MB), but it is a
visible change: compression is lossy and the mip chain would come from the
package instead of from `_build_texture_mipmaps`. **Not landed, and it should
not be landed as a patch** - it is a decision about how the maps look.

### (f) Walk-surface collision, the largest item left

Not on the original list, but it is now 4.8 s of the 12.3 s across twelve and
the biggest single phase. A scratch probe split it:

| region | surface nodes | distinct meshes | faces (k) | building the shapes | hanging the bodies |
| --- | ---: | ---: | ---: | ---: | ---: |
| four_gates | 27 | 24 | 111 | 144 ms | 83 ms |
| crownwater | 189 | 49 | 214 | 276 ms | 133 ms |
| amberwood | 35 | 25 | 235 | 253 ms | 121 ms |
| verdant_stair | 83 | 55 | 246 | 293 ms | 150 ms |
| sunmane_steppe | 102 | 102 | 95 | 84 ms | 34 ms |
| manymouth_delta | 213 | 132 | 264 | 342 ms | 161 ms |

Two thirds is `Mesh.create_trimesh_shape()` and the BVH the physics server
builds under it, at about a microsecond a triangle; a third is creating a
`StaticBody3D` and a `CollisionShape3D` per node and adding them to a world
that is already in the tree, at about 0.75 ms a body. The shapes are already
built once per mesh rather than once per node - that was the third pass. What
is left to try is building the bodies before the world is attached rather than
after, so the physics server sees them once rather than one at a time into a
live broadphase, and moving the shape building to the worker thread option (a)
would need anyway. Both want `sunmane_grounding.gd` and `sunmane_caves.gd`
run against them, because this is what holds the player up.

## Recommendation

1. **Landed: regroup wide sibling lists.** 56% of the twelve-region load, no
   disk, no cache to invalidate, and 245 pixels of 7.4 million where a depth
   tie inside foliage falls the other way. Done, with a per-map switch if even
   that is too much.
2. **Threaded parse and scene build.** Measured feasible and cheap; hides
   400-610 ms of the 500-1 400 ms that is left. Wants a decision about what the
   client shows while the worker runs, and a run of the whole `rendered_*`
   set - the seam is already `load_completed` and every fixture already polls
   `world_root`, so nothing in `tests/` should need to change.
3. **Landed: the map cache.** 41% of what is left on every visit after the
   first, for 383 MB of the player's disk, 58-147 ms of hashing on every load,
   and one 0.3-1.3 s hitch per region the first time it is entered. Done, with
   a settings row, a switch for fixtures, and a format version that has to be
   raised whenever `WorldLoader` changes.
4. **Walk-surface collision.** The largest phase left on a build, and now also
   the largest phase the cache is skipping rather than fixing. Try attaching
   the world after the collision passes rather than before, and measure again.
5. **Compressed textures at build time.** 180 ms a region, and a decision about
   how the maps look rather than a patch. Worth revisiting now for a second
   reason: 40-60 MB of every cache entry is decoded image data, so smaller
   textures would take the 383 MB down with them.
6. **Cells and streaming.** The largest change, the least certain payoff, and
   the only one the player would see.

## Open questions

* The bucket is `sqrt(n)` on the theory that the groups and the buckets should
  be the same width. 64, 128 and 256 were all within 60 ms of each other on
  Amberwood, so the choice is not load-bearing, but it has not been measured on
  a package built differently from these.
* `MAX_SIBLINGS` is 512 so that a package under that width is handed to Godot
  exactly as it was authored. That leaves Crownwater and Amethyst Barrens, at
  440 and 405, paying about 30 and 25 ms of name checking they need not. The
  limit could go to 256 for that; it has not been measured whether it is worth
  the extra depth.
* Nothing here measures a cold disk. Every number is with the page cache warm,
  which is what a second load in a session sees and not what a first launch
  sees. This matters more for the cache than it did for anything before it: a
  warm load is 3 853 ms of reading 383 MB across the twelve, and on a cold
  spinning disk that is a different column. The cache should still win - it is
  reading 33 MB where a build reads 23 MB and then does 700 ms of work on it -
  but that is an argument, not a measurement.
* **The cache is never bounded.** Fifty-three packages at 14-42 MB is about
  1.6 GB if a player visits every one, and nothing evicts. The twelve regions
  are 383 MB and the interiors are smaller, so this is a real number rather
  than an alarming one, but there is no budget, no least-recently-used rule and
  no warning - only the size in the settings row and the button beside it.
* **`CACHE_FORMAT_VERSION` is a promise a person has to keep.** Nothing checks
  that a change to `WorldLoader` raised it. A hash over the loader's own source
  would be automatic and would also invalidate the world on every comment, so
  it was not done; a test that pins the version against a list of the passes it
  covers might be the middle ground and has not been tried.
* Whether the pack can be made cheap enough to run inside the load, which would
  remove the three-frame window and the snapshot that guards it entirely. It is
  24-542 ms, so on the worst regions the answer is currently no.
* **The write hitch is the least satisfying thing here.** 0.3-1.3 s on one
  frame, once per region, and it cannot go on a thread (see above). What is
  left to try is doing it on the way *out* of a region instead of on the way
  in - `unload_world` still has the whole tree, and a freeze during a map
  change is one the player is already braced for. It would mean a region
  visited once and never left is never cached, and a crash loses the entry;
  neither was measured against the hitch it would remove.
* The 6.90 ms a frame that `sunmane_performance.gd` reports is the headless
  idle pad, not a frame time, and has been in its output since before this
  work.
