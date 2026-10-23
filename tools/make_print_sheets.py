r"""Print sheets for a judge or a new user: the box markers and the calibration board, as vector PDFs at true size.

    python tools/make_print_sheets.py            -> docs/print/markers_A4.pdf, docs/print/charuco_A4.pdf

The marker and board settings come from tools/common.py (the same ones the agent and tools/calibrate.py use).
Every cell of every marker is drawn as a filled square in millimetres, so a print at 100% (actual size) gives
an 80 mm box marker and 30 mm board squares. Measure the print anyway and pass the values with --marker-mm and
--square-mm.
"""
import argparse
import os

import cv2
import numpy as np

import common

PT_PER_MM = 72.0 / 25.4
A4 = (210.0, 297.0)                 # mm, portrait
MARKER_IDS = (0, 1, 2)              # the boxes in config/boxes.json
CUT_MM = 100.0                      # white square around each 80 mm marker (10 mm quiet zone), cut along it
RULER_MM = 100.0


class Page:
    """A PDF page drawn in millimetres from the top-left corner."""

    def __init__(self, w_mm, h_mm):
        self.w, self.h = w_mm, h_mm
        self.ops = []

    def _y(self, y_mm, h_mm=0.0):
        return (self.h - y_mm - h_mm) * PT_PER_MM

    def rect(self, x, y, w, h, fill=True, gray=0.0, line=0.25, dash=None):
        r = f"{x * PT_PER_MM:.4f} {self._y(y, h):.4f} {w * PT_PER_MM:.4f} {h * PT_PER_MM:.4f} re"
        if fill:
            self.ops.append(f"{gray:.3f} g {r} f")
        else:
            d = f"[{' '.join(f'{v * PT_PER_MM:.3f}' for v in dash)}] 0 d" if dash else "[] 0 d"
            self.ops.append(f"{gray:.3f} G {line * PT_PER_MM:.3f} w {d} {r} S [] 0 d")

    def line(self, x0, y0, x1, y1, width=0.2, gray=0.0):
        self.ops.append(f"{gray:.3f} G {width * PT_PER_MM:.3f} w {x0 * PT_PER_MM:.4f} {self._y(y0):.4f} m "
                        f"{x1 * PT_PER_MM:.4f} {self._y(y1):.4f} l S")

    def text(self, x, y, s, size=9.0, bold=False, gray=0.0, center=False):
        # Helvetica with WinAnsiEncoding: plain ASCII plus the middle dot; width estimated for centring only
        if center:
            x -= len(s) * size * 0.5 / PT_PER_MM / 2
        esc = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self.ops.append(f"BT {gray:.3f} g /{'F2' if bold else 'F1'} {size:.2f} Tf "
                        f"{x * PT_PER_MM:.4f} {self._y(y):.4f} Td ({esc}) Tj ET")

    def cells(self, x, y, side, bits):
        """A marker from its bit image (one pixel per cell, 0 = black), side in mm."""
        n = bits.shape[0]
        c = side / n
        self.rect(x, y, side, side, gray=1.0)
        for r in range(n):
            for k in range(n):
                if bits[r, k] < 128:
                    self.rect(x + k * c, y + r * c, c, c)

    def ruler(self, x, y, length=RULER_MM):
        self.line(x, y, x + length, y, width=0.3)
        for mm in range(int(length) + 1):
            tick = 6.0 if mm % 10 == 0 else 4.0 if mm % 5 == 0 else 2.5
            self.line(x + mm, y, x + mm, y + tick, width=0.15 if mm % 5 else 0.25)
            if mm % 10 == 0:
                self.text(x + mm - 0.9, y + 10.0, str(mm // 10), size=7)
        self.text(x + length + 3, y + 5.0, f"{int(length)} mm (cm marks). Measure it: it must be {int(length)} mm.", size=7.5)


def write_pdf(path, pages):
    objs = []

    def add(body):
        objs.append(body)
        return len(objs)

    font1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 1 + 2 * len(pages)
    kids = []
    for p in pages:
        stream = "\n".join(p.ops).encode("cp1252")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add((f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {p.w * PT_PER_MM:.4f} {p.h * PT_PER_MM:.4f}] "
                    f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> /Contents {content} 0 R >>").encode())
        kids.append(page)
    assert add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()) == pages_id
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R /ViewerPreferences << /PrintScaling /None >> >>".encode())
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    with open(path, "wb") as f:
        f.write(bytes(out))


def marker_bits(dictionary, marker_id):
    d = cv2.aruco.getPredefinedDictionary(dictionary)
    return cv2.aruco.generateImageMarker(d, marker_id, d.markerSize + 2)       # one pixel per cell, 1-cell border


def markers_page():
    p = Page(*A4)
    side = common.BOX_MARKER_MM
    p.text(10, 9, "Drystone box markers: ArUco DICT_4X4_50, black square exactly 80 mm", size=11, bold=True)
    p.text(10, 14.5, "Print at 100% (Actual size). Do not fit to page.", size=10, bold=True)
    spots = [(5.0, 20.0), (105.0, 20.0), (5.0, 124.0)]
    for marker_id, (x, y) in zip(MARKER_IDS, spots):
        p.rect(x, y, CUT_MM, CUT_MM, fill=False, gray=0.45, line=0.25, dash=(2.0, 1.5))
        q = (CUT_MM - side) / 2
        p.cells(x + q, y + q, side, marker_bits(common.BOX_DICT, marker_id))
        p.text(x + CUT_MM / 2, y + CUT_MM - 3.6, f"ID {marker_id} · {side:.0f} mm", size=8, center=True, gray=0.25)
    notes = ["Cut along the dashed lines. Keep the white border:",
             "the camera needs it to find the marker.",
             "",
             "Stick one marker in the middle of the front",
             "face of each box, flat and straight:",
             "ID 0 on the bottom box, then ID 1, ID 2.",
             "",
             "Measure the black square of one printed",
             "marker and pass it to the agent, e.g.",
             "  python tools/agent.py --marker-mm 80",
             "",
             "Box sizes and weights per ID go in",
             "config/boxes.json."]
    for i, s in enumerate(notes):
        p.text(112, 132 + i * 5.2, s, size=8.5, bold=(i == 0))
    p.ruler(10, 244)
    p.text(10, 268, "Print at 100% (Actual size). Do not fit to page.", size=10, bold=True)
    p.text(10, 274, "Generated by tools/make_print_sheets.py (OpenCV 5, settings from tools/common.py).", size=7, gray=0.35)
    return p


def charuco_page():
    w, h = A4[1], A4[0]                 # landscape: the 210 x 150 mm board would touch both edges of a portrait A4
    p = Page(w, h)
    board = common.make_board(common.BOARD_SQUARE_MM)
    cols, rows = common.BOARD_SQUARES
    sq = common.BOARD_SQUARE_MM
    x0, y0 = (w - cols * sq) / 2, 20.0
    ids = board.getIds().flatten()
    corners = board.getObjPoints()      # metres, x right and y down from the board's top-left corner
    white = set()
    for mid, c in zip(ids, corners):
        c = np.asarray(c)[:, :2] * 1000.0
        cx, cy = c.mean(axis=0)
        white.add((int(cy // sq), int(cx // sq)))
        x, y = c[:, 0].min(), c[:, 1].min()
        p.cells(x0 + x, y0 + y, c[:, 0].max() - x, marker_bits(common.BOARD_DICT, int(mid)))
    for r in range(rows):
        for k in range(cols):
            if (r, k) not in white:
                p.rect(x0 + k * sq, y0 + r * sq, sq, sq)
    p.text(x0, 9, f"Drystone calibration board: ChArUco {cols}x{rows}, squares {sq:.0f} mm, markers "
                  f"{sq * common.BOARD_MARKER_RATIO:.0f} mm, DICT_5X5_100", size=11, bold=True)
    p.text(x0, 14.5, "Print at 100% (Actual size). Do not fit to page.", size=10, bold=True)
    p.text(x0, y0 + rows * sq + 8, "Mount on a rigid, flat board. Measure a square and pass it as --square-mm.", size=10, bold=True)
    p.text(x0, y0 + rows * sq + 13.5, "e.g.  python tools/calibrate.py --name laptop --square-mm 29.8 --auto", size=8.5)
    p.ruler(x0, y0 + rows * sq + 18)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(common.ROOT, "docs", "print"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, page in (("markers_A4.pdf", markers_page()), ("charuco_A4.pdf", charuco_page())):
        path = os.path.join(args.out, name)
        write_pdf(path, [page])
        print(f"wrote {os.path.relpath(path, common.ROOT)}")


if __name__ == "__main__":
    main()
