# Legwear concept tiles

Eight supplied sheets of eight designs each, sliced into the sixty-four tiles
`legwear_roster.py` keys every leg garment to. The slug of a design names the
tile it was read from: `emberforge_cuisses` is sheet `legendary`, tile 1.

| sheet | what it is |
|---|---|
| `legendary` | flame, frost, void, bone, holy, shadow, stone and lion plate |
| `arcane` | robes, sashes, crystal scale and layered panels |
| `amberwood` | bark, moss, leaf, antler and amber woodland |
| `sunmane` | steppe leather, chaps, sashes and sun-disc plate |
| `ceremonial` | white, gold and crimson ceremonial plate cuisses |
| `militia` | gambeson, mail, brigandine, splint and kneecops |
| `ranger` | worn leather, straps, pouches and fur |
| `frontier` | patched cloth trousers |

**These are evidence, not source art.** They are stored at half the supplied
resolution, which is enough to re-derive a palette and to sit beside a render
in a comparison sheet, and small enough that sixty-four of them do not dominate
the repository. The full-resolution sheets are not committed; the same
convention the creature sheets follow.

They are not decoration either. `legwear_palettes.py` measures every garment's
colour from its own tile rather than inventing one, and the contact sheets put
each finished model beside the tile it claims to match. Comparing a model to a
picture of itself always agrees, so nothing generated is ever written back into
this directory.

## Re-deriving the palettes

    python eloria-assets/tools/legwear_palettes.py

rewrites `legwear_palettes.json` from these tiles. It is reproducible from what
is committed here — the tiles were downsampled before the palettes were cached,
so the file in the tree is what these images actually produce.

Do not quantise these images. An earlier pass stored them at 128 colours with
Floyd–Steinberg dithering to save four megabytes; the dithering scattered each
flat surface across neighbouring bins, the k-means clustering underneath the
palette extractor followed it, and `umbral_drapes` came back grey instead of
purple and `rimeguard_cuisses` lost its blue entirely.
