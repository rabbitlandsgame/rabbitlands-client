# Separate crest clump textures

The explicit material names `rl_hair_clump_crest`,
`rl_hair_clump_crest_lod1` and `rl_hair_clump_crest_lod2` use the ordinary
`rl_hair_clump` shader role. Names outside this list retain their old behavior;
there is no prefix matching. The complete concrete name remains the runtime
material/cache key and the key for glTF extras and texture lookup.

Each crest material declares its own `extras.texture`. This allows a module to
reuse a qualified cap's original texture and keep a donor or baked chart for
each crest LOD. The materials share clump shading, the 0.5 alpha gate, optional
root coverage and the existing detail/age values. No new shader uniform or
appearance field is added. Material values mode still makes independent
per-face copies without mixing their textures.

`coverage.py` uses the same explicit role mapping for interpolated root alpha
and retains its conservative 0.5 gate. Its per-primitive embedded-image lookup
continues to use each material's concrete texture index. `validate.py` requires
an explicit texture for the three new roles, and the Blender preview resolves
that declared image beside the asset or in the runtime texture directory.
Existing named materials and their fallback paths remain unchanged.
