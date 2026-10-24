r"""Camera calibration with the ChArUco board (docs/print/charuco_A4.pdf).

Prepare the board first: tape the sheet on all four sides to something hard and flat (a hardcover book, a
clipboard, thick card), then measure the side of one black square (for example 29.8 mm).
A bent sheet makes the calibration fail, and no lens model can fix that.

Laptop webcam, guided (default): a blue outline shows where to hold the board and how to tilt it. Match it, hold
still, and the frame is saved by itself; then the next outline comes (14 targets). The calibration runs at the end.
    python tools/calibrate.py --name laptop --square-mm 29.8

Laptop webcam, free (--auto): no outlines; a frame is saved each time the board is held still at a new position:
    python tools/calibrate.py --name laptop --square-mm 29.8 --auto

Laptop webcam, with someone pressing SPACE (--manual):
    python tools/calibrate.py --name laptop --square-mm 29.8 --manual

Phone photos (15-25 photos of the board, zoom 1x, same orientation, in data/calib_hp/):
    python tools/calibrate.py --name hp --square-mm 29.8 --images "data/calib_hp/*.jpg"

Guide in the camera window:
  - green cells = parts of the image already covered by board corners. Cover at least 9 of the 12 cells,
    especially the corners and edges of the image.
  - tilt = estimated angle of the board to the camera. For each side (left, right, top, bottom), try to
    have a frame with the board tilted 20-40 degrees.
  - a frame almost the same as a saved one is rejected.
Keys (KEYS below): guided N = skip target, B = back one target, C = calibrate now, Q = quit;
--auto C, Q; --manual SPACE = save frame, C, Q.

Every result gets a verdict. PASS is saved to data/camera_<name>.yaml. RETRY is saved to
data/camera_<name>_draft.yaml with its list of fixes, so an older calibration that passed
is not overwritten. (In the YAML, `quality` keeps the values LAYAK / ULANGI: see common.CALIB_PASS.)
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

import agent_hud as hud
import common

MIN_CORNERS = 8          # ChArUco corners needed to keep a view
MIN_VIEWS = 10           # distinct views needed before calibrating
SAME_SHIFT = 0.05        # a view repeats a saved one if the board outline moved less than 5% of its size
SAME_TURN_DEG = 15.0     # ... and the board turned less than this
MIN_TILT_DEG = 20.0      # a view counts as tilted toward a side from this angle
GRID = (4, 3)            # image coverage grid: columns, rows
CELL_POINTS = 4          # saved corners a grid cell needs to count as covered
MAX_RMS_PX = 1.0
MAX_F_SD_PCT = 1.0       # 1-sigma uncertainty of fx and fy, in percent
MIN_CELLS = 9
STILL_PX = 2.0           # auto mode: corners moving less than this per frame count as held still
STILL_SEC = 0.8          # ... for this long before the frame is saved
SIDES = ("left", "right", "top", "bottom")
# keys per mode: the camera loop handles exactly these, the intro and the bottom bar print them, and the judges'
# Setup tab lists the guided ones (tests/test_setup_commands.py checks that they stay the same)
KEYS = {"guided": (("N", "skip target"), ("B", "back one target"), ("C", "calibrate now"), ("Q", "quit")),
        "auto": (("C", "calibrate now"), ("Q", "quit")),
        "manual": (("SPACE", "save frame"), ("C", "calibrate"), ("Q", "quit"))}

# ---------------------------------------------------------------- guided mode: one target outline at a time
GUIDE_F = 0.7            # focal length guess (x image width) to draw the targets and read the tilt against them
MATCH_POS = 0.06         # matched: the four outline corners within 6% of the image diagonal on average,
MATCH_TILT_DEG = 10.0    # the tilt within 10 degrees of the target's,
MATCH_SEC = 0.5          # held still for half a second
FULL_CORNERS = 20        # targets away from the image corners want (almost) the whole board: 20 of its 24 corners
HINT_POS = 0.03          # hints: move when the centre is off by more than 3% of the diagonal,
HINT_SCALE = 0.12        # closer / further when the size is off by more than 12%,
HINT_TILT_DEG = 6.0      # tilt when an angle is off by more than 6 degrees
# (name, centre x and y as fractions of the image, board width as a fraction of the image width when flat, yaw, pitch)
# yaw < 0: the board's left side away from the camera (it faces the left of the image); pitch < 0: its top away.
# The first nine cover all 12 coverage cells and the four tilt sides; the other five add perspective, which pins down
# the focal length.
TARGETS = (
    ("centre, flat", 0.50, 0.50, 0.36, 0, 0),
    ("top-left corner", 0.21, 0.28, 0.28, 0, 0),
    ("top-right corner", 0.79, 0.28, 0.28, 0, 0),
    ("bottom-right corner", 0.79, 0.72, 0.28, 0, 0),
    ("bottom-left corner", 0.21, 0.72, 0.28, 0, 0),
    ("left edge, left side away", 0.25, 0.50, 0.30, -30, 0),
    ("right edge, right side away", 0.75, 0.50, 0.30, 30, 0),
    ("top edge, top away", 0.50, 0.29, 0.30, 0, -30),
    ("bottom edge, bottom away", 0.50, 0.71, 0.30, 0, 30),
    ("close to the camera", 0.50, 0.50, 0.52, 0, 0),
    ("top-left, tilted", 0.30, 0.34, 0.27, 25, 22),
    ("top-right, tilted", 0.70, 0.34, 0.27, -25, 22),
    ("bottom-left, tilted", 0.30, 0.66, 0.27, 25, -22),
    ("bottom-right, tilted", 0.70, 0.66, 0.27, -25, -22),
)
CORNER_TARGETS = {1, 2, 3, 4}   # these may lose a few board corners at the image edge


class BoardView:
    """One detected board: its corners plus what the duplicate check and the guide need."""

    def __init__(self, board, corners, ids, size, name=""):
        self.name = name
        obj, img = board.matchImagePoints(corners, ids)
        self.obj = np.asarray(obj, np.float32).reshape(-1, 3)
        self.img = np.asarray(img, np.float32).reshape(-1, 2)
        self.outline = board_outline(board, self.obj, self.img)
        self.normal = rough_normal(self.obj, self.img, size)
        self.guide_normal = rough_normal(self.obj, self.img, size, GUIDE_F)   # the tilt as the guided targets see it


def detect(detector, img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _, _ = detector.detectBoard(gray)
    return corners, ids, (0 if ids is None else len(ids))


def board_outline(board, obj, img):
    """Image position of the board's four outer corners (via the plane homography), or None."""
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    H, _ = cv2.findHomography(obj[:, :2], img, 0)
    if H is None:
        return None
    quad = np.float32([[0, 0], [cols * s, 0], [cols * s, rows * s], [0, rows * s]]).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(quad, H).reshape(-1, 2)


def rough_normal(obj, img, size, f_frac=0.8):
    """Board normal (pointing at the camera) in camera axes, from a pose with a guessed focal length.

    A guess of 0.8 x image width is enough to tell how far and which way the board is turned;
    the real focal length is what the calibration is about to measure."""
    f = f_frac * size[0]
    K = np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]])
    ok, rvec, _ = cv2.solvePnP(obj, img, K, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return np.array([0.0, 0.0, -1.0])
    R, _ = cv2.Rodrigues(rvec)
    return -R[:, 2]


def turn(normal):
    """(left-right, up-down) turn in degrees. Negative = the board faces the left / top of the image."""
    yaw = float(np.degrees(np.arctan2(normal[0], -normal[2])))
    pitch = float(np.degrees(np.arctan2(normal[1], -normal[2])))
    return yaw, pitch


def tilt_sides(normal):
    yaw, pitch = turn(normal)
    hits = (yaw <= -MIN_TILT_DEG, yaw >= MIN_TILT_DEG, pitch <= -MIN_TILT_DEG, pitch >= MIN_TILT_DEG)
    return {side for side, hit in zip(SIDES, hits) if hit}


def tilt_text(normal):
    yaw, pitch = turn(normal)
    return (f"tilt {'left' if yaw < 0 else 'right'} {abs(yaw):.0f}, "
            f"{'top' if pitch < 0 else 'bottom'} {abs(pitch):.0f} degrees")


def find_repeat(view, saved):
    """The saved view this one practically repeats (same place, same tilt), or None."""
    if view.outline is None:
        return None
    for s in saved:
        if s.outline is None:
            continue
        move = np.mean(np.linalg.norm(view.outline - s.outline, axis=1))
        size_px = 0.5 * (np.linalg.norm(view.outline[0] - view.outline[2]) +
                         np.linalg.norm(s.outline[0] - s.outline[2]))
        turned = np.degrees(np.arccos(np.clip(np.dot(view.normal, s.normal), -1.0, 1.0)))
        if move / size_px < SAME_SHIFT and turned < SAME_TURN_DEG:
            return s
    return None


def guide_camera(size):
    f = GUIDE_F * size[0]
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]], float)


def _rot(axis, deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) if axis == "y" else np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def target_pose(board, size, t):
    """(R, tvec) that puts the board where target t asks, seen through guide_camera: rotation about the vertical axis
    (yaw) and then the horizontal one (pitch), the board's centre on the asked image point."""
    _, cx, cy, wfrac, yaw, pitch = t
    K = guide_camera(size)
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    bw, bh = cols * s, rows * s
    z = K[0, 0] * bw / (wfrac * size[0])
    centre = z * (np.linalg.inv(K) @ np.array([cx * size[0], cy * size[1], 1.0]))
    R = _rot("y", -yaw) @ _rot("x", pitch)          # turn() reads yaw = -rotation about y, pitch = rotation about x
    return R, centre - R @ np.array([bw / 2, bh / 2, 0.0])


def board_corners_3d(board):
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    return np.float32([[0, 0, 0], [cols * s, 0, 0], [cols * s, rows * s, 0], [0, rows * s, 0]])


def project_outline(board, R, tvec, size):
    """The board's four outer corners in the image (same order as board_outline), through guide_camera."""
    cam = (R @ board_corners_3d(board).T).T + tvec
    p = (guide_camera(size) @ cam.T).T
    return (p[:, :2] / p[:, 2:]).astype(np.float32)


def quad_distance(a, b):
    """Mean distance of the four corners of two outlines, whichever way round the board is held."""
    return float(min(np.mean(np.linalg.norm(np.roll(a, k, axis=0) - b, axis=1)) for k in range(4)))


class Guide:
    """Guided mode: one target outline at a time. A board that matches it and is held still is saved, then the next
    target comes. check() also says what to change when it does not match yet."""

    def __init__(self, board, size):
        self.size, self.i, self.since = size, 0, None
        self.diag = float(np.hypot(*size))
        self.targets = []
        for k, t in enumerate(TARGETS):
            R, tvec = target_pose(board, size, t)
            self.targets.append({"name": t[0], "quad": project_outline(board, R, tvec, size), "yaw": t[4],
                                 "pitch": t[5], "need": MIN_CORNERS if k in CORNER_TARGETS else FULL_CORNERS})

    @property
    def done(self):
        return self.i >= len(self.targets)

    def target(self):
        return None if self.done else self.targets[self.i]

    def check(self, view, n):
        """(matched, hints) for the board seen now against the current target."""
        t = self.target()
        if view is None or view.outline is None or n < t["need"]:
            return False, ["show the whole board"]
        q, tq = view.outline, t["quad"]
        hints = []
        d = (tq.mean(axis=0) - q.mean(axis=0)) / self.diag
        if abs(d[0]) > HINT_POS:
            hints.append("move right" if d[0] > 0 else "move left")
        if abs(d[1]) > HINT_POS:
            hints.append("move down" if d[1] > 0 else "move up")
        scale = float(np.sqrt(cv2.contourArea(q.astype(np.float32)) / cv2.contourArea(tq)))
        if scale < 1 - HINT_SCALE:
            hints.append("closer")
        elif scale > 1 + HINT_SCALE:
            hints.append("further")
        yaw, pitch = turn(view.guide_normal)
        dy, dp = t["yaw"] - yaw, t["pitch"] - pitch
        for delta, flat, less, more in ((dy, t["yaw"] == 0, "tilt left side away", "tilt right side away"),
                                        (dp, t["pitch"] == 0, "tilt top away", "tilt bottom away")):
            if abs(delta) > HINT_TILT_DEG:
                hints.append("face the camera" if flat else less if delta < 0 else more)
        hints = list(dict.fromkeys(hints))                 # "face the camera" only once
        matched = (quad_distance(q, tq) < MATCH_POS * self.diag and abs(dy) <= MATCH_TILT_DEG
                   and abs(dp) <= MATCH_TILT_DEG)
        if matched:
            return True, []
        return False, hints or ["line the corners up with the blue outline"]

    def update(self, view, n, views, now, still=True):
        """One camera frame. Returns (event, hints): "save" (the caller saves the view, then calls next()), "hold",
        "repeat" (it matches, but repeats a saved frame), "move" (not matched yet) or "done"."""
        if self.done:
            return "done", []
        matched, hints = self.check(view, n)
        if not matched:
            self.since = None
            return "move", hints
        same = find_repeat(view, views)
        if same is not None:
            self.since = None
            return "repeat", [f"already saved as {same.name}: N for the next target"]
        if not still:
            self.since = None
            return "hold", ["hold still..."]
        self.since = now if self.since is None else self.since
        if now - self.since >= MATCH_SEC:
            self.since = None
            return "save", []
        return "hold", ["hold still..."]

    def next(self):
        self.i, self.since = min(self.i + 1, len(self.targets)), None

    def back(self):
        self.i, self.since = max(self.i - 1, 0), None


def coverage(views, size):
    """Boolean grid (rows x columns): which parts of the image the saved corners cover."""
    counts = np.zeros((GRID[1], GRID[0]), int)
    for v in views:
        col = np.clip((v.img[:, 0] * GRID[0] / size[0]).astype(int), 0, GRID[0] - 1)
        row = np.clip((v.img[:, 1] * GRID[1] / size[1]).astype(int), 0, GRID[1] - 1)
        np.add.at(counts, (row, col), 1)
    return counts >= CELL_POINTS


def calibrate(views, size):
    if len(views) < MIN_VIEWS:
        print(f"Only {len(views)} different board positions so far, at least {MIN_VIEWS} needed.")
        return None
    obj = [v.obj for v in views]
    img = [v.img for v in views]
    # k3 is left out: with 15-25 views it tends to overfit on ordinary webcams and phone cameras
    rms, K, dist, _, _, sd, _, per_view = cv2.calibrateCameraExtended(
        obj, img, size, None, None, flags=cv2.CALIB_FIX_K3)
    return rms, K, dist, np.asarray(sd).ravel(), np.asarray(per_view).ravel()


def assess(views, size, rms, K, sd):
    """Acceptance rules. Returns (verdict, fixes, f_sd_pct, cells, sides)."""
    f_sd = 100.0 * max(sd[0] / K[0, 0], sd[1] / K[1, 1])
    cells = coverage(views, size)
    sides = set().union(*(tilt_sides(v.normal) for v in views))
    missing = [s for s in SIDES if s not in sides]
    fixes = []
    if rms > MAX_RMS_PX:
        fixes.append("RMS too high: the board is not flat or the image is blurred. Fix the board to something hard, "
                     "hold it still while a frame is taken, and use enough light.")
    if f_sd > MAX_F_SD_PCT:
        # with a bent board the focal length drifts too; then the RMS fix above comes first
        if missing:
            fixes.append("Focal length not certain yet: tilt the board 20-40 degrees, especially toward the "
                         + ", ".join(missing) + ".")
        elif rms <= MAX_RMS_PX:
            fixes.append("Focal length not certain yet: tilt the board further (30-40 degrees) and add frames.")
    if cells.sum() < MIN_CELLS:
        fixes.append("Not enough coverage: put the board in the '.' cells of the coverage map (corners and edges of the image).")
    return ("ULANGI" if fixes else "LAYAK"), fixes, f_sd, cells, sides


def _rule():
    return hud.rule() if hud.COLOR else "-" * 72      # the box-drawing line only on a terminal (cp1252 pipes)


def _tag(text, kind):
    """A coloured label on a terminal, the plain word otherwise (files, pipes)."""
    return hud.label(text, kind) if hud.COLOR else text


def _row(key, value):
    print(f"  {hud.paint(f'{key:<15}', fg='MUTED')}{value}")


def report_and_save(views, size, result, args, frames_dir):
    rms, K, dist, sd, per_view = result
    verdict, fixes, f_sd, cells, sides = assess(views, size, rms, K, sd)
    mark = lambda good, bad: hud.paint("OK", fg="GREEN", bold=True) if good else hud.paint(bad, fg="WARN", bold=True)
    print()
    print(_rule())
    print("  " + _tag("CALIBRATION RESULT", "BRAND"))
    _row("Views used", f"{len(views)} different board positions")
    _row("RMS error", f"{rms:.3f} px  {mark(rms <= MAX_RMS_PX, "TOO HIGH")}  (max {MAX_RMS_PX}, good < 0.5)")
    _row("Uncertainty", f"fx {100 * sd[0] / K[0, 0]:.2f}%, fy {100 * sd[1] / K[1, 1]:.2f}%  "
                        f"{mark(f_sd <= MAX_F_SD_PCT, "TOO HIGH")}  (max {MAX_F_SD_PCT}%)")
    _row("Image coverage", f"{cells.sum()}/{cells.size} cells  {mark(cells.sum() >= MIN_CELLS, "TOO LOW")}  "
                           f"(min {MIN_CELLS}; # = covered, . = empty)")
    for row in cells:
        print(" " * 17 + " ".join(hud.paint("#", fg="GREEN", bold=True) if c else hud.paint(".", fg="MUTED")
                                  for c in row))
    _row("Tilt sides", f"{', '.join(s for s in SIDES if s in sides) or 'none yet'}  "
                       f"(estimate, >= {MIN_TILT_DEG:.0f} degrees)")
    _row("fx, fy", f"{K[0, 0]:.1f}, {K[1, 1]:.1f}  (+- {sd[0]:.1f}, {sd[1]:.1f})")
    _row("cx, cy", f"{K[0, 2]:.1f}, {K[1, 2]:.1f}  (+- {sd[2]:.1f}, {sd[3]:.1f}; image {size[0]}x{size[1]})")
    _row("Distortion", ", ".join(f"{v:.4f}" for v in dist.ravel()[:5]))
    worst = np.argsort(per_view)[::-1][:3]
    _row("Worst views", ", ".join(f"{views[i].name} ({per_view[i]:.2f} px)" for i in worst))
    print()
    _row("VERDICT", _tag(common.VERDICT_TEXT[verdict], "GREEN" if verdict == common.CALIB_PASS else "YELLOW"))
    for fix in fixes:
        print("  - " + hud.paint(fix, fg="WARN"))
    if verdict == common.CALIB_PASS and rms > 0.5:
        # simulated: a board sagging 1 mm still passes at ~0.6 px but shifts fx by ~2.5%
        print("  Note: RMS above 0.5 px usually means the board is not quite flat or the image not quite sharp. "
              "It can still be used; the pose test (tools/pose_test.py) decides.")
    name = args.name if verdict == common.CALIB_PASS else f"{args.name}_draft"
    out = os.path.join(common.DATA_DIR, f"camera_{name}.yaml")
    try:
        frames_dir = os.path.relpath(frames_dir, common.ROOT)
    except ValueError:      # Windows: frames on another drive
        pass
    common.save_calibration(out, K, dist, size, rms, len(views), args.square_mm, extra={
        "quality": verdict, "f_sd_pct": float(f_sd), "coverage_cells": int(cells.sum()),
        "tilt_sides": ",".join(s for s in SIDES if s in sides), "frames": frames_dir})
    _row("Saved", out)
    if verdict != common.CALIB_PASS:
        print(" " * 17 + hud.paint(f"(draft; data/camera_{args.name}.yaml is not overwritten)", dim=True))
    print(_rule())
    print()
    return verdict


def run_images(args, board, detector):
    views, size = [], None
    for p in common.list_images(args.images):
        img = common.read_image(p)
        s = (img.shape[1], img.shape[0])
        if size is None:
            size = s
        elif s != size:
            sys.exit(f"{os.path.basename(p)} has a different size ({s[0]}x{s[1]} vs {size[0]}x{size[1]}). "
                     "All photos must come from the same camera, zoom and orientation.")
        name = os.path.basename(p)
        corners, ids, n = detect(detector, img)
        if n < MIN_CORNERS:
            print(f"{name}: {n} corners, skipped (at least {MIN_CORNERS} needed)")
            continue
        view = BoardView(board, corners, ids, size, name)
        same = find_repeat(view, views)
        if same:
            print(f"{name}: {n} corners, almost the same as {same.name}, skipped")
            continue
        views.append(view)
        print(f"{name}: {n} corners, {tilt_text(view.normal)}")
    result = calibrate(views, size)
    if result:
        report_and_save(views, size, result, args, os.path.dirname(os.path.abspath(args.images)))


def corner_map(corners, ids):
    return {int(i): c for i, c in zip(np.asarray(ids).ravel(), np.asarray(corners).reshape(-1, 2))}


def mean_shift(a, b):
    """Average movement (px) of the ChArUco corners two frames have in common."""
    common_ids = set(a) & set(b)
    if len(common_ids) < 4:
        return float("inf")
    return float(np.mean([np.linalg.norm(a[k] - b[k]) for k in common_ids]))


# ---------------------------------------------------------------- camera window (display only, agent_hud style)

WIN = "Drystone calibration"
SAVED_DOT = (154, 214, 127)          # BGR of #7FD69A, the page's "copied" green
LEGEND = (("board now", "EDGE", False), ("covered cell", "GREEN", False))
GUIDE_LEGEND = (("target", "BRAND", False), ("board now", "WHITE", False), ("covered cell", "GREEN", False))
CHIP_SIZE, CHIP_PAD = 15, 9


def side_chips(img, y, sides):
    """A row of rounded chips under the card: one per side, green once a saved view is tilted that way."""
    cap = hud.metrics(CHIP_SIZE, 600)[0]
    h = cap + 2 * CHIP_PAD
    x = hud.M
    chips = [(f"tilt {MIN_TILT_DEG:.0f}+ deg", hud.BGR["NAVY"], hud.BGR["MUTED"])]
    chips += [(s, hud.BGR["GREEN"], hud.BGR["WHITE"]) if s in sides else (s, hud.BGR["NAVY"], hud.BGR["MUTED"])
              for s in SIDES]
    for t, fill, ink in chips:
        w = hud.text_w(t, CHIP_SIZE, 600) + 2 * 12
        hud.rounded(img, x, y, x + w, y + h, h // 2, fill, 0.88)
        hud.text(img, t, (x + 12, y + CHIP_PAD + cap), CHIP_SIZE, ink, 600)
        x += w + 6
    # what the colours mean
    w = hud.text_w("green = done", CHIP_SIZE - 2, 500) + 2 * 10
    hud.rounded(img, x + 4, y, x + 4 + w, y + h, h // 2, hud.BGR["NAVY"], 0.6)
    hud.text(img, "green = done", (x + 14, y + CHIP_PAD + cap), CHIP_SIZE - 2, hud.BGR["MUTED"], 500)
    return y + h


def draw_target(img, quad, matched):
    """The guided target: the board's outline in brand blue with viewfinder corners (green once it matches)."""
    q = quad.astype(np.int32)
    color = hud.BGR["GREEN"] if matched else hud.BGR["BRAND"]
    cv2.polylines(img, [q], True, color, 3, cv2.LINE_AA)
    for k in range(4):                                  # short L brackets at the corners
        p, a, b = q[k].astype(float), q[k - 1].astype(float), q[(k + 1) % 4].astype(float)
        for o in (a, b):
            e = p + (o - p) * min(1.0, 34 / max(1.0, np.linalg.norm(o - p)))
            cv2.line(img, tuple(int(v) for v in p), tuple(int(v) for v in e), hud.BGR["EDGE"], 6, cv2.LINE_AA)


def progress_bar(img, y, done, total):
    x0, w, h = hud.M, 260, 8
    hud.rounded(img, x0, y, x0 + w, y + h, h // 2, hud.BGR["NAVY"], 0.85)
    if done:
        hud.rounded(img, x0, y, x0 + max(h, int(w * done / total)), y + h, h // 2, hud.BGR["BRAND"], 0.95)


def next_step(views, cur, n, size, cells, sides):
    """What the person should do now, as (text, pill kind)."""
    missing = [s for s in SIDES if s not in sides]
    if cur is None:
        return f"show the whole board: {n} corners found, at least {MIN_CORNERS} needed", "warn"
    if cur.outline is not None and cv2.contourArea(cur.outline) < 0.05 * size[0] * size[1]:
        return "board too small in the image: move it closer", "warn"
    if missing:
        return f"no board tilted toward: {', '.join(missing)} yet", "info"
    if cells.sum() < cells.size:
        return "move the board to cells that are not green yet (corners and edges)", "info"
    if len(views) < MIN_VIEWS:
        return f"add frames at other positions (at least {MIN_VIEWS})", "info"
    return "coverage and tilts complete: press C to calibrate", "ok"


def draw_guide(frame, views, cur, corners, n, size, status, keys, title, note=None, guide=None, matched=False):
    """Live view: covered grid cells in green, saved corners as dots, the board now in blue, a card with the
    counts and the current tilt, chips for the four tilt sides, then the next step (and the last verdict) as pills.
    Guided mode adds the target outline, the board now in white, and "target 4/14" with a progress bar."""
    cells = coverage(views, size)
    cw, ch = size[0] / GRID[0], size[1] / GRID[1]
    canvas = frame.copy()
    over = canvas.copy()
    for r, c in zip(*np.nonzero(cells)):
        cv2.rectangle(over, (int(c * cw), int(r * ch)), (int((c + 1) * cw), int((r + 1) * ch)), hud.BGR["GREEN"], -1)
    canvas = cv2.addWeighted(over, 0.3, canvas, 0.7, 0)
    lines = canvas.copy()
    for c in range(1, GRID[0]):
        cv2.line(lines, (int(c * cw), 0), (int(c * cw), size[1]), hud.BGR["WHITE"], 1, cv2.LINE_AA)
    for r in range(1, GRID[1]):
        cv2.line(lines, (0, int(r * ch)), (size[0], int(r * ch)), hud.BGR["WHITE"], 1, cv2.LINE_AA)
    canvas = cv2.addWeighted(lines, 0.4, canvas, 0.6, 0)
    for v in views:
        for x, y in v.img:
            cv2.circle(canvas, (int(x), int(y)), 2, SAVED_DOT, -1, cv2.LINE_AA)
    if cur is not None and cur.outline is not None:
        cv2.polylines(canvas, [cur.outline.astype(np.int32)], True,
                      hud.BGR["WHITE"] if guide is not None else hud.BGR["EDGE"], 2, cv2.LINE_AA)
    if n:
        for x, y in np.asarray(corners).reshape(-1, 2):
            cv2.circle(canvas, (int(x), int(y)), 5, hud.BGR["NAVY"], -1, cv2.LINE_AA)
            cv2.circle(canvas, (int(x), int(y)), 3, hud.BGR["EDGE"], -1, cv2.LINE_AA)
    sides = set().union(*(tilt_sides(v.normal) for v in views)) if views else set()
    hud.top_bar(canvas, title)
    rows = [{"segs": [(f"{n} corners", 20, 700), ("·", 20, 500), (f"{len(views)} saved", 20, 500), ("·", 20, 500),
                      (f"coverage {cells.sum()}/{cells.size}", 20, 500)]},
            {"segs": [(tilt_text(cur.normal) if cur is not None else
                       "board only partly in view" if n else "no board in view", 16, 500)], "gap": 8}]
    if guide is not None:
        t = guide.target()
        rows.insert(0, {"segs": [(f"target {min(guide.i + 1, len(guide.targets))}/{len(guide.targets)}", 22, 700),
                                 ("·", 20, 500), (t["name"] if t else "all targets done", 20, 500)]})
    y = hud.card(canvas, rows)
    if guide is not None:
        progress_bar(canvas, y + 8, guide.i, len(guide.targets))
        y += 8 + 8
    side_chips(canvas, y + 8, sides)
    hud.pills(canvas, [p for p in (note, status or next_step(views, cur, n, size, cells, sides)) if p])
    hud.bottom_bar(canvas, keys, GUIDE_LEGEND if guide is not None else LEGEND)
    if guide is not None and not guide.done:            # last, so the card never hides part of the outline
        draw_target(canvas, guide.target()["quad"], matched)
    return canvas


def intro(args, frames_dir):
    print()
    print(hud.paint("Drystone", fg="EDGE", bold=True) + hud.paint(" · Camera calibration", bold=True))
    print(_rule())
    for k, v in (("Camera", f"{args.name} (source {args.source}, {args.width}x{args.height})"),
                 ("Board square", f"{args.square_mm:g} mm"), ("Frames", frames_dir),
                 ("Saves", f"data/camera_{args.name}.yaml when the verdict is PASS")):
        print(f"  {hud.paint(f'{k:<15}', fg='MUTED')}{v}")
    print()
    mode = mode_of(args)
    for k, v in KEYS[mode]:
        print(f"  {hud.paint(f'{k:<8}', fg='EDGE', bold=True)}{v}")
    print()
    lines = {"guided": ("Match the board to the blue outline on screen; it saves by itself and moves to the next one.",
                        f"About {len(TARGETS)} targets. The hints say how to move or tilt the board.",
                        "After the last target the calibration runs by itself; C runs it at any time.",
                        "Then the verdict is PASS or RETRY."),
             "auto": ("Hold the board still at a new position: the frame is saved by itself.",
                      "Fill the green grid (corners and edges) and tilt the board left, right, up and down.",
                      f"After {args.target} frames the calibration runs by itself; C runs it at any time.",
                      "Repeat until the verdict is PASS."),
             "manual": ("Press SPACE at each new position and tilt.",
                        "Fill the green grid (corners and edges) and tilt the board left, right, up and down.",
                        f"After at least {MIN_VIEWS} frames, press C to calibrate.",
                        "Repeat until the verdict is PASS.")}[mode]
    for s in lines:
        print(f"  {hud.paint(s, dim=True)}")
    print(_rule())


def mode_of(args):
    return "auto" if args.auto else "manual" if args.manual else "guided"


def run_camera(args, board, detector):
    cap = common.open_camera(args.source, args.width, args.height)
    frames_dir = os.path.join(common.DATA_DIR, f"calib_{args.name}", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(frames_dir, exist_ok=True)
    intro(args, frames_dir)
    mode = mode_of(args)
    keys = " · ".join(f"{k} {v.split()[0]}" for k, v in KEYS[mode])
    allowed = {k for k, _ in KEYS[mode]}
    title = f"Calibration · {args.name} · {args.square_mm:g} mm squares · {mode}"
    views, size, guide = [], None, None
    prev, still_since, auto_done, flash, note = {}, None, False, 0, None
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)   # scale the whole frame, never crop it
    cv2.resizeWindow(WIN, 960, 540)

    def save(frame, view):
        view.name = f"{len(views) + 1:02d}.png"
        views.append(view)
        cv2.imwrite(os.path.join(frames_dir, view.name), frame)
        print(f"{view.name} saved ({len(view.img)} corners, {tilt_text(view.normal)})")

    def compute():
        nonlocal note
        result = calibrate(views, size)
        if not result:
            note = (f"only {len(views)} different board positions: at least {MIN_VIEWS} needed", "warn")
        elif report_and_save(views, size, result, args, frames_dir) == common.CALIB_PASS:
            note = (f"PASS · saved data/camera_{args.name}.yaml · Q to quit", "ok")
        else:
            note = ("RETRY · the terminal says what to fix · add frames, then C", "warn")
            print("Add frames as suggested above, then press C to calibrate again.")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("The camera stopped sending images.")
            break
        size = (frame.shape[1], frame.shape[0])
        if mode == "guided" and guide is None:
            guide = Guide(board, size)
        corners, ids, n = detect(detector, frame)
        cur = BoardView(board, corners, ids, size) if n >= MIN_CORNERS else None
        same = find_repeat(cur, views) if cur is not None else None
        positions = corner_map(corners, ids) if n else {}
        if same is None:
            status = None
        elif same is views[-1]:
            status = (f"{same.name} saved · move to a new position or tilt", "ok")
        else:
            status = (f"like {same.name}: move or tilt the board", "warn")
        matched = False
        free = mode == "auto" or (mode == "guided" and guide.done)   # after the last target: free, like --auto
        if mode == "guided" and not guide.done:
            still = bool(prev) and mean_shift(positions, prev) < STILL_PX
            event, hints = guide.update(cur, n, views, time.time(), still)
            matched = event in ("hold", "save")
            if event == "save":
                save(frame, cur)
                print(f"  target {guide.i + 1}/{len(guide.targets)} done: {guide.target()['name']}")
                guide.next()
                flash, status = 4, None
                if guide.done and not auto_done:
                    auto_done = True
                    compute()
            else:
                status = (" · ".join(hints), "ok" if event == "hold" else "warn" if event == "repeat" else "info")
        elif free and (cur is None or same):
            still_since = None
            if mode == "guided" and status is None:
                status = ("all targets done: hold the board still anywhere to add frames, C to calibrate", "info")
        elif free:
            still = bool(prev) and mean_shift(positions, prev) < STILL_PX
            still_since = (still_since or time.time()) if still else None
            if still_since and time.time() - still_since >= STILL_SEC:
                save(frame, cur)
                still_since, flash, status = None, 4, None
                if mode == "auto" and len(views) >= args.target and not auto_done:
                    auto_done = True
                    compute()
            else:
                status = ("hold still...", "info")
        prev = positions
        canvas = draw_guide(frame, views, cur, corners, n, size, status, keys, title, note, guide, matched)
        if flash:
            cv2.rectangle(canvas, (0, 0), (size[0] - 1, size[1] - 1), hud.BGR["GREEN"], 10)
            flash -= 1
        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(1) & 0xFF
        press = "Q" if key == 27 else "SPACE" if key == ord(" ") else chr(key).upper() if key != 255 else ""
        if press not in allowed:
            continue
        if press == "SPACE":
            if cur is None:
                print(f"Not saved: only {n} corners found, at least {MIN_CORNERS} needed.")
            elif same:
                print(f"Not saved: almost the same as {same.name}. Move or tilt the board first.")
            else:
                save(frame, cur)
                flash = 4
        elif press == "N":
            guide.next()
        elif press == "B":
            guide.back()
        elif press == "C":
            compute()
        elif press == "Q":
            break
    cap.release()
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Camera calibration with the ChArUco board")
    ap.add_argument("--name", required=True, help="camera name, for example mycam; saves data/camera_<name>.yaml")
    ap.add_argument("--square-mm", type=float, default=common.BOARD_SQUARE_MM,
                    help="side of one printed board square, in mm (measure your print)")
    ap.add_argument("--images", help='photo file pattern, for example "data/calib_hp/*.jpg"')
    ap.add_argument("--source", default="0", help="webcam index (0, 1, ...) or camera URL")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--auto", action="store_true",
                    help="free mode, no target outlines: save a frame by itself when the board is held still at a new position")
    ap.add_argument("--manual", action="store_true", help="save a frame only when SPACE is pressed")
    ap.add_argument("--target", type=int, default=20, help="auto mode: number of frames before the calibration runs")
    args = ap.parse_args()
    if args.auto and args.manual:
        sys.exit("Use --auto or --manual, not both (without either: guided mode).")
    if args.square_mm == common.BOARD_SQUARE_MM:
        print("Note: --square-mm not given, using 30.0 mm. Measure your print for accurate results.")
    board = common.make_board(args.square_mm)
    detector = cv2.aruco.CharucoDetector(board)
    if args.images:
        run_images(args, board, detector)
    else:
        run_camera(args, board, detector)


if __name__ == "__main__":
    main()
