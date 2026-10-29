"""Draw the integration's brand icon: a DIN-rail energy meter.

Run with Pillow available, for example ``uv run --with pillow python
tools/make_icon.py``. It writes ``icon.png`` (256 px) and ``icon@2x.png``
(512 px) into the integration's ``brand`` folder.
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = (
    Path(__file__).parent.parent
    / "custom_components"
    / "carlo_gavazzi_modbus"
    / "brand"
)

# Drawn at four times the largest size, then scaled down for smooth edges.
SCALE = 4
SIZE = 512 * SCALE

BODY = (55, 71, 79)
DISPLAY = (178, 223, 219)
DIGITS = (38, 50, 56)
BOLT = (255, 193, 7)
TERMINAL = (144, 164, 174)


def s(value: float) -> int:
    """Scale a coordinate on the 512 px grid to the drawing."""
    return round(value * SCALE)


def draw() -> Image.Image:
    """Return the icon at 512 px."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    # The meter's body, with screw terminals along the top and bottom.
    for x in (136, 216, 296, 376):
        pen.rounded_rectangle(
            (s(x - 22), s(40), s(x + 22), s(92)), radius=s(8), fill=TERMINAL
        )
        pen.rounded_rectangle(
            (s(x - 22), s(420), s(x + 22), s(472)), radius=s(8), fill=TERMINAL
        )
    pen.rounded_rectangle((s(64), s(72), s(448), s(440)), radius=s(48), fill=BODY)

    # The display, with three rows of segments.
    pen.rounded_rectangle((s(108), s(116), s(404), s(268)), radius=s(20), fill=DISPLAY)
    for row, width in ((150, 236), (192, 180), (234, 120)):
        pen.rounded_rectangle(
            (s(138), s(row - 12), s(138 + width), s(row + 12)),
            radius=s(10),
            fill=DIGITS,
        )

    # A lightning bolt below the display.
    bolt = [(276, 292), (210, 368), (252, 368), (232, 412), (304, 330), (262, 330)]
    pen.polygon([(s(x), s(y)) for x, y in bolt], fill=BOLT)

    return image.resize((512, 512), Image.Resampling.LANCZOS)


def main() -> None:
    """Write the icon in both sizes."""
    BRAND.mkdir(exist_ok=True)
    icon = draw()
    icon.save(BRAND / "icon@2x.png", optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        BRAND / "icon.png", optimize=True
    )


if __name__ == "__main__":
    main()
