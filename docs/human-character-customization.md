# Human character appearance

Human male and female characters can customize their face, grooming and body
proportions. Other races keep their current appearance options.

During character creation, scroll to **Face & silhouette**. Choose facial hair
and a hair finish, then adjust jaw width, cheekbones, nose profile, height and
body breadth. Rowan, Mira and Tavi offer starting looks inspired by the
leaderboard portraits. They preserve your selected sex and starting class.
Use **Inspect face** for a close-up while adjusting your facial features.
**Reset shape** returns the face, grooming and proportions to their original
settings without changing your hair colour or wardrobe dyes.

For an existing Human, open **Statistics → Appearance**. The dressing room
previews your choices before you apply them. Drag the model to rotate it, use
**Face / full body** for a closer look, and toggle **Show equipment** to check
your current outfit. **Apply appearance** asks the server to save the complete
look; its confirmation appears in chat. Close or Escape leaves unapplied
changes behind.

Height ranges from 90% to 110% of the authored body height. Body breadth ranges
from 85% to 115%. These choices change appearance only: movement speed, reach,
tile footprint, combat rules and equipment statistics stay the same. Clothes,
armour, hair, held items and capes follow the same chosen proportions.

The available facial hair includes clean shaven, stubble, moustache, goatee,
short beard and full beard. Facial hair uses the selected hair colour. Classic
hair retains the original shape; Tousled adds uneven locks and Swept gives a
more arranged silhouette. Swept on the female Buns style gathers the buns into
an asymmetric crown updo.

Stubble is pigment in the skin material with filtered detail, so it follows
the face during movement and camera rotation. Longer facial hair uses fitted,
skinned geometry. Both Human bodies have subtle chest and waist definition,
arm taper and palm refinements. Skinned garments and equipment receive the
same adjustment in the wearer's rest space; joint and grip anchors stay fixed.

Human walking has a relaxed elbow bend. Running balances the left and right
arm swing and steadies the wrists. The male body has a separate arm pass with
closer elbow placement, a sustained running bend and inward-facing palms.
The female walk and run retain their previous motion. These changes preserve
the original lower body movement, clip lengths, attack and spell timing. Equipped weapon poses
continue to adjust the hands after animation playback.

Low and Medium graphics use the lightweight Human appearance. High graphics
adds face colour, facial regions and baked normal maps for both bodies, with
refined head geometry recovering eyelid, nose and lip form from the retained
high-resolution sources. Eye colour retains the source iris detail. Human
eye colours also have a more restrained brightness in Low and Medium.
High hair refines curved edges, asymmetric sweeps and the female updo while
reusing its existing textures. The maps follow fixed mesh UVs during animation.
Switching back to Low or Medium restores the lightweight geometry and materials
and releases unused High portrait resources. All graphics levels use the
same body proportions, facial settings, grooming choices and animation controls.

The High pass is a foundation for further painting and anatomy work. The
leaderboard portraits remain the art direction; the current models do not yet
match their fine painted detail.

## Local preview

In the prepared customization checkout, double-click
`test-human-customization.bat`. The offline workshop offers both Human bodies,
the portrait outfits and four starter outfits, animation poses, camera rotation
and all appearance controls. Choose **Graphics → Low / Medium / High** to
compare the two artwork paths; the workshop starts in Medium.
**Front view** faces the model straight toward the camera for checking the
face and elbow placement. Dragging still lets you inspect other angles.
**Save preview** stores choices separately for
each body on this computer. **Screenshot** saves an image in the preview's
private user-data folder; **Open saves** opens that folder. Closing the window
or pressing Escape finishes the session.

This launcher uses the prepared `.local/validation` project and its existing
asset cache. It runs with networking blocked and an isolated editor/user
profile. Server account creation and online saving are tested separately.
`-SmokeTest` runs the launcher's automatic check in a separate preview profile;
`-Compatibility` selects the compatibility renderer when needed.
