# Authored outer aprons

`outer_aprons.capture(build, region)` records actual native terrain triangles and their physical perimeter, native sea geometry/UVs, content footings, and natural scenery contact offsets. Call it immediately before `streaming_borders.apply`.

`outer_aprons.apply(build, region, snapshot)` runs after shared-border and regional landform finishes. It returns and stores `build.outer_apron_audit`. Calling it twice fails; rebuild from source instead.

The explicit eight-region curve table modifies only the unplayable outer apron. The native playable rectangle plus two metres stays fixed. Shared contours have a 48-metre unchanged band; road centre lines have a 20-metre unchanged buffer. Linked content and structures preserve their footprint plus a transition margin. Terrain triangles crossing the protected core are split before deformation, so moving an outer vertex cannot tilt the native walking face.

Wet aprons descend into the existing regional water datum. Extension substrate first samples the actual captured native triangles, then their physical perimeter when outside those triangles. This prevents a clamped height-grid edge from raising seabed into a new strip of land. The water replacement contains actual geometry and preserves the native piecewise UV mapping; it removes coincident old water only in its replacement domain. Raised pools and shared approaches retain their original water.

Whitehorn instead ends in an authored glacial escarpment, cut physically at a varying outer contour with rock faces. It creates no ocean. These contours never remove native playable ground.

Unlinked outer trees, rocks and ground scatter follow the finished triangle surface with their original contact offset. Dry scenery which loses support or becomes submerged is removed. Manymouth's explicitly authored mangrove and root-mat habitat retains its native tidal bed limit of -1.35 metres. Linked props, services, structures and native-core scenery remain protected.

CPU pilot (one region per process because legacy source modules have local names):

```
python eloria-assets/maps/nymara-regions/_outer/probe_outer_aprons.py --region amberwood --output <artifact-directory>
python eloria-assets/maps/nymara-regions/_outer/probe_outer_aprons.py --region whitehorn_range --output <artifact-directory>
```

The pilot calls the source builder without exporting a package. It renders matching full-ownership atlas images using the native cartography renderer, checks 1,225 native surface rays, and records old/new physical samples. It does not start Godot or write a server profile.
