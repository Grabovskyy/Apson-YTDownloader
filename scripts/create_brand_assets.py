from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"


def create_icon() -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 255, 255), radius=52, fill="#0e141f")
    accent = "#6d9eff"
    light = "#e8edf7"
    green = "#77d9a8"
    draw.line((128, 42, 128, 149), fill=accent, width=24)
    draw.line((85, 111, 128, 154, 171, 111), fill=accent, width=24, joint="curve")
    draw.line((57, 184, 199, 184), fill=light, width=18)
    draw.line((185, 55, 185, 119), fill=green, width=14)
    draw.polygon(((185, 55), (223, 47), (223, 66), (185, 75)), fill=green)
    draw.ellipse((151, 109, 192, 148), fill=green)

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    image.save(ICON_DIR / "apson-ytdownloader.png")
    image.save(
        ICON_DIR / "apson-ytdownloader.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    create_icon()
