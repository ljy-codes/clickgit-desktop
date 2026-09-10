"""Generate ClickGit's original geometric artwork using the pinned Qt renderer.

Run with the project's Python/PySide6 6.10.3 environment. No fonts, downloads,
randomness, timestamps, image-generation service, or third-party art is involved.
The SVG is the editable vector master. All ICO frames are individually rendered,
not scaled from the largest bitmap, to retain small-size edge quality.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "src/clickgit/resources"
NAVY = "#080F20"
CYAN = "#53E6F4"

# The open C forms a circuit housing. Three linked nodes identify Git branching.
# Bold silhouettes, no text and no hairline-only details in the 16px artwork.
CHIP = f"""
<path d="M56 24 H200 L232 56 V200 L200 232 H56 L24 200 V56 Z"
      fill="{NAVY}" stroke="#258EBC" stroke-width="8" stroke-linejoin="round"/>
<g stroke="#258EBC" stroke-width="8" stroke-linecap="round">
  <path d="M80 12 V24 M128 12 V24 M176 12 V24
           M80 232 V244 M128 232 V244 M176 232 V244
           M12 80 H24 M12 128 H24 M12 176 H24
           M232 80 H244 M232 128 H244 M232 176 H244"/>
</g>
<path d="M187 76 L165 54 H85 L55 84 V172 L85 202 H165 L187 180
         L168 161 L153 176 H97 L81 160 V96 L97 80 H153 L168 95 Z"
      fill="{CYAN}"/>
<path d="M121 107 V151 M121 128 H148 L174 107"
      fill="none" stroke="{CYAN}" stroke-width="12"
      stroke-linejoin="round" stroke-linecap="round"/>
<g fill="#ECFCFF">
  <circle cx="121" cy="106" r="12"/>
  <circle cx="121" cy="151" r="12"/>
  <circle cx="177" cy="104" r="12"/>
</g>
"""


def svg_document(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n{body}\n</svg>\n'
    )


def render_png(svg: str, width: int, height: int) -> bytes:
    renderer = QSvgRenderer(svg.encode("utf-8"))
    if not renderer.isValid():
        raise ValueError("Invalid generated SVG")
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Qt could not encode brand artwork")
    buffer.close()
    return bytes(data)


def ico_bytes(frames: list[tuple[int, bytes]]) -> bytes:
    """Write a Windows ICO directory plus lossless RGBA PNG frames."""
    offset = 6 + 16 * len(frames)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    for size, payload in frames:
        dimension = 0 if size == 256 else size
        directory.extend(struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset,
        ))
        offset += len(payload)
    return bytes(directory) + b"".join(payload for _, payload in frames)


def wizard_panel_svg() -> str:
    grid = "".join(
        f'<path d="M{x} 0 V942 M0 {x} H492" />' for x in range(30, 943, 42)
    )
    # Custom vector wordmark; not dependent on installed fonts or font fallback.
    letters = {
        "C": "M22 0 H6 L0 6 V26 L6 32 H22",
        "L": "M0 0 V32 H22",
        "I": "M2 0 H22 M12 0 V32 M2 32 H22",
        "K": "M0 0 V32 M22 0 L0 16 L22 32",
        "G": "M22 0 H6 L0 6 V26 L6 32 H22 V17 H13",
        "T": "M0 0 H24 M12 0 V32",
    }
    wordmark = "".join(
        f'<path transform="translate({i * 37} 0)" d="{letters[letter]}" />'
        for i, letter in enumerate("CLICKGIT")
    )
    return svg_document(492, 942, f"""
<defs>
  <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="{NAVY}"/><stop offset="1" stop-color="#102B45"/>
  </linearGradient>
  <radialGradient id="halo">
    <stop stop-color="#147395" stop-opacity=".32"/>
    <stop offset="1" stop-color="#147395" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="492" height="942" fill="url(#panel)"/>
<g fill="none" stroke="#25739B" stroke-width="1" opacity=".14">{grid}</g>
<circle cx="246" cy="373" r="235" fill="url(#halo)"/>
<g fill="none" stroke="#258EBC" stroke-width="2" opacity=".6">
  <path d="M0 190 H110 L176 256 V280 M492 174 H390 L322 242 V279"/>
  <path d="M0 628 H92 L158 562 V499 M492 685 H389 L335 631 V490"/>
  <path d="M38 40 H112 M38 40 V114 M454 828 V902 H380"/>
  <path d="M38 860 H224 M38 878 H158"/>
</g>
<g fill="{CYAN}">
  <circle cx="110" cy="190" r="5"/><circle cx="390" cy="174" r="5"/>
  <circle cx="92" cy="628" r="5"/><circle cx="389" cy="685" r="5"/>
  <rect x="38" y="63" width="6" height="26"/>
</g>
<g transform="translate(96 223) scale(1.171875)">{CHIP}</g>
<g transform="translate(108 581)" fill="none" stroke="#ECFCFF" stroke-width="3.5"
   stroke-linejoin="round" stroke-linecap="square">{wordmark}</g>
<path d="M176 645 H316" stroke="{CYAN}" stroke-width="3"/>
<g fill="#258EBC">
  <rect x="38" y="898" width="6" height="6"/>
  <rect x="51" y="898" width="6" height="6"/>
  <rect x="64" y="898" width="6" height="6"/>
</g>
""")


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    icon_svg = svg_document(256, 256, CHIP)
    panel_svg = wizard_panel_svg()
    small_svg = svg_document(
        192, 192,
        f'<rect width="192" height="192" fill="{NAVY}"/>'
        f'<g transform="translate(20 20) scale(.59375)">{CHIP}</g>',
    )
    assets = {
        "clickgit.svg": icon_svg.encode("utf-8"),
        "wizard-panel.svg": panel_svg.encode("utf-8"),
        "wizard-small.svg": small_svg.encode("utf-8"),
        "wizard-panel.png": render_png(panel_svg, 492, 942),
        "wizard-small.png": render_png(small_svg, 192, 192),
    }
    frames = [(size, render_png(icon_svg, size, size)) for size in ICON_SIZES]
    assets.update({f"clickgit-{size}.png": payload for size, payload in frames})
    assets["clickgit.ico"] = ico_bytes(frames)
    for name, data in assets.items():
        path = output / name
        if path.is_symlink():
            raise ValueError(f"Refusing to overwrite symbolic link: {path}")
        path.write_bytes(data)
    print(f"Generated {len(assets)} brand assets in {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    generate(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
