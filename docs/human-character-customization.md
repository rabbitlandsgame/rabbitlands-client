# Human character appearance

Human male and female characters can customize their face, grooming and body
proportions. Other races keep their current appearance options.

During character creation, scroll to **Face & silhouette**. Choose facial hair
and a hair finish, then adjust jaw width, cheekbones, face length, nose profile
and width, lip fullness, brow definition, eye size, eye angle and eye spacing.
Hair length and volume adjust the selected hairstyle. Height and body breadth
control the overall silhouette. Rowan, Mira and Tavi offer editable starting
looks guided by the archived Human player studies. They also select the study's
hair, eye and skin colours, and preserve your selected sex and starting class.
The skin list includes **Soft tan**, the Human bodies' own painted skin tone,
beside the other natural tones.
Use **Inspect face** for a close-up while adjusting your facial features.
**Reset shape** returns the face, grooming and proportions to their original
settings without changing your hair colour or wardrobe dyes.

For an existing Human, open **Statistics → Appearance**. The dressing room
previews your choices before you apply them. Drag the model to rotate it, use
**Face / full body** for a closer look, and toggle **Show equipment** to check
your current outfit. **Apply appearance** asks the server to save the complete
look; its confirmation appears in chat. Close or Escape leaves unapplied
changes behind.

Saving the new face, eye and hair controls online requires a server with the
matching appearance update. The client checks support before sending the look
and explains when an older server cannot save it. Local previews and local
preview saves support all controls without a server connection.

### Colours, hair finish and face detail (updated servers)

On a server with the latest appearance update, Human creation and the dressing
room offer finer controls. Other races, and servers without the update, keep the
lists described above.

* **Skin tone.** A slider runs through the natural tones from pale beige to
  ebony brown, with marks at the named tones; **‹** and **›** jump between
  them. The **Undertone** slider below moves the tone towards Pink, Rosy,
  Golden or Olive; its centre keeps the tone as designed and snaps back there.
  Very strong undertones are limited to natural skin colours, and a note says
  so. The four Eloria tones are swatches beside the slider.
* **Hair, eyes, shirt, pants and boots.** Each keeps its list and adds
  **Custom…**, which opens a colour wheel with lightness and saturation sliders
  and the list's colours as swatches. A custom colour shows as "Custom, near"
  the closest list colour, and choosing from the list replaces it. The hair
  wheel shows the colour the hair appears, so one choice looks alike on every
  hairstyle, at every graphics level and on the beard. Some hairstyles cannot
  show the very lightest colours: the wheel marks how light this hairstyle and
  every hairstyle can go, and the **On this hairstyle** swatch shows the
  result. Opening the eye wheel switches the preview to a face close-up, and
  very dark or very light irises are kept readable. A shirt or trousers too
  close to the skin colour is drawn a little lighter or darker so it stands out.
* **Hair finish.** A **Sleek ↔ Messy** slider replaces the three finishes, with
  Swept, Classic and Tousled marked on it. It applies at every graphics level;
  High also shows fine flyaway strands. It is disabled for Bald.
* **More face detail.** This section, closed until you open it, adds eyelids,
  brow height, shape and thickness, nose length, bridge and tip, mouth width,
  cupid's bow, cheek fullness, chin projection and width, ear size, freckles,
  eyeliner and its wing, stubble shadow (men), lip colour and a choice of
  High-detail hair. These show at High graphics; Low and Medium keep the
  classic look. Details marked **Auto** follow your skin tone, sex and facial
  hair.
* **Presets and Randomize.** Rowan, Mira and Tavi also set the skin tone,
  undertone and hair colour of their concept art, and their face detail.
  Randomize also rolls a skin tone and a near-neutral undertone.

Without the update, each list shows the closest colour, and other players on
older clients see those closest colours. If you return to an older server with
custom values, they are kept and a note offers **Use nearest palette colours**,
**Use nearest finish** or **Reset to Auto**; the server cannot save them until
you do. Every slider takes the arrow keys, Page Up and Page Down, Home and End,
and every control has a name for screen readers.

Height ranges from 90% to 110% of the authored body height. Body breadth ranges
from 85% to 115%. These choices change appearance only: movement speed, reach,
tile footprint, combat rules and equipment statistics stay the same. Clothes,
armour, hair, held items and capes follow the same chosen proportions.

The available facial hair includes clean shaven, stubble, moustache, goatee,
short beard and full beard. Facial hair uses the selected hair colour. Classic
hair uses the authored style; Tousled adds uneven locks and Swept gives a
more arranged silhouette. Swept on the female Buns style gathers the buns into
an asymmetric crown updo. Length and volume adjustments follow the same scalp
and face fitting as the hairstyle.

Stubble is pigment in the skin material with filtered detail, so it follows
the face during movement and camera rotation. Longer facial hair uses fitted,
skinned geometry. Both Human bodies have subtle chest and waist definition,
arm taper and palm refinements. Skinned garments and equipment receive the
same adjustment in the wearer's rest space; joint and grip anchors stay fixed.

Human walking has a relaxed elbow bend. Running balances the left and right
arm swing and steadies the wrists. The male body has a separate arm pass with
outward upper-arm placement that varies through the stride, a continuous
running pump and inward-facing hands, guided by the supplied reference videos.
The native elbow hinge follows the intended bend plane; the rising running
hand reaches toward the sternum while its elbow stays outside the torso.
Both bodies keep open walking hands and use a more curled, relaxed fist when
running. Held hands retain their equipment grip, including the left hand for
bows and shields. The female travel arms and the accepted male elbow motion
stay unchanged. Standing arms settle toward the midpoint of the walk while
retaining the standing animation's breathing. The male idle has a small
shoulder extension that moves the relaxed hands about 6–7 cm farther back.
The original lower body movement,
travel clip lengths and spell timing stay unchanged.

Normal Human weapon attacks use one deliberate cut with a windup and recovery,
lasting 1.06 seconds. Opposing forehand and backhand cuts play in shuffled pairs;
an off-hand-only blade uses the mirrored left-hand family. The previous rapid
combinations remain available as Flurry previews for future skill use. Unarmed
attacks keep their jabs. The fitted weapon-ready pose gives the shield more
clearance. These are presentation changes; server damage, attack rounds and
skill rules are unchanged.

Low and Medium graphics use the lightweight Human appearance. High graphics
draws the RL head (see **High graphics: the RL head** below). The earlier
High portrait pass described next is kept, dormant, behind the developer
switch `RL_HEADS=classic` for side-by-side checks and rollback, until the RL
head is accepted in game. That classic High pass
adds face colour, facial regions and baked normal maps for both bodies, with
refined head geometry recovering eyelid, nose and lip form from the retained
high-resolution sources. The face controls deform the eyes, lids, brows and
grooming together. High eyes add a defined pupil and limbal ring, irregular iris
detail, a continuous upper lid and warm inner corners, with a restrained corneal
reflection. The mouth has a defined Cupid bow, lip border, corners and philtrum.
Bounded relief reduces the under-eye roll and adds male cheek definition while
following the face controls. The three study presets tune eye opening, spacing,
lip fullness, brow and jaw proportions together. Eye colour retains source iris
detail. Human
eye colours also have a more restrained brightness in Low and Medium.
High hair adds overlapping tapered locks, curved edges, asymmetric sweeps and
the female updo while reusing its existing textures and materials. Filtered
strand highlights give the locks more definition. The swept female fringe sits
lower around the forehead while its crown, buns and attached strands retain
their positions. The maps
follow fixed mesh UVs during animation.
Switching back to Low or Medium restores the lightweight geometry and materials
and releases unused High portrait resources. All graphics levels use the
same body proportions, facial settings and animation controls, and the same
saved grooming choices; the RL head at High shows two of them differently
(see below).

## High graphics: the RL head

At High every Human - players, NPCs and leaderboard and dialogue portraits -
draws the RL head in the Forward+ and Mobile renderers (the Compatibility
renderer keeps the classic High head for now: even with its face shapes baked
the RL head costs that renderer 1.2-1.5 times the crowd frame time, and large
crowds run out of its per-instance colour slots): a new head, upper neck and
eyes fitted to the shipped Human
bodies, with painted skin, freckles, liner and brows, blinking, and
spring-lock hair on the two RL hairstyles. It is derived entirely from the
saved appearance, so no new data is saved or sent and every older save and
server shows it. Low and Medium, other races and every saved value are
unchanged; switching quality swaps the heads in place.

* **Face.** The ten face controls drive the RL head's matching shape controls
  around the Rowan (male) and Mira (female) presets: those presets reproduce
  the authored RL faces, and moving a slider moves the RL face about as far per
  step as the Low/Medium face moves. The default face (every slider at 50) is
  therefore a different face from Rowan and Mira at High.
* **Hair.** Male Parted is drawn as the RL `rowan_shag` and female Buns as the
  RL `mira_bun` hairstyle; every other hairstyle keeps its fitted Low/Medium
  model with the High hair finish. On the RL hairstyles, Hair length and
  volume lengthen or shorten each lock and loft or flatten the hair around
  the Rowan and Mira presets, which show the hairstyles as authored. The hair
  finish runs from sleek to messy: Swept is sleekest and Tousled messiest, and
  the preset's own finish (Tousled for Rowan, Swept for Mira) shows the
  authored strands. A sleeker finish drops loose flyaway strands, and a
  messier one adds strays, frizz and loose locks and breaks the strands up
  more (only Mira's Classic and Tousled are messier than her preset). The
  hair covers the scalp from every side, and the RL hair and beards are shaded
  as a soft, flat colour mass with a faint sheen, like the concept art. The
  other hairstyles take length, volume and finish as before.
* **Facial hair.** Moustache, goatee, short and full beards are RL beards that
  follow facial expressions and light like hair of the same colour. Stubble is
  painted into the RL skin. Women show no beard and no stubble at High for now;
  their saved choice is kept and shows at Low and Medium.
* **Colour.** Skin, eye and hair colour use the same palette choices, tuned so
  the High head matches what Low and Medium show for the same choice, the RL
  hair and beards included. Freckles, liner, brow shape and lip colour follow
  per-sex defaults by skin tone.
* **Portraits.** Dialogue and leaderboard portraits show the full-detail head
  with a neutral expression and open eyes.

Developer switches: `RL_HEADS=classic` draws the classic High head instead,
`RL_HEADS=all` draws the RL head in the Compatibility renderer too (its face
shapes baked per face there; `RL_HEAD_BAKE=1`/`0` bakes in every renderer or
none);
`RL_HEADWEAR_FIT=shipped` also refits open headwear on the Low/Medium heads
(off by default, pending an owner decision). Mapping data is
`data/actors/rl_head_wire_defaults.json`; see
[the RL head notes](../godot-client/docs/rl-head-prototype.md).

The High pass is a foundation for further painting and anatomy work. The
leaderboard portraits remain the art direction; the current models do not yet
match their fine painted detail.

## Resource budget

The RL head at High (measured 2026-10-28; details and method in
[the RL head notes](../godot-client/docs/rl-head-prototype.md#cost-at-high-perf-gate-2026-10-28)):
crowds of 40 and 160 Humans run within about 10% of the classic High head in
Forward+ at the gameplay camera (about 1.15-1.3 times at a 10 m camera). Up close a Human
draws about 25,000-30,000 head, hair and beard triangles against about 17,000-23,500,
and about two more draw calls. Its maps take about 37 MB of video memory with both
sexes loaded, and its meshes about 55 MB more than the classic head, because the
shared source meshes carry every face shape; the RL files are 27.0 MB in the
repository, and a game package carries 54.2 MB of them: 17.1 MB of models beside the
game and 36.7 MB of maps compressed for the graphics card inside its data pack.
Rebuilding the creation preview takes 70-160 ms, and switching 40 Humans up to High
about 5 seconds (the classic High head takes about 6).

The classic High head (kept for `RL_HEADS=classic` and the Compatibility renderer):
Low and Medium retain their existing triangle counts and texture set. High
uses six shared 1024-square face maps: approximately 8 MiB of compiled texture
data for both bodies, plus 384 KiB of compressed sculpt data (768 KiB decoded
CPU data) and 35 KiB of hair curves. These resources are shared; equipment
files are reused.

The four head surfaces contain about 7,600–7,900 triangles at High, compared
with 1,900–2,600 at Medium. The three study hairstyles add approximately
3,200–4,500 triangles at High. The High full beard adds about 1,900 triangles.
These refinements reuse their existing draw surfaces and bone rig.

Meshes and clips are derived when an appearance changes and cached. They do
not add a per-frame script modifier. On the development machine, a new High
study look took roughly 0.2–0.35 seconds to prepare after loading the source
assets. Novel hair length choices with warmed assets took roughly 42–174 ms;
repeated controls took 4–11 ms. These are debug preview measurements, not a frame-rate
guarantee for other devices or scenes. Hand, idle and attack refinements derive
shared clips at load time; they add no model or animation asset files and no
extra per-frame pose modifier.
The combined stance, grip and single-cut derivatives used about 1.35 MiB of
debug process memory per body, roughly 2.18 MiB more for both bodies together
than the accepted travel-only pass. Preparing a new shared set took 17–35 ms
on this machine; cached access took under 0.03 ms. These are estimates from the
isolated preview, excluding source asset loading and the rest of the game.

A warmed, isolated head comparison on an RTX 5080 Laptop GPU at 1280×720
measured median GPU time of 0.225→0.240 ms for sixteen Humans sharing two faces,
and 0.114→0.128 ms for one close-up head, with unchanged texture and mesh memory.
Hair and other quality settings stayed
at Medium in that comparison, so these numbers isolate the face pass rather
than predicting the cost of the entire High graphics setting.

The additional saved face, eye and hair fields add nine bytes to an updated
actor appearance packet and about 164 bytes to a player's saved appearance.
Private concept references and local review captures are authoring evidence
and are excluded from the game package.

## Local preview

In the prepared customization checkout, double-click
`test-human-customization.bat`. The offline workshop offers both Human bodies,
the portrait outfits and four starter outfits, animation poses, camera rotation
and all appearance controls. Choose **Graphics → Low / Medium / High** to
compare the two artwork paths; the workshop starts in Medium.
**Front view** faces the model straight toward the camera for checking the
face and elbow placement. Dragging still lets you inspect other angles.
The **Equipment** menu offers **No equipment**, **Sword and shield**, and
**Staff** independently of the chosen clothing and cape. It uses the existing
game assets, attachment sockets and grip rules. The pose menu includes both
single-cut directions, the original Flurry, and the weapon-ready pose.
Changing equipment replays the selected pose, so the normal armed cuts can be
compared with the unarmed jabs. Use **Pause** to hold a pose for inspection.
When the local MPFB study is available, **Model → Current / MPFB prototype**
compares the two models with the same appearance, equipment and pose. The
prototype uses High graphics. Choosing Low or Medium returns to the Current
model while keeping those choices.
**Save preview** stores choices separately for
each body on this computer. **Screenshot** saves an image in the preview's
private user-data folder; **Open saves** opens that folder. Closing the window
or pressing Escape finishes the session.

This launcher uses the prepared `.local/validation` project and its existing
asset cache. It runs with networking blocked and an isolated editor/user
profile. Server account creation and online saving are tested separately.
`-SmokeTest` runs the launcher's automatic check in a separate preview profile;
`-Compatibility` selects the compatibility renderer when needed.

`tests/human_portrait_comparison.gd` renders Rowan, Mira and Tavi through the
production High appearance path in front and three-quarter portrait views.
`RL_HUMAN_PORTRAIT_OUTPUT` selects the local output folder. The default studio
view uses soft shadows and the existing High scene occlusion settings;
`RL_HUMAN_PORTRAIT_LIGHTING=flat` keeps a plain diagnostic light. Portraits are
rendered from the models, with no painted retouching of the captured images.

The optional `test-mpfb-prototype.bat` opens the same workshop directly in
MPFB High mode. Use the Rowan and Mira presets for the concept study looks.
The locally authored studies use new heads and upper necks on the
accepted body and hands, preserving current motion and equipment. They are
review candidates, outside the production registry and package. Low/Medium
continue using the current models. The High study adds concept-led curved hair,
painted face detail, wider eye openings and refined lower-face proportions.
Its ten face controls reuse the same topology per sex. Brow color follows the
hair palette, and skin-bound stubble uses coverage packed into the existing
head texture. Other hair choices retain their existing sources. Facial
expression and blinking targets have not yet been authored.
See the [MPFB authoring and measured budget](../eloria-assets/tools/mpfb/README.md)
for reproducible sources, validation scope, limitations and performance results.
