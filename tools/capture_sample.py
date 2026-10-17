r"""Take a clean sample photo for the judges' web page (raw JPEG, no drawings on it).

Live view with marker outlines (only on screen). SPACE = take 10 frames; the photo is saved only if every
catalogued marker of the stack is read in every frame and the stack reading has no problem. Then it prints
the shift between boxes in cm (S3 should be about +6 cm), from the 10 frames and from the saved frame alone,
since the web service reads the saved frame alone.

Before taking the photo: plain background, no faces, no room, only the stacked boxes in view.

    python tools/capture_sample.py --name s3
    python tools/capture_sample.py --name s3 --out E:\drystone_samples
Keys: SPACE take photo, Q quit.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

import common
from agent import CAPTURE_FRAMES, outlined, read_stack
from predict_test import detect_poses, load_catalog
from service import _Frames

WIN = "Drystone sample photo"


def print_stack(title, stack, catalog):
    print(f"  {title}:")
    for k, b in enumerate(stack):
        line = f"    box ID {b['id']}: x {b['x'] * 100:+6.2f} cm, height {b['y'] * 100:6.2f} cm"
        if k:
            below = stack[k - 1]
            shift = (b["x"] - below["x"]) * 100
            line += (f" | shift from ID {below['id']} below: {shift:+.1f} cm "
                     f"({shift / (catalog[b['id']]['L'] * 100) * 100:+.0f}% overhang)")
        print(line)


def take(cap, detector, catalog, obj, K, dist, base_id):
    """10 frames -> (raw last frame, problem). Every frame must show the same markers, all readable."""
    frames = []
    for _ in range(CAPTURE_FRAMES):
        ok, f = cap.read()
        if not ok:
            return None, "camera is not sending frames"
        frames.append(f)
    sets = [tuple(sorted(detect_poses(detector, f, catalog, obj, K, dist, base_id))) for f in frames]
    if not sets[0] or base_id not in sets[0]:
        return None, f"bottom box marker (ID {base_id}) not visible"
    if any(s != sets[0] for s in sets):
        missing = sorted(set().union(*sets) - set.intersection(*map(set, sets)))
        return None, f"marker ID {missing} is not read in every frame -> check light and glare, then retake"
    stack, _, _, _, problem = read_stack(_Frames(frames), detector, catalog, obj, K, dist, base_id,
                                         n=len(frames))
    if problem:
        return None, problem
    print(f"\n  markers in all {len(frames)} frames: ID {list(sets[0])}")
    print_stack(f"median of {len(frames)} frames", stack, catalog)
    single, _, _, _, problem = read_stack(_Frames([frames[-1]]), detector, catalog, obj, K, dist, base_id, n=1)
    if problem:
        return None, f"the saved frame alone reads badly: {problem}"
    print_stack("saved frame alone (what the web service reads)", single, catalog)
    return frames[-1], None


def main():
    ap = argparse.ArgumentParser(description="Take a raw sample photo for the judges' web page")
    ap.add_argument("--name", required=True, help="sample id, e.g. s1, s2, s3 (file name <name>_<time>.jpg)")
    ap.add_argument("--out", default=r"E:\drystone_samples", help="folder for the photos (outside the repo)")
    ap.add_argument("--calib", default=os.path.join(common.DATA_DIR, "camera_laptop.yaml"))
    ap.add_argument("--marker-mm", type=float, default=common.BOX_MARKER_MM)
    ap.add_argument("--boxes", default=os.path.join(common.ROOT, "config", "boxes.json"))
    ap.add_argument("--base-id", type=int, default=0)
    ap.add_argument("--source", default="0")
    args = ap.parse_args()

    catalog = load_catalog(args.boxes)
    K, dist, size = common.load_calibration(args.calib)
    obj = np.array([[-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0]], np.float32) * (args.marker_mm / 2000.0)
    detector = common.make_marker_detector()
    cap = common.open_camera(args.source, size[0], size[1])
    ok, frame = cap.read()
    if not ok or (frame.shape[1], frame.shape[0]) != tuple(size):
        sys.exit(f"The camera must give {size[0]}x{size[1]} (the calibration size).")
    os.makedirs(args.out, exist_ok=True)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 540)
    print(__doc__.split("\n    python")[0])
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("The camera stopped sending frames.")
                break
            view = frame.copy()                       # drawings only on the copy, never on the saved photo
            for i, (_, _, c4) in detect_poses(detector, frame, catalog, obj, K, dist, args.base_id).items():
                cv2.polylines(view, [c4.astype("int32")], True, (0, 255, 0), 2)
                outlined(view, f"ID {i}", tuple(int(v) for v in c4[0]), 0.6, (0, 255, 0))
            outlined(view, f"{args.name}: SPACE take photo | Q quit", (10, 30))
            cv2.imshow(WIN, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key == ord(" "):
                raw, problem = take(cap, detector, catalog, obj, K, dist, args.base_id)
                if problem:
                    print(f"\n  NOT saved: {problem}")
                    continue
                path = os.path.join(args.out, f"{args.name}_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
                ok, jpg = cv2.imencode(".jpg", raw, [cv2.IMWRITE_JPEG_QUALITY, 92])
                with open(path, "wb") as f:              # works with non-ASCII Windows paths too
                    f.write(jpg.tobytes())
                print(f"  saved {path} ({os.path.getsize(path) // 1024} KB, {raw.shape[1]}x{raw.shape[0]})")
                print("  Check the photo: no face, no room, no papers with names. Take another with SPACE or Q to quit.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
