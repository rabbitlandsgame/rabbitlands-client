"""Render an orthographic scientific review of the actual global height field."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from test_landscape import landscape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    x = np.arange(0, 1501, 3, dtype=float)
    z = np.arange(0, 1681, 3, dtype=float)
    xx, zz = np.meshgrid(x, z)
    h = landscape.height_at(xx, zz)
    rgb = landscape.terrain_color(xx, zz, h)
    water = landscape.water_fields(xx, zz, h)
    dz, dx = np.gradient(h, 3, 3)
    normal = np.stack((-dx, np.ones_like(h), -dz), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1)[..., None]
    sun = np.array([-0.5, 0.75, -0.5]); sun /= np.linalg.norm(sun)
    shade = np.clip(np.sum(normal * sun, axis=-1), 0, 1)
    rgb *= (0.72 + shade * 0.43)[..., None]
    rgb[water["mask"]] = [0.14, 0.37, 0.44]
    rgb[water["river_mask"]] = [0.21, 0.48, 0.52]
    levels = np.array([-25, 0, 5, 20, 50, 100, 150, 220])
    palette = np.array([[30,63,86],[65,110,124],[93,143,100],[154,178,117],
                        [209,195,129],[170,132,102],[139,121,113],[239,238,228]]) / 255
    elevation_rgb = np.stack([np.interp(h, levels, palette[:, i]) for i in range(3)], axis=-1)
    elevation_rgb *= (0.8 + shade * 0.25)[..., None]
    elevation_rgb[water["mask"]] = [0.14, 0.37, 0.44]
    contour = (np.floor(h / 10) != np.roll(np.floor(h / 10), 1, axis=0)) | (np.floor(h / 10) != np.roll(np.floor(h / 10), 1, axis=1))
    elevation_rgb[contour & (h > 0)] *= 0.7
    scale = 1.8
    panel_size = (int(x.size * scale), int(z.size * scale))
    left = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).resize(panel_size)
    right = Image.fromarray((np.clip(elevation_rgb, 0, 1) * 255).astype(np.uint8)).resize(panel_size)
    canvas = Image.new("RGB", (panel_size[0] * 2 + 100, panel_size[1] + 180), "#eeeade")
    canvas.paste(left, (30, 110)); canvas.paste(right, (panel_size[0] + 60, 110))
    draw = ImageDraw.Draw(canvas)
    def font(size):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
        except OSError:
            return ImageFont.load_default()
    draw.text((30, 18), "Eloria - Diagonal Mountain Spine", fill="#223c38", font=font(32))
    draw.text((30, 70), "Actual shared surface and climate colours", fill="#223c38", font=font(20))
    draw.text((panel_size[0] + 60, 70), "Elevation and drainage - contours every 10 m", fill="#223c38", font=font(20))
    for river in landscape.load_plan()["rivers"]:
        p = landscape.curved_points(river["points"])
        points = [(panel_size[0] + 60 + a / 3 * scale, 110 + b / 3 * scale) for a, b in p[:, :2]]
        draw.line(points, fill="#4db1d0", width=3)
    for region in landscape.load_plan()["regions"]:
        a, b = region["center"]
        px, py = 30 + a / 3 * scale, 110 + b / 3 * scale
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill="white")
        label = region["name"].replace(" ", "\n", 1)
        draw.multiline_text((px, py + 8), label, anchor="ma", align="center", font=font(18), fill="white", stroke_width=2, stroke_fill="#293c30")
    draw.text((30, panel_size[1] + 128), "North up. X east / Z south. Bounds 1,500 x 1,680 m. Regional centres shown; ownership does not affect the terrain.", fill="#223c38", font=font(19))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(f"Saved {args.output}; sampled elevation {h.min():.2f}..{h.max():.2f}m; water {water['mask'].mean():.1%}")


if __name__ == "__main__":
    main()
