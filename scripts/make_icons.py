"""Render the app icons (three fanned cards) and a web-optimised dealer image.

Dev-only helper: `pip install pillow && python scripts/make_icons.py`.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "app" / "static" / "img"

FELT = (15, 42, 46)
CARDS = [(43, 99, 217), (30, 154, 90), (216, 52, 44)]
CREAM = (242, 235, 221)


def icon(size: int, padding: float = 0.0) -> Image.Image:
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), FELT + (255,))
    inner = s * (1 - padding * 2)
    offset = s * padding
    w, h = inner * 0.42, inner * 0.62
    cx, cy = offset + inner / 2, offset + inner * 0.54
    for i, color in enumerate(CARDS):
        card = Image.new("RGBA", (int(w * 1.6), int(h * 1.6)), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        x0, y0 = (card.width - w) / 2, (card.height - h) / 2
        d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=w * 0.14, fill=color + (255,))
        inset = w * 0.1
        d.rounded_rectangle(
            [x0 + inset, y0 + inset, x0 + w - inset, y0 + h - inset],
            radius=w * 0.08, outline=CREAM + (150,), width=max(1, int(w * 0.035)),
        )
        if i == len(CARDS) - 1:
            r = w * 0.2
            d.ellipse([x0 + w / 2 - r, y0 + h / 2 - r, x0 + w / 2 + r, y0 + h / 2 + r], fill=CREAM + (255,))
        card = card.rotate((1 - i) * 18, resample=Image.BICUBIC, expand=False)
        img.alpha_composite(card, (int(cx - card.width / 2 + (i - 1) * w * 0.28), int(cy - card.height / 2)))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    icon(192).save(IMG / "icon-192.png", optimize=True)
    icon(512).save(IMG / "icon-512.png", optimize=True)
    icon(512, padding=0.12).save(IMG / "icon-maskable-512.png", optimize=True)
    icon(180).convert("RGB").save(IMG / "apple-touch-icon.png", optimize=True)
    icon(48).save(IMG / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # Social preview: icon on felt with generous margin.
    og = Image.new("RGB", (1200, 630), FELT)
    og.paste(icon(420).convert("RGB"), (390, 105))
    og.save(IMG / "og-image.png", optimize=True)

    dealer = Image.open(IMG / "dealer.png")
    dealer.thumbnail((640, 640))
    dealer.save(IMG / "dealer.webp", quality=82, method=6)


if __name__ == "__main__":
    main()
