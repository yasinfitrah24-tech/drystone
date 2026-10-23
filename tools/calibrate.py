r"""Camera calibration with the ChArUco board (docs/print/charuco_A4.pdf).

Prepare the board first: tape the sheet on all four sides to something hard and flat (a hardcover book, a
clipboard, thick card), then measure the side of one black square (for example 29.8 mm).
A bent sheet makes the calibration fail, and no lens model can fix that.

Laptop webcam, on your own (recommended): a frame is saved by itself each time the board is held still for ~1 s
    python tools/calibrate.py --name laptop --square-mm 29.8 --auto

Laptop webcam, with someone pressing SPACE:
    python tools/calibrate.py --name laptop --square-mm 29.8

Phone photos (15-25 photos of the board, zoom 1x, same orientation, in data/calib_hp/):
    python tools/calibrate.py --name hp --square-mm 29.8 --images "data/calib_hp/*.jpg"

Guide in the camera window:
  - green cells = parts of the image already covered by board corners. Cover at least 9 of the 12 cells,
    especially the corners and edges of the image.
  - tilt = estimated angle of the board to the camera. For each side (left, right, top, bottom), try to
    have a frame with the board tilted 20-40 degrees.
  - a frame almost the same as a saved one is rejected.
Keys: SPACE = save frame, C = calibrate, Q = quit.

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


class BoardView:
    """One detected board: its corners plus what the duplicate check and the guide need."""

    def __init__(self, board, corners, ids, size, name=""):
        self.name = name
        obj, img = board.matchImagePoints(corners, ids)
        self.obj = np.asarray(obj, np.float32).reshape(-1, 3)
        self.img = np.asarray(img, np.float32).reshape(-1, 2)
        self.outline = board_outline(board, self.obj, self.img)
        self.normal = rough_normal(self.obj, self.img, size)


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


def rough_normal(obj, img, size):
    """Board normal (pointing at the camera) in camera axes, from a pose with a guessed focal length.

    A guess of 0.8 x image width is enough to tell how far and which way the board is turned;
    the real focal length is what the calibration is about to measure."""
    f = 0.8 * size[0]
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
    mark = lambda good: hud.paint("OK", fg="GREEN", bold=True) if good else hud.paint("TOO LOW", fg="WARN", bold=True)
    print()
    print(_rule())
    print("  " + _tag("CALIBRATION RESULT", "BRAND"))
    _row("Views used", f"{len(views)} different board positions")
    _row("RMS error", f"{rms:.3f} px  {mark(rms <= MAX_RMS_PX)}  (max {MAX_RMS_PX}, good < 0.5)")
    _row("Uncertainty", f"fx {100 * sd[0] / K[0, 0]:.2f}%, fy {100 * sd[1] / K[1, 1]:.2f}%  "
                        f"{mark(f_sd <= MAX_F_SD_PCT)}  (max {MAX_F_SD_PCT}%)")
    _row("Image coverage", f"{cells.sum()}/{cells.size} cells  {mark(cells.sum() >= MIN_CELLS)}  "
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


def draw_guide(frame, views, cur, corners, n, size, status, keys, title, note=None):
    """Live view: covered grid cells in green, saved corners as dots, the board now in blue, a card with the
    counts and the current tilt, chips for the four tilt sides, then the next step (and the last verdict) as pills."""
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
        cv2.polylines(canvas, [cur.outline.astype(np.int32)], True, hud.BGR["EDGE"], 2, cv2.LINE_AA)
    if n:
        for x, y in np.asarray(corners).reshape(-1, 2):
            cv2.circle(canvas, (int(x), int(y)), 5, hud.BGR["NAVY"], -1, cv2.LINE_AA)
            cv2.circle(canvas, (int(x), int(y)), 3, hud.BGR["EDGE"], -1, cv2.LINE_AA)
    sides = set().union(*(tilt_sides(v.normal) for v in views)) if views else set()
    hud.top_bar(canvas, title)
    y = hud.card(canvas, [
        {"segs": [(f"{n} corners", 20, 700), ("·", 20, 500), (f"{len(views)} saved", 20, 500), ("·", 20, 500),
                  (f"coverage {cells.sum()}/{cells.size}", 20, 500)]},
        {"segs": [(tilt_text(cur.normal) if cur is not None else
                   "board only partly in view" if n else "no board in view", 16, 500)], "gap": 8}])
    side_chips(canvas, y + 8, sides)
    hud.pills(canvas, [p for p in (note, status or next_step(views, cur, n, size, cells, sides)) if p])
    hud.bottom_bar(canvas, keys, LEGEND)
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
    keys = (("C", "calibrate now"), ("Q", "quit")) if args.auto else \
        (("SPACE", "save frame"), ("C", "calibrate"), ("Q", "quit"))
    for k, v in keys:
        print(f"  {hud.paint(f'{k:<8}', fg='EDGE', bold=True)}{v}")
    print()
    first = ("Hold the board still at a new position: the frame is saved by itself." if args.auto else
             "Press SPACE at each new position and tilt.")
    for s in (first,
              "Fill the green grid (corners and edges) and tilt the board left, right, up and down.",
              f"After {args.target} frames the calibration runs by itself; C runs it at any time." if args.auto else
              f"After at least {MIN_VIEWS} frames, press C to calibrate.",
              "Repeat until the verdict is PASS."):
        print(f"  {hud.paint(s, dim=True)}")
    print(_rule())


def run_camera(args, board, detector):
    cap = common.open_camera(args.source, args.width, args.height)
    frames_dir = os.path.join(common.DATA_DIR, f"calib_{args.name}", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(frames_dir, exist_ok=True)
    intro(args, frames_dir)
    keys = "C calibrate · Q quit" if args.auto else "SPACE save · C calibrate · Q quit"
    title = f"Calibration · {args.name} · {args.square_mm:g} mm squares" + (" · auto" if args.auto else "")
    views, size = [], None
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
        if args.auto and (cur is None or same):
            still_since = None
        elif args.auto:
            still = bool(prev) and mean_shift(positions, prev) < STILL_PX
            still_since = (still_since or time.time()) if still else None
            if still_since and time.time() - still_since >= STILL_SEC:
                save(frame, cur)
                still_since, flash, status = None, 4, None
                if len(views) >= args.target and not auto_done:
                    auto_done = True
                    compute()
            else:
                status = ("hold still...", "info")
        prev = positions
        canvas = draw_guide(frame, views, cur, corners, n, size, status, keys, title, note)
        if flash:
            cv2.rectangle(canvas, (0, 0), (size[0] - 1, size[1] - 1), hud.BGR["GREEN"], 10)
            flash -= 1
        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            if cur is None:
                print(f"Not saved: only {n} corners found, at least {MIN_CORNERS} needed.")
            elif same:
                print(f"Not saved: almost the same as {same.name}. Move or tilt the board first.")
            else:
                save(frame, cur)
                flash = 4
        elif key in (ord("c"), ord("C")):
            compute()
        elif key in (ord("q"), ord("Q"), 27):
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
                    help="save a frame by itself when the board is held still at a new position (no SPACE needed)")
    ap.add_argument("--target", type=int, default=20, help="auto mode: number of frames before the calibration runs")
    args = ap.parse_args()
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
