"""Generate PWA icons: an orange road cone motif on dark rounded background."""
from PIL import Image, ImageDraw
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"


def make_icon(size: int, path: Path) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 5
    d.rounded_rectangle([0, 0, size, size], radius=r, fill=(17, 18, 20, 255))
    # Road
    d.polygon(
        [(size * 0.30, size * 0.88), (size * 0.70, size * 0.88),
         (size * 0.58, size * 0.25), (size * 0.42, size * 0.25)],
        fill=(58, 59, 64, 255),
    )
    # Center dashes
    for y0, y1 in [(0.30, 0.40), (0.48, 0.58), (0.66, 0.76)]:
        d.polygon(
            [(size * 0.49, size * y1), (size * 0.51, size * y1),
             (size * 0.515, size * y0), (size * 0.495, size * y0)],
            fill=(180, 180, 186, 255),
        )
    # The pothole
    cx, cy = size * 0.5, size * 0.72
    rx, ry = size * 0.13, size * 0.075
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(255, 122, 26, 255))
    d.ellipse([cx - rx * 0.65, cy - ry * 0.6, cx + rx * 0.65, cy + ry * 0.65], fill=(20, 21, 24, 255))
    img.save(path)


make_icon(192, STATIC / "icon-192.png")
make_icon(512, STATIC / "icon-512.png")
make_icon(180, STATIC / "apple-touch-icon.png")
print("icons written")
