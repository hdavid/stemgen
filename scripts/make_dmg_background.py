#!/usr/bin/env python3
"""Generate the .dmg background image (assets/dmg/background.tiff).

Draws the classic installer hint — an arrow from the app icon position to
the /Applications icon position plus a "drag to install" caption — at 1x
and 2x, then combines both into a single HiDPI TIFF via `tiffutil`.

The output is committed to the repo (assets/dmg/background.tiff) so the
packaging step never has to draw anything; re-run this script only when
the design or the geometry in scripts/dmg_settings.py changes.

Geometry must stay in sync with scripts/dmg_settings.py:
  window content:      660 x 400
  app icon center:     (166, 170)   (top-left origin)
  Applications center: (494, 170)
"""

import pathlib
import subprocess
import sys
import tempfile

import AppKit
import Foundation

WIDTH, HEIGHT = 660, 400
ICON_Y = 170          # icon center, top-left origin — matches dmg_settings.py
ARROW_X0, ARROW_X1 = 258, 402
CAPTION = "Drag StemGen into Applications to install"
CAPTION_Y = 318       # baseline area, top-left origin


def render(scale: int, out_png: pathlib.Path) -> None:
    px_w, px_h = WIDTH * scale, HEIGHT * scale
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, px_w, px_h, 8, 4, True, False, AppKit.NSCalibratedRGBColorSpace, 0, 0
    )
    rep.setSize_((WIDTH, HEIGHT))

    AppKit.NSGraphicsContext.saveGraphicsState()
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)

    # Background fill.
    AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.955, 1.0).setFill()
    AppKit.NSBezierPath.fillRect_(((0, 0), (WIDTH, HEIGHT)))

    # AppKit origin is bottom-left; convert the top-left design coords.
    arrow_y = HEIGHT - ICON_Y

    grey = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.62, 1.0)
    grey.setStroke()
    grey.setFill()

    # Arrow shaft.
    shaft = AppKit.NSBezierPath.bezierPath()
    shaft.setLineWidth_(5.0)
    shaft.setLineCapStyle_(AppKit.NSLineCapStyleRound)
    shaft.moveToPoint_((ARROW_X0, arrow_y))
    shaft.lineToPoint_((ARROW_X1 - 14, arrow_y))
    shaft.stroke()

    # Arrow head.
    head = AppKit.NSBezierPath.bezierPath()
    head.moveToPoint_((ARROW_X1, arrow_y))
    head.lineToPoint_((ARROW_X1 - 20, arrow_y + 12))
    head.lineToPoint_((ARROW_X1 - 20, arrow_y - 12))
    head.closePath()
    head.fill()

    # Caption, centered horizontally.
    font = AppKit.NSFont.systemFontOfSize_(15.0)
    attrs = {
        AppKit.NSFontAttributeName: font,
        AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.42, 1.0),
    }
    text = Foundation.NSString.stringWithString_(CAPTION)
    size = text.sizeWithAttributes_(attrs)
    text.drawAtPoint_withAttributes_(((WIDTH - size.width) / 2, HEIGHT - CAPTION_Y), attrs)

    AppKit.NSGraphicsContext.restoreGraphicsState()

    png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    ok = png.writeToFile_atomically_(str(out_png), True)
    if not ok:
        sys.exit(f"failed to write {out_png}")


def main() -> None:
    out = pathlib.Path(__file__).resolve().parent.parent / "assets" / "dmg" / "background.tiff"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        one_x = pathlib.Path(td) / "background.png"
        two_x = pathlib.Path(td) / "background@2x.png"
        render(1, one_x)
        render(2, two_x)
        # -cathidpicheck merges 1x+2x into a single HiDPI TIFF Finder
        # renders crisply on retina displays.
        subprocess.run(
            ["tiffutil", "-cathidpicheck", str(one_x), str(two_x), "-out", str(out)],
            check=True,
        )
    print(f"→ {out}")


if __name__ == "__main__":
    main()
