# Four Gates visual QA

- `four_gates_cartography.png` is mip level zero from the generated client DDS.
- `four_gates_overhead.png` is a deterministic ELM overhead render. Gold marks
  gatehouses and bridges, pale marks civic towers, green marks the park belt,
  and the white cross marks the unobstructed `(58,58)` arrival.
- The rebuilt city is centred at actor `(96,96)` and uses a 156-unit outer
  footprint (up from roughly 88), three primary ward rings, two secondary
  courtyard rings, four outer approaches, modular markets, gardens, farms,
  field plots, cliff banks, waterfalls, an inner citadel gate, and a northern
  summit portal. A Palon Vertas density pass adds original market stalls,
  benches, stacked crates, flower planters, public wells, road bollards, and
  irregular outer groves. These are new Eloria assets influenced by the
  reference's composition and density, not copied Eternal Lands geometry or
  textures. Materials use brighter warm stone, meadow greens, gold roads, and
  cyan water with expanded daylight fill. The protected arrival is `(96,42)`
  on the ceremonial axis.
  The authored reference
  GLBs informed silhouette and materials; runtime E3Ds use simplified,
  non-overlapping procedural masses and reusable modular pieces.
- `four_gates_civic_tower_wireframe.png` is an isometric topology view of the
  representative 560-vertex civic tower E3D.
- `four_gates_gatehouse_wireframe.png` is the corresponding view of the refined
  848-vertex monumental gatehouse.
- `four_gates_terrain_sheet.png` shows the full-resolution civic stone,
  highland grass, ceremonial road and water materials used by tile IDs 4-7.

Regenerate after building the asset pack:

> Reproduction commands removed: this stage was validated against the
> Eternal Lands format data pack, which was deleted with the C client
> on 2026-09-03. The evidence below is kept as the record of it.
