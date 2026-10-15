#!/usr/bin/env python3
"""Build a subdued inactive-state companion for the active HUD atlas."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "ui" / "eloria_gamebuttons.png"
DESTINATION = ROOT / "assets" / "ui" / "eloria_gamebuttons_inactive.png"


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            luminance = round(0.2126 * red + 0.7152 * green + 0.0722 * blue)
            pixels[x, y] = (
                round((red * 0.35 + luminance * 0.65) * 0.68),
                round((green * 0.35 + luminance * 0.65) * 0.68),
                round((blue * 0.35 + luminance * 0.65) * 0.72),
                alpha,
            )
    image.save(DESTINATION, optimize=True)


if __name__ == "__main__":
    main()
