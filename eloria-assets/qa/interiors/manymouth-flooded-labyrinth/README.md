# Manymouth Flooded Labyrinth QA

The Flooded Labyrinth now uses an authored delta-smuggler layout instead of the
shared interior template. Alternating boardwalk crossings traverse flood
channels between smuggler shelves and fishing-cargo caches.

The layout contains 12 flooded floors, 14 stilt walls, ten boardwalk sections,
eight flood channels, six smuggler shelves, and six fishing-crate clusters.
Eight green water lights supplement the four transition lights. The `(58,10)`
arrival, map identity, and transition metadata remain unchanged.

> Reproduction commands removed: this stage was validated against the
> Eternal Lands format data pack, which was deleted with the C client
> on 2026-09-03. The evidence below is kept as the record of it.

Validation asserts exact module counts, dependencies, scenery and lighting
density, and a clear arrival radius. Shaded map-editor and client captures
remain pending a GPU-capable session.
