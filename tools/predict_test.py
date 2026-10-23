r"""Drystone Test 2: how often the fall prediction matches what really happens.

Each trial:
1. Stack 2-3 boxes, markers facing the camera, box ID 0 at the bottom. Hold the overhanging part up with a
   temporary prop (for example a pile of books) so it does not fall yet. The prop must not cover a marker.
2. Press SPACE (webcam) or take a photo (phone). The script reads each box position, runs hundreds of
   physics simulations, and shows the chance of a fall (GREEN < 10%, YELLOW 10-50%, RED > 50%).
3. Remove the prop slowly, then type the result in the terminal: r = fell, b = stood, s = skip.
At the end: a table of prediction vs reality, the accuracy, and a CSV in data/.

Fill in config/boxes.json first (size and mass of each box per marker ID).
Set --pos-sd-cm to the position error from Test 1 (for example the mean of the "Total" column).

Webcam:
    python tools/predict_test.py --calib data/camera_laptop.yaml --marker-mm 79.5 --pos-sd-cm 0.5
Phone photos (one photo per trial, file name order = trial order):
    python tools/predict_test.py --calib data/camera_hp.yaml --marker-mm 79.5 --pos-sd-cm 0.3 --images "data/stack_hp/*.jpg"
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import mujoco
import numpy as np

import common

SIM_SECONDS = 1.5
FALL_DROP_M = 0.03       # a box counts as fallen if it drops more than 3 cm ...
FALL_TILT_DEG = 15.0     # ... or tilts more than 15 degrees


FLIP_Z = np.diag([-1.0, -1.0, 1.0])


def zone(p):
    if p < 0.10:
        return "GREEN", (0, 170, 0)
    if p <= 0.50:
        return "YELLOW", (0, 200, 255)
    return "RED", (0, 0, 255)


def load_catalog(path):
    if not os.path.exists(path):
        sys.exit(f"Box catalog not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    cat = {}
    for key, v in raw.items():
        if key.startswith("_"):
            continue
        cat[int(key)] = {"L": v["length_cm"] / 100, "D": v["depth_cm"] / 100,
                         "H": v["height_cm"] / 100, "m": float(v["mass_kg"])}
    return cat


def rot_angle_deg(Ra, Rb):
    c = (np.trace(Ra.T @ Rb) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def detect_poses(detector, img, catalog, obj, K, dist, base_id):
    """Pose of every catalogued marker. Ambiguous flat-marker solutions are resolved
    toward the base box orientation, since stacked boxes are roughly aligned."""
    corners, ids, _ = detector.detectMarkers(img)
    raw = {}
    if ids is not None:
        for c, i in zip(corners, ids.ravel()):
            i = int(i)
            if i in catalog and i not in raw:
                c4 = c.reshape(4, 2).astype(np.float32)
                n, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, c4, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
                if n:
                    raw[i] = ([cv2.Rodrigues(r)[0] for r in rvecs], [t.ravel() for t in tvecs],
                              np.asarray(errs, dtype=np.float64).ravel(), c4)
    poses = {}
    if base_id in raw:
        Rs, ts, errs, c4 = raw[base_id]
        b = int(np.argmin(errs))
        poses[base_id] = (Rs[b], ts[b], c4)
    R_ref = poses[base_id][0] if base_id in poses else None
    for i, (Rs, ts, errs, c4) in raw.items():
        if i == base_id:
            continue
        b = int(np.argmin(errs))
        if R_ref is not None and len(errs) > 1 and errs.max() < 1.5 * max(errs.min(), 1e-6):
            b = int(np.argmin([rot_angle_deg(R_ref, R) for R in Rs]))
        poses[i] = (Rs[b], ts[b], c4)
    return poses


def stack_from_poses(poses, catalog, base_id):
    """Box centres in the base-marker frame: x right along the front face, y up, z toward the camera."""
    R0, t0, _ = poses[base_id]
    boxes = []
    for i, (R, t, _) in poses.items():
        p = R0.T @ (t - t0)                         # marker centre
        normal = R0.T @ R[:, 2]                     # marker normal, points toward the camera
        c = p - normal * catalog[i]["D"] / 2.0      # marker sits on the middle of the front face
        Rrel = R0.T @ R
        boxes.append({"id": i, "x": float(c[0]), "y": float(p[1]), "z": float(c[2]),
                      # a marker stuck upside-down reads as 180 deg about its own axis: not a real turn
                      "turn_deg": min(rot_angle_deg(np.eye(3), Rrel), rot_angle_deg(FLIP_Z, Rrel))})
    boxes.sort(key=lambda b: b["y"])
    return boxes


def static_check(boxes, catalog):
    """Rigid-box rule: at every contact, the centre of mass of everything above must sit over the contact area.
    Returns (stable, margin_m): margin is the distance of the worst centre of mass inside (+) or outside (-) its support."""
    worst = np.inf
    for k in range(1, len(boxes)):
        lo, up = boxes[k - 1], boxes[k]
        cl, cu = catalog[lo["id"]], catalog[up["id"]]
        x0 = max(lo["x"] - cl["L"] / 2, up["x"] - cu["L"] / 2)
        x1 = min(lo["x"] + cl["L"] / 2, up["x"] + cu["L"] / 2)
        z0 = max(lo["z"] - cl["D"] / 2, up["z"] - cu["D"] / 2)
        z1 = min(lo["z"] + cl["D"] / 2, up["z"] + cu["D"] / 2)
        if x0 >= x1 or z0 >= z1:
            return False, -1.0
        above = boxes[k:]
        mass = sum(catalog[b["id"]]["m"] for b in above)
        cx = sum(catalog[b["id"]]["m"] * b["x"] for b in above) / mass
        cz = sum(catalog[b["id"]]["m"] * b["z"] for b in above) / mass
        margin = min(cx - x0, x1 - cx, cz - z0, z1 - cz)
        worst = min(worst, margin)
    return worst > 0, float(worst)


def simulate_once(boxes, catalog, rng, pos_sd, com_sd, friction):
    bodies, z = [], 0.0
    for k, b in enumerate(boxes):
        c = catalog[b["id"]]
        noise = rng.normal(0, pos_sd, 2) if k else np.zeros(2)
        x = b["x"] - boxes[0]["x"] + noise[0]
        y = -(b["z"] - boxes[0]["z"]) + noise[1]            # MuJoCo: x right, y away from camera, z up
        com = rng.normal(0, com_sd, 2) if com_sd > 0 else np.zeros(2)
        L, D, H, m = c["L"], c["D"], c["H"], c["m"]
        inertia = (m * (D * D + H * H) / 12, m * (L * L + H * H) / 12, m * (L * L + D * D) / 12)
        bodies.append(
            f'<body name="b{k}" pos="{x:.5f} {y:.5f} {z + H / 2 + 0.0005:.5f}"><freejoint/>'
            f'<inertial pos="{com[0]:.5f} {com[1]:.5f} 0" mass="{m}" diaginertia="{inertia[0]:.6f} {inertia[1]:.6f} {inertia[2]:.6f}"/>'
            f'<geom type="box" size="{L / 2} {D / 2} {H / 2}" density="0" friction="{friction} 0.005 0.0001"/></body>')
        z += H + 0.001
    model = mujoco.MjModel.from_xml_string(
        '<mujoco><option timestep="0.002"/><worldbody><geom type="plane" size="5 5 0.1" '
        f'friction="{friction} 0.005 0.0001"/>{"".join(bodies)}</worldbody></mujoco>')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    z0 = [float(data.xpos[model.body(f"b{k}").id][2]) for k in range(len(boxes))]
    for _ in range(int(SIM_SECONDS / model.opt.timestep)):
        mujoco.mj_step(model, data)
    for k in range(len(boxes)):
        bid = model.body(f"b{k}").id
        q = data.xquat[bid]
        tilt = np.degrees(2 * np.arccos(min(1.0, abs(float(q[0])))))
        if z0[k] - data.xpos[bid][2] > FALL_DROP_M or tilt > FALL_TILT_DEG:
            return True
    return False


def p_fall(boxes, catalog, args, rng):
    """Monte Carlo over camera error and unknown contents. Near the 50% line, run more samples."""
    pos_sd, com_sd = args.pos_sd_cm / 100, args.com_sd_cm / 100
    falls = [simulate_once(boxes, catalog, rng, pos_sd, com_sd, args.friction) for _ in range(args.samples)]
    p = float(np.mean(falls))
    if 0.3 <= p <= 0.7:
        falls += [simulate_once(boxes, catalog, rng, pos_sd, com_sd, args.friction) for _ in range(args.samples)]
        p = float(np.mean(falls))
    return p, len(falls)


def overhang_text(boxes, catalog):
    parts = []
    for k in range(1, len(boxes)):
        lo, up = boxes[k - 1], boxes[k]
        parts.append(f"{(up['x'] - lo['x']) / catalog[up['id']]['L'] * 100:+.0f}%")
    return " ".join(parts)


def evaluate(img, poses, catalog, args, rng, trial, out_dir):
    # an ID below the highest visible one is probably a box in the stack whose marker is hidden
    missing = sorted(i for i in set(catalog) - set(poses) if poses and i < max(poses))
    if args.base_id not in poses:
        print(f"Trial {trial}: the bottom box marker (ID {args.base_id}) is not visible -> take the photo again.")
        return None
    if len(poses) < 2:
        print(f"Trial {trial}: only {len(poses)} marker visible, at least 2 boxes needed -> take the photo again.")
        return None
    boxes = stack_from_poses(poses, catalog, args.base_id)
    if boxes[0]["id"] != args.base_id:
        print(f"Note: the bottom box reads as ID {boxes[0]['id']}, not ID {args.base_id}.")
    stable, margin = static_check(boxes, catalog)
    t = time.time()
    p, n = p_fall(boxes, catalog, args, rng)
    name, color = zone(p)
    turned = [b for b in boxes if b["turn_deg"] > 5]
    print(f"\nTrial {trial}: {len(boxes)} boxes (bottom->top ID {[b['id'] for b in boxes]}), "
          f"overhang {overhang_text(boxes, catalog)}")
    print(f"  Static check    : {'STANDS' if stable else 'FALLS'} (centre-of-mass margin {margin * 100:+.1f} cm)")
    print(f"  Simulation      : P(fall) = {p:.0%}  -> {name}   ({n} simulations, {time.time() - t:.1f} s)")
    if turned:
        print("  Note: box " + ", ".join(f"ID {b['id']} ({b['turn_deg']:.0f} deg)" for b in turned)
              + " reads as tilted/turned; the simulation treats boxes as straight.")
    if missing:
        print(f"  Warning: marker ID {missing} not visible. If that box is in the stack -> take the photo again.")
    view = img.copy()
    for i, (_, _, c4) in poses.items():
        cv2.polylines(view, [c4.astype(np.int32)], True, (0, 255, 0), 2)
        cv2.putText(view, f"ID {i}", tuple(int(v) for v in c4[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.rectangle(view, (0, 0), (view.shape[1], 46), (40, 40, 40), -1)
    cv2.putText(view, f"#{trial}  P(fall) {p:.0%}  {name}  | static: {'stands' if stable else 'falls'}",
                (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.imwrite(os.path.join(out_dir, f"percobaan_{trial:02d}.png"), view)
    return {"boxes": boxes, "stable": stable, "margin": margin, "p": p, "zone": name, "n": n, "view": view}


def ask_outcome(preset, idx):
    if preset is not None:
        if idx >= len(preset):
            return None
        ch = preset[idx]
    else:
        ch = input("  Remove the prop. Result? r = fell, b = stood, s = skip: ").strip().lower()[:1]
    return {"r": True, "b": False}.get(ch)


def report(results, args, out_dir):
    done = [r for r in results if r["fell"] is not None]
    print("\n=== Test 2 result: prediction vs reality ===")
    print(f"{'#':>3} {'Overhang':>14} {'Static':>8} {'P(fall)':>9} {'Zone':>7} {'Real':>8} {'Sim':>4} {'Stat':>5}")
    for r in results:
        real = "-" if r["fell"] is None else ("fell" if r["fell"] else "stood")
        ok_sim = "" if r["fell"] is None else ("yes" if (r["p"] > 0.5) == r["fell"] else "NO")
        ok_st = "" if r["fell"] is None else ("yes" if (not r["stable"]) == r["fell"] else "NO")
        print(f"{r['trial']:>3} {r['overhang']:>14} {'stands' if r['stable'] else 'falls':>8} {r['p']:>9.0%} "
              f"{r['zone']:>7} {real:>8} {ok_sim:>4} {ok_st:>5}")
    if done:
        sim_acc = np.mean([(r["p"] > 0.5) == r["fell"] for r in done])
        st_acc = np.mean([(not r["stable"]) == r["fell"] for r in done])
        brier = np.mean([(r["p"] - float(r["fell"])) ** 2 for r in done])
        print(f"\nSimulation accuracy    : {sim_acc:.0%} of {len(done)} trials (target >= 80%) -> "
              f"{'PASS' if sim_acc >= 0.8 else 'NOT YET'}")
        print(f"Static check accuracy  : {st_acc:.0%}")
        print(f"Brier score            : {brier:.3f} (0 = perfect, 0.25 = the same as guessing 50%)")
        green = [r for r in done if r["zone"] == "GREEN"]
        green_fell = [r["trial"] for r in green if r["fell"]]
        print(f"Falls in the GREEN zone: {len(green_fell)} of {len(green)} (target 0)"
              + (f" -> trials {green_fell}" if green_fell else ""))
    path = os.path.join(out_dir, "hasil.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trial", "source", "box_ids_bottom_to_top", "overhang", "x_cm", "depth_cm", "static_stable",
                    "static_margin_cm", "p_fall", "zone", "simulations", "actual_fell"])
        for r in results:
            w.writerow([r["trial"], r["source"], " ".join(str(b["id"]) for b in r["boxes"]), r["overhang"],
                        " ".join(f"{b['x'] * 100:.2f}" for b in r["boxes"]),
                        " ".join(f"{b['z'] * 100:.2f}" for b in r["boxes"]), int(r["stable"]),
                        f"{r['margin'] * 100:.2f}", f"{r['p']:.3f}", r["zone"], r["n"],
                        "" if r["fell"] is None else int(r["fell"])])
    print(f"Saved: {path} (+ one image per trial in the same folder)\n")


def record(results, ev, source, fell):
    results.append({"trial": len(results) + 1, "source": source, "boxes": ev["boxes"], "stable": ev["stable"],
                    "margin": ev["margin"], "p": ev["p"], "zone": ev["zone"], "n": ev["n"], "fell": fell,
                    "overhang": overhang_text(ev["boxes"], CATALOG)})


def run_images(args, catalog, obj, K, dist, calib_size, rng, out_dir):
    detector = common.make_marker_detector()
    results = []
    for p in common.list_images(args.images):
        img = common.read_image(p)
        common.check_size(img, calib_size, os.path.basename(p))
        ev = evaluate(img, detect_poses(detector, img, catalog, obj, K, dist, args.base_id),
                      catalog, args, rng, len(results) + 1, out_dir)
        if ev:
            record(results, ev, os.path.basename(p), ask_outcome(args.outcomes, len(results)))
    report(results, args, out_dir)


def run_camera(args, catalog, obj, K, dist, calib_size, rng, out_dir):
    detector = common.make_marker_detector()
    cap = common.open_camera(args.source, calib_size[0], calib_size[1])
    results = []
    # resizable window: the fixed 1280x720 window does not fit small laptop screens
    cv2.namedWindow("Drystone Test 2", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Drystone Test 2", 960, 540)
    print("SPACE = predict the stack now, Q = finish")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("The camera stopped sending images.")
            break
        poses = detect_poses(detector, frame, catalog, obj, K, dist, args.base_id)
        view = frame.copy()
        for i, (_, _, c4) in poses.items():
            cv2.polylines(view, [c4.astype(np.int32)], True, (0, 255, 0), 2)
            cv2.putText(view, f"ID {i}", tuple(int(v) for v in c4[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        info = f"markers visible: {sorted(poses)}"
        if args.base_id in poses and len(poses) >= 2:
            stable, margin = static_check(stack_from_poses(poses, catalog, args.base_id), catalog)
            info += f" | static: {'stands' if stable else 'FALLS'} ({margin * 100:+.1f} cm)"
        # black outline so the text stays readable on a bright background
        for row, text in enumerate([info, f"trial {len(results) + 1} | SPACE predict | Q finish"]):
            org = (10, 30 + 30 * row)
            cv2.putText(view, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(view, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Drystone Test 2", view)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            ev = evaluate(frame, poses, catalog, args, rng, len(results) + 1, out_dir)
            if ev:
                cv2.imshow("Drystone Test 2", ev["view"])
                cv2.waitKey(1)
                record(results, ev, "webcam", ask_outcome(args.outcomes, len(results)))
        elif key in (ord("q"), ord("Q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    report(results, args, out_dir)


def recheck(args, catalog):
    """Re-run the Monte Carlo on box positions saved in an old hasil.csv (same physics, new settings)."""
    rng = np.random.default_rng(args.seed)
    results = []
    with open(args.recheck, newline="") as f:
        for row in csv.DictReader(f):
            ids = [int(v) for v in row["box_ids_bottom_to_top"].split()]
            xs = [float(v) / 100 for v in row["x_cm"].split()]
            zs = [float(v) / 100 for v in row["depth_cm"].split()]
            boxes = [{"id": i, "x": x, "y": 0.0, "z": z, "turn_deg": 0.0} for i, x, z in zip(ids, xs, zs)]
            stable, margin = static_check(boxes, catalog)
            p, n = p_fall(boxes, catalog, args, rng)
            fell = None if row["actual_fell"] == "" else bool(int(row["actual_fell"]))
            results.append({"trial": int(row["trial"]), "source": "recheck", "boxes": boxes,
                            "overhang": row["overhang"], "stable": stable, "margin": margin,
                            "p": p, "zone": zone(p)[0], "n": n, "fell": fell})
    print(f"Recomputing {args.recheck} with --pos-sd-cm {args.pos_sd_cm} --com-sd-cm {args.com_sd_cm}")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(args.recheck)),
                           f"recheck_pos{args.pos_sd_cm:g}_com{args.com_sd_cm:g}")
    os.makedirs(out_dir, exist_ok=True)
    report(results, args, out_dir)


CATALOG = {}


def main():
    global CATALOG
    ap = argparse.ArgumentParser(description="Test the fall prediction against what really happens")
    ap.add_argument("--calib", help="calibration file, for example data/camera_laptop.yaml")
    ap.add_argument("--marker-mm", type=float, default=common.BOX_MARKER_MM, help="black side of the printed marker (mm)")
    ap.add_argument("--boxes", default=os.path.join(common.ROOT, "config", "boxes.json"), help="box catalog")
    ap.add_argument("--base-id", type=int, default=0, help="marker ID of the bottom box")
    ap.add_argument("--pos-sd-cm", type=float, default=1.0,
                    help="position error: camera (Test 1: 0.5) + placement and box edges (Test 2) (cm)")
    ap.add_argument("--com-sd-cm", type=float, default=2.0, help="uncertainty of the centre of mass of the box contents (cm)")
    ap.add_argument("--samples", type=int, default=150, help="number of simulations per trial")
    ap.add_argument("--friction", type=float, default=0.5, help="friction coefficient of the boxes")
    ap.add_argument("--images", help='photo file pattern, for example "data/stack_hp/*.jpg"')
    ap.add_argument("--outcomes", help="real results in order, without asking, for example rbbr (r = fell, b = stood)")
    ap.add_argument("--source", default="0", help="webcam index or camera URL")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--recheck", help="recompute an old hasil.csv with the current settings (no camera)")
    args = ap.parse_args()
    if args.marker_mm == common.BOX_MARKER_MM:
        print("Note: --marker-mm not given, using 80.0 mm. Measure your print for accurate results.")
    CATALOG = load_catalog(args.boxes)
    if args.base_id not in CATALOG:
        sys.exit(f"Bottom box ID {args.base_id} is not in {args.boxes}.")
    if args.recheck:
        recheck(args, CATALOG)
        return
    if not args.calib:
        sys.exit("Give --calib, for example --calib data/camera_laptop.yaml")
    K, dist, calib_size = common.load_calibration(args.calib)
    obj = np.array([[-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0]], dtype=np.float32) * (args.marker_mm / 2000.0)
    out_dir = os.path.join(common.DATA_DIR, f"tes2_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    if args.images:
        run_images(args, CATALOG, obj, K, dist, calib_size, rng, out_dir)
    else:
        run_camera(args, CATALOG, obj, K, dist, calib_size, rng, out_dir)


if __name__ == "__main__":
    main()
