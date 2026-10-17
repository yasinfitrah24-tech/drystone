r"""Agent Drystone: pandu penumpukan kardus satu per satu.

Alur tiap kardus:
1. Kamera membaca tumpukan (marker ArUco) -> kembaran digital. Kotak garis = calon posisi kardus berikutnya.
2. Geser calon dengan A / D (1 cm), lalu SPASI = minta keputusan agent.
3. Agent: HIJAU -> pandu. KUNING -> minta persetujuan supervisor (di cmd).
   MERAH -> tolak + usul posisi aman terdekat; lanjut hanya lewat override dengan alasan tercatat.
4. Taruh kardus sesuai kotak, lepas tangan, tekan SPASI -> agent cek ulang (sesuai rencana / meleset / roboh).
Semua keputusan tercatat di data/agent_<waktu>/log.jsonl (+ foto tiap langkah).

Tombol di jendela kamera: A / D geser calon, SPASI keputusan / cek ulang, X batal, Q selesai.

    python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

import common
import drystone_core as core
from predict_test import FLIP_Z, detect_poses, load_catalog

WIN = "Agent Drystone"
CAPTURE_FRAMES = 10        # frames per reading; the median is used
MAX_JITTER_M = 0.01        # left-right spread between frames above 1 cm -> read again
MAX_TURN_DEG = 12.0        # a box turned more than this cannot be simulated as straight -> ask to straighten
MAX_RETRIES = 3
COLORS = {"HIJAU": (0, 170, 0), "KUNING": (0, 200, 255), "MERAH": (0, 0, 255), "CALON": (200, 200, 200)}


class Log:
    def __init__(self, out_dir):
        self.dir = out_dir
        self.path = os.path.join(out_dir, "log.jsonl")
        self.step = 0

    def write(self, event, frame=None, **data):
        self.step += 1
        entry = {"step": self.step, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **data}
        if frame is not None:
            name = f"langkah_{self.step:03d}_{event}.png"
            cv2.imwrite(os.path.join(self.dir, name), frame)
            entry["image"] = name
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=float) + "\n")
        return entry


def outlined(img, text, org, scale=0.65, color=(255, 255, 255)):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def draw_box(img, box, catalog, R0, t0, K, dist, color, thick=2):
    """Wireframe of a box given in the base-marker frame."""
    c = catalog[box["id"]]
    hx, hy, hz = c["L"] / 2, c["H"] / 2, c["D"] / 2
    corners = np.array([[box["x"] + sx * hx, box["y"] + sy * hy, box["z"] + sz * hz]
                        for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    cam = (R0 @ corners.T).T + t0
    if np.any(cam[:, 2] <= 0.05):
        return
    pts, _ = cv2.projectPoints(cam, np.zeros(3), np.zeros(3), K, dist)
    pts = pts.reshape(-1, 2).astype(np.int32)
    for a in range(8):
        for b in range(a + 1, 8):
            if bin(a ^ b).count("1") == 1:          # corners differing in one axis share an edge
                cv2.line(img, tuple(pts[a]), tuple(pts[b]), color, thick, cv2.LINE_AA)


def yaw_deg(poses, i, base_id):
    """Turn of box i about the vertical axis relative to the base box. Only yaw matters for stacking;
    the tilt of a single flat marker toward/away from the camera is poorly determined, so it is ignored."""
    n = poses[base_id][0].T @ poses[i][0][:, 2]
    a = abs(float(np.degrees(np.arctan2(n[0], n[2]))))
    return min(a, 180.0 - a) if a > 90 else a


def stack_aligned(poses, catalog, base_id):
    """Box centres in the base-marker frame, assuming every box faces the same way as the base box.

    The facing direction of one small marker wobbles a few degrees from frame to frame; pushing the marker
    centre 8.5 cm back along that wobbling direction turned it into centimetres of fake movement. The base
    box sits on the table and its orientation is the steadiest, so all boxes are pushed back along it."""
    R0, t0, _ = poses[base_id]
    boxes = []
    for i, (R, t, _) in poses.items():
        p = R0.T @ (t - t0)
        boxes.append({"id": i, "x": float(p[0]), "y": float(p[1]), "z": float(p[2] - catalog[i]["D"] / 2.0),
                      "turn_deg": yaw_deg(poses, i, base_id)})
    boxes.sort(key=lambda b: b["y"])
    return boxes


def mean_rotation(Rs):
    """Chordal mean of rotation matrices (average, then project back onto a rotation)."""
    U, _, Vt = np.linalg.svd(np.sum(Rs, axis=0))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R


def common_rotation(frames, base_id):
    """One facing direction for the whole reading, averaged over every marker in every frame.

    A single marker's orientation wobbles a few degrees per frame. Positions are measured relative to the base
    marker, so that wobble swings the upper boxes sideways: 3 degrees at 40 cm above the base is 2 cm.
    Averaging ~10 frames x 2-3 markers makes the orientation steady. Markers stuck upside-down are flipped first."""
    R_ref = mean_rotation([f[base_id][0] for f in frames])
    Rs = []
    for f in frames:
        for R, _, _ in f.values():
            flipped = R @ FLIP_Z
            Rs.append(flipped if np.trace(R_ref.T @ flipped) > np.trace(R_ref.T @ R) else R)
    return mean_rotation(Rs)


def read_stack(cap, detector, catalog, obj, K, dist, base_id, n=CAPTURE_FRAMES):
    """Several frames -> median box positions + quality checks. Returns (stack, R0, t0, frame, problem)."""
    frames, frame = [], None
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            return None, None, None, frame, "kamera tidak mengirim gambar"
        poses = detect_poses(detector, frame, catalog, obj, K, dist, base_id)
        if base_id in poses:
            frames.append(poses)
    if not frames:
        return None, None, None, frame, f"marker kardus bawah (ID {base_id}) tidak terlihat"
    id_sets = [tuple(sorted(f)) for f in frames]
    ids = max(set(id_sets), key=id_sets.count)
    if id_sets.count(ids) < max(2, len(frames) // 2 + 1):
        return None, None, None, frame, "marker yang terlihat berubah-ubah antar-frame"
    frames = [f for f, s in zip(frames, id_sets) if s == ids]
    Rc = common_rotation(frames, base_id)
    stack = []
    for i in ids:
        rel = np.array([Rc.T @ (f[i][1] - f[base_id][1]) for f in frames])   # marker centre, base frame
        med = np.median(rel, axis=0)
        Ri = mean_rotation([f[i][0] for f in frames])
        n_i = Rc.T @ Ri[:, 2]
        a = abs(float(np.degrees(np.arctan2(n_i[0], n_i[2]))))
        xs = rel[:, 0]
        stack.append({"id": i, "x": float(med[0]), "y": float(med[1]), "z": float(med[2] - catalog[i]["D"] / 2.0),
                      "turn_deg": 180.0 - a if a > 90 else a,
                      "jitter_m": float(1.4826 * np.median(np.abs(xs - np.median(xs))))})
    stack.sort(key=lambda b: b["y"])
    R0, t0 = Rc, np.median([f[base_id][1] for f in frames], axis=0)
    shaky = [f"ID {b['id']} ({b['jitter_m'] * 100:.1f} cm)" for b in stack if b["jitter_m"] > MAX_JITTER_M]
    if shaky:
        return stack, R0, t0, frame, ("posisi kardus " + ", ".join(shaky)
                                      + " goyang antar-frame (> 1 cm): jangan sentuh meja/kardus")
    if stack[0]["id"] != base_id:
        return stack, R0, t0, frame, f"kardus paling bawah terbaca ID {stack[0]['id']}, harusnya ID {base_id}"
    turned = [f"ID {b['id']} ({b['turn_deg']:.0f} deg)" for b in stack if b["turn_deg"] > MAX_TURN_DEG]
    if turned:
        return stack, R0, t0, frame, "kardus " + ", ".join(turned) + " miring/berputar -> luruskan"
    for lo, up in zip(stack, stack[1:]):
        gap = up["y"] - lo["y"] - (catalog[lo["id"]]["H"] + catalog[up["id"]]["H"]) / 2
        if gap < -0.10:
            return stack, R0, t0, frame, (f"kardus ID {up['id']} tidak berada di atas tumpukan "
                                          "(tergeletak di samping?) -> singkirkan dari pandangan kamera")
        if abs(gap) > 0.04:
            return stack, R0, t0, frame, (f"jarak tinggi ID {lo['id']} -> ID {up['id']} {gap * 100:+.0f} cm dari "
                                          "seharusnya (marker tertutup / kardus tidak menumpuk?)")
    return stack, R0, t0, frame, None


def perceive(cap, detector, catalog, obj, K, dist, base_id, log, reason):
    """The agent re-reads by itself when a reading looks bad; asks the worker only after several tries."""
    for attempt in range(1, MAX_RETRIES + 1):
        stack, R0, t0, frame, problem = read_stack(cap, detector, catalog, obj, K, dist, base_id)
        if problem is None:
            if attempt > 1:
                print(f"  [agent] bacaan ke-{attempt} bersih")
            return stack, R0, t0, frame, None
        print(f"  [agent] bacaan {attempt}/{MAX_RETRIES} untuk {reason}: {problem} -> foto ulang")
        log.write("foto_ulang", frame, reason=reason, attempt=attempt, problem=problem)
        time.sleep(0.3)
    print(f"  [agent] tetap gagal: {problem}. Perbaiki susunan/kamera, lalu tekan SPASI lagi.")
    return None, None, None, frame, problem


def ask(prompt, valid):
    while True:
        ans = input(prompt).strip().lower()
        if ans[:1] in valid:
            return ans[:1]
        print(f"  ketik salah satu: {', '.join(valid)}")


def ask_text(prompt, min_len=1):
    while True:
        ans = input(prompt).strip()
        if len(ans) >= min_len:
            return ans
        print(f"  wajib diisi (minimal {min_len} huruf)")


def next_box_id(stack, catalog):
    used = {b["id"] for b in stack}
    free = [i for i in sorted(catalog) if i not in used]
    return free[0] if free else None


def print_decision(d):
    print(f"\n[agent] keputusan untuk kardus ID {d['box_id']} menjorok {d['overhang_pct']:+.0f}%:")
    for line in d["trace"]:
        print(f"  - {line}")
    print(f"  => P(roboh) {d['p']:.0%} (+-{d['ci']:.0%}, {d['n']} simulasi) -> {d['zone']}: {d['action']}")
    if d["alternative"]:
        a = d["alternative"]
        print(f"  => usulan: geser ke {a['offset_m'] * 100:+.0f} cm ({a['overhang_pct']:+.0f}%), P(roboh) {a['p']:.0%}")


def handle_decision(d, frame, log, supervisor):
    """Human control. Returns (approved, offset_m, how)."""
    entry = {k: v for k, v in d.items() if k != "trace"}
    log.write("keputusan", frame, **entry, trace=d["trace"])
    if d["zone"] == "HIJAU":
        print("  [agent] HIJAU: silakan taruh kardus di kotak hijau.")
        return True, d["offset_m"], "otomatis"
    if d["zone"] == "KUNING":
        print("  [agent] KUNING: butuh persetujuan supervisor.")
        choice = ask("  Supervisor: s = setuju, u = pakai usulan agent, t = tolak: ", "sut")
        if choice == "s":
            name = supervisor or ask_text("  Nama supervisor: ")
            log.write("persetujuan", None, box_id=d["box_id"], offset_m=d["offset_m"], p=d["p"], supervisor=name)
            return True, d["offset_m"], f"disetujui {name}"
    else:
        print("  [agent] MERAH: DITOLAK. Posisi ini kemungkinan besar roboh.")
        choice = ask("  u = pakai usulan agent, o = override (wajib alasan), t = batal: ", "uot")
        if choice == "o":
            name = supervisor or ask_text("  Nama supervisor: ")
            reason = ask_text("  Alasan override (dicatat): ", min_len=5)
            log.write("override", None, box_id=d["box_id"], offset_m=d["offset_m"], p=d["p"],
                      supervisor=name, reason=reason)
            print("  [agent] override tercatat. Risiko ditanggung supervisor.")
            return True, d["offset_m"], f"override {name}: {reason}"
    if choice == "u":
        if d["alternative"] is None:
            print("  [agent] tidak ada usulan hijau. Batal.")
        else:
            a = d["alternative"]
            log.write("pakai_usulan", None, box_id=d["box_id"], offset_m=a["offset_m"], p=a["p"])
            print(f"  [agent] usulan dipakai: taruh di kotak hijau ({a['offset_m'] * 100:+.0f} cm).")
            return True, a["offset_m"], "usulan agent"
    log.write("batal", None, box_id=d["box_id"], offset_m=d["offset_m"])
    print("  [agent] dibatalkan. Geser calon lalu SPASI lagi.")
    return False, d["offset_m"], "batal"


def main():
    ap = argparse.ArgumentParser(description="Agent Drystone: pandu, minta persetujuan, atau tolak tiap penempatan")
    ap.add_argument("--calib", required=True)
    ap.add_argument("--marker-mm", type=float, default=common.BOX_MARKER_MM)
    ap.add_argument("--boxes", default=os.path.join(common.ROOT, "config", "boxes.json"))
    ap.add_argument("--base-id", type=int, default=0)
    ap.add_argument("--pos-sd-cm", type=float, default=1.0)
    ap.add_argument("--com-sd-cm", type=float, default=2.0)
    ap.add_argument("--friction", type=float, default=0.5)
    ap.add_argument("--supervisor", default="", help="nama supervisor (kalau kosong, ditanya saat dibutuhkan)")
    ap.add_argument("--source", default="0")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    catalog = load_catalog(args.boxes)
    K, dist, calib_size = common.load_calibration(args.calib)
    obj = np.array([[-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0]], dtype=np.float32) * (args.marker_mm / 2000.0)
    settings = core.Settings(args.pos_sd_cm, args.com_sd_cm, args.friction, args.seed)
    out_dir = os.path.join(common.DATA_DIR, f"agent_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    log = Log(out_dir)
    log.write("mulai", None, settings={"pos_sd_cm": args.pos_sd_cm, "com_sd_cm": args.com_sd_cm,
                                        "friction": args.friction, "marker_mm": args.marker_mm,
                                        "p_green": core.P_GREEN, "p_red": core.P_RED})
    detector = common.make_marker_detector()
    cap = common.open_camera(args.source, calib_size[0], calib_size[1])
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 540)
    print(__doc__.split("\n    python")[0])

    offset = 0.0          # candidate shift (m) relative to the current top box
    plan = None           # approved placement waiting to be checked: {"before", "box", "how", "zone", "p"}
    last = None           # last decision, drawn until the candidate moves
    stats = {"keputusan": 0, "HIJAU": 0, "KUNING": 0, "MERAH": 0, "override": 0, "roboh": 0}
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Kamera berhenti mengirim gambar.")
                break
            poses = detect_poses(detector, frame, catalog, obj, K, dist, args.base_id)
            view = frame.copy()
            for i, (_, _, c4) in poses.items():
                cv2.polylines(view, [c4.astype(np.int32)], True, (0, 255, 0), 2)
                outlined(view, f"ID {i}", tuple(int(v) for v in c4[0]), 0.6, (0, 255, 0))
            lines = []
            if args.base_id in poses:
                R0, t0 = poses[args.base_id][0], poses[args.base_id][1]
                stack = stack_aligned(poses, catalog, args.base_id)
                if plan:
                    draw_box(view, plan["box"], catalog, R0, t0, K, dist, COLORS[plan["zone"]], 3)
                    lines.append(f"taruh kardus ID {plan['box']['id']} di kotak, lepas tangan, lalu SPASI = cek ulang")
                else:
                    nid = next_box_id(stack, catalog)
                    if nid is not None:
                        cand = core.candidate_box(stack, nid, offset, catalog)
                        color = COLORS[last["zone"]] if last else COLORS["CALON"]
                        draw_box(view, cand, catalog, R0, t0, K, dist, color, 2)
                        if last and last["alternative"]:
                            alt = core.candidate_box(stack, nid, last["alternative"]["offset_m"], catalog)
                            draw_box(view, alt, catalog, R0, t0, K, dist, COLORS["HIJAU"], 1)
                        lines.append(f"calon ID {nid}: {offset * 100:+.0f} cm ({core.overhang_pct(stack, cand, catalog):+.0f}%)"
                                     + (f" | {last['zone']} {last['p']:.0%}" if last else ""))
                        lines.append("A/D geser 1 cm | SPASI keputusan | Q selesai")
                lines.insert(0, f"tumpukan: {[b['id'] for b in stack]}")
            else:
                lines.append(f"marker kardus bawah (ID {args.base_id}) tidak terlihat")
            for row, text in enumerate(lines):
                outlined(view, text, (10, 30 + 30 * row))
            cv2.imshow(WIN, view)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), ord("Q"), 27):
                break
            if plan is None and key in (ord("a"), ord("A"), ord("d"), ord("D")):
                offset += (-0.01 if key in (ord("a"), ord("A")) else 0.01)
                offset = round(offset, 3)
                last = None
            elif plan is not None and key in (ord("x"), ord("X")):
                log.write("batal", None, box_id=plan["box"]["id"], note="rencana dibatalkan sebelum ditaruh")
                plan = None
            elif key == ord(" ") and plan is None:
                stack, R0, t0, shot, _ = perceive(cap, detector, catalog, obj, K, dist, args.base_id, log, "keputusan")
                if stack is None:
                    continue
                nid = next_box_id(stack, catalog)
                if nid is None:
                    print("  [agent] semua kardus di katalog sudah ada di tumpukan.")
                    continue
                d = core.decide(stack, nid, offset, catalog, settings)
                stats["keputusan"] += 1
                stats[d["zone"]] += 1
                print_decision(d)
                last = d
                snap = shot.copy()
                draw_box(snap, core.candidate_box(stack, nid, offset, catalog), catalog, R0, t0, K, dist, COLORS[d["zone"]], 3)
                outlined(snap, f"ID {nid} {d['overhang_pct']:+.0f}%: P(roboh) {d['p']:.0%} {d['zone']} -> {d['action']}", (10, 30))
                cv2.imshow(WIN, snap)
                cv2.waitKey(1)
                approved, off, how = handle_decision(d, snap, log, args.supervisor)
                if how.startswith("override"):
                    stats["override"] += 1
                if approved:
                    box = core.candidate_box(stack, nid, off, catalog)
                    zone_now = d["zone"] if off == d["offset_m"] else "HIJAU"
                    p_now = d["p"] if off == d["offset_m"] else d["alternative"]["p"]
                    plan = {"before": stack, "box": box, "how": how, "zone": zone_now, "p": p_now}
                    offset = off
                last = None if approved else d
            elif key == ord(" ") and plan is not None:
                stack, R0, t0, shot, problem = perceive(cap, detector, catalog, obj, K, dist, args.base_id, log,
                                                         "cek ulang")
                if stack is None and problem and "tidak terlihat" in problem:
                    # base marker gone right after a placement: the stack may have fallen onto it
                    v = {"status": "ROBOH?", "message": "kardus bawah tidak terlihat setelah penempatan", "deviation_m": None}
                elif stack is None:
                    continue                       # bad reading (box turned, shaky...): keep the plan, worker fixes it
                else:
                    v = core.verify(plan["before"], stack, plan["box"], catalog)
                print(f"\n[agent] cek ulang: {v['status']} - {v['message']}")
                extra = {}
                if v["status"] in ("OK", "MELESET") and stack is not None:
                    p, n, ci, z = core.stack_risk(stack, catalog, settings)
                    extra = {"p_now": p, "zone_now": z, "n": n}
                    print(f"  tumpukan sekarang: P(roboh) {p:.0%} -> {z}")
                    if z != "HIJAU":
                        print("  [agent] PERINGATAN: tumpukan sekarang tidak aman. Jangan tambah kardus; "
                              "betulkan posisi kardus atas lalu SPASI lagi.")
                if v["status"].startswith("ROBOH"):
                    stats["roboh"] += 1
                log.write("cek_ulang", shot, **v, planned_by=plan["how"], planned_zone=plan["zone"],
                          planned_p=plan["p"], **extra)
                if v["status"] == "BELUM":
                    continue                       # box not placed yet: keep the plan
                if v["status"] == "MELESET" and extra.get("zone_now", "HIJAU") != "HIJAU":
                    continue                       # wait for the worker to fix it, then check again
                plan = None
                offset = 0.0
                last = None
    except KeyboardInterrupt:
        print("\nDihentikan dengan Ctrl+C.")
    cap.release()
    cv2.destroyAllWindows()
    log.write("selesai", None, stats=stats)
    print(f"\nRingkasan: {stats}")
    print(f"Log: {log.path}")


if __name__ == "__main__":
    main()
