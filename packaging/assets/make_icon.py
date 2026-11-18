"""Generate the application icon (PNG + multi-size ICO).

Run:  python packaging/assets/make_icon.py
Outputs:
  app/resources/icon.png            256x256, used by the window and Linux .desktop
  packaging/windows/app.ico         16..256 px, used by the .exe and installer
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SIZE = 1024


def draw() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    # Rounded dark tile.
    d.rounded_rectangle((32, 32, SIZE - 32, SIZE - 32), radius=200, fill=(15, 23, 42, 255))
    d.rounded_rectangle(
        (32, 32, SIZE - 32, SIZE - 32), radius=200, outline=(38, 50, 68, 255), width=16
    )

    # Film strip along the bottom: the "frames" half of the app.
    d.rectangle((140, 690, 884, 860), fill=(30, 41, 59, 255))
    for x in range(170, 860, 110):
        d.rounded_rectangle((x, 708, x + 70, 742), radius=10, fill=(15, 23, 42, 255))
        d.rounded_rectangle((x, 808, x + 70, 842), radius=10, fill=(15, 23, 42, 255))

    # Ball trajectory (TrackNet's job): fading trail + ball.
    trail = [(230, 560, 26), (320, 455, 32), (420, 375, 38), (530, 320, 44)]
    for i, (x, y, r) in enumerate(trail):
        alpha = 70 + i * 40
        d.ellipse((x - r, y - r, x + r, y + r), fill=(34, 197, 94, alpha))

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((560, 170, 840, 450), fill=(163, 230, 53, 160))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    image.alpha_composite(glow)

    d = ImageDraw.Draw(image)
    d.ellipse((590, 200, 810, 420), fill=(190, 242, 100, 255))
    # Crosshair = annotation.
    d.line((700, 150, 700, 470), fill=(248, 250, 252, 255), width=14)
    d.line((540, 310, 860, 310), fill=(248, 250, 252, 255), width=14)
    d.ellipse((676, 286, 724, 334), fill=(15, 23, 42, 255))
    return image


def main():
    big = draw()
    png = ROOT / "app" / "resources" / "icon.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    big.resize((256, 256), Image.LANCZOS).save(png)

    ico = ROOT / "packaging" / "windows" / "app.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    big.resize((256, 256), Image.LANCZOS).save(
        ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"wrote {png}\nwrote {ico}")


if __name__ == "__main__":
    main()
