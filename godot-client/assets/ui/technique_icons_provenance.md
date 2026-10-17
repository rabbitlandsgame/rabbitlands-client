# Technique and Abilities icon provenance

These icons were generated for Rabbit Lands on 2026-10-17 with the ChatGPT image
generation tool (Codex `image_generation`, through the gpt-image-bridge skill). No
Meshy credits were used. The generated 2x2 source sheets and the build scripts are
kept in the client's ignored authoring workspace,
`.local/asset-authoring/workspace/work-output/technique-icons/`.

## `technique_icons.png`

24 icons, 64 px cells, 8 per row, in the server catalogue order
(`eloria/techniques.py` `TECHNIQUES`). Each source sheet held four icons; they
were sliced at the black gutter, scaled to 64 px, sharpened slightly, and given
the gold frame copied from the first cell of `spell_sigils.png`
(`build_technique_icons.py`). Style reference: a 2x enlargement of
`spell_sigils.png`.

Shared prompt (each call named four subjects):

```text
Image 1 is a STYLE reference only: a sheet of painted fantasy spell icons from the same game. Match its painterly rendering, rich saturated colours, strong bold silhouettes, dark teal-blue textured backgrounds with a soft vignette and warm rim lighting. Do NOT copy any of its subjects and do NOT draw its gold frames. Compose exactly FOUR separate square icons arranged in a 2x2 grid that fills the whole canvas edge to edge, with a thin plain black gutter between the four squares. Each square is one complete icon: a dark teal-blue painted background with vignette filling the entire square, one subject centred and large, readable when shrunk to 64 pixels. No frames, no borders inside the squares, no text, no letters, no numbers, no UI chrome.
```

Subjects, in order:

1. Heavy Blow: a broadsword coming down in a crushing overhead swing with a bright white impact burst where it lands.
2. Measured Strike: a sword point aimed precisely at the centre of a faint golden target ring, calm and exact.
3. Fighting Retreat: an armoured boot stepping backwards beside a raised round shield, a curved arrow showing the step away.
4. Charge: a helmeted warrior silhouette lunging forward shield-first with streaking speed lines and kicked-up dust.
5. Challenge: an armoured gauntlet beckoning with two fingers, a red defiant aura around it.
6. Second Wind: a warrior's chest with a swirling green-gold breath of air rising from it, renewed vigour.
7. War Cry: a curved horned war horn blasting golden rings of sound outwards.
8. Executioner's Stroke: a heavy executioner's axe silhouetted against a blood-red crescent moon.
9. Shield Bash: a round iron-rimmed shield slamming forward with orange impact stars and a stunned spiral.
10. Brace: a tall tower shield planted firmly in the earth, cracks in the ground around its base, immovable.
11. Intercept: a large shield stepping in front of a small cowering figure, protecting it from an incoming claw.
12. Cleave: a two-handed greataxe sweeping a wide glowing crescent arc.
13. Sunder: a war hammer cracking a steel breastplate, shards of armour flying.
14. Flurry: three bright crossing sword slashes in quick succession, motion blur.
15. Hamstring: a curved blade slicing behind the leg of a snarling wolf, the beast stumbling.
16. Riposte: two crossed rapiers, one deflecting the other, with a curved golden counter-arrow.
17. Backstab: a dagger gleaming in deep shadow behind a hooded unaware figure.
18. Lunge: a spear thrusting straight forward with a long white motion trail.
19. Keep at Bay: a polearm held level, its blade pushing back a snarling beast's head.
20. Aimed Shot: a fully drawn longbow with a glowing eye-shaped sight along the arrow.
21. Pinning Shot: an arrow driven through a creature's paw into the ground, pinning it.
22. Volley: a rain of many arrows arcing down from a stormy sky.
23. Step Back: a hooded archer leaping backwards with bow in hand, dust trail at the feet.
24. Mark Target: a glowing red crosshair rune hovering over a beast's head.

## Spells & Techniques HUD button

The Spells cell of `eloria_gamebuttons.png` (region 192,32) was repainted with a
book-and-blade pictogram; its frame is unchanged. The greyed cell in
`eloria_gamebuttons_inactive.png` is derived from it with the grey mapping fitted
from the other cells (`build_hud_icon.py`). Style reference: a 3x enlargement of
`eloria_gamebuttons.png`.

```text
Image 1 is a STYLE reference: a sheet of small HUD action button icons from the same game (flat, chunky pixel-friendly pictograms in muted cream, steel grey and warm gold on a dark teal square with a brass riveted frame). Paint ONE new pictogram in exactly that style: an open spellbook lying flat with a short straight sword laid diagonally across it, hilt bottom-left and point top-right, a few small sparkles above the book. Very simple shapes, thick readable silhouette, limited palette of cream pages, steel blade, gold hilt and gold sparkles. Centre it on a plain flat dark teal (#0b2433) background that fills the whole square canvas. No frame, no border, no text.
```
