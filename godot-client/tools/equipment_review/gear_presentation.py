"""Authored, preview-only gear names and descriptions. Item identities stay canonical."""
from __future__ import annotations

PARTS = (3, 5, 4, 6)
ICON_ROOT = "res://tools/equipment_review/icons/"

# Set | outfit appearance | head | body | legs | feet. Each component describes
# the installed design, rather than its authoring source or an invented effect.
FAMILIES = [
    ((149, 232, 243, 224), "Clothing", "Cap Hat Hat Cap Headscarf Hat Hood Cap".split(),
     "Shirt Tunic Shirt Shirt Tunic Tunic Shirt Tunic".split(), "Pants", """
Homespun|plain cloth, brown leather, and practical repairs|A soft wool cap with a folded edge|A loose, pale shirt tied at the waist|Brown trousers with visible patches|Short leather boots with simple fastenings
Drover|weathered brown cloth and workwear|A broad, floppy hat with a low crown|A warm brown tunic with a laced neckline|Plain work trousers with a relaxed fit|Soft boots with folded, slouching shafts
Patchwork|mended fabric and mismatched patches|A sunhat made from patched cloth|A worn shirt held together with visible repairs|Ragged trousers reinforced with patches|Leather boots with laced fronts
Shepherd|pale cloth, dark edging, and sturdy stitching|A close cap with protective ear flaps|A light shirt edged with dark stitching|Loose trousers with contrasting trim|Soft footwear secured with cords
Wayfarer|cream cloth, red accents, and a travelling sash|A linen kerchief wrapped around the head|A light tunic crossed by a broad sash|Cloth pants gathered beneath a waist sash|Tall riding boots with reinforced fronts
Traveller|earthy cloth and practical travelling clothes|A felt hat with a creased crown and wide brim|A field tunic with a laced neck|Trousers with reinforced knees|Warm boots with soft cuffs
Ragged|faded blue fabric and worn hems|A cloth hood framing the face|A faded blue shirt with a tattered hem|Worn pants with a loose cut|Simple canvas footwear
Winter|brown wool, fur trim, and warm layers|A rounded cap trimmed with fur|A heavy wool tunic with broad sleeves|Warm wool pants|Thick boots with turned cuffs
"""),
    ((133, 208, 219, 248), "Militia", "Hood Helmet Helmet Helmet Hood Helmet Helmet Helmet".split(),
     ["Armor"] * 8, "Leggings", """
Recruit|quilted padding and simple leather fittings|A padded hood enclosing the sides of the head|A quilted coat with simple front ties|Padded leg coverings with stitched panels|Leather boots protected by small shin plates
Guard|studded brown leather, quilted sleeves, and metal bands|A leather helmet with a central brow strip and cheek flaps|A fitted leather vest covered in metal studs|Reinforced leather leggings with rounded knee plates|Tall brown boots secured by metal bands
Footman|dark leather reinforced with steel strips|A broad-brimmed steel helmet|A dark vest reinforced with vertical metal splints|Leg protection built around long metal strips|Steel protection covering the shins and feet
Soldier|mail, leather straps, and plain steel fittings|A segmented metal helmet with a reinforced brow|A short-sleeved shirt of interlinked metal rings|Mail leg protection held by leather straps|Sturdy boots capped with metal over the toes
Mercenary|riveted plates, dark leather, and overlapping panels|A hood of closely linked mail|Overlapping riveted plates covering the chest and waist|Layered plates protecting the upper legs|Boots fitted with broad metal shin guards
Sentry|plain steel plate over quilted cloth|A steel helmet with extended cheek protection|A smooth breastplate over a padded coat|Steel knee protection over leather leggings|Boots reinforced with narrow metal splints
Sergeant|brass-colored plate and substantial leather fittings|A warm-toned metal helmet with cheek protection|A broad brass-colored breastplate|Layered leg protection with matching metal panels|Tall boots with colored plates and heavy straps
Captain|steel plate, crimson panels, and fur-trimmed boots|A helmet with a crimson central panel|A steel cuirass over crimson cloth|Segmented leggings with crimson accents|Tall armored boots finished with fur cuffs
"""),
    ((157, 224, 227, 232), "Leather", "Hood Cap Hood Hat Hood Cap Cap Hood".split(),
     ["Armor"] * 8, "Leggings", """
Hunter|dark leather, bone fastenings, and small travelling pouches|A close hood edged with small fang details|A leather coat closed with bone hooks|Leather legwear with a pouch-bearing belt|Leather boots tied with decorated cords
Scout|brown leather, a feathered cap, and fur cuffs|A fitted cap with a feather detail|A light leather vest worn over cloth sleeves|Leather leggings held beneath a decorated belt|Boots finished with soft fur cuffs
Rogue|dark leather, crossed straps, and deep red cloth|A buckled hood with a close-fitting brow|A dark leather coat crossed by a sash|Leather legwear wrapped in supporting straps|Boots with broad leather buckles
Archer|brown leather, brass buckles, and a plumed hat|A broad-brimmed hat with a feather plume|A leather coat secured by brass-colored buckles|Leather leggings laced along the sides|Boots with small hanging bead details
Tracker|green cloth, dark leather, and small woodland charms|A hood carrying small hanging charms|A leather coat edged with green fringe|Leg protection decorated with bone charms|Field boots tied with contrasting red laces
Adventurer|weathered leather, rings, and coiled fastenings|A leather cap reinforced with small studs|A leather coat fastened with coiled cord|Legwear secured with rings and coiled straps|Boots wrapped with decorated bands
Outrider|riveted leather, a banded cap, and reinforced boots|A close leather cap crossed by a broad band|A fitted coat reinforced with metal rivets|Studded leather panels protecting the legs|Heavy field boots with reinforced fronts
Trapper|fur, dark leather, and warm layered clothing|A deep hood edged with thick fur|A heavy leather coat lined with fur|Warm legwear wrapped with fur panels|Rugged boots secured with several straps
"""),
    ((117, 184, 171, 200), "Woodland", "Hood Cap Headband Hood Helmet Hood Helmet Helmet".split(),
     "Armor Coat Tunic Armor Armor Coat Armor Armor".split(), "Leggings", """
Forester|bark-like leather, leaf details, and earthy colors|A pointed hood edged with leaf shapes|A long leather coat with bark-like panels|Layered leg protection with a leafy belt|Boots with rough, bark-like shafts
Moss|deep green cloth, mossy trim, and twisting decoration|A green cap crowned with curling woodland details|A green coat with mossy shoulders and trim|Green legwear with twisting decorative bands|Boots with soft green cuffs and vine-like ties
Herbalist|pale cloth, roots, and green-and-gold ornament|A narrow headband formed from curling root shapes|A pale tunic crossed by root-like decoration|Light legwear with winding decorative panels|Boots wrapped with curling bands
Leaf|overlapping leaf shapes and dark green armor|A hood built around overlapping leaf shapes|Layered leaf-shaped plates covering the torso|Leaf-shaped panels protecting the legs|Green boots reinforced with leaf-like sections
Bark|dark green panels, woody textures, and gold edging|A tall helmet with branching decoration|A fitted cuirass with dark woodland panels|Leg protection finished with woody, branching patterns|Tall boots with carved-looking fronts
Antler|brown leather, pale fur, and antler ornament|A fur-lined hood bearing small antlers|A warm coat with pale fur down the front|Layered leggings finished with warm fur trim|Leather boots with thick, pale fur cuffs
Amber|amber-colored panels, dark green cloth, and gold borders|A metal helmet set with amber-colored decoration|A cuirass with bright amber-colored plates|Leg protection with matching amber-colored panels|Tall boots with amber-colored fronts
Ivory|pale branching ornament over deep green armor|A helmet with tall, pale branching points|A deep green cuirass framed by ivory-colored vines|Green leg protection edged with pale decoration|Boots with curling ivory-colored details
"""),
    ((165, 240, 235, 216), "Riding", "Hat Headwrap Helmet Turban Helmet Headband Hood Helmet".split(),
     "Tunic Robe Armor Coat Armor Tunic Coat Armor".split(), "Pants Pants Leggings Pants Leggings Pants Pants Leggings".split(), """
Rider|light travelling cloth, tassels, and riding leathers|A brimmed riding hat with a decorated band|A pale tunic finished with hanging tassels|Close-fitting riding pants with reinforced knees|Riding boots decorated with tassels
Nomad|layered cream cloth, fringed edges, and patterned sashes|A headwrap draped around the head and neck|A loose robe with fringed, overlapping panels|Loose pants beneath a wrapped outer layer|Soft boots secured by layered cloth wraps
Cavalry|brown leather, metal fittings, and mounted field gear|A leather helmet with protective side flaps|A fitted leather vest with an armored waist|Leather leg protection shaped for riding|Riding boots with bronze-colored reinforcement
Wanderer|pale cloth, bone toggles, and wrapped travelling layers|A cloth turban wrapped around the head and lower face|A pale coat closed with bone-colored toggles|Travel pants held with decorated fastenings|Boots fastened with small bone-colored pegs
Lancer|bronze-colored plate and round sun-shaped emblems|A metal helmet decorated with a round emblem|A cuirass bearing a large sun-shaped disc|Layered protection for the upper legs|Armored boots with matching warm-toned plates
Red Sash|deep red cloth, gold ornament, and broad wrapped panels|A decorated headband with hanging cloth|A wrapped tunic crossed by a broad red sash|Pants tied with long decorative cords|Boots secured with sash-like wraps
Courier|tan leather, red scarves, and practical riding clothes|A hood wrapped with a dark red scarf|A fitted riding coat with several front fastenings|Riding pants secured with cords|Boots laced with matching cords
Raider|bone-colored plates, red accents, and a tall crest|A metal helmet bearing a red plume|A coat covered with overlapping bone-colored plates|Layered protection covering the thighs and knees|Tall riding boots with pale armored fronts
"""),
    ((141, 200, 187, 240), "Plate", ["Helmet"] * 8, ["Armor"] * 8, "Leggings", """
Knight|fluted steel, gold borders, and dark red cloth|A closed helmet with a gilded brow and narrow face opening|A breastplate shaped with long vertical flutes|Segmented plate leggings with decorated knees|Articulated metal boots with fluted fronts
Cavalier|polished silver plate and delicate gold ornament|A polished helmet with a perforated visor|A bright cuirass with fine curling decoration|Plate leggings with floral knee ornaments|Polished boots with leaf-like ornament
Paladin|dark plate, gold vines, and pale cloth panels|A great helmet with a broad cross-shaped face plate|A dark cuirass traced with gilded vines|Plate leggings worn over crimson fabric|Metal boots covered with curling gold decoration
Sentinel|silver scales, layered plate, and dark edging|A swept metal helmet with a narrow visor|A cuirass built from overlapping scale-like plates|Pale plate leggings with broad knee protection|Layered metal boots with angular fronts
Herald|bright plate, wing motifs, and small rose ornaments|A helmet with raised wing-shaped sides|An ornate silver cuirass with small rose-like decorations|Decorated leggings with lion-shaped knee details|Bright armored boots with contrasting emblems
Noble|silver-and-gold plate and a crown-like crest|An open helmet topped by a crown-like band|A rounded cuirass with broad overlapping waist plates|Polished leggings with elaborate borders|Plate boots bearing star-shaped decoration
Marshal|crimson cloth, gold trim, and ceremonial plate|A crested helmet with a tall plume|A mantled cuirass worn over crimson fabric|Decorated plate leggings with rose-like ornament|Armored boots with crimson inset panels
Black Knight|blackened plate and fine silver tracing|A closed dark helmet with a sculpted face plate|A blackened cuirass edged with silver lines|Dark plate leggings with raised ornament|Blackened articulated metal boots
"""),
    ((109, 216, 179, 192), "Arcane", "Hat Hood Headband Crown Helmet Veil Hood Helmet".split(),
     "Robe Coat Armor Armor Armor Robe Tunic Armor".split(), "Leggings", """
Mage|navy cloth, gold borders, and blue jewel details|A folded cloth hat with a blue jewel|A long robe with a patterned front panel|Dark leg protection draped with patterned cloth|Tall boots with pale cuffs and blue jewel details
Runic|dark leather and luminous blue linework|A close hood with a bright blue jewel at the brow|A fitted coat traced with bright blue lines|Dark leggings crossed by matching blue decoration|Leather boots with blue-inset bindings
Silver Ward|pale metal, blue cloth, and angular jewel settings|A narrow silver-colored headband with a blue centerpiece|A pale cuirass with a central blue jewel|Pale leg protection with angular blue details|Pale armored boots with blue inset stones
Starglass|deep blue plate and a web of silver-and-blue ornament|A delicate crown with pointed blue accents|A dark blue cuirass framed by angular silver patterns|Layered blue leg protection with matching silver borders|Boots crossed by silver bands and blue jewel details
Twilight|dark purple cloth, black plate, and cool metal borders|A closed dark helmet with a narrow face opening|A dark cuirass with pointed layered shoulders|Dark leggings edged with cool-colored metal|Tall dark boots with angular silver bindings
Tidecaller|turquoise fabric, pale cloth, and flowing gold lines|A turquoise veil held by an ornate headpiece|A flowing turquoise robe crossed by pale cloth|Wrapped legwear with wave-like gold decoration|Turquoise boots tied with pale cords
Acolyte|pale cloth, gold edging, and blue jewel accents|A pale hood with a small blue pendant|A light tunic bordered with gold-colored trim|Pale leggings with long, hanging cloth panels|Light boots with simple gold-colored borders
Crystalward|pale blue plate, pointed layers, and gold framing|A tall helmet with pointed sides and a narrow face plate|A layered cuirass set with pale blue details|Armored leggings edged with pointed blue plates|Tall metal boots with angular fronts
"""),
    ((125, 192, 195, 208), "Legendary", ["Helmet"] * 8, ["Armor"] * 8, "Leggings", """
Phoenix|fiery red plate, gold feathers, and a phoenix emblem|A high helmet with flame-like golden wings|A red-and-gold cuirass bearing a large phoenix motif|Red plate leggings with sweeping gold feather patterns|Gold-trimmed boots with flame-like armored fronts
Glacier|icy blue metal, silver points, and frost-like ornament|A silver-blue helmet crowned by icy points|A pale blue cuirass with sweeping silver ornament|Blue plate leggings with layered silver borders|Pale armored boots with sharp, icy-looking details
Nightstorm|black plate, purple stones, and sharp gold borders|A closed dark helmet with angular purple accents|A black cuirass with pointed shoulders and purple jewels|Dark plate leggings with long, angular panels|Dark armored boots edged with gold-colored points
Dragonbone|ivory-colored bone plates and deep red cloth|A helmet shaped around a horned dragon skull|An ivory-colored cuirass with ribbed bone-like layers|Leg protection formed from jagged bone-like plates|Pale armored boots with claw-like projections
Sunburst|white-and-gold plate and radiating sun ornament|A bright open helmet with a pointed golden crest|A pale cuirass covered with radiating gold patterns|Bright leggings decorated with long golden flourishes|White-and-gold armored boots with radiant ornament
Amethyst|purple cloth, dark plate, and violet jewel settings|A pointed helmet with a violet jewel at the brow|A dark cuirass with purple insets and a central jewel|Dark leggings with purple cloth and jewel accents|Dark armored boots decorated with violet details
Runestone|green insets and carved-looking spiral ornament|A tall, angular helmet with carved-looking green details|A heavy cuirass covered with interwoven spiral patterns|Green-and-gray leggings with matching carved ornament|Armored boots with interlocking spiral decoration
Lionheart|crimson plate, gold borders, and lion emblems|A crowned helmet with a sculpted lion-like brow|A crimson cuirass bearing a large golden lion emblem|Crimson leggings decorated with gold lion motifs|Gold-trimmed boots with ornate crimson panels
"""),
]

# Current displayed name | new name | physical component description.
WEAPONS = """
Iron Sword|Iron Sword|A straight iron-colored blade with a simple crossguard and wrapped grip.
Cavalry Sword|Cavalry Sword|A long riding sword with a swept guard and narrow pointed blade.
Cutlass|Cutlass|A broad curved sword with a protective hand guard.
Amberwood Leafblade|Leaf Blade|A short sword whose broad blade follows a leaf-like outline.
Steppe Saber|Saber|A curved single-edged sword with a compact guard and decorated grip.
Rondel Dagger|Dagger|A narrow pointed dagger with a round guard and short grip.
Parrying Dagger|Parrying Dagger|A short defensive blade with an extended protective guard.
Gladius|Short Sword|A compact straight sword with a broad blade and rounded grip fittings.
Heavy Falchion|Heavy Sword|A heavy, broad-bladed sword with a pronounced cutting edge.
Rapier|Rapier|A slender thrusting sword surrounded by an elaborate hand guard.
Woodsman's Hatchet|Hatchet|A small wood-handled axe with a broad chopping head.
Bearded Axe|Bearded Axe|A one-handed axe with a long lower edge extending beneath its head.
Battle Axe|Battle Axe|A stout axe with a broad metal head and reinforced haft.
Sunmane Crescent Axe|Crescent Axe|An axe with a sweeping crescent-shaped cutting head.
Amberwood Tomahawk|Hand Axe|A compact axe with a decorated wooden handle.
Flanged Mace|Mace|A blunt metal weapon with raised flanges around its head.
War Hammer|War Hammer|A heavy hammer with a reinforced striking head and long grip.
Chain Morningstar|Spiked Flail|A spiked striking head suspended from a short chain and handle.
Blacksmith Maul|Forge Hammer|A broad-headed hammer with a stout wooden haft.
Crystal Cudgel|Crystal Mace|A short striking weapon capped with a faceted crystal head.
Short Spear|Short Spear|A compact spear with a pointed metal head and plain shaft.
Throwing Javelin|Javelin|A slender spear with a light shaft and narrow point.
Mariner's Trident|Trident|A long-handled weapon ending in three metal prongs.
Boar Spear|Boar Spear|A sturdy spear with a broad head and stopping lugs near the blade.
Hooked Spear|Hooked Spear|A pointed spear with a hooked side blade near its head.
Hand Crossbow|Hand Crossbow|A compact crossbow with a short stock and small bow arms.
Throwing Knife Fan|Knife Fan|A fan-shaped arrangement of short throwing blades.
War Chakram|Throwing Disc|A circular throwing weapon with a sharpened outer rim.
Focus Wand|Focus Wand|A short wand with a decorated grip and a bright focus at its tip.
Crescent Sickle|Crescent Sickle|A short-handled sickle with a curved crescent blade.
Greatsword|Greatsword|A long two-handed sword with a broad blade and extended grip.
Highland Claymore|Claymore|A large two-handed sword with a long crossguard and straight blade.
Flamberge Zweihander|Flamberge|A two-handed sword with a distinctive wavy cutting edge.
Executioner's Sword|Execution Sword|A broad, heavy sword with a long grip and substantial blade.
Flame Greatsword|Flame Greatsword|A large sword with flame-shaped blade details and warm-colored ornament.
Halberd|Halberd|A long polearm combining a spear point, axe blade, and rear hook.
Glaive|Glaive|A long shaft topped by a sweeping single-edged blade.
Poleaxe|Poleaxe|A long-handled weapon with an axe-like head and opposing striking face.
Steppe Bardiche|Long Axe|A tall pole-mounted axe with a long curved cutting blade.
Voulge|Pole Cleaver|A broad cleaver-like blade mounted along a long wooden pole.
Militia Pike|Pike|A long infantry spear with a narrow metal point.
War Scythe|War Scythe|A long polearm ending in a curved scythe-like blade.
Ranseur|Forked Spear|A long spear with side prongs beneath its central point.
Winged Partisan|Winged Spear|A broad spearhead with wing-like extensions at its base.
Heavy Boar Spear|Heavy Spear|A thick-shafted spear with a substantial cutting head.
Iron Sledgehammer|Sledgehammer|A large iron-colored striking head mounted on a long handle.
Lucerne Hammer|Pole Hammer|A long hammer with a compact striking face, rear spike, and pointed tip.
Great Maul|Maul|A large blunt weapon with a massive head and long two-handed grip.
Studded Club|Studded Club|A heavy club reinforced with rows of metal studs.
Quarterstaff|Quarterstaff|A long staff with a broad grip and reinforced ends.
Amberwood Longbow|Longbow|A tall wooden bow with long limbs and a simple central grip.
Sunmane Recurve Bow|Recurve Bow|A bow whose curved limb tips turn away from the archer.
Siege Crossbow|Siege Crossbow|A large crossbow with a heavy stock and broad bow assembly.
Repeating Crossbow|Repeating Crossbow|A crossbow fitted with a mechanical repeating assembly.
Hand Cannon|Hand Cannon|A compact cannon-like ranged weapon with a reinforced barrel and grip.
Arcane Double Staff|Double Staff|A decorated staff with elaborate fittings at both ends.
Amberwood Bowblade|Bowblade|A hybrid weapon combining a curved bow-like frame with edged limbs.
Sunmane Glaive|Crescent Glaive|A long polearm decorated with paired crescent-shaped blades.
Banner Spear|Banner Spear|A spear fitted with a hanging cloth banner beneath its head.
Storm Spear|Storm Spear|A decorated spear with a forked, tuning-fork-like head.
Segmented Whip Sword|Whip Sword|A sword built from linked blade segments along a flexible spine.
Chain Sickle|Chain Sickle|A curved sickle paired with a hanging length of chain.
Bladed War Fans|War Fans|A pair of folding fans built around sharpened metal leaves.
Lantern Flail|Lantern Flail|A hanging lantern-like striking head attached to a chain and handle.
Serpent Coil Whip|Serpent Whip|A coiled flexible weapon decorated with serpent-like forms.
Twinblade|Twinblade|A double-ended weapon with blades extending from both sides of its grip.
Circular Ringblade|Ringblade|A large open ring with a sharpened outer edge and an internal hand grip.
Polarity War Hammer|Magnetic Hammer|A large hammer with paired metal faces and contrasting decorative insets.
Gravity Anchor|Anchor Hammer|A heavy anchor-shaped weapon with a broad central grip.
Folding Crescent Bow|Folding Bow|A crescent-shaped bow built from articulated folding sections.
Rune Battle Gauntlet|Rune Gauntlet|An armored fighting glove decorated with inset rune-like markings.
Alchemist Cannon|Alchemy Cannon|A compact cannon with an elaborate chamber and alchemical-looking fittings.
Crystal Prism Staff|Prism Staff|A long staff crowned by a faceted crystal prism.
Clockwork Saw Lance|Saw Lance|A mechanical lance fitted with a toothed, saw-like cutting assembly.
Living Vine Bow|Vine Bow|A bow shaped from twisting vine-like limbs and branching decoration.
Phoenix Feather Spear|Phoenix Spear|A decorated spear with sweeping feather-like blades and warm golden ornament.
Void Glass Greatblade|Void Greatsword|A large dark blade edged with angular glass-like details.
Sun Chakram|Sun Disc|A circular throwing blade decorated with radiating sun-like points.
Echo Bell Hammer|Bell Hammer|A long-handled hammer whose heavy head incorporates a bell-like form.
Stormglass Shield Spear|Shield Spear|A spear combined with a broad shield-like guard near its grip.
Bellwatch Practice Bow|Practice Bow|A plain training bow with simple limbs and a wrapped hand grip.
Wayfarer Practice Sword|Practice Sword|A straightforward training sword with a simple guard and grip.
"""

SHIELDS = """
Wooden Round Shield|Round Shield|A round wooden shield with a central boss and reinforced rim.
Steel Heater Shield|Heater Shield|A pointed shield reinforced with a broad steel-colored rim.
Norman Kite Shield|Kite Shield|A long tapering shield with a rounded upper edge and narrow point.
Parrying Buckler|Buckler|A small hand-held shield with a prominent central boss.
Tower Shield|Tower Shield|A tall rectangular shield covering much of the bearer.
Crossbowman's Pavise|Pavise|A broad protective shield with a raised central ridge.
Highland Targe|Leather Shield|A round shield faced with decorated leather and metal fittings.
Legionary Scutum|Legion Shield|A tall curved shield with a broad rectangular outline.
Lantern Shield|Lantern Shield|A metal shield incorporating a small protected lantern housing.
Long Dueling Shield|Dueling Shield|A long narrow shield with extended points and a central hand grip.
Knightly Lion Shield|Lion Shield|An ornate shield carrying a raised lion motif.
Sunmane Shield|Hide Shield|A hide-faced shield with bronze-colored reinforcement.
Amberwood Shield|Bark Shield|A shield formed around overlapping bark-like layers.
Crystal Shield|Crystal Shield|An angular shield decorated with a large crystal-like centerpiece.
Barricade Shield|Barricade Shield|A rugged shield with broad protective panels and reinforced edges.
Mirror Shield|Mirror Shield|A polished shield with a bright reflective-looking face.
Dragon Scale Shield|Dragon Shield|A shield built around overlapping dragon-scale-like plates.
Ice Crystal Shield|Ice Shield|A pale shield with pointed, ice-like crystal details.
Molten Forge Shield|Forge Shield|A heavy shield decorated with warm metallic and forge-like forms.
Thorned Root Shield|Thorn Shield|A shield shaped from twisting root-like structures and pointed thorns.
"""

CAPE_NAMES = {
    "Four Gates Guard Cape": "Guard Cape", "Four Gates Guardian Cape": "Guardian Cape",
    "Amberwood Leaf Cape": "Leaf Cape", "Glasswarden Cape": "Crystal Cape",
    "Greyhaven Storm Cape": "Storm Cape", "Orun Rider Cape": "Rider Cape",
    "Ssarathi Frond Cape": "Frond Cape", "Green Cloak": "Green Cape",
    "Echo Practice Cape": "Echo Practice Cape", "Heat Practice Mantle": "Heat Practice Cape",
    "Cold Practice Mantle": "Cold Practice Cape", "Radiation Practice Mantle": "Radiation Practice Cape",
    "Gatherer's Cape": "Gatherer Cape", "Artificer's Cape": "Artificer Cape",
    "Cape of Renewal": "Renewal Cape", "Cape of Endurance": "Endurance Cape",
    "Mirror Cape": "Mirror Cape", "Piercer's Cape": "Piercer Cape",
    "Conjurer's Cape": "Conjurer Cape", "Bloodbound Cape": "Bloodbound Cape",
    "Eagle Eye Cape": "Eagle Eye Cape", "Standard Bearer's Cape": "Standard Cape",
}
CAPE_LOOKS = {
    "Guard Cape": "teal ceremonial cloth", "Guardian Cape": "ceremonial cloth and ornate edging",
    "Leaf Cape": "green cloth and a gold-colored border", "Crystal Cape": "purple cloth and pale blue edging",
    "Storm Cape": "storm-colored cloth", "Rider Cape": "riding-cloak proportions and warm-toned cloth",
    "Frond Cape": "green cloth and a dark contrasting border", "Green Cape": "plain green cloth",
}
COLOR_CAPES = {
    0: "Black", 1: "Blue", 2: "Slate", 3: "Brown", 4: "Taupe", 5: "Gray", 7: "Olive",
    8: "Purple", 9: "White", 10: "Fur", 11: "Gold", 12: "Red", 13: "Orange", 14: "Indigo",
    15: "Teal", 16: "Crimson", 17: "Moss", 18: "Steel", 19: "Cream", 20: "Burgundy",
    21: "Ash", 22: "Tan",
}
QUIVERS = {
    "Basic Quiver": ("Basic Quiver", "A simple arrow case with a shoulder strap."),
    "Hunter's Quiver": ("Hunting Quiver", "A hunting arrow case with a fitted shoulder strap."),
    "Bodkin Quiver": ("Piercing Quiver", "A reinforced arrow case for armor-piercing shots."),
    "Farshot Quiver": ("Range Quiver", "A long arrow case fitted for distant shots."),
    "Skirmisher's Quiver": ("Skirmish Quiver", "A broad arrow case with substantial strap fittings."),
    "Ember Quiver": ("Ember Quiver", "An arrow case with warm-colored, ember-like decoration."),
    "Frost Quiver": ("Frost Quiver", "An arrow case with cool, frost-colored decoration."),
    "Arcane Quiver": ("Arcane Quiver", "An arrow case with ornate arcane-looking fittings."),
}


def _rows(text: str):
    return [row.strip().split("|") for row in text.strip().splitlines() if row.strip()]


def armor_styles() -> tuple[dict, dict]:
    visuals, sets = {}, {}
    for starts, family, heads, bodies, legs, text in FAMILIES:
        for index, (name, appearance, *details) in enumerate(_rows(text)):
            assert len(details) == 4
            set_description = f"The {name} set combines {appearance}."
            sets[f"5:{starts[1] + index}"] = {"name": name, "family": family,
                                               "description": set_description}
            types = (heads[index], bodies[index], legs[index] if isinstance(legs, list) else legs, "Boots")
            for part, start, kind, detail in zip(PARTS, starts, types, details):
                key = f"{part}:{start + index}"
                visuals[key] = {"name": f"{name} {kind}", "description": f"{detail}. {set_description}",
                                "set_name": name, "set_description": set_description}
            if family == "Legendary":
                # Disabled historical alternatives remain distinct in old note replays.
                key = f"6:{107 + index}"
                visuals[key] = {"name": f"{name} Plate Boots",
                                "description": f"Articulated metal footwear from the {name} set. {set_description}",
                                "set_name": name, "set_description": set_description}
    return visuals, sets


def decorate_items(items: list[dict], registry: dict) -> dict:
    armor, sets = armor_styles()
    weapons = {old: (name, description) for old, name, description in _rows(WEAPONS)}
    shields = {old: (name, description) for old, name, description in _rows(SHIELDS)}
    visuals = {}
    for item in items:
        key = item["key"]
        old_name = item["name"]
        if key in armor:
            presentation = armor[key]
        elif old_name in weapons:
            name, text = weapons[old_name]
            context = " It can be combined with different armor sets."
            if name == "Phoenix Spear":
                context = " Its feather motif complements the Phoenix set."
            presentation = {"name": name, "description": text + context, "set_name": ""}
        elif old_name in shields:
            name, text = shields[old_name]
            presentation = {"name": name, "description": text + " A shared off-hand piece for mixed outfits.", "set_name": ""}
        elif old_name in CAPE_NAMES:
            name = CAPE_NAMES[old_name]
            look = CAPE_LOOKS.get(name, "a decorated fabric panel and a shoulder fastening")
            text = f"A draped cape with {look}. It can finish a matching or mixed outfit."
            if name not in CAPE_LOOKS and "concept" not in item["description"].casefold():
                # Perk/training facts are authored game data, distinct from visual flavor.
                text += " " + item["description"]
            presentation = {"name": name, "description": text, "set_name": ""}
        elif old_name in QUIVERS:
            name, text = QUIVERS[old_name]
            presentation = {"name": name, "description": text + " A reusable ranged accessory for any outfit. " + item["description"], "set_name": ""}
        else:
            raise ValueError(f"Missing authored gear presentation: {item['id']} {old_name}")
        item.update(presentation)
        item["icon"] = ICON_ROOT + key.replace(":", "_") + ".png"
        visuals.setdefault(key, {**presentation, "icon": item["icon"], "image_id": item["image_id"]})

    for key, model in registry["models"].items():
        if key in visuals:
            continue
        part, number = map(int, key.split(":"))
        if part == 2 and number in COLOR_CAPES:
            color = COLOR_CAPES[number]
            name = color + " Cape"
            description = f"A draped cape in {color.lower()} tones, with a shoulder fastening and a contrasting border. A finishing layer for any armor set."
            if color == "Fur":
                description = "A warm cape with a fur-like surface and a contrasting border. A finishing layer for cold-weather outfits."
            visuals[key] = {"name": name, "description": description, "set_name": "", "image_id": -1,
                            "icon": ICON_ROOT + key.replace(":", "_") + ".png"}
        else:
            raise ValueError(f"Missing visual-only presentation: {key} {model.get('name', '')}")
    return {"sets": sets, "visuals": visuals}
