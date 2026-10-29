"""Contact sheet of evidence renders.

    contact_sheet.py out.png --rows "<label>=<glob>;..." [--cell 240] [--cols N]
Each row is one glob (sorted); or --dirs a,b with --pattern to pair folders.
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--rows', required=True, help='label=glob;label=glob')
    ap.add_argument('--cell', type=int, default=240)
    ap.add_argument('--title', default='')
    a = ap.parse_args()
    rows = []
    for part in a.rows.split(';'):
        if not part.strip():
            continue
        label, pattern = part.split('=', 1)
        rows.append((label, sorted(glob.glob(pattern))))
    cols = max(len(files) for _, files in rows)
    top = 22 if a.title else 0
    W = Image.new('RGB', (a.cell * cols, a.cell * len(rows) + top), (18, 18, 20))
    d = ImageDraw.Draw(W)
    if a.title:
        d.text((6, 4), a.title, fill=(255, 255, 255))
    for r, (label, files) in enumerate(rows):
        for c, f in enumerate(files):
            im = Image.open(f).convert('RGB')
            im.thumbnail((a.cell, a.cell))
            W.paste(im, (c * a.cell, top + r * a.cell))
            d.text((c * a.cell + 4, top + r * a.cell + 4), os.path.basename(f)[:40], fill=(255, 255, 0))
        d.text((4, top + r * a.cell + a.cell - 16), label, fill=(120, 255, 120))
    W.save(a.out)
    print(a.out)


if __name__ == '__main__':
    main()
