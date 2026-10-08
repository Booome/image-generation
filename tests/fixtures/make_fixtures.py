#!/usr/bin/env python3
"""Generate the bundled test fixture (a small JPEG used by the E2E and request tests)."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "sample.jpg"


def main():
    w, h = 640, 360
    img = Image.new("RGB", (w, h), (40, 44, 52))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 40):
        d.line([(x, 0), (x, h)], fill=(70, 76, 88), width=1)
    for y in range(0, h, 40):
        d.line([(0, y), (w, y)], fill=(70, 76, 88), width=1)
    d.rectangle([200, 120, 440, 260], outline=(180, 190, 200), width=3)
    d.ellipse([280, 160, 360, 240], fill=(150, 90, 80))
    img.save(OUT, "JPEG", quality=90)
    print("wrote", OUT, img.size)


if __name__ == "__main__":
    main()
