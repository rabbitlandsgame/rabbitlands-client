"""Render the authored Markdown as an offline illustrated storyboard collection.

Run with Python 3.10+; no dependencies. Markdown remains the source of prose.
The diagrams below are editorial blocking plans, never gameplay screenshots.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Nodes in each frame show the spatial/action relationship to test. They do
# not invent additional gameplay objectives; the Markdown defines those.
BOOKS = [
    dict(slug="summoning", topic="Summoning", title="The Missing Caravan", place="Reedway Halt", size="128 × 128", duration="30–40 min", color="#b2ce96", group="Specialization", gates=["Reed Pen", "Axle Lane", "Rival Yard", "Return Road"], center="Hitching ring", hook="Reunite three wagons with help you know how to command.", scenes=[
        [("person","Keeper","borrowed profile"),("book","Summoning","read requirements"),("gate","Level 30","behavior access")],
        [("box","Ingredients","Bones · Reed · Salt"),("spark","Real mix","ether consumed"),("summon","Owned otter","actor, not an item")],
        [("person","Player","walk the lane"),("summon","Companion","ordinary movement"),("cart","Wagon latch","player uses object")],
        [("person","Player","choose opponent"),("enemy","Raider","shared target"),("summon","Companion","joins this fight")],
        [("enemy","Engaged","summon blocked"),("shield","Disengage","normal flee"),("summon","New call","outside combat")],
        [("summon","Healthy summon","quiet pen"),("clock","Decay tick","ordinary timer"),("book","Prepare","read remaining life")],
        [("summon","Your summon","select a filter"),("spark","Hostile summon","summoned only"),("enemy","Ordinary enemy","exclude summons")],
        [("summon","Your summon","attack at will"),("party","Party summon","excluded"),("enemy","Hostile actor","eligible target")],
        [("box","Preparation","costs · behavior"),("enemy","Changed yard","ownership differs"),("cart","Final wagon","fit the axle")],
        [("cart","Three wagons","caravan reunited"),("book","Real profile","restore belongings"),("gate","Your next call","actual requirement")],
    ]),
    dict(slug="crafting", topic="Production & research", title="The Broken Workshop", place="Cinderbank Works", size="128 × 128", duration="35–45 min", color="#e5b584", group="Specialization", gates=["Raw Yard", "Reading Room", "Foundry", "Dispatch"], center="Work Court", hook="Turn scattered materials and unfinished knowledge into a working workshop.", scenes=[
        [("book","Sword order","trace the recipe"),("ingot","Iron Bar","intermediate"),("ore","Ore + coal","first requirements")],
        [("ore","Real resources","reachable objects"),("box","Pack","capacity + tools"),("store","Storage","only needed stock")],
        [("ore","3 ore + 2 coal","current recipe"),("bench","Mix One","ordinary outcome"),("ingot","One bar","actual output")],
        [("book","Steel Smelting","start research"),("clock","Real minute","positive food"),("bench","Parallel work","finish the sword")],
        [("ingot","Bounded stock","enough attempts"),("bench","Mix All · stop","count successes"),("sword","Sword","usable product")],
        [("store","Storage stock","nearby access"),("bench","Source toggle","tool in pack"),("gate","Distant bench","rejection + return")],
        [("book","Queue plan","intermediate first"),("bench","Start · stop","edit remaining work"),("ingot","Completed goods","persist separately")],
        [("book","Knowledge ready","real completion"),("ingot","Steel Bar","all requirements"),("bench","Pump brace","nearby object use")],
        [("book","Changed order","shield + torch"),("store","Find the stock","tool is missing"),("cart","Delivery","accept valid routes")],
        [("bench","Working forge","orders fulfilled"),("book","Real knowledge","research restored"),("gate","Next recipe","actual blocker")],
    ]),
    dict(slug="character-development", topic="Character development", title="The Wraith's Three Trials", place="Echo Court", size="112 × 112", duration="30–40 min", color="#b5b4e5", group="Specialization", gates=["Weight Walk", "Keeper's Pen", "Guard's Court", "Unwritten Road"], center="Three lanterns", hook="Try three possible futures before spending on the one you will keep.", scenes=[
        [("person","Real character","unspent choices"),("book","Practice ledger","declared budget"),("gate","Confirm · cancel","no mutation")],
        [("box","Too much load","real rejection"),("spark","Attribute point","capacity changes"),("cart","Porter delivery","now within limit")],
        [("gate","Animal Nexus","eligibility blocked"),("spark","Practice spend","not skill XP"),("summon","Actual summon","permission used")],
        [("bench","Do the work","valid activity"),("spark","Skill + Overall","actual XP"),("book","Point budget","threshold matters")],
        [("book","Read the perk","cost + condition"),("coin","Real purchase","borrowed budget"),("enemy","Matching trial","effective modifier")],
        [("coin","Remaining budget","finite resources"),("gate","Blocked tier","cost or conflict"),("book","Choose or save","valid alternative")],
        [("shield","Worn effect","registered gear"),("book","Owned tier","stays unchanged"),("box","Unequip","effect changes")],
        [("gem","Removal stone","specific rule"),("book","Real mutation","refund + restriction"),("spark","Practice reset","clearly disclosed")],
        [("book","Fresh budget","choose a plan"),("party","Three needs","multiple routes"),("cart","Crossing solved","use chosen change")],
        [("spark","Three lanterns","possibilities tried"),("person","Real character","choices preserved"),("gate","Your decision","saving is valid")],
    ]),
    dict(slug="equipment", topic="Equipment & maintenance", title="The Quartermaster's Test", place="Wayfarer Bastion", size="128 × 128", duration="30–40 min", color="#9fbfd0", group="Preparation", gates=["Fitting Hall", "Weather Yard", "Repair Bench", "Rescue Road"], center="Quarter Court", hook="Prepare three packs for the road, its hazards and the trip home.", scenes=[
        [("book","Route brief","what is needed?"),("shield","Item details","benefit + cost"),("box","Three packs","effective kit")],
        [("sword","One hand","with shield"),("shield","Slot rules","inspect changes"),("sword","Two hands","excludes shield")],
        [("gate","Requirement","actual blocker"),("book","Inspect","read the reason"),("shield","Usable kit","valid alternative")],
        [("shield","First armor","effective stats"),("enemy","Physical lane","ordinary attacks"),("shield","Second armor","compare modifiers")],
        [("spark","Heat threat","typed attack"),("shield","Protection","matching modifier"),("person","Test + recover","no forced damage")],
        [("bow","Bow + ammo","real aimed shot"),("enemy","Close contact","normal engagement"),("sword","Weapon swap","valid melee kit")],
        [("sword","Copy A","pre-worn instance"),("book","Exact identity","read durability"),("sword","Copy B","same name")],
        [("book","Current slot","verify selection"),("coin","Repair cost","immediate if funded"),("sword","Restored item","other copy unchanged")],
        [("book","Changed hazard","new damage type"),("box","Chosen pack","load + maintenance"),("party","Rescue","several kits work")],
        [("box","Packs ready","team departs"),("shield","Original gear","exact restoration"),("book","Next improvement","activity first")],
    ]),
    dict(slug="trading", topic="Trade & marketplace", title="The First Commission", place="Lantern Exchange", size="112 × 112", duration="30–40 min", color="#dcc18a", group="Preparation", gates=["Merchant Row", "Trading Awning", "Exchange Desk", "Dispatch"], center="Ledger Court", hook="Fulfill a real order by checking stock, reviewing exchanges and collecting proceeds.", scenes=[
        [("book","Commission","exact shortfall"),("store","Owned stock","check before buying"),("coin","Practice budget","total costs")],
        [("person","Merchant","actual stock"),("coin","Quantity × price","buy then sell"),("box","Receipt","goods + coin delta")],
        [("person","Player","request trade"),("party","Pella · scripted","reciprocal acceptance"),("book","Trade session","correct participants")],
        [("box","Your offer","exact quantity"),("book","Review twice","changes reset ready"),("coin","Their offer","mutual commitment")],
        [("book","Reject offer","no net transfer"),("store","Near Storage","destination rules"),("box","Receive there","find actual goods")],
        [("book","Two listings","unit + total"),("coin","Buy All / partial","different requests"),("box","Purchase","actual escrow")],
        [("box","Exact stock","verify current slot"),("book","Your listing","goods held"),("store","Cancel + collect","return escrow")],
        [("party","Buyer","actual transaction"),("coin","Pending proceeds","not yet in pack"),("box","Collect","capacity matters")],
        [("book","Revised order","changed quantities"),("store","Procurement","choose valid source"),("cart","Dispatch","budget reconciled")],
        [("book","Practice ledger","settle all claims"),("coin","Real balance","fully restored"),("gate","Public exchange","no guaranteed buyer")],
    ]),
    dict(slug="parties", topic="Parties & gauntlets", title="The Sealed Road", place="Waystone Yard", size="144 × 144", duration="35–45 min + optional duo", color="#98cfc9", group="Cooperation", gates=["Assembly", "Split Road", "Captain's Court", "Vault Walk"], center="Muster Court", hook="Gather the people who will enter, choose a road and bring everyone to their share.", scenes=[
        [("person","Player","invite by name"),("party","Ise · scripted","actual acceptance"),("book","Party roster","live membership")],
        [("book","Party chat","correct audience"),("party","Members","health + location"),("gate","Assembly","arrive together")],
        [("party","Bran is far","party ≠ participant"),("person","Keeper","nearby intake"),("gate","Valid roster","actual start check")],
        [("book","Challenge menu","inspect scale"),("party","Strongest member","actual base level"),("clock","Run begins","real time limit")],
        [("enemy","First wave","clear the leg"),("gate","Chosen fork","other route closes"),("party","Trailing member","path stays reachable")],
        [("party","Wounded Ise","eligible recipient"),("spark","Useful support","actual restoration"),("enemy","Encounter","ordinary resolution")],
        [("person","Current leader","promote Ise"),("party","New leader","actual authority"),("book","Transfer back","transient group")],
        [("enemy","Court quiet","boss + remaining"),("box","Cache","each claims once"),("party","Every member","capacity preserved")],
        [("party","Changed roster","check readiness"),("gate","New short road","choose + support"),("box","Individual shares","real outcomes")],
        [("gem","Waystone","actual exit"),("person","Real character","practice group ends"),("party","Optional duo","human validation")],
    ]),
    dict(slug="worship", topic="Gods & worship", title="The Unlit Shrine", place="Votive Crossing", size="112 × 112", duration="30–40 min", color="#d9bf91", group="Optional paths", gates=["Hall of Names", "Offering Garden", "Blessing Walk", "Pilgrim Road"], center="Lamp Court", hook="Rehearse an oath, fulfill its terms and discover what is yours to choose.", scenes=[
        [("book","Patron terms","skill + enemies"),("person","Borrowed pilgrim","voluntary entry"),("gate","Neutral exit","no oath required")],
        [("spark","Join Lucaa","starts at rank −2"),("ore","Real harvest","eligible XP"),("book","−8% modifier","not an instant bonus")],
        [("box","Flowers in pack","wrong source"),("store","Deposit shortfall","exact quantity"),("spark","Offering","rank −2 → −1")],
        [("ore","A few roses","actual harvest"),("store","Complete stock","borrowed remainder"),("spark","Next offering","rank −1 → 0")],
        [("ore","Same resource","matched conditions"),("store","Coal offering","rank 0 → +1"),("book","Changed XP","associated skill")],
        [("spark","Lucaa","current affiliation"),("gate","Unolas rejected","real conflict"),("book","Other choices","three-god maximum")],
        [("store","Two offerings","reach rank 3"),("coin","Blessing price","practice gold"),("spark","Temporary skill","base unchanged")],
        [("ore","Use the blessing","real activity"),("clock","Normal tick","temporary decay"),("book","Base + standing","remain distinct")],
        [("book","Changed request","inventory source"),("store","Offer or decline","read conditions"),("spark","Renounce + rejoin","practice rank resets")],
        [("spark","Shrines lit","pilgrimage complete"),("person","Real worship","original state"),("gate","Free choice","neutral departure")],
    ]),
    dict(slug="pvp", topic="PvP & zone rules", title="The Chalk Circle", place="Chalkwatch Yard", size="128 × 128", duration="30–40 min + optional spar", color="#d4a4a0", group="Optional paths", gates=["Boundary Walk", "Measured Ring", "Retreat Yard", "Open Choice"], center="Chalk Court", hook="Read the ground, choose an engagement and learn how to leave one.", scenes=[
        [("person","Vale","practice agreement"),("shield","Borrowed kit","private conditions"),("gate","Free exit","voluntary entry")],
        [("person","Outside zone","attack rejected"),("gate","Shared boundary","both positions"),("enemy","Rook · scripted","eligible engagement")],
        [("book","A/D cap","limited normalization"),("shield","Other modifiers","still matter"),("enemy","Real attacks","effective stats")],
        [("sword","Melee lane","reach + approach"),("bow","Ranged option","ammo + range"),("person","Reposition","legal ground")],
        [("enemy","Engaged","flee can fail"),("person","Normal retreat","combat resolves"),("shield","Refuge","useful recovery")],
        [("enemy","One opponent","single-combat rule"),("party","Two rivals","multi-combat zone"),("person","Simplify the fight","remove or retreat")],
        [("shield","Matching ward","specific protection"),("spark","Hostile spell","eligible player"),("book","Cancel + retry","right recipient")],
        [("book","Read loss rules","optional rehearsal"),("enemy","Actual defeat","practice value only"),("box","Reconcile kit","no random bag gate")],
        [("book","Changed rules","read before acting"),("enemy","Engage or bypass","valid decision"),("cart","Dispatch delivered","survival matters")],
        [("shield","Clean exit","no delayed damage"),("person","Original character","belongings restored"),("gate","Beyond the chalk","rules may differ")],
    ]),
]


def esc(value):
    return html.escape(str(value), quote=True)


def inline(value):
    # Protect code and links before processing emphasis; all raw HTML is escaped.
    tokens = []
    def hold(markup):
        tokens.append(markup)
        return f"\x00{len(tokens)-1}\x00"
    value = re.sub(r"`([^`]+)`", lambda m: hold(f"<code>{esc(m[1])}</code>"), value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: hold(f'<a href="{esc(m[2])}">{esc(m[1])}</a>'), value)
    value = esc(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m[1])], value)


def anchor(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def markdown(source):
    lines = source.strip().splitlines()
    result, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [p.strip() for p in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", p) for p in row):
                    rows.append(row)
                i += 1
            result.append('<div class="table-wrap"><table>')
            for n, row in enumerate(rows):
                tag = "th" if n == 0 else "td"
                result.append("<tr>" + "".join(f"<{tag}>{inline(cell)}</{tag}>" for cell in row) + "</tr>")
            result.append("</table></div>")
            continue
        heading = re.match(r"(#{1,4}) (.+)", line)
        if heading:
            level = len(heading[1])
            result.append(f'<h{level} id="{anchor(heading[2])}">{inline(heading[2])}</h{level}>')
            i += 1
            continue
        if line.startswith("- "):
            result.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                result.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            result.append("</ul>")
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"(?:#|\||- )", lines[i].strip()):
            paragraph.append(lines[i].strip())
            i += 1
        result.append(f'<p>{inline(" ".join(paragraph))}</p>')
    return "\n".join(result)


ICONS = {
    "person": '<circle cy="-9" r="6"/><path d="M-11 13V2Q0-10 11 2V13M-6 13V22M6 13V22"/>',
    "party": '<circle cx="-10" cy="-6" r="5"/><circle cx="10" cy="-6" r="5"/><path d="M-19 15V3Q-10-5-1 3V15M1 15V3Q10-5 19 3V15"/>',
    "enemy": '<path d="M0-21 17-11 13 14 0 22-13 14-17-11ZM-9-3 9 8M9-3-9 8"/>',
    "summon": '<path d="M-20 9Q-22-8-7-9L-11-20 1-13 12-17 14-6Q23-4 22 8L12 14H-11ZM-11 14V22M10 14V22"/><circle cx="9" cy="-2" r="1"/>',
    "book": '<path d="M0-15Q-10-21-23-15V16Q-10 10 0 16Q10 10 23 16V-15Q10-21 0-15V16M-17-7-7-8M7-8 17-7M-17 1-7 0M7 0 17 1"/>',
    "gate": '<path d="M-23 21V-20H23V21M-16 21V-9Q0-30 16-9V21M-25 21H25"/>',
    "box": '<path d="M-23-13 0-22 23-13V14L0 23-23 14ZM-23-13 0-4 23-13M0-4V23M-12-17 12-8V1"/>',
    "store": '<path d="M-24-9 0-24 24-9M-20-8V21H20V-8M-8 21V0H8V21M-25 21H25"/>',
    "cart": '<path d="M-23-16H18V10H-23ZM18-7 29 2M-20-6H14"/><circle cx="-14" cy="17" r="6"/><circle cx="12" cy="17" r="6"/>',
    "spark": '<path d="M0-24 6-7 24 0 6 7 0 24-6 7-24 0-6-7ZM17-19 20-12 27-9M-20 13-24 20"/>',
    "clock": '<circle r="23"/><path d="M0-15V0L12 7M-27-24-18-28M18-28 27-24"/>',
    "shield": '<path d="M0-24 23-16 18 10 0 25-18 10-23-16ZM0-15V13M-12-2H12"/>',
    "sword": '<path d="M4-25 12-25 13-17-9 9-17 1ZM-23-2-6 15M-15 7-25 20M-27 17-21 23"/>',
    "bow": '<path d="M-15-26Q29 0-15 26L-3 0ZM-26 0H26M17-8 26 0 17 8"/>',
    "ore": '<path d="M-25 18-19-6-6-20 6-10 15-18 26 18ZM-19-6-4 5-6-20M-4 5 8 18M6-10 13 3 26 18"/>',
    "ingot": '<path d="M-25 12-16-11 15-17 25 5 17 16-15 22ZM-25 12 7 6 15-17M7 6 17 16"/>',
    "bench": '<path d="M-28-7H28V2H-28ZM-21 2V23M21 2V23M-12-7V-21H8V-7M-15 13H15"/>',
    "coin": '<ellipse cx="-6" cy="5" rx="20" ry="7"/><path d="M-26 5V13C-26 23 14 23 14 13V5"/><ellipse cx="7" cy="-9" rx="20" ry="7"/><path d="M-13-9V-1C-13 9 27 9 27-1V-9"/>',
    "gem": '<path d="M-24-8-13-22H13L24-8 0 25ZM-24-8H24M-13-22-8-8 0 25 8-8 13-22"/>',
}


def scene_svg(book, number):
    nodes = book["scenes"][number-1]
    uid = f'{book["slug"]}-{number}'
    # Alternating layouts prevent the visual story becoming a repetitive row.
    ys = ([100, 78, 100] if number % 3 == 1 else [82, 110, 82] if number % 3 == 2 else [94, 94, 94])
    xs = [93, 280, 467]
    title = " → ".join(n[1] for n in nodes)
    parts = [f'<svg viewBox="0 0 560 230" role="img" aria-labelledby="title-{uid}"><title id="title-{uid}">{esc(title)}</title>',
        '<rect width="560" height="230" fill="#152427"/>',
        f'<defs><pattern id="grid-{uid}" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#91a8a1" opacity=".08"/></pattern><marker id="arrow-{uid}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1L7 4 1 7" fill="none" stroke="{book["color"]}"/></marker></defs>',
        f'<rect width="560" height="230" fill="url(#grid-{uid})"/>',
        '<path d="M25 150V42H160M400 42H535V150" fill="none" stroke="#647970" stroke-width="7" opacity=".4"/>']
    for index in range(2):
        parts.append(f'<path d="M{xs[index]+49} {ys[index]}Q{(xs[index]+xs[index+1])//2} {ys[index+1]} {xs[index+1]-49} {ys[index+1]}" fill="none" stroke="{book["color"]}" stroke-width="1.5" stroke-dasharray="5 5" marker-end="url(#arrow-{uid})" opacity=".8"/>')
    for x, y, (icon, label, sub) in zip(xs, ys, nodes):
        color = "#e2a299" if icon == "enemy" else book["color"]
        parts.append(f'<circle cx="{x}" cy="{y}" r="39" fill="#223437" stroke="{color}" stroke-opacity=".5"/>')
        parts.append(f'<g transform="translate({x} {y})" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</g>')
        parts.append(f'<text x="{x}" y="178" text-anchor="middle" class="diagram-label">{esc(label)}</text><text x="{x}" y="199" text-anchor="middle" class="diagram-sub">{esc(sub)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def map_svg(book, compact=False):
    uid = book["slug"] + ("-mini" if compact else "-map")
    coords = [(320,73),(525,212),(320,353),(115,212)]
    directions = ["NORTH", "EAST", "SOUTH", "WEST"]
    parts = [f'<svg viewBox="0 0 640 426" role="img" aria-labelledby="{uid}-title"><title id="{uid}-title">{esc(book["place"])} four-gate concept: North {esc(book["gates"][0])}, East {esc(book["gates"][1])}, South {esc(book["gates"][2])}, West {esc(book["gates"][3])}.</title>',
      '<rect x="1" y="1" width="638" height="424" rx="12" fill="#152427" stroke="#344a4a"/>',
      '<path d="M320 74V355M115 212H525" fill="none" stroke="#687669" stroke-width="36" opacity=".18"/>',
      '<path d="M205 109H270M370 109H435V161M435 263V315H370M270 315H205V263M205 161V109" fill="none" stroke="#688074" stroke-width="9" opacity=".6"/>',
      f'<rect x="258" y="173" width="124" height="78" rx="14" fill="#293c37" stroke="{book["color"]}"/>',
      f'<text x="320" y="208" text-anchor="middle" class="map-center">{esc(book["center"])}</text><text x="320" y="229" text-anchor="middle" class="diagram-sub">REFUGE · RESUME</text>']
    for i, ((x, y), direction, name) in enumerate(zip(coords, directions, book["gates"])):
        parts.append(f'<rect x="{x-87}" y="{y-38}" width="174" height="76" rx="7" fill="#203236" stroke="#485f5c"/>')
        parts.append(f'<text x="{x}" y="{y-10}" text-anchor="middle" class="map-direction" style="fill:{book["color"]}">{i+1:02d} / {direction}</text><text x="{x}" y="{y+14}" text-anchor="middle" class="map-name">{esc(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)


CSS = """
:root{color-scheme:dark;--bg:#101b1f;--surface:#18282d;--text:#ecebe0;--muted:#b1c2bf;--line:#354b4e;--accent:#ddbe84;--blue:#9ad5de}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:80px}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 'Segoe UI',Arial,sans-serif}a{color:var(--accent);text-underline-offset:4px}main{max-width:1280px;margin:auto;padding:46px 36px 80px}.topnav{position:sticky;top:0;z-index:5;border-bottom:1px solid var(--line);background:#101b1ff5;display:flex;justify-content:space-between;gap:16px;padding:13px max(20px,calc((100vw - 1208px)/2));font-size:12px}.topnav a{text-decoration:none}.eyebrow,.meta,.kicker{font-size:11px;font-weight:650;letter-spacing:.15em;text-transform:uppercase;color:var(--accent)}h1,h2,h3{font-family:Georgia,'Times New Roman',serif;font-weight:400;line-height:1.13;letter-spacing:-.025em}h1{font-size:clamp(43px,6.4vw,82px);max-width:1000px;margin:17px 0 21px}h2{font-size:36px;margin:42px 0 20px}h3{font-size:28px;margin:12px 0 20px}.intro{font-size:21px;max-width:790px;color:#cbd6ce;margin:15px 0 24px}.tags{display:flex;gap:8px;flex-wrap:wrap}.tags span{font-size:12px;color:var(--muted);border:1px solid var(--line);padding:5px 11px;border-radius:3px}.notice{border-left:2px solid var(--accent);padding:13px 17px;background:#203034;margin:25px 0;font-size:13px;color:var(--muted)}.notice strong{color:var(--text)}.overview{display:grid;grid-template-columns:1.12fr 1fr;gap:35px;align-items:center;margin:40px 0}.overview svg{width:100%;display:block}.overview p{color:var(--muted);font-size:15px}.overview h2{margin:12px 0}.diagram-label{font:600 12px 'Segoe UI',sans-serif;fill:#e6e8dc}.diagram-sub{font:10px 'Segoe UI',sans-serif;fill:#b3c9c3;letter-spacing:.25px}.map-center{font:600 13px 'Segoe UI',sans-serif;fill:#efead9}.map-direction{font:600 10px 'Segoe UI',sans-serif;letter-spacing:1.2px}.map-name{font:14px 'Segoe UI',sans-serif;fill:#ecebdd}.learning{display:grid;grid-template-columns:repeat(3,1fr);gap:25px;border-block:1px solid var(--line);padding:22px 0;margin:35px 0}.learning p{font-size:14px;color:var(--muted);margin:7px 0}.learning b{font-size:11px;letter-spacing:.12em;color:var(--accent)}.toolbar{display:flex;align-items:center;gap:13px;flex-wrap:wrap;margin:20px 0 28px}button,input{font:inherit;font-size:13px;border:1px solid #536b6c;border-radius:4px;background:#182a2e;color:var(--text);padding:9px 13px}button{cursor:pointer}button:hover,button[aria-pressed=true]{border-color:var(--accent);background:#30433e}input{min-width:200px;flex:1;max-width:420px}button:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--blue);outline-offset:4px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px}.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;min-width:0}.card svg{width:100%;display:block}.frame-label{font-size:9px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);background:#203238;padding:8px 22px}.card-body{padding:25px 28px 27px}.meta{display:flex;justify-content:space-between;gap:14px;font-size:10px}.card p{font-size:14px;color:#c7d5d0;margin:15px 0}.card p strong.field{display:block;font-size:10px;letter-spacing:.12em;color:var(--accent);text-transform:uppercase;margin-bottom:4px}blockquote{margin:20px 0;padding:0 0 0 16px;border-left:2px solid #6f8172;font:italic 18px/1.5 Georgia,serif;color:#e2d4b3}details{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}summary{cursor:pointer;color:var(--blue);font-size:13px}.spec{max-width:1050px}.spec p,.spec li{color:#c1d0cb;font-size:15px}.spec h2{padding-top:12px}.spec h3{font-size:24px}.spec li{margin:9px 0}.table-wrap{overflow-x:auto;margin:22px 0;border:1px solid var(--line);border-radius:5px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:13px 16px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}th{background:#24363a;color:var(--accent);font-weight:600}td{color:#bfd0c8;min-width:115px}tr:last-child td{border-bottom:0}code{font:12px/1.6 Consolas,monospace;color:#cbded7;overflow-wrap:anywhere}.below{border-top:1px solid var(--line);margin-top:55px;padding-top:15px}footer{font-size:12px;color:var(--muted);margin-top:45px;padding-top:23px;border-top:1px solid var(--line)}.collection-card{display:grid;grid-template-columns:1fr;transition:border-color .15s}.collection-card:hover{border-color:var(--accent)}.collection-card .card-body{padding:22px 26px}.collection-card h3 a{color:var(--text);text-decoration:none}.collection-card svg{padding:16px 16px 0}.count{color:var(--muted);font-size:12px}.scene-nav{display:flex;flex-wrap:wrap;gap:9px;margin:24px 0}.scene-nav a{display:inline-block;font-size:12px;text-decoration:none;border:1px solid var(--line);border-radius:3px;padding:5px 11px}.skip{position:absolute;left:-9999px}.skip:focus{left:15px;top:15px;z-index:100;background:var(--bg);padding:10px}.empty{padding:20px;border:1px solid var(--line);color:var(--muted)}[hidden]{display:none!important}.backlinks{display:flex;gap:20px;flex-wrap:wrap}
@media(max-width:780px){main{padding:30px 18px 50px}.topnav{padding:12px 18px}.overview,.grid{grid-template-columns:1fr}.overview{gap:12px;margin:30px 0}.learning{gap:13px}.learning p{font-size:12px}.card-body{padding:22px}.intro{font-size:18px}h2{font-size:30px}h3{font-size:26px}.toolbar{gap:8px}input{max-width:none;width:100%}.spec p,.spec li{font-size:14px}.table-wrap{max-width:100%}.map-name{font-size:15px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
@media print{:root{color-scheme:light;--text:#1b3032;--muted:#385153;--accent:#665025;--line:#b8c6c2}body{background:white;color:var(--text);font-size:12px}main{padding:0;max-width:none}.topnav,.toolbar,.scene-nav,.skip{display:none}.grid{display:block}.card{background:white;break-inside:avoid;margin-bottom:20px}.card svg{max-height:180px}.card p,.spec p,.spec li,td,.overview p,.intro{color:#283d3c}.card h3,.collection-card h3 a{color:#16292d}.notice,th{background:#edf2ef}.frame-label{background:#e4ece8;color:#243c3b}.card-body{padding:17px}.meta,blockquote,code{color:#5e4927}details{display:block}.overview{break-inside:avoid}.collection-card{break-inside:avoid}.collection-card svg{max-height:230px}a{color:#254f55}.spec h2{break-after:avoid}.table-wrap{overflow:visible}h1{font-size:48px}h2{font-size:29px}footer{color:#385153}}
"""

SCRIPT = """
const notes=[...document.querySelectorAll('details.playtest')];
const toggle=document.querySelector('#notes-toggle');
if(toggle) toggle.addEventListener('click',()=>{const open=toggle.getAttribute('aria-pressed')!=='true';notes.forEach(n=>n.open=open);toggle.setAttribute('aria-pressed',String(open));toggle.textContent=open?'Collapse evidence & recovery':'Expand evidence & recovery';});
const cards=[...document.querySelectorAll('[data-search]')],search=document.querySelector('#search');
let group='All';
function filter(){let visible=0;const q=search.value.trim().toLowerCase();cards.forEach(c=>{const show=(group==='All'||c.dataset.group===group)&&c.dataset.search.includes(q);c.hidden=!show;if(show)visible++;});document.querySelector('#result-count').textContent=`${visible} of 8 adventures`;document.querySelector('#empty').hidden=visible!==0;}
if(search){search.addEventListener('input',filter);document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{group=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));filter();}));}
const printDetails=[...document.querySelectorAll('details')];
let printStates=[];
addEventListener('beforeprint',()=>{printStates=printDetails.map(n=>n.open);printDetails.forEach(n=>n.open=true);});
addEventListener('afterprint',()=>printDetails.forEach((n,i)=>n.open=printStates[i]??false));
"""


def page(title, body, nav, css_path, js_path, color="#ddbe84"):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Eloria storyboards</title><meta name="description" content="Eight proposed hands-on Eloria tutorial adventures, with scene diagrams, gameplay evidence, recovery and playtest plans."><link rel="stylesheet" href="{css_path}"></head><body style="--accent:{color}"><a class="skip" href="#main">Skip to content</a><nav class="topnav" aria-label="Collection navigation">{nav}</nav><main id="main">{body}<footer>Eloria · Storyboard proposals · 9 September 2026<br>Diagrams show spatial and action relationships. They are not client screenshots, final map art or evidence of implemented gameplay.</footer></main><script src="{js_path}" defer></script></body></html>'''


def parse_book(book):
    raw = (ROOT / book["slug"] / "README.md").read_text(encoding="utf-8")
    prefix, frame_text = raw.split("## Ten storyboard frames\n", 1)
    match = re.search(r"^## ", frame_text, re.M)
    assert match, f'Missing coverage after frames: {book["slug"]}'
    frames_raw, suffix = frame_text[:match.start()], frame_text[match.start():]
    chunks = re.split(r"^### (\d{2}) · (.+?) — (\d+) minutes\n", frames_raw, flags=re.M)
    frames = []
    for i in range(1, len(chunks), 4):
        number, title, minutes, content = chunks[i:i+4]
        fields = dict(re.findall(r"^\*\*([^*]+):\*\* (.+?)(?=\n\n\*\*|\Z)", content.strip(), re.S | re.M))
        required = {"Picture", "Voice", "Play", "Learn", "Evidence", "Recovery / observe"}
        assert set(fields) == required, (book["slug"], number, set(fields))
        frames.append(dict(number=int(number), title=title, minutes=int(minutes), fields=fields))
    assert [f["number"] for f in frames] == list(range(1,11)), book["slug"]
    # Strip the already represented title, status and navigation paragraphs.
    prelude = "\n\n".join(prefix.strip().split("\n\n")[3:])
    return raw, prelude, frames, suffix


def render_book(book, index):
    raw, prelude, frames, suffix = parse_book(book)
    next_book = BOOKS[(index+1) % len(BOOKS)]
    nav = f'<a href="../index.html">← Eight roads after the lantern</a><a href="../{next_book["slug"]}/storyboard.html">Next: {esc(next_book["topic"])} →</a>'
    total = sum(f["minutes"] for f in frames)
    body = f'<header><div class="eyebrow">ELORIA / FOLLOW-UP {index+1:02d} / {esc(book["topic"])}</div><h1>{esc(book["title"])}</h1><p class="intro">{esc(book["hook"])}</p><div class="tags"><span>Native gameplay proposal</span><span>{esc(book["duration"])}</span><span>4 gates · 10 frames</span><span>Hands-on learning</span></div><div class="notice"><strong>Design proposal — not implemented or human-playtested.</strong> Timings are targets. Each frame specifies real input, evidence, recovery and a changed application; required implementation work is identified below.</div></header>'
    body += f'<section class="overview" aria-label="Four-gate map">{map_svg(book)}<div><div class="kicker">{esc(book["place"])} / {esc(book["size"])} TILE CONCEPT</div><h2>One refuge.<br>Four useful journeys.</h2><p>Guided courts introduce a mechanic, change a constraint, combine skills and then ask the player to solve a new problem.</p><p>Return paths stay available. Movement instructions become action instructions on arrival. Map and viewport markers refer to the same real target.</p><p>Frame budgets total {total} minutes; the broader session range allows for individual pacing. Optional experiments are separate.</p><p><a href="README.md">Read the Markdown specification</a><br><a href="../design-contract.html">Shared gameplay and playtest contract</a></p></div></section>'
    body += '<section class="learning" aria-label="Learning rhythm"><div><b>01 / SHOW</b><p>Expose the real control when the story creates a need.</p></div><div><b>02 / PRACTICE</b><p>Let the player act, inspect the result and recover.</p></div><div><b>03 / TRANSFER</b><p>Change the problem and reduce mechanical prompts.</p></div></section>'
    body += f'<details><summary>Premise, access and map specification</summary><div class="spec">{markdown(prelude)}</div></details><h2 id="frames">The playable story</h2><nav class="scene-nav" aria-label="Storyboard frames">'
    body += "".join(f'<a href="#scene-{f["number"]:02d}" title="{esc(f["title"])}">{f["number"]:02d}</a>' for f in frames)
    body += '</nav><div class="toolbar"><button type="button" id="notes-toggle" aria-pressed="false">Expand evidence &amp; recovery</button><a href="#coverage">Coverage, dependencies &amp; playtesting ↓</a></div><section class="grid" aria-label="Ten storyboard frames">'
    for frame in frames:
        n, fields = frame["number"], frame["fields"]
        body += f'<article class="card" id="scene-{n:02d}">{scene_svg(book,n)}<div class="frame-label">Blocking diagram · Frame {n:02d} · Proposed gameplay</div><div class="card-body"><div class="meta"><span>FRAME {n:02d}</span><span>{frame["minutes"]} MIN</span></div><h3>{esc(frame["title"])}</h3><p><strong class="field">Picture</strong>{inline(fields["Picture"])}</p><blockquote>{inline(fields["Voice"])}</blockquote><p><strong class="field">Play</strong>{inline(fields["Play"])}</p><p><strong class="field">Learn</strong>{inline(fields["Learn"])}</p><details class="playtest"><summary>Evidence, recovery &amp; observation</summary><p><strong class="field">Evidence</strong>{inline(fields["Evidence"])}</p><p><strong class="field">Recovery / observe</strong>{inline(fields["Recovery / observe"])}</p></details></div></article>'
    body += f'</section><section class="below spec" id="coverage">{markdown(suffix)}</section><div class="backlinks"><a href="../index.html">← All eight adventures</a><a href="../design-contract.html">Shared test protocol</a><a href="README.md">Source specification</a></div>'
    (ROOT / book["slug"] / "storyboard.html").write_text(page(book["title"], body, nav, "../storyboards.css", "../storyboards.js", book["color"]), encoding="utf-8")
    return dict(slug=book["slug"], frames=len(frames), frame_minutes=total, words=len(raw.split()))


def render_index():
    body = '<header><div class="eyebrow">ELORIA / THE NEXT ADVENTURES / DESIGN COLLECTION</div><h1>Eight roads<br>after the lantern.</h1><p class="intro">A caravan to reunite. A workshop to reopen. A future to choose. Eight follow-up adventures that teach Eloria through the things a player actually does.</p><div class="tags"><span>8 adventures</span><span>80 core storyboard frames</span><span>8 four-gate maps</span><span>Solo first · optional human play</span></div><div class="notice"><strong>The first six are now playable.</strong> Open Help → Practice adventures in the updated client. <a href="implementation.md">Play commands, recovery and verification</a>. Worship and PvP remain proposals. Every adventure includes scene composition, guide dialogue, native actions, completion evidence, recovery, optional specialist exercises and a human playtest plan. Durations and learning targets are unmeasured.</div></header>'
    body += '<section class="learning"><div><b>CHOICE</b><p>Understand summons, production and the character you are building.</p></div><div><b>PREPARATION</b><p>Choose equipment, maintain it and finish a commission within a budget.</p></div><div><b>COOPERATION</b><p>Read group, worship and PvP rules before taking the next step.</p></div></section><h2 id="adventures">Choose an adventure</h2><div class="toolbar"><label class="kicker" for="search">Find a topic</label><input id="search" type="search" placeholder="Search adventures or mechanics…">'
    for group in ["All", "Specialization", "Preparation", "Cooperation", "Optional paths"]:
        body += f'<button type="button" data-filter="{group}" aria-pressed="{str(group == "All").lower()}">{group}</button>'
    body += '</div><p class="count" id="result-count" aria-live="polite">8 of 8 adventures</p><p id="empty" class="empty" hidden>No adventures match. Clear the search or choose All.</p><section class="grid" aria-label="Adventure collection">'
    for i, book in enumerate(BOOKS):
        searchable = " ".join([book["title"],book["topic"],book["hook"],book["place"], *[node[1] for scene in book["scenes"] for node in scene]]).lower()
        body += f'<article class="card collection-card" style="--accent:{book["color"]}" data-group="{esc(book["group"])}" data-search="{esc(searchable)}">{map_svg(book,True)}<div class="card-body"><div class="meta"><span>{i+1:02d} / {esc(book["topic"])}</span><span>{esc(book["duration"])}</span></div><h3><a href="{book["slug"]}/storyboard.html">{esc(book["title"])}</a></h3><p>{esc(book["hook"])}</p><p><a href="{book["slug"]}/storyboard.html">Open illustrated storyboard →</a></p><p><a href="{book["slug"]}/README.md">Full specification</a> · 10 frames + specialist exercises</p></div></article>'
    body += '</section><section class="below spec"><h2>The work behind each adventure</h2><p>Each story has a separate practice state, an outcome the player can see, explicit recovery and a final problem with fewer prompts. Public trading, permanent character choices and optional multiplayer exercises are kept truthful about their costs and requirements.</p><p>The source audit calls out concrete dependencies: level-30 summon controls, real research timing, direct repair commands, marketplace quantity behavior, private escrow, gauntlet cache capacity, negative initial worship standing and the actual ordering of PvP loss rules.</p><p><a href="design-contract.html">Read the shared gameplay and playtest contract →</a></p><p><a href="source-audit.md">Source findings and implementation requirements</a></p><p><a href="README.md">Collection specification and suggested production sequence</a> · <a href="../invasion-tutorial/storyboard.html">The Second Bell</a> · <a href="../magic-tutorial/storyboard.html">The Borrowed Sky</a></p></section>'
    nav = '<a href="#adventures">ELORIA / Tutorial storyboards</a><a href="design-contract.html">Gameplay &amp; playtest contract →</a>'
    (ROOT / "index.html").write_text(page("Eight roads after the lantern", body, nav, "storyboards.css", "storyboards.js"), encoding="utf-8")


def main():
    (ROOT / "storyboards.css").write_text(CSS.strip()+"\n", encoding="utf-8")
    (ROOT / "storyboards.js").write_text(SCRIPT.strip()+"\n", encoding="utf-8")
    results = [render_book(book, i) for i,book in enumerate(BOOKS)]
    render_index()
    contract = (ROOT / "design-contract.md").read_text(encoding="utf-8")
    body = f'<div class="eyebrow">ELORIA / ALL EIGHT ADVENTURES</div><div class="spec">{markdown(contract)}</div><p><a href="index.html">← Return to the collection</a></p>'
    (ROOT / "design-contract.html").write_text(page("Shared gameplay and playtest contract", body, '<a href="index.html">← Eight roads after the lantern</a><a href="design-contract.md">Markdown source</a>', "storyboards.css", "storyboards.js"), encoding="utf-8")
    print(json.dumps({"adventures":results,"total_frames":sum(r["frames"] for r in results)},indent=2))


if __name__ == "__main__":
    main()
