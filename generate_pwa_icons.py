"""
Generate PWA icons for SignDocs.

Usage:
    .venv/bin/python generate_pwa_icons.py

Produces PNG icons in ``static/icons/`` using the SignDocs brand gradient
(#4361ee -> #7209b7) and a "signed document" glyph. Re-run any time the brand
colours change; the generated files are committed to the repo.
"""

from pathlib import Path

from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "static" / "icons"

# Brand palette (must match static/css/style.css design tokens)
PRIMARY = (67, 97, 238)      # #4361ee
PRIMARY_DARK = (114, 9, 183)  # #7209b7
SUCCESS = (6, 214, 160)      # #06d6a0
WHITE = (255, 255, 255)
FOLD = (220, 224, 240)
LINE = (203, 210, 224)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def diagonal_gradient(size):
    """Vertical-diagonal gradient from PRIMARY to PRIMARY_DARK."""
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    denom = 2 * (size - 1) if size > 1 else 1
    for y in range(size):
        for x in range(size):
            px[x, y] = lerp(PRIMARY, PRIMARY_DARK, (x + y) / denom)
    return grad


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_glyph(img, size, scale):
    """Draw a document with a folded corner + a checkmark badge.

    ``scale`` is the fraction of the canvas the glyph occupies (<1 leaves the
    maskable safe-zone padding around the icon).
    """
    draw = ImageDraw.Draw(img, "RGBA")

    glyph = size * scale
    offset = (size - glyph) / 2

    doc_w = glyph * 0.70
    doc_h = glyph * 0.84
    doc_x0 = offset + (glyph - doc_w) / 2
    doc_y0 = offset + (glyph - doc_h) / 2
    doc_x1 = doc_x0 + doc_w
    doc_y1 = doc_y0 + doc_h

    radius = doc_w * 0.10
    draw.rounded_rectangle(
        [doc_x0, doc_y0, doc_x1, doc_y1], radius=radius, fill=WHITE
    )

    # Folded top-right corner.
    fold = doc_w * 0.28
    draw.polygon(
        [
            (doc_x1 - fold, doc_y0),
            (doc_x1, doc_y0 + fold),
            (doc_x1 - fold, doc_y0 + fold),
        ],
        fill=FOLD,
    )

    # Text lines.
    line_h = doc_h * 0.055
    line_gap = doc_h * 0.135
    line_x0 = doc_x0 + doc_w * 0.16
    line_x1 = doc_x1 - doc_w * 0.16
    line_y = doc_y0 + doc_h * 0.34
    for i, factor in enumerate((1.0, 1.0, 0.62)):
        y = line_y + i * line_gap
        draw.rounded_rectangle(
            [line_x0, y, line_x0 + (line_x1 - line_x0) * factor, y + line_h],
            radius=line_h / 2,
            fill=LINE,
        )

    # Checkmark badge (bottom-right).
    badge_r = glyph * 0.24
    bx = doc_x1 - badge_r * 0.35
    by = doc_y1 - badge_r * 0.35
    draw.ellipse(
        [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
        fill=WHITE,
    )
    draw.ellipse(
        [bx - badge_r * 0.86, by - badge_r * 0.86, bx + badge_r * 0.86, by + badge_r * 0.86],
        fill=SUCCESS,
    )

    check_w = badge_r * 0.30
    draw.line(
        [
            (bx - badge_r * 0.42, by + badge_r * 0.02),
            (bx - badge_r * 0.10, by + badge_r * 0.34),
            (bx + badge_r * 0.46, by - badge_r * 0.34),
        ],
        fill=WHITE,
        width=max(2, int(check_w)),
        joint="curve",
    )
    # Round the checkmark endpoints for a soft finish.
    for px, py in (
        (bx - badge_r * 0.42, by + badge_r * 0.02),
        (bx + badge_r * 0.46, by - badge_r * 0.34),
    ):
        draw.ellipse(
            [px - check_w / 2, py - check_w / 2, px + check_w / 2, py + check_w / 2],
            fill=WHITE,
        )


def make_icon(size, maskable=False, path=None):
    """Build a single icon. Maskable icons are full-bleed with a safe zone."""
    img = diagonal_gradient(size).convert("RGBA")

    if maskable:
        # Full-bleed background, glyph confined to the ~80% safe zone.
        draw_glyph(img, size, scale=0.58)
    else:
        draw_glyph(img, size, scale=0.72)
        img.putalpha(rounded_mask(size, radius=int(size * 0.22)))

    img.save(path or (OUT_DIR / f"icon-{size}x{size}.png"))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Standard icons
    make_icon(192, path=OUT_DIR / "icon-192x192.png")
    make_icon(512, path=OUT_DIR / "icon-512x512.png")

    # Maskable icons (Android adaptive)
    make_icon(192, maskable=True, path=OUT_DIR / "icon-maskable-192x192.png")
    make_icon(512, maskable=True, path=OUT_DIR / "icon-maskable-512x512.png")

    # Apple touch icon (iOS applies its own rounding, so full-bleed square)
    make_icon(180, maskable=True, path=OUT_DIR / "apple-touch-icon.png")

    # Favicons
    make_icon(32, path=OUT_DIR / "favicon-32x32.png")
    make_icon(16, path=OUT_DIR / "favicon-16x16.png")

    print(f"Generated PWA icons in {OUT_DIR}")


if __name__ == "__main__":
    main()
