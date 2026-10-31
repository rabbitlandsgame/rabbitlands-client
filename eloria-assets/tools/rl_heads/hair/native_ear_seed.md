# Coherent Native ear seed

`coherent_ear_seed(P, bands, shift_mm, max_shift_mm=14)` supplies an explicit
initial POSITION delta for Native-only fitting. It never moves the High input,
fits a surface, writes an asset, raises a displacement bound or qualifies hair.
The caller supplies all coordinate bands in bind-space metres. The side shift
mirrors bilaterally; the vertical and front/back shifts agree on both sides.

For the close-cut male source, a continuous upward/rear seed avoided opposite
nearest-surface branches around the ear crease:

```python
bands = {'x': [.045, .060], 'y': [1.69, 1.72],
         'z': [-.10, -.075, .010, .035]}
D0, seed_receipt = coherent_ear_seed(P, bands, [0, 8, -5])
D1, vertex_receipt = fit_vertices(rest_union, P, targets,
    initial_delta=D0, margin_mm=2.6, max_shift_mm=14)
```

The successful authoring route then supported all triangle centres/midpoints
across the nine grooms against the complete evaluated Rest union at a 2.5 mm
fitting margin, retaining the independent 2 mm production gate. That source's
three clump LODs converged with a maximum 11.89 mm corrective (11.69 mm at LOD0). Its exact LOD0
seed first used the neutral complete fixture at 2.8 mm; LOD1/2 used the complete
Rest union at 2.6 mm. This is an example, not an automatic setting for other
families, sexes, head frames or styles. Fine-root attachment, total corrective
bound, triangle budget, stand-off, full evaluated controls/poses and rendered
silhouette must still be checked independently.
