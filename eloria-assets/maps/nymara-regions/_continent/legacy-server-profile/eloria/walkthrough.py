"""The Four Gates walkthrough: a popup-led introduction to the Nymara profile.

The walkthrough talks through the client's two native popup windows rather than
the NPC dialogue box, so it follows the player around the region instead of
holding them in front of someone. Choice panels use DISPLAY_POPUP, which
carries clickable options; teaching panels use chat channel 255, whose first
line becomes the window title.

This module holds the panel table and the pure progression rules. Everything
that touches a session lives in World, which calls `event()` as the player
plays and sends whatever `panel_for()` returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Character
from .map_layout import FOUR_GATES_ARRIVAL


# Persisted on the character. `STATE` counts panels and lands on DONE.
STATE = "nymara_intro"
SKIPPED = "nymara_intro_skipped"
STOPPED = "nymara_intro_stopped"
POPUPS = "nymara_intro_popups"

DONE = 99
FIRST_STAGE = 1
CHECKPOINT_STAGE = 8

# Chapter two: the five systems that reward a character rather than introduce
# one. It is a separate quest with its own state, so a player who never comes
# back never sees it.
ROADS_STATE = "nymara_roads"
ROADS_DEFERRED = "nymara_roads_deferred"
ROADS_STOPPED = "nymara_roads_stopped"
ROADS_FIRST_STAGE = 13
ROADS_DONE = 99
ROADS_ACHIEVEMENT = "The Long Roads"

# Chapter two opens only once a character can actually afford to act on any of
# it: a sigil, a bow and an auction listing in the same week.
ROADS_LEVEL = 20
ROADS_GOLD = 1000

# Popup ids 4000-4099 belong to the walkthrough. The client silently drops a
# popup whose id is already open, so the two choice panels take distinct ids.
INTRO_POPUP = 4000
CHECKPOINT_POPUP = 4001
ROADS_POPUP = 4002
POPUP_IDS = frozenset({INTRO_POPUP, CHECKPOINT_POPUP, ROADS_POPUP})

OPTION_ACCEPT = 1
OPTION_DECLINE = 2

# Marker ids 500-506 belong to the compatibility profile's tutorial.
MARKER_ID = 520

# The walkthrough is Nymara content; `four_gates` is absent from the
# compatibility profile's map table and so gates the whole feature.
HOME_MAP = "four_gates"
SPAWN = FOUR_GATES_ARRIVAL
# Open paving south of the native monument, with a clear approach from arrival.
PLAZA = (203, 190)
# A server tile is one metre; interaction reach retains its familiar distance.
REACH_RADIUS = 3

GUIDE_NPC = "Gate Warden Ilyon"
SAGE = "Sage"
SAGE_TARGET = 5
TORCH = "Torch"
STARTER_CREATURE = "river_otter"
FOOD_TARGET = 35

# Chapter two's subjects, each the cheapest reachable example of its system.
BOOK = "Book of Beginnings"
FIRST_SPELL = "Heal"
SUMMON_STONE_RECIPE = "Otter"
SCHOLAR_NPC = "Scholar Meret"
GOLD = "Gold Coins"


@dataclass(frozen=True)
class Panel:
    """One window, one lesson, one thing the player has to do to move on."""

    stage: int
    title: str
    body: tuple[str, ...]
    objective: str
    event: str = ""
    target: int = 1
    marker: tuple[int, int] | None = None
    marker_label: str = ""
    marker_npc: str = ""
    marker_role: str = ""
    grants: tuple[tuple[str, int], ...] = ()
    experience: tuple[tuple[str, int], ...] = ()
    popup_id: int = 0
    choices: tuple[tuple[int, str], ...] = ()

    @property
    def is_choice(self) -> bool:
        return self.event == "choice"


INTRO = Panel(
    stage=1,
    title="Nymara",
    body=(
        "Twelve regions ring the lake. Mirrorhold counts its halls in "
        "reflections, Crownwater keeps a drowned king, the Whitehorn Range "
        "keeps the cold honest, and the Grey Moors keep whatever the barrows "
        "were given.",
        "Eight peoples tell eight different stories about how the world began. "
        "All eight agree on one thing: the roads meet here, at Four Gates.",
        "You arrived carrying your name and nothing else. Gate Warden Ilyon "
        "will not ask you for more than that.",
        "Shall someone walk you through your first hour?",
    ),
    objective="Decide whether to be shown around Four Gates.",
    event="choice",
    popup_id=INTRO_POPUP,
    choices=((OPTION_ACCEPT, "Show me the roads."),
             (OPTION_DECLINE, "I will find my own way.")),
)

CHECKPOINT = Panel(
    stage=CHECKPOINT_STAGE,
    title="Halfway",
    body=(
        "You can walk it, read it, gather it, store it, and make from it. What "
        "is left is the part of Nymara that can hurt you, and the roads that "
        "lead out of Four Gates.",
    ),
    objective="Decide whether to carry on past the peaceful half.",
    event="choice",
    popup_id=CHECKPOINT_POPUP,
    choices=((OPTION_ACCEPT, "Keep going."),
             (OPTION_DECLINE, "That is enough for now.")),
    grants=(("Militia Arming Sword", 1), ("Wooden Round Shield", 1),
            ("Bonehook Jerkin", 1), ("Bread", 3)),
)

PANELS: dict[int, Panel] = {panel.stage: panel for panel in (
    INTRO,
    Panel(
        stage=2,
        title="Walking",
        body=(
            "Click any tile to walk there. Your steps route around water, "
            "walls, and anything else you cannot cross.",
            "Press Tab for the map. The blue mark is you — click anywhere "
            "on it to travel across the region.",
            "The compass sits at the top right. Click it to read your "
            "coordinates, and write down the ones worth finding twice. Nymara "
            "does not label its roads for you.",
            "A marker now stands in the central plaza. Walk to it.",
        ),
        objective="Walk to the marker in the central plaza.",
        event="reach",
        marker=PLAZA,
        marker_label="The central plaza",
        experience=(("overall", 60),),
    ),
    Panel(
        stage=3,
        title="The Gate Warden",
        body=(
            "Ilyon has held this gate long enough to stop being impressed by "
            "arrivals. Follow his marker, walk close and click him to talk.",
            "Anything a person asks of you is written into your quest log, so "
            "you never have to remember an errand exactly as it was worded.",
            "While you are here: what you type reaches everyone standing near "
            "you. Use #jc to join a numbered channel, then put @ in front of a "
            "message to send it there instead.",
        ),
        objective=f"Talk to {GUIDE_NPC}.",
        event="talk",
        marker_npc=GUIDE_NPC,
        marker_label=GUIDE_NPC,
        grants=(("Hatchet", 1), ("Wood Plank", 1), ("Cloth Roll", 1)),
        experience=(("overall", 60),),
    ),
    Panel(
        stage=4,
        title="What the Board Says",
        body=(
            "Not everything that answers you is a person. Boards, caches, "
            "forges, and waygates all respond to a click once you are standing "
            "close enough.",
            "The information board south of the plaza records the roads, "
            "the current dangers, and unclaimed work. Follow its marker and click it.",
        ),
        objective="Read the marked information board south of the plaza.",
        event="information",
        marker_role="information",
        marker_label="Information board",
        experience=(("overall", 60),),
    ),
    Panel(
        stage=5,
        title="Take Only What You Can Carry",
        body=(
            "Move onto a resource until the cursor becomes a pickaxe, then "
            "click once. You keep gathering until you stop, your pack fills, "
            "or an event interrupts you. Click again to restart after an interruption.",
            "Harvesting returns experience. Keep food above zero to recover "
            "health and ether. Gathering something above your level is slower, not "
            "forbidden.",
            f"Bring back five {SAGE}. A marker points at the nearest patch.",
        ),
        objective=f"Harvest {SAGE_TARGET} {SAGE}.",
        event="harvest",
        target=SAGE_TARGET,
        marker_label=SAGE,
        experience=(("harvesting", 200),),
    ),
    Panel(
        stage=6,
        title="The Cache",
        body=(
            "Weight is real here. Carry determines how much fits in your pack, "
            "and a full pack refuses to accept anything more.",
            "The wayfarer's cache takes what you are not using. Whatever you "
            "leave in one cache can be drawn from any other cache in Nymara.",
            "Follow the marker to Cache Keeper Dellin, open storage, and deposit the sage.",
        ),
        objective=f"Store {SAGE_TARGET} {SAGE}.",
        event="storage",
        marker_npc="Cache Keeper Dellin",
        marker_label="Cache Keeper Dellin",
        target=SAGE_TARGET,
        experience=(("overall", 80),),
    ),
    Panel(
        stage=7,
        title="Made, Not Found",
        body=(
            "Most of what you will use is made rather than found. Ilyon left "
            "you a hatchet, a plank, and a roll of cloth.",
            "Follow the field station marker, open your manufacture window, put the "
            "plank and the cloth into it, and make a torch.",
            "Mixing spends food. Positive food also keeps your health and "
            "ether recovering while you travel.",
            "If a failed mix uses up the supplies, Quartermaster Perrin Lock "
            "sells replacement planks, cloth and tools. Bettany Orl buys Sage "
            "and Reed and sells Bread on the plaza.",
        ),
        objective=f"Make a {TORCH}.",
        event="mix",
        marker_role="crafting_station",
        marker_label="Field station",
        experience=(("manufacturing", 200),),
    ),
    CHECKPOINT,
    Panel(
        stage=9,
        title="Teeth on the Road",
        body=(
            "Put on what Ilyon gave you. Double-click a weapon or a piece of "
            "armour in your pack, or drag it onto yourself.",
            "Click a creature to attack it. Your health is the bar beneath "
            "your name and the creature's is beneath its own; both of you keep "
            "swinging until one stops.",
            "If you fall, you wake at the Four Gates beam a few seconds later "
            "with your pack untouched. Dying here costs you time, not "
            "property.",
            "Otters work the water meadows past the field edge. Follow the "
            "habitat marker, look nearby for an Otter, and take one.",
        ),
        objective="Kill an Otter.",
        event="kill",
        marker_label="Otter habitat",
        experience=(("attack", 150), ("defense", 150)),
    ),
    Panel(
        stage=10,
        title="What It Leaves",
        body=(
            "What dies leaves a bag on the ground. Click it to open, then Get "
            "All to empty it. Walk away and it closes itself.",
            "Kills also pay attack and defence experience, and the server "
            "keeps a private tally of everything you have ever killed.",
            "Empty the otter's bag.",
            "With Auto-gather enabled, collecting the drops directly into your "
            "pack also completes this lesson. If the bag is gone, loot another kill.",
        ),
        objective="Empty the bag your kill left behind.",
        event="loot",
        experience=(("overall", 80),),
    ),
    Panel(
        stage=11,
        title="Bread and Breath",
        body=(
            "Your food falls by one every minute. While it stays above zero "
            "you recover health and mana on your own; at zero you recover "
            "nothing and begin losing ground.",
            "Eat by double-clicking food in your pack. One shared cooldown "
            "governs how soon food will help you again, so eating twice in a "
            "row wastes the second meal.",
            f"Eat until your food reads {FOOD_TARGET} or better.",
        ),
        objective=f"Raise your food to {FOOD_TARGET}.",
        event="food",
        marker_npc="Bettany Orl",
        marker_label="Bettany Orl — food",
        target=FOOD_TARGET,
        experience=(("overall", 80),),
    ),
    Panel(
        stage=12,
        title="The Roads Out",
        body=(
            "Four roads meet here, and the gates east and west will put you on "
            "them.",
            "Toran posts work against whatever is thinning the herds. Vestra, "
            "in Mirrorhold, pays for gathering. Nima Vey keeps the Exchange, "
            "where the escrow is real and the listings outlast you.",
            "Nothing further will be explained. Take a road.",
        ),
        objective="Leave Four Gates through one of its gates.",
        event="travel",
        marker_label="Road out of Four Gates",
        experience=(("overall", 120),),
    ),
)}

FINALE = (
    "The Road Is Yours",
    "You can walk it, read it, gather it, store it, make from it, fight on it, "
    "and feed yourself along the way. That is the whole of what anyone can "
    "teach you in an hour.",
    "Ilyon has written your name into the Four Gates register. The rest of "
    "Nymara has not heard of you yet.",
)

DECLINED = (
    "As You Like",
    "The roads are marked and the gate is open.",
    f"If you change your mind, {GUIDE_NPC} will start the walkthrough at any "
    "time, or type #tutorial.",
)

STOPPED_HERE = (
    "Enough For Now",
    "The peaceful half is yours and the rest will keep.",
    f"{GUIDE_NPC} will pick this up again whenever you want it, or type "
    "#tutorial.",
)

ACHIEVEMENT = "Four Gates Register"



ROADS_INTRO = Panel(
    stage=ROADS_FIRST_STAGE,
    title="The Longer Roads",
    body=(
        "You have walked the plaza and come back alive. What remains are five "
        "things Nymara does not hand out at the gate: what is written down, "
        "what is drawn in sigils, what kills at a distance, what fights in "
        "your place, and what other people will pay for.",
        "None of it is required. Each one takes longer than an hour and costs "
        "more than you are carrying.",
        f"{SCHOLAR_NPC} keeps the reading. The rest you will find on the "
        "roads out.",
    ),
    objective="Decide whether to learn the long way.",
    event="choice",
    popup_id=ROADS_POPUP,
    choices=((OPTION_ACCEPT, "Teach me the long way."),
             (OPTION_DECLINE, "Later.")),
)

ROADS_PANELS: dict[int, Panel] = {panel.stage: panel for panel in (
    ROADS_INTRO,
    Panel(
        stage=14,
        title="What Is Written Down",
        body=(
            "Knowledge is not something you are told. It is read slowly, in "
            "the background, while you get on with other things.",
            "Start a book and you read at your Rationality in pages a minute "
            "— but only while your food is above zero. A hungry scholar "
            "learns nothing.",
            "Type #research to see what you are reading and how much is left, "
            "and #know to see what you have already learned. Recipes you have "
            "not read for will refuse to be mixed at all.",
            f"{SCHOLAR_NPC} sells the {BOOK} for 25 Gold Coins. Follow his marker, "
            "buy it, and use it from your inventory. Start it, then carry on with the "
            "rest of this. It will finish while you work.",
        ),
        objective=f"Begin reading the {BOOK}.",
        event="read",
        marker_npc=SCHOLAR_NPC,
        marker_label=SCHOLAR_NPC,
        experience=(("overall", 150),),
    ),
    Panel(
        stage=15,
        title="Sigils",
        body=(
            "A spell is not a word. It is a set of sigils you own permanently, "
            "a handful of reagents you spend, and ether you can afford to use.",
            "Every reagent does one of three jobs. A catalyst supplies the raw "
            "power, a resonant decides what the spell does, and an anchor "
            "decides who it reaches and how. Change the anchor and the same "
            "spell finds a different target.",
            "Buy Change and Move from Sigil Keeper Ansa at 400 Gold Coins each. "
            "She also sells Heal's reagents: one Life Distillate and one Woven "
            "Charm per cast. Withdraw gold from Dellin if it is stored.",
            "Choose Power 1 and cast Heal. Higher power makes the same spell stronger; "
            "there are no separate Greater Heal or Greater Poison spells.",
            "Early casts often fail. A failed cast keeps the reagents but spends ether. "
            "Keep food positive, let your ether recover, and try again.",
            "A base name affects you. Target selects one actor. Allies reaches your "
            "nearby party or guild; Burst affects an area. Match Magic, Heat, Cold "
            "and Radiation Wards to incoming damage. Dispel removes harmful effects.",
            "Later, Transmute turns selected inventory items into gold: rarer items "
            "need more power. Recall returns to Four Gates at Power 1–4 and opens "
            "a choice of map portal entrances at Power 5. The encyclopedia explains both.",
        ),
        objective=f"Cast {FIRST_SPELL}.",
        event="cast",
        marker_npc="Sigil Keeper Ansa",
        marker_label="Sigil Keeper Ansa",
        grants=(("Amberwood Yew Longbow", 1), ("Arrow", 40)),
        experience=(("magic", 300),),
    ),
    Panel(
        stage=16,
        title="At a Distance",
        body=(
            "A bow will not fire at something standing next to you. Ranging "
            "needs at least four tiles between you and whatever you are "
            "shooting at.",
            "Equip a bow and its ammunition together — one without the other "
            "does nothing at all, and arrows will not feed a crossbow.",
            "Every shot spends ammunition. Early shots often miss, so you may "
            "need more than the first quiver. Bettany buys Sage and Reed if you "
            "need gold for replacement arrows.",
            "There is a longbow and a quiver in your pack. Put an arrow "
            "into something before it reaches you. The marker points to an "
            "otter habitat. Perrin Lock sells replacement arrows.",
        ),
        objective="Kill something at range.",
        event="ranged_kill",
        marker_label="Otter habitat",
        experience=(("ranging", 300),),
    ),
    Panel(
        stage=17,
        title="Borrowed Teeth",
        body=(
            "Summoning is a making skill before it is a fighting one. The "
            "starter recipes summon directly when the mix succeeds.",
            "What you can call up is limited by your summoning level and by "
            "what the ingredients cost. A creature that dies must be summoned again.",
            "Later, at summoning level thirty, you can also tell your "
            "creatures what to do — attack what you attack, leave your "
            "opponent alone, or attack nothing at all. Until then they decide "
            "for themselves.",
            "Choose Otter in the manufacture window. Mix one Bones, "
            "two Reed and one Aether Salt with at least five ether and positive food. "
            "Reed grows at the marker; Perrin sells Bones and Ansa sells Aether Salt.",
        ),
        objective="Summon a creature.",
        event="summon",
        marker_label="Reed",
        experience=(("summoning", 300),),
    ),
    Panel(
        stage=18,
        title="The Exchange",
        body=(
            "Nima Vey keeps the Exchange. It is not a shop — it is a ledger "
            "between players, and the server holds both sides of every "
            "bargain.",
            "#auction sell takes an inventory slot, a quantity and a price per "
            "unit, and puts the goods into escrow. They stay listed for a year "
            "whether or not you ever log in again.",
            "#auction browse reads the listings and #auction buy takes them. "
            "What you earn waits in a separate balance until #auction collect "
            "brings it home, and anything cancelled or expired comes back to "
            "you rather than to whoever noticed first.",
            "Sell something you gathered.",
        ),
        objective="List one item on the Exchange.",
        event="auction",
        marker_npc="Nima Vey",
        marker_label="Nima Vey — Exchange",
        experience=(("overall", 200),),
    ),
)}

ROADS_FINALE = (
    "The Long Roads",
    "You can read, cast, shoot, summon, and trade. None of it was necessary "
    "and all of it compounds.",
    "Use #research to check Meret's book. Keep your food above zero until it "
    "finishes. Then find out what the other eleven regions think they know.",
)

ROADS_DECLINED = (
    "Later, Then",
    "The five roads keep. None of them is going anywhere.",
    f"{GUIDE_NPC} will start this whenever you ask, or type #tutorial.",
)


def roads_stage_of(character: Character) -> int:
    return int(character.quest_state.get(ROADS_STATE, 0))


def roads_is_active(character: Character) -> bool:
    if character.quest_state.get(ROADS_STOPPED):
        return False
    stage = roads_stage_of(character)
    return ROADS_FIRST_STAGE < stage < ROADS_DONE


def roads_panel_for(character: Character) -> Panel | None:
    return ROADS_PANELS.get(roads_stage_of(character))


def held_gold(character: Character) -> int:
    """Count the entry budget in both the pack and storage."""
    return (character.inventory.get(GOLD, 0)
            + character.storage.get(GOLD, 0))


def roads_ready(character: Character) -> bool:
    """Chapter two waits until its lessons are affordable, not merely unlocked."""
    return (int(character.quest_state.get(STATE, 0)) == DONE
            and not roads_stage_of(character)
            and not character.quest_state.get(ROADS_DEFERRED)
            and character.skills["overall"] >= ROADS_LEVEL
            and held_gold(character) >= ROADS_GOLD)


def roads_matches(panel: Panel, event: str, detail: str) -> bool:
    if panel.event != event:
        return False
    expected = {
        "read": BOOK.casefold(),
        "cast": FIRST_SPELL.casefold(),
    }.get(event)
    return expected is None or detail.casefold() == expected

def stage_of(character: Character) -> int:
    return int(character.quest_state.get(STATE, 0))


def is_active(character: Character) -> bool:
    """True while the walkthrough should react to what the player does."""
    if character.quest_state.get(SKIPPED) or character.quest_state.get(STOPPED):
        return False
    stage = stage_of(character)
    return FIRST_STAGE < stage < DONE


def wants_popups(character: Character) -> bool:
    """Popups are the default; a player may switch to console text instead."""
    return bool(int(character.quest_state.get(POPUPS, 1)))


def panel_for(character: Character) -> Panel | None:
    return PANELS.get(stage_of(character))


def progress_key(stage: int) -> str:
    return f"{STATE}_progress_{stage}"


def progress(character: Character, stage: int) -> int:
    return int(character.quest_state.get(progress_key(stage), 0))


def matches(panel: Panel, event: str, detail: str) -> bool:
    """Decide whether a gameplay event belongs to the panel now showing."""
    if panel.event != event:
        return False
    expected = {
        "talk": GUIDE_NPC.casefold(),
        "harvest": SAGE.casefold(),
        "storage": SAGE.casefold(),
        "mix": TORCH.casefold(),
        "kill": STARTER_CREATURE.casefold(),
    }.get(event)
    return expected is None or detail.casefold() == expected


def record(character: Character, panel: Panel, amount: int = 1, *,
           key: str | None = None) -> bool:
    """Bank progress toward a panel; return True once it is complete.

    Counting events accumulate, level-style events report an absolute value,
    and single-shot events complete on the first matching report.
    """
    key = key or progress_key(panel.stage)
    if panel.event == "harvest":
        current = int(character.quest_state.get(key, 0)) + amount
    elif panel.event in {"storage", "food"}:
        # Both report where the player stands now, not what just changed.
        current = amount
    else:
        current = panel.target
    character.quest_state[key] = current
    return current >= panel.target


@dataclass(frozen=True)
class Chapter:
    """One walkthrough: its own state key, panels, endings and achievement."""

    state: str
    panels: dict[int, Panel]
    first_stage: int
    skipped: str
    stopped: str
    finale: tuple[str, ...]
    declined: tuple[str, ...]
    stopped_text: tuple[str, ...]
    achievement: str
    matches: object

    def stage_of(self, character: Character) -> int:
        return int(character.quest_state.get(self.state, 0))

    def is_active(self, character: Character) -> bool:
        if character.quest_state.get(self.skipped) \
                or character.quest_state.get(self.stopped):
            return False
        return self.first_stage < self.stage_of(character) < DONE

    def panel_for(self, character: Character) -> Panel | None:
        return self.panels.get(self.stage_of(character))

    def progress_key(self, stage: int) -> str:
        return f"{self.state}_progress_{stage}"

    def progress(self, character: Character, stage: int) -> int:
        return int(character.quest_state.get(self.progress_key(stage), 0))


FOUR_GATES = Chapter(
    state=STATE, panels=PANELS, first_stage=FIRST_STAGE,
    skipped=SKIPPED, stopped=STOPPED, finale=FINALE, declined=DECLINED,
    stopped_text=STOPPED_HERE, achievement=ACHIEVEMENT, matches=matches)

LONG_ROADS = Chapter(
    state=ROADS_STATE, panels=ROADS_PANELS, first_stage=ROADS_FIRST_STAGE,
    skipped=ROADS_DEFERRED, stopped=ROADS_STOPPED, finale=ROADS_FINALE,
    declined=ROADS_DECLINED, stopped_text=ROADS_DECLINED,
    achievement=ROADS_ACHIEVEMENT, matches=roads_matches)

CHAPTERS = (FOUR_GATES, LONG_ROADS)

POPUP_CHAPTERS = {panel.popup_id: chapter
                  for chapter in CHAPTERS
                  for panel in chapter.panels.values() if panel.popup_id}


def active_chapter(character: Character) -> Chapter | None:
    """The chapter currently waiting on the player, if any."""
    for chapter in CHAPTERS:
        stage = chapter.stage_of(character)
        if stage == chapter.first_stage and not character.quest_state.get(
                chapter.skipped):
            return chapter
        if chapter.is_active(character):
            return chapter
    return None
