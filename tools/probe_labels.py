#!/usr/bin/env python3
"""Calibrate a new layout template.

Run this on the enhanced_gray.png of ONE clean specimen of a new form layout:

    python tools/probe_labels.py runs/mydoc/enhanced_gray.png

It prints every OCR line with its y position and a rel_y column normalized
between the first and last line you will pick as reference anchors. Copy the
printed-label lines into a new config/templates/<layout>.json (see
volet_v1.json for the shape), set each anchor's rel_y from this output, give
the template a detect_keyword that appears only on this layout, and the
locator handles the rest (fuzzy matching, occurrence disambiguation,
interpolation of anchors OCR misses on worse scans).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from pipeline.locate import ocr_lines  # noqa: E402


def main() -> None:
    gray = cv2.imread(sys.argv[1], 0)
    lines = ocr_lines(gray)
    ys = [ln.bbox[1] for ln in lines]
    y0, y1 = min(ys), max(ys)
    span = max(1, y1 - y0)
    print(f"{'y':>5} {'rel_y':>7}  x     text")
    for ln in lines:
        x, y, w, h = ln.bbox
        print(f"{y:5d} {round((y - y0) / span, 3):7} {x:5d}  {ln.text[:70]}")


if __name__ == "__main__":
    main()
