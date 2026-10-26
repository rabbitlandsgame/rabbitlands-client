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

The result retains Rabbit Lands' stylized Human models and painted materials.
The leaderboard paintings provide art direction rather than an exact match
for fine portrait detail.

## Local preview

In the prepared customization checkout, double-click
`test-human-customization.bat`. The offline workshop offers both Human bodies,
the portrait outfits and four starter outfits, animation poses, camera rotation
and all appearance controls. **Save preview** stores choices separately for
each body on this computer. **Screenshot** saves an image in the preview's
private user-data folder; **Open saves** opens that folder. Closing the window
or pressing Escape finishes the session.

This launcher uses the prepared `.local/validation` project and its existing
asset cache. It runs with networking blocked and an isolated editor/user
profile. Server account creation and online saving are tested separately.
`-SmokeTest` runs the launcher's automatic check in a separate preview profile;
`-Compatibility` selects the compatibility renderer when needed.
