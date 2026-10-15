# The Red Canyon — modeling assumptions

The Sunmane Steppe concept board supplies warm dry ground, weathered stone,
cloth standards, timber and sparse grass. The gauntlet's dry-wash lore gives
the route its purpose: herds seek shade, and predators follow them. The
canyon therefore opens to the sky, with eroded sandstone banks in place
of the previous masonry rooms and timber lids. All geometry and textures
come from shared toolkit recipes.

The staging bay provides shelter and travelling supplies before the first
gate. Wind-cut remnants stagger the next room's banks. The Horse Cave is
an undercut bank with broad stone ledges, dry grass bedding and a clear
central lane. These are herd shelters rather than a second settlement.

The Ridge Path is a narrow surviving rock rib across a dry ravine. Its
banks flare into the bed three metres below its continuous top. Standards
are seated on that top, and low talus sits on the ravine bed. This retains
the two-abreast timed encounter without the old water-filled chamber.

The Scree Stair is a surveyed three-metre climb. Its continuous sloping
floor is divided into strips no longer than 0.4 metres because the shared
collision exporter assigns each triangle its highest point. One long
triangle would turn the whole slope into a three-metre step. The strips
keep the approximation within one server height stage; no grid patch or
exterior correction pass is used.

A central remnant separates the fork mouths. The Shade Fork has long
undercut ledges and sheltered bedding; the Sun Fork has exposed remnants
and sparse grass. The existing branch names, choices and encounter rules
remain. Staggered remnants and side shelters divide the Long Wash, with
the Seed alcove kept accessible. The split crown of sandstone towers
ends the upper wash's view at the final court. Feeding bays sit at its
sides, and two low steps connect the boss shelf to the reward gap.

Open room banks meet full-height door mouths. Erosion returns to a flat
end profile at each join so corner seams remain closed. Small remnants
soften those corners without taking over narrow landings. Passage banks
omit buried end caps where they meet room banks or sealed gates, avoiding
nearly coplanar coverage. The actual floor and structural faces own collision.

The seven legs, timed crossing, fork and court remain. Shorter connecting
slots remove thirty-six metres from arrival to vault, reducing it from
347 to 311 metres. The outer cliff backs make the geometry footprint about
331 metres long. This remains an instanced encounter route with a safe
arrival and increasing danger, rather than an exterior service hub.

The new sandstone texture and sand material register through canyoncraft.
They append two material names; no existing material or terrain surface
class changes. The sand reuses the shared packed-earth texture. Bedding UVs
follow height, and dry grass uses paired opposite-facing opaque blades.
Warm timber, cloth and existing lamps retain the game's material language.

The route declares open sky, directional sunlight and six local lamps
under ledges. The small shelter overhangs remain visible from underneath;
they are scenery above side bays, not lids across entire rooms. No full
room roof is added to the ordinary geometry bucket. Captures use the
package's actual environment in the Compatibility renderer.

The server layout refresh preserves roster, rules, rewards, keeper
coordinates and exterior returns. Geometry-derived gate cuts remain
sealed until the instance opens them. The exterior Sunmane package is
unchanged; this is its separate gauntlet map.
