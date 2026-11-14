"""Build the vector leather book covers used by the stable book artwork IDs.

One silhouette, a distinct leather colour and a legible embossed subject mark.
No editor/runtime dependency is needed to regenerate these small SVG assets.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Keep IDs in sync with the server's eloria/book_types.py.
COVERS = {
    640: ("melee", "#aa4145", "M30 13l3 3-9 13-3-2z M21 25l7 5 M23 29l-4 5 M17 33l4 2"),
    641: ("ranging", "#40865a", "M25 13q15 10-4 21 M25 13l-4 21 M17 24h17 M30 21l4 3-4 3"),
    642: ("magic", "#8055b2", "M29 13l-3 7-7 2 6 3-1 8 5-6 6 1-3-6 4-5-7 1z"),
    643: ("manufacturing", "#4d7fa8", "M21 15l4-3 10 6-4 4-10-6z M27 20l-8 13 3 2 8-13"),
    644: ("alchemy", "#329b9d", "M26 12h6 M28 12l-1 9-8 9q-2 4 3 4h9q5 0 3-4l-5-9 1-9 M23 27h9"),
    645: ("potions", "#c58336", "M25 13h8 M27 14l-1 6q-10 5-6 12 2 4 9 2 7-2 4-8l-4-6 1-6 M22 27q5-3 11 0"),
    646: ("crafting", "#b09a42", "M21 17l7-4 8 6-10 14-7-11z M21 17l5 16 2-20 8 6-17 3"),
    647: ("tailoring", "#b35e86", "M22 32l11-19q1-2 2 0l-10 20z M31 17l2-3 M23 31q-8 5-6-2t6-5"),
    648: ("engineering", "#b77449", "M27 14v4 M27 30v4 M17 24h4 M33 24h4 M20 17l3 3 M31 28l3 3 M20 31l3-3 M31 20l3-3"),
}


def main():
    output = ROOT / "godot-client/assets/ui/items/books"
    output.mkdir(parents=True, exist_ok=True)
    for _, (name, colour, symbol) in COVERS.items():
        extra = '<circle cx="27" cy="24" r="7"/><circle cx="27" cy="24" r="2.5"/>' if name == "engineering" else ""
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 50 50">
<defs>
 <linearGradient id="leather" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{colour}"/><stop offset=".52" stop-color="{colour}"/><stop offset="1" stop-color="#202029"/></linearGradient>
 <linearGradient id="pages" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#e7d5a6"/><stop offset="1" stop-color="#8e7854"/></linearGradient>
</defs>
<path d="M6 35L16 5 44 12 35 43 9 42 5 38z" fill="#110f13" opacity=".6"/>
<path d="M8 35l27 6 5-7-27-7z" fill="url(#pages)" stroke="#453627" stroke-width="1.2"/>
<path d="M10 36l25 5 M12 34l24 5" fill="none" stroke="#6e5b41" stroke-width=".7"/>
<path d="M6 34L15 5l28 7-9 28-26-5z" fill="url(#leather)" stroke="#302427" stroke-width="1.6" stroke-linejoin="round"/>
<path d="M15 5l5 1-9 29-4-1z" fill="#17191d" opacity=".48"/>
<path d="M21 9l18 5-7 22-18-4z" fill="none" stroke="#e0b66c" stroke-width=".65" opacity=".8"/>
<path d="M12 11l5 1 M10 18l5 1 M8 26l5 1 M8 32l4 1 M21 9l-1 4 M36 13l2 1-1 4 M15 28l-1 4 4 1 M29 36l3 1 1-4" fill="none" stroke="#cda669" stroke-width="1.8"/>
<g fill="none" stroke="#f2d290" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="{symbol}"/>{extra}</g>
<path d="M16 6l26 7" stroke="#ffe0a0" stroke-width=".7" opacity=".6"/>
</svg>
'''
        (output / f"{name}.svg").write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
