r"""Drystone Test 1: how accurately a box position is read from its ArUco marker.

Setup:
- Calibrate the same camera at the same resolution first (tools/calibrate.py).
- Stick marker ID 0 flat in the middle of the box's front face. Measure the black side of the printed marker
  as exactly as you can (for example 79.5 mm): 1 mm off here = 1.25% off in every distance.
- Camera still on a stand, about 1 m away, tilted down a little (10-20 degrees), facing the box's front face.
- Put a ruler on the table, parallel to the box's front face. Keep one side of the box against the edge of a
  book or board so the box slides straight left/right without turning.

Webcam:
    python tools/pose_test.py --calib data/camera_laptop.yaml --marker-mm 79.5
Phone photos (1 photo per position, file name order = position order):
    python tools/pose_test.py --calib data/camera_hp.yaml --marker-mm 79.5 --images "data/pose_hp/*.jpg"

Default positions 0, 5, 10, ..., 45 cm: put the box at each ruler mark and press SPACE.
Keys: SPACE = record position, U = undo the last recording, Q = finish and show the result.
"""
import argparse
import csv
import os
import sys
import time

import cv2
import numpy as np

import common

TARGET_POS_CM = 1.0
TARGET_ROT_DEG = 3.0


def marker_points(size_m):
    h = size_m / 2.0
    # corner order of ArUco detections: top-left, top-right, bottom-right, bottom-left
    return np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]], dtype=np.float32)


def rot_angle_deg(r1, r2):
    R1, _ = cv2.Rodrigues(np.asarray(r1, dtype=np.float64))
    R2, _ = cv2.Rodrigues(np.asarray(r2, dtype=np.float64))
    c = (np.trace(R1.T @ R2) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def estimate(detector, img, marker_id, obj, K, dist, prev_rvec=None):
    corners, ids, _ = detector.detectMarkers(img)
    if ids is None:
        return None
    hits = np.where(ids.ravel() == marker_id)[0]
    if len(hits) == 0:
        return None
    c = corners[hits[0]].reshape(4, 2).astype(np.float32)
    n, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, c, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
    if n == 0:
        return None
    errs = np.asarray(errs, dtype=np.float64).ravel()
    best = int(np.argmin(errs))
    ambiguous = n > 1 and errs.max() < 1.5 * max(errs.min(), 1e-6)
    if ambiguous and prev_rvec is not None:
        # a flat marker seen almost head-on has two similar solutions: keep the one closest to the last frame
        best = int(np.argmin([rot_angle_deg(prev_rvec, r) for r in rvecs]))
    return rvecs[best].ravel(), tvecs[best].ravel(), c, ambiguous


def record_step(cap, detector, args, obj, K, dist, prev_rvec):
    """Average a short burst of frames so one noisy frame does not decide the result."""
    rs, ts, amb = [], [], 0
    t_end = time.time() + 6.0
    while len(ts) < args.frames and time.time() < t_end:
        ok, frame = cap.read()
        if not ok:
            break
        est = estimate(detector, frame, args.id, obj, K, dist, prev_rvec)
        if est:
            r, t, _, a = est
            rs.append(r)
            ts.append(t)
            amb += int(a)
            prev_rvec = r
        view = frame.copy()
        cv2.putText(view, f"recording... {len(ts)}/{args.frames}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.imshow("Drystone pose test", view)
        cv2.waitKey(1)
    if len(ts) < max(3, args.frames // 2):
        print("Recording failed: the marker was not read often enough. Check light and distance, then try again.")
        return None
    ts, rs = np.array(ts), np.array(rs)
    t_med = np.median(ts, axis=0)
    jitter_mm = float(np.median(np.linalg.norm(ts - t_med, axis=1)) * 1000)
    return {"t": t_med, "r": np.median(rs, axis=0), "jitter_mm": jitter_mm, "frames": len(ts), "amb": amb}


def analyse(steps_cm, records):
    a = np.asarray(steps_cm[:len(records)], dtype=np.float64)
    a = a - a[0]
    T = np.array([rec["t"] for rec in records]) * 100.0          # camera frame, cm
    d = T - T[0]
    if len(T) >= 3:
        u = np.linalg.svd(T - T.mean(axis=0))[2][0]              # main direction of motion
    else:
        u = d[-1] / max(np.linalg.norm(d[-1]), 1e-9)
    if np.dot(u, d[-1]) < 0:
        u = -u
    along = d @ u                                                 # measured slide along the ruler
    rel = T - T.mean(axis=0)
    cross = np.linalg.norm(rel - np.outer(rel @ u, u), axis=1)  # sideways / depth deviation from a straight line
    err_along = along - a
    err_total = np.sqrt(err_along ** 2 + cross ** 2)
    rot = np.array([rot_angle_deg(records[0]["r"], rec["r"]) for rec in records])
    scale = float(along @ a / (a @ a)) if a @ a > 0 else float("nan")
    return a, along, err_along, cross, err_total, rot, scale, T


def report(steps_cm, records, args):
    if len(records) < 3:
        print("At least 3 positions are needed to judge the accuracy.")
        return
    a, along, err_along, cross, err_total, rot, scale, T = analyse(steps_cm, records)
    print("\n=== Test 1 result: box position accuracy (relative to the first position) ===")
    print(f"Camera to marker: about {np.linalg.norm(T[0]):.0f} cm")
    print(f"{'Ruler':>9} {'Measured':>8} {'Error':>7} {'Sideways':>8} {'Total':>7} {'Turn':>7} {'Jitter':>7}")
    print(f"{'(cm)':>9} {'(cm)':>8} {'(cm)':>7} {'(cm)':>8} {'(cm)':>7} {'(deg)':>7} {'(mm)':>7}")
    for i, rec in enumerate(records):
        print(f"{a[i]:9.1f} {along[i]:8.2f} {err_along[i]:+7.2f} {cross[i]:8.2f} {err_total[i]:7.2f} "
              f"{rot[i]:7.2f} {rec['jitter_mm']:7.1f}")
    pos_ok = err_total.max() <= TARGET_POS_CM
    rot_ok = rot.max() <= TARGET_ROT_DEG
    print(f"\nScale measured/ruler    : {scale:.3f}  (ideal 1.000; off by > 1% -> check --marker-mm or calibrate again)")
    print(f"Max position error      : {err_total.max():.2f} cm  (target <= {TARGET_POS_CM}) -> {'PASS' if pos_ok else 'NOT YET'}")
    print(f"Max turn error          : {rot.max():.2f} deg (target <= {TARGET_ROT_DEG}) -> {'PASS' if rot_ok else 'NOT YET'}")
    amb = sum(rec["amb"] for rec in records)
    if amb:
        print(f"Note: {amb} ambiguous frames (marker seen almost head-on). "
              "Tilt the camera 10-20 degrees down for a steadier rotation.")
    os.makedirs(common.DATA_DIR, exist_ok=True)
    name = os.path.splitext(os.path.basename(args.calib))[0].replace("camera_", "")
    out = os.path.join(common.DATA_DIR, f"pose_{name}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ruler_cm", "measured_cm", "err_along_cm", "cross_cm", "err_total_cm",
                    "rot_err_deg", "jitter_mm", "frames", "ambiguous_frames", "tx_cm", "ty_cm", "tz_cm"])
        for i, rec in enumerate(records):
            w.writerow([f"{a[i]:.1f}", f"{along[i]:.3f}", f"{err_along[i]:.3f}", f"{cross[i]:.3f}",
                        f"{err_total[i]:.3f}", f"{rot[i]:.3f}", f"{rec['jitter_mm']:.2f}",
                        rec["frames"], rec["amb"], *[f"{v:.3f}" for v in T[i]]])
    print(f"Saved: {out}\n")


def run_images(args, steps, obj, K, dist, calib_size):
    detector = common.make_marker_detector()
    paths = common.list_images(args.images)
    if len(paths) > len(steps):
        sys.exit(f"{len(paths)} photos but only {len(steps)} positions in --steps.")
    records, prev = [], None
    for p in paths:
        img = common.read_image(p)
        common.check_size(img, calib_size, os.path.basename(p))
        est = estimate(detector, img, args.id, obj, K, dist, prev)
        if not est:
            sys.exit(f"Marker ID {args.id} not found in {os.path.basename(p)}.")
        r, t, _, amb = est
        prev = r
        records.append({"t": t, "r": r, "jitter_mm": float("nan"), "frames": 1, "amb": int(amb)})
        print(f"{os.path.basename(p)}: z = {t[2] * 100:.1f} cm")
    report(steps, records, args)


def run_camera(args, steps, obj, K, dist, calib_size):
    detector = common.make_marker_detector()
    cap = common.open_camera(args.source, calib_size[0], calib_size[1])
    ok, frame = cap.read()
    if ok:
        common.check_size(frame, calib_size, "the camera")
    records, prev = [], None
    print("SPACE = record position, U = undo the last recording, Q = finish")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("The camera stopped sending images.")
            break
        est = estimate(detector, frame, args.id, obj, K, dist, prev)
        view = frame.copy()
        if est:
            r, t, c, _ = est
            prev = r
            cv2.polylines(view, [c.astype(np.int32)], True, (0, 255, 0), 2)
            cv2.drawFrameAxes(view, K, dist, r, t, obj[1, 0])
            info = f"distance {np.linalg.norm(t) * 100:.1f} cm"
            if records:
                info += f" | moved from position 1: {np.linalg.norm(t - records[0]['t']) * 100:.1f} cm"
        else:
            info = f"marker ID {args.id} not visible"
        nxt = steps[len(records)] if len(records) < len(steps) else None
        todo = f"put it at {nxt:g} cm, then SPACE" if nxt is not None else "all positions recorded - press Q"
        cv2.putText(view, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if est else (0, 0, 255), 2)
        cv2.putText(view, f"[{len(records)}/{len(steps)}] {todo} | U undo | Q finish", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.imshow("Drystone pose test", view)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" ") and nxt is not None:
            rec = record_step(cap, detector, args, obj, K, dist, prev)
            if rec:
                records.append(rec)
                print(f"Position {nxt:g} cm recorded ({rec['frames']} frames, jitter {rec['jitter_mm']:.1f} mm)")
        elif key in (ord("u"), ord("U")) and records:
            records.pop()
            print("Last recording undone.")
        elif key in (ord("q"), ord("Q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    report(steps, records, args)


def main():
    ap = argparse.ArgumentParser(description="Test how accurately a box position is read from its ArUco marker")
    ap.add_argument("--calib", required=True, help="calibration file, for example data/camera_laptop.yaml")
    ap.add_argument("--marker-mm", type=float, default=common.BOX_MARKER_MM,
                    help="black side of the printed marker, in mm")
    ap.add_argument("--id", type=int, default=0, help="marker ID on the box (default 0)")
    ap.add_argument("--steps", default="0,5,10,15,20,25,30,35,40,45",
                    help="ruler positions in cm, comma-separated")
    ap.add_argument("--frames", type=int, default=20, help="number of frames averaged per position")
    ap.add_argument("--images", help='photo file pattern, for example "data/pose_hp/*.jpg"')
    ap.add_argument("--source", default="0", help="webcam index (0, 1, ...) or camera URL")
    args = ap.parse_args()
    if args.marker_mm == common.BOX_MARKER_MM:
        print("Note: --marker-mm not given, using 80.0 mm. Measure your print for accurate results.")
    steps = [float(s) for s in args.steps.split(",") if s.strip()]
    K, dist, calib_size = common.load_calibration(args.calib)
    obj = marker_points(args.marker_mm / 1000.0)
    if args.images:
        run_images(args, steps, obj, K, dist, calib_size)
    else:
        run_camera(args, steps, obj, K, dist, calib_size)


if __name__ == "__main__":
    main()
