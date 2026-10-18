r"""Drystone agent: guides stacking one box at a time.

For each box:
1. The camera reads the stack (ArUco markers) -> digital twin. The wireframe = candidate spot for the next box.
2. Move the candidate with A / D (1 cm), then SPACE = ask the agent for a decision.
3. Agent: GREEN -> guide. YELLOW -> ask the supervisor for approval (in the terminal).
   RED -> reject + suggest the nearest safe spot; only a supervisor override with a logged reason goes ahead.
4. Place the box in the wireframe, let go, press SPACE -> the agent checks again (as planned / off plan / fell).
Every decision is logged in data/agent_<time>/log.jsonl (+ a photo per step).

Keys in the camera window: A / D move candidate, SPACE decide / check, X cancel, Q quit.
Evaluation on a fixed trial list (docs/EVAL_PROTOCOL.md): add --eval-plan config/eval_plan.json --supervisor <name>.

    python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80
Decisions computed on AWS Lambda (the laptop only does camera + display; if AWS fails, the laptop computes):
    python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80 --aws https://<function-url>/
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

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
COLORS = {"GREEN": (0, 170, 0), "YELLOW": (0, 200, 255), "RED": (0, 0, 255), "CANDIDATE": (200, 200, 200)}


class Log:
    def __init__(self, out_dir):
        self.dir = out_dir
        self.path = os.path.join(out_dir, "log.jsonl")
        self.step = 0
        self.extra = {}           # added to every entry (evaluation: the current trial_id)

    def write(self, event, frame=None, **data):
        self.step += 1
        entry = {"step": self.step, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **self.extra, **data}
        if frame is not None:
            name = f"step_{self.step:03d}_{event}.png"
            cv2.imwrite(os.path.join(self.dir, name), frame)
            entry["image"] = name
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=float) + "\n")
        return entry


def outlined(img, text, org, scale=0.65, color=(255, 255, 255)):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def project_box(box, catalog, R0, t0, K, dist):
    """8 image corners (float, index = 4*x + 2*y + z bit) of a box given in the base-marker frame, or None."""
    c = catalog[box["id"]]
    hx, hy, hz = c["L"] / 2, c["H"] / 2, c["D"] / 2
    corners = np.array([[box["x"] + sx * hx, box["y"] + sy * hy, box["z"] + sz * hz]
                        for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    cam = (R0 @ corners.T).T + t0
    if np.any(cam[:, 2] <= 0.05):
        return None
    pts, _ = cv2.projectPoints(cam, np.zeros(3), np.zeros(3), K, dist)
    return pts.reshape(-1, 2)


def draw_box(img, box, catalog, R0, t0, K, dist, color, thick=2):
    """Wireframe of a box given in the base-marker frame."""
    pts = project_box(box, catalog, R0, t0, K, dist)
    if pts is None:
        return
    pts = pts.astype(np.int32)
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


def common_rotation(frames, base_id, ids=None):
    """One facing direction for the whole reading, averaged over every marker in every frame.

    A single marker's orientation wobbles a few degrees per frame. Positions are measured relative to the base
    marker, so that wobble swings the upper boxes sideways: 3 degrees at 40 cm above the base is 2 cm.
    Averaging ~10 frames x 2-3 markers makes the orientation steady. Markers stuck upside-down are flipped first.
    ids: only these markers (the stack, see stack_rotation); None = every marker."""
    R_ref = mean_rotation([f[base_id][0] for f in frames])
    Rs = []
    for f in frames:
        for i, (R, _, _) in f.items():
            if ids is not None and i not in ids:
                continue
            flipped = R @ FLIP_Z
            Rs.append(flipped if np.trace(R_ref.T @ flipped) > np.trace(R_ref.T @ R) else R)
    return mean_rotation(Rs)


class LiveSmoother:
    """Steady live overlay. Each frame: one facing direction from the stacked markers (stack_rotation), then an
    exponential moving average over time. A box that really moves (> SNAP_M) snaps at once instead of sliding.
    Display only: decisions still use read_stack (median of 10 fresh frames). Boxes off the stack: self.loose."""
    ALPHA = 0.15
    SNAP_M = 0.03

    def __init__(self):
        self.R = self.t = None
        self.boxes = {}
        self.loose = []

    def update(self, poses, catalog, base_id):
        Rc = stack_rotation([poses], catalog, base_id, sorted(poses))
        t0 = poses[base_id][1]
        if self.R is None or np.linalg.norm(t0 - self.t) > self.SNAP_M:
            self.R, self.t, self.boxes = Rc, t0.copy(), {}
        else:
            self.R = mean_rotation([self.ALPHA * Rc + (1 - self.ALPHA) * self.R])
            self.t = self.ALPHA * t0 + (1 - self.ALPHA) * self.t
        stack = []
        for i, (R, t, _) in poses.items():
            p = self.R.T @ (t - t0)
            now = np.array([p[0], p[1], p[2] - catalog[i]["D"] / 2.0])
            old = self.boxes.get(i)
            pos = now if old is None or np.linalg.norm(now - old) > self.SNAP_M else self.ALPHA * now + (1 - self.ALPHA) * old
            self.boxes[i] = pos
            stack.append({"id": i, "x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
                          "turn_deg": yaw_deg(poses, i, base_id)})
        for gone in set(self.boxes) - set(poses):
            del self.boxes[gone]
        stack, self.loose = build_stack(stack, catalog, base_id)
        return stack, self.R, self.t


STACK_GAP_M = 0.04         # a box rests on the one below if its bottom is within 4 cm of that box's top


def _box_positions(frames, ids, Rc, base_id, catalog):
    """Median position (base-marker frame), facing angle and jitter of each box over the frames."""
    boxes = []
    for i in ids:
        rel = np.array([Rc.T @ (f[i][1] - f[base_id][1]) for f in frames])   # marker centre, base frame
        med = np.median(rel, axis=0)
        Ri = mean_rotation([f[i][0] for f in frames])
        n_i = Rc.T @ Ri[:, 2]
        a = abs(float(np.degrees(np.arctan2(n_i[0], n_i[2]))))
        xs = rel[:, 0]
        boxes.append({"id": i, "x": float(med[0]), "y": float(med[1]), "z": float(med[2] - catalog[i]["D"] / 2.0),
                      "turn_deg": 180.0 - a if a > 90 else a,
                      "jitter_m": float(1.4826 * np.median(np.abs(xs - np.median(xs))))})
    return boxes


def build_stack(boxes, catalog, base_id):
    """The stack by physical contact, from the base box up: the next box is the one whose bottom is within
    STACK_GAP_M of the current top box's top and which overlaps it in plan view. Every other visible box is
    'loose' (fallen, set aside, held in the air), with where it is: "floor", "beside" or "gap" (above the top box
    but not touching it). Image height alone is not enough: a box that fell next to the stack is at floor level."""
    by_id = {b["id"]: b for b in boxes}
    stack, rest = [by_id[base_id]], [b for b in boxes if b["id"] != base_id]
    while rest:
        top, ct = stack[-1], catalog[stack[-1]["id"]]
        fits = []
        for b in rest:
            c = catalog[b["id"]]
            gap = (b["y"] - c["H"] / 2) - (top["y"] + ct["H"] / 2)
            if (abs(gap) <= STACK_GAP_M and abs(b["x"] - top["x"]) < (ct["L"] + c["L"]) / 2
                    and abs(b["z"] - top["z"]) < (ct["D"] + c["D"]) / 2):
                fits.append((abs(gap), b))
        if not fits:
            break
        nxt = min(fits, key=lambda f: f[0])[1]
        stack.append(nxt)
        rest.remove(nxt)
    base = stack[0]
    base_top = base["y"] + catalog[base["id"]]["H"] / 2
    loose = []
    for b in sorted(rest, key=lambda b: b["id"]):
        top, ct, c = stack[-1], catalog[stack[-1]["id"]], catalog[b["id"]]
        over_top = abs(b["x"] - top["x"]) < (ct["L"] + c["L"]) / 2
        if b["y"] < base_top:
            where = "floor"                    # marker below the top of the base box: standing or lying on the floor
        elif over_top and b["y"] > top["y"]:
            where = "gap"                      # above the top box but not resting on it
        else:
            where = "beside"
        loose.append(dict(b, where=where, gap_m=float((b["y"] - c["H"] / 2) - (top["y"] + ct["H"] / 2))))
    return stack, loose


def loose_problem(b, stack):
    """Message for a visible box that is not part of the stack (decision readings must not have one)."""
    if b["where"] == "gap":
        return (f"height gap ID {stack[-1]['id']} -> ID {b['id']} is {b['gap_m'] * 100:+.0f} cm off "
                "(marker covered / boxes not stacked?)")
    place = "on the floor next to the stack" if b["where"] == "floor" else "beside the stack"
    return f"box ID {b['id']} is {place}, not on it -> move it out of the camera view"


def stack_rotation(frames, catalog, base_id, ids):
    """Facing direction for the reading, from the stack only: first the base marker alone (averaged over the
    frames) to find which boxes are on the stack, then every stacked marker x frame. A fallen or turned box
    must not tilt the frame of the stack (a box turned 50 deg on the floor tilted it by 16 deg)."""
    R_base = common_rotation(frames, base_id, [base_id])
    stack, _ = build_stack(_box_positions(frames, ids, R_base, base_id, catalog), catalog, base_id)
    return common_rotation(frames, base_id, [b["id"] for b in stack])


def read_scene(cap, detector, catalog, obj, K, dist, base_id, n=CAPTURE_FRAMES):
    """Several frames -> stack (by contact, bottom first), loose boxes, quality checks.
    Returns (stack, loose, R0, t0, frame, problem). Loose boxes are not a problem here; read_stack makes them one."""
    frames, frame = [], None
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            return None, [], None, None, frame, "camera is not sending frames"
        poses = detect_poses(detector, frame, catalog, obj, K, dist, base_id)
        if base_id in poses:
            frames.append(poses)
    if not frames:
        return None, [], None, None, frame, f"bottom box marker (ID {base_id}) not visible"
    id_sets = [tuple(sorted(f)) for f in frames]
    ids = max(set(id_sets), key=id_sets.count)
    if id_sets.count(ids) < (1 if len(frames) == 1 else max(2, len(frames) // 2 + 1)):
        return None, [], None, None, frame, "visible markers change between frames"
    frames = [f for f, s in zip(frames, id_sets) if s == ids]
    Rc = stack_rotation(frames, catalog, base_id, ids)
    stack, loose = build_stack(_box_positions(frames, ids, Rc, base_id, catalog), catalog, base_id)
    R0, t0 = Rc, np.median([f[base_id][1] for f in frames], axis=0)
    shaky = [f"ID {b['id']} ({b['jitter_m'] * 100:.1f} cm)" for b in stack if b["jitter_m"] > MAX_JITTER_M]
    if shaky:
        return stack, loose, R0, t0, frame, ("position of box " + ", ".join(shaky)
                                             + " jitters between frames (> 1 cm): do not touch the table or boxes")
    turned = [f"ID {b['id']} ({b['turn_deg']:.0f} deg)" for b in stack if b["turn_deg"] > MAX_TURN_DEG]
    if turned:
        return stack, loose, R0, t0, frame, "box " + ", ".join(turned) + " is turned -> straighten it"
    return stack, loose, R0, t0, frame, None


def read_stack(cap, detector, catalog, obj, K, dist, base_id, n=CAPTURE_FRAMES):
    """Reading for a decision: like read_scene, but any visible box that is not on the stack is a problem
    (idle boxes must be out of view). Returns (stack, R0, t0, frame, problem)."""
    stack, loose, R0, t0, frame, problem = read_scene(cap, detector, catalog, obj, K, dist, base_id, n)
    if problem is None and loose:
        problem = loose_problem(loose[0], stack)
    return stack, R0, t0, frame, problem


def perceive(cap, detector, catalog, obj, K, dist, base_id, log, reason, allow_loose=False):
    """The agent re-reads by itself when a reading looks bad; asks the worker only after several tries.
    allow_loose (check after a placement): boxes off the stack are an outcome to report, not a bad reading.
    Returns (stack, loose, R0, t0, frame, problem)."""
    for attempt in range(1, MAX_RETRIES + 1):
        stack, loose, R0, t0, frame, problem = read_scene(cap, detector, catalog, obj, K, dist, base_id)
        if problem is None and loose and not allow_loose:
            # a box off the stack will not move by itself: tell the worker once instead of retaking
            problem = loose_problem(loose[0], stack)
            print(f"  [agent] {reason}: {problem}. Then press SPACE again.")
            log.write("retake", frame, reason=reason, attempt=attempt, problem=problem)
            return None, loose, None, None, frame, problem
        if problem is None:
            if attempt > 1:
                print(f"  [agent] reading {attempt} is clean")
            return stack, loose, R0, t0, frame, None
        print(f"  [agent] reading {attempt}/{MAX_RETRIES} for {reason}: {problem} -> retake")
        log.write("retake", frame, reason=reason, attempt=attempt, problem=problem)
        time.sleep(0.3)
    print(f"  [agent] still failing: {problem}. Fix the stack or camera, then press SPACE again.")
    return None, [], None, None, frame, problem


AWS_FRAMES = 3            # photos sent per request (JPEG ~150 KB each; PNG was 1.4 MB and took ~8 s to upload)
AWS_TIMEOUT_S = 60


def _cm(b):
    return {"id": int(b["id"]), "x_cm": round(b["x"] * 100, 2), "y_cm": round(b["y"] * 100, 2),
            "z_cm": round(b["z"] * 100, 2)}


def aws_call(url, body, cap, first):
    """POST photos + request to the Lambda Function URL. Returns (response dict, seconds) or raises."""
    frames = [first] + [f for ok, f in (cap.read() for _ in range(AWS_FRAMES - 1)) if ok]
    body = dict(body, return_image=False,
                images=[base64.b64encode(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()).decode()
                        for f in frames])
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=AWS_TIMEOUT_S) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:            # the service answers 400 with a JSON problem
        out = json.loads(e.read() or b"{}")
        if not out:
            raise
    if isinstance(out.get("body"), str):           # raw Lambda proxy response (emulator / direct invoke)
        out = json.loads(out["body"])
    return out, time.time() - t


def decide_aws(url, cap, shot, stack, nid, offset, catalog, settings):
    """Decision from AWS Lambda. Falls back to the laptop if AWS is unreachable or fails (logged in the trace)."""
    try:
        r, sec = aws_call(url, {"mode": "decide", "box_id": nid, "offset_cm": round(offset * 100, 1)}, cap, shot)
        if r.get("action") == "RETAKE":
            return None, f"AWS asks for a retake: {r.get('problem')}"
        if not r.get("ok") or "decision" not in r:
            raise RuntimeError(r.get("problem") or "incomplete answer from AWS")
        dec = r["decision"]
        alt = dec.get("alternative")
        d = {"box_id": dec["box_id"], "offset_m": dec["offset_cm"] / 100, "overhang_pct": dec["overhang_pct"],
             "static_margin_m": dec["static_margin_cm"] / 100, "p": dec["p"], "ci": dec["ci"], "n": dec["n"],
             "zone": dec["zone"], "action": dec["action"],
             "alternative": None if not alt else {"offset_m": alt["offset_cm"] / 100,
                                                   "overhang_pct": alt["overhang_pct"], "p": alt["p"]},
             "trace": [f"computed on AWS Lambda ({sec:.1f} s round trip, {r.get('seconds', 0):.1f} s on the server)"] + dec["trace"],
             "source": "aws", "aws_seconds": round(sec, 2)}
        return d, None
    except Exception as e:                          # network, timeout, bad answer: keep working on the laptop
        d = core.decide(stack, nid, offset, catalog, settings)
        d["trace"].insert(0, f"AWS failed ({type(e).__name__}: {str(e)[:80]}) -> computed on the laptop")
        d["source"] = "laptop (fallback)"
        return d, None


def verify_aws(url, cap, shot, plan, catalog, settings, stack, loose=None):
    """Check after placement via AWS; falls back to the laptop."""
    try:
        r, sec = aws_call(url, {"mode": "check", "plan": {"before": [_cm(b) for b in plan["before"]],
                                                          "box": _cm(plan["box"])}}, cap, shot)
        v = r.get("verify")
        if not v:
            raise RuntimeError(r.get("problem") or "incomplete answer from AWS")
        dev = v.get("deviation_cm")
        v = {"status": v["status"], "message": v["message"] + f" [AWS {sec:.1f} s]",
             "deviation_m": None if dev is None else dev / 100}
        risk = r.get("risk_now")
        extra = {} if not risk else {"p_now": risk["p"], "zone_now": risk["zone"], "n": risk["n"]}
        return v, extra, "aws"
    except Exception as e:
        if stack is None:
            return ({"status": "FELL?", "message": f"AWS failed ({type(e).__name__}) and the stack is unreadable",
                     "deviation_m": None}, {}, "laptop (fallback)")
        v = core.verify(plan["before"], stack, plan["box"], catalog, loose=loose)
        v["message"] += f" [AWS failed: {type(e).__name__}, checked on the laptop]"
        extra = {}
        if v["status"] in ("OK", "OFF_PLAN"):
            p, n, ci, z = core.stack_risk(stack, catalog, settings)
            extra = {"p_now": p, "zone_now": z, "n": n}
        return v, extra, "laptop (fallback)"


def ask(prompt, valid, allow_empty=False):
    """One letter from valid. An empty answer (Enter) only counts when allow_empty: '' is "in" every string, so it
    used to slip through as an answer (Enter at the f/p question meant "fell")."""
    while True:
        ans = input(prompt).strip().lower()
        if (ans and ans[0] in valid) or (allow_empty and not ans):
            return ans[:1]
        print(f"  type one of: {', '.join(valid)}")


def ask_text(prompt, min_len=1):
    while True:
        ans = input(prompt).strip()
        if len(ans) >= min_len:
            return ans
        print(f"  required (at least {min_len} characters)")


def next_box_id(stack, catalog):
    """Next box to place: the smallest ID that is not on the stack (boxes are stacked in ID order, so a box that
    fell or was taken off is planned again before any higher ID)."""
    used = {b["id"] for b in stack}
    free = [i for i in sorted(catalog) if i not in used]
    return free[0] if free else None


def not_visible_only(plan, stack, loose):
    """True when the planned box is nowhere in view (not on the stack, not on the floor) and every box that stood
    before the placement still stands: the camera cannot tell "fell out of view" from "not placed yet"."""
    on_stack = {b["id"] for b in stack}
    seen = on_stack | {b["id"] for b in loose or []}
    return plan["box"]["id"] not in seen and all(b["id"] in on_stack for b in plan["before"])


def fallen_message(ids):
    names = ", ".join(f"ID {i}" for i in ids)
    return (f"box {names} fell. Pick it up and keep it out of the camera view, "
            f"then press SPACE to plan {names} again.")


def print_decision(d):
    print(f"\n[agent] decision for box ID {d['box_id']} overhanging {d['overhang_pct']:+.0f}%:")
    for line in d["trace"]:
        print(f"  - {line}")
    print(f"  => P(fall) {d['p']:.0%} (+-{d['ci']:.0%}, {d['n']} simulations) -> {d['zone']}: {d['action']}")
    if d["alternative"]:
        a = d["alternative"]
        print(f"  => suggestion: move to {a['offset_m'] * 100:+.0f} cm ({a['overhang_pct']:+.0f}%), P(fall) {a['p']:.0%}")


def handle_decision(d, frame, log, supervisor):
    """Human control. Returns (approved, offset_m, how)."""
    entry = {k: v for k, v in d.items() if k != "trace"}
    log.write("decision", frame, **entry, trace=d["trace"])
    if d["zone"] == "GREEN":
        print("  [agent] GREEN: place the box in the green wireframe.")
        return True, d["offset_m"], "automatic"
    if d["zone"] == "YELLOW":
        print("  [agent] YELLOW: supervisor approval needed.")
        choice = ask("  Supervisor: a = approve, s = use the agent's suggestion, r = reject: ", "asr")
        if choice == "a":
            name = supervisor or ask_text("  Supervisor name: ")
            log.write("approval", None, box_id=d["box_id"], offset_m=d["offset_m"], p=d["p"], supervisor=name)
            return True, d["offset_m"], f"approved by {name}"
    else:
        print("  [agent] RED: REJECTED. This position will most likely fall.")
        choice = ask("  s = use the agent's suggestion, o = override (reason required), c = cancel: ", "soc")
        if choice == "o":
            name = supervisor or ask_text("  Supervisor name: ")
            reason = ask_text("  Override reason (logged): ", min_len=5)
            log.write("override", None, box_id=d["box_id"], offset_m=d["offset_m"], p=d["p"],
                      supervisor=name, reason=reason)
            print("  [agent] override logged. The supervisor takes responsibility for the risk.")
            return True, d["offset_m"], f"override {name}: {reason}"
    if choice == "s":
        if d["alternative"] is None:
            print("  [agent] no green suggestion. Cancelled.")
        else:
            a = d["alternative"]
            log.write("use_suggestion", None, box_id=d["box_id"], offset_m=a["offset_m"], p=a["p"])
            print(f"  [agent] suggestion accepted: place the box in the green wireframe ({a['offset_m'] * 100:+.0f} cm).")
            return True, a["offset_m"], "agent suggestion"
    log.write("cancel", None, box_id=d["box_id"], offset_m=d["offset_m"])
    print("  [agent] cancelled. Move the candidate, then press SPACE again.")
    return False, d["offset_m"], "cancel"


class Evaluation:
    """--eval-plan: walk through a fixed trial list (docs/EVAL_PROTOCOL.md). For each trial the worker builds the
    stack, the agent decides at the planned shift, the box is placed there anyway (YELLOW / RED as an override with
    reason "evaluation"), and the check after placement gives the outcome, confirmed by the worker."""

    def __init__(self, path, start, log):
        with open(path, "rb") as f:
            raw = f.read()
        self.trials = json.loads(raw)["trials"]
        self.i = max(0, start - 1)
        self.log = log
        self.last_decision = None
        log.write("eval_start", None, plan=os.path.basename(path), plan_sha256=hashlib.sha256(raw).hexdigest(),
                  n_trials=len(self.trials), start_trial=self.i + 1)
        self._enter()

    @property
    def trial(self):
        return self.trials[self.i] if self.i < len(self.trials) else None

    def _enter(self):
        self.log.extra = {"trial_id": self.trial["trial_id"]} if self.trial else {}
        self.last_decision = None

    def needed_ids(self):
        return [b["id"] for b in self.trial["stack"]]

    def describe(self):
        t = self.trial
        base = " + ".join(f"ID {b['id']}" + (f" at {b['shift_cm']:+d} cm" if "shift_cm" in b else "") for b in t["stack"])
        return f"{t['trial_id']} ({self.i + 1}/{len(self.trials)}): {base}; then ID {t['box_id']} at {t['shift_cm']:+d} cm"

    SETUP_TOL_M = 0.015        # a setup box must be within 1.5 cm of its planned shift

    def state(self, stack):
        """For the stack the camera sees: ("ready", None) | ("setup", (box id, shift m)) | ("shift", (box id, planned m,
        seen m)) when a setup box is too far from its planned shift | ("wrong", None)."""
        need, now = self.needed_ids(), [b["id"] for b in stack]
        if now == need:
            for planned, below, b in zip(self.trial["stack"][1:], stack, stack[1:]):
                want, seen = planned.get("shift_cm", 0) / 100.0, b["x"] - below["x"]
                if abs(seen - want) > self.SETUP_TOL_M:
                    return "shift", (b["id"], want, seen)
            return "ready", None
        if now == need[:len(now)]:
            b = self.trial["stack"][len(now)]
            return "setup", (b["id"], b.get("shift_cm", 0) / 100.0)
        return "wrong", None

    @staticmethod
    def setup_shifts(stack):
        return [round((b["x"] - a["x"]) * 100, 1) for a, b in zip(stack, stack[1:])]

    def finish(self, v, fell_auto, fell, extra):
        t, d = self.trial, self.last_decision or {}
        dev = v.get("deviation_m")
        self.log.write("eval_result", None, box_id=t["box_id"], shift_cm=t["shift_cm"], n_boxes=len(t["stack"]) + 1,
                       expected_zone=t["expected_zone"], expected_p=t["expected_p"], p=d.get("p"), ci=d.get("ci"),
                       n=d.get("n"), zone=d.get("zone"), action=d.get("action"), source=d.get("source"),
                       aws_seconds=d.get("aws_seconds"), setup_shift_cm=d.get("setup_shift_cm"),
                       check_status=v["status"], check_message=v.get("message"),
                       deviation_cm=None if dev is None else round(dev * 100, 2),
                       fell_auto=fell_auto, fell=fell, corrected=fell != fell_auto,
                       p_now=extra.get("p_now"), zone_now=extra.get("zone_now"))
        self.i += 1
        self._enter()


def eval_decision(d, frame, log, supervisor, ev, stack):
    """Evaluation: the box goes where the trial says. GREEN as usual; YELLOW / RED as a logged override."""
    ev.last_decision = dict(d, setup_shift_cm=ev.setup_shifts(stack))
    entry = {k: v for k, v in d.items() if k != "trace"}
    log.write("decision", frame, **entry, trace=d["trace"], eval=True, stack_cm=[_cm(b) for b in stack],
              setup_shift_cm=ev.setup_shifts(stack))
    if d["zone"] == "GREEN":
        print("  [eval] GREEN: place the box in the green wireframe.")
        return True, d["offset_m"], "automatic"
    log.write("override", None, box_id=d["box_id"], offset_m=d["offset_m"], p=d["p"], supervisor=supervisor,
              reason="evaluation", eval=True)
    print(f"  [eval] {d['zone']}: placed anyway for the evaluation (override by {supervisor}, reason 'evaluation', "
          "logged). Place the box in the wireframe, let go, wait 5 s, then SPACE.")
    return True, d["offset_m"], f"override {supervisor}: evaluation"


def main():
    ap = argparse.ArgumentParser(description="Drystone agent: guide, ask for approval, or reject each placement")
    ap.add_argument("--calib", required=True)
    ap.add_argument("--marker-mm", type=float, default=common.BOX_MARKER_MM)
    ap.add_argument("--boxes", default=os.path.join(common.ROOT, "config", "boxes.json"))
    ap.add_argument("--base-id", type=int, default=0)
    ap.add_argument("--pos-sd-cm", type=float, default=1.0)
    ap.add_argument("--com-sd-cm", type=float, default=2.0)
    ap.add_argument("--friction", type=float, default=0.5)
    ap.add_argument("--supervisor", default="", help="supervisor name (asked when needed if empty)")
    ap.add_argument("--source", default="0")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--aws", default=os.environ.get("DRYSTONE_URL", ""),
                    help="Drystone Lambda Function URL; empty = everything runs on the laptop")
    ap.add_argument("--eval-plan", help="evaluation trial list (config/eval_plan.json, docs/EVAL_PROTOCOL.md)")
    ap.add_argument("--eval-start", type=int, default=1, help="evaluation: start at this trial number (resume)")
    args = ap.parse_args()
    if args.eval_plan and not args.supervisor:
        sys.exit("--eval-plan needs --supervisor <name>: evaluation overrides are logged under that name.")

    catalog = load_catalog(args.boxes)
    K, dist, calib_size = common.load_calibration(args.calib)
    obj = np.array([[-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0]], dtype=np.float32) * (args.marker_mm / 2000.0)
    settings = core.Settings(args.pos_sd_cm, args.com_sd_cm, args.friction, args.seed)
    out_dir = os.path.join(common.DATA_DIR, f"agent_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    log = Log(out_dir)
    log.write("start", None, settings={"pos_sd_cm": args.pos_sd_cm, "com_sd_cm": args.com_sd_cm,
                                        "friction": args.friction, "marker_mm": args.marker_mm,
                                        "p_green": core.P_GREEN, "p_red": core.P_RED},
              decisions_on="aws" if args.aws else "laptop")
    if args.aws:
        print("Decisions are computed on AWS Lambda (fallback: laptop).")
    detector = common.make_marker_detector()
    cap = common.open_camera(args.source, calib_size[0], calib_size[1])
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 540)
    print(__doc__.split("\n    python")[0])
    ev = Evaluation(args.eval_plan, args.eval_start, log) if args.eval_plan else None
    if ev:
        print(f"\nEVALUATION MODE ({len(ev.trials)} trials). A/D are off; the shift comes from the trial list.")
        if ev.trial:
            print(f"  next: {ev.describe()}")

    smoother = LiveSmoother()
    offset = 0.0          # candidate shift (m) relative to the current top box
    plan = None           # approved placement waiting to be checked: {"before", "box", "how", "zone", "p"}
    last = None           # last decision, drawn until the candidate moves
    fallen = []           # boxes that fell off: not placed any more, planned again once picked up
    expected = [args.base_id]  # box IDs the agent last saw standing on the stack (after a check)
    stats = {"decisions": 0, "GREEN": 0, "YELLOW": 0, "RED": 0, "override": 0, "fell": 0, "retry_after_fall": 0}
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("The camera stopped sending frames.")
                break
            poses = detect_poses(detector, frame, catalog, obj, K, dist, args.base_id)
            view = frame.copy()
            for i, (_, _, c4) in poses.items():
                cv2.polylines(view, [c4.astype(np.int32)], True, (0, 255, 0), 2)
                outlined(view, f"ID {i}", tuple(int(v) for v in c4[0]), 0.6, (0, 255, 0))
            lines = []
            if args.base_id in poses:
                stack, R0, t0 = smoother.update(poses, catalog, args.base_id)
                if plan:
                    draw_box(view, plan["box"], catalog, R0, t0, K, dist, COLORS[plan["zone"]], 3)
                    lines.append(f"place box ID {plan['box']['id']} in the wireframe, let go, then SPACE = check")
                elif ev is not None:
                    if ev.trial is None:
                        lines.append("evaluation finished | Q quit")
                    else:
                        what, setup = ev.state(stack)
                        lines.append("EVAL " + ev.describe())
                        if what == "setup":
                            sid, sshift = setup
                            draw_box(view, core.candidate_box(stack, sid, sshift, catalog), catalog, R0, t0, K, dist,
                                     COLORS["CANDIDATE"], 2)
                            lines.append(f"setup (not scored): place ID {sid} at {sshift * 100:+.0f} cm")
                        elif what == "shift":
                            sid, want, seen = setup
                            draw_box(view, core.candidate_box(stack[:-1], sid, want, catalog), catalog, R0, t0, K,
                                     dist, COLORS["CANDIDATE"], 2)
                            lines.append(f"setup (not scored): move ID {sid} to {want * 100:+.0f} cm "
                                         f"(now {seen * 100:+.1f} cm)")
                        elif what == "wrong":
                            lines.append(f"take boxes off: this trial needs the stack {ev.needed_ids()}")
                        else:
                            offset = ev.trial["shift_cm"] / 100.0
                            cand = core.candidate_box(stack, ev.trial["box_id"], offset, catalog)
                            draw_box(view, cand, catalog, R0, t0, K, dist, COLORS["CANDIDATE"], 2)
                            lines.append("SPACE decide | Q quit")
                else:
                    if fallen:
                        lines.append(fallen_message(fallen))
                    nid = next_box_id(stack, catalog)
                    if nid is not None:
                        cand = core.candidate_box(stack, nid, offset, catalog)
                        color = COLORS[last["zone"]] if last else COLORS["CANDIDATE"]
                        draw_box(view, cand, catalog, R0, t0, K, dist, color, 2)
                        if last and last["alternative"]:
                            alt = core.candidate_box(stack, nid, last["alternative"]["offset_m"], catalog)
                            draw_box(view, alt, catalog, R0, t0, K, dist, COLORS["GREEN"], 1)
                        lines.append(f"candidate ID {nid}: {offset * 100:+.0f} cm ({core.overhang_pct(stack, cand, catalog):+.0f}%)"
                                     + (f" | {last['zone']} {last['p']:.0%}" if last else ""))
                        lines.append("A/D move 1 cm | SPACE decide | Q quit")
                lines.insert(0, f"stack: {[b['id'] for b in stack]}"
                             + "".join(f" | ID {b['id']} off the stack ({b['where']})" for b in smoother.loose))
            else:
                lines.append(f"bottom box marker (ID {args.base_id}) not visible")
            for row, text in enumerate(lines):
                outlined(view, text, (10, 30 + 30 * row))
            cv2.imshow(WIN, view)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), ord("Q"), 27):
                break
            if plan is None and ev is None and key in (ord("a"), ord("A"), ord("d"), ord("D")):
                offset += (-0.01 if key in (ord("a"), ord("A")) else 0.01)
                offset = round(offset, 3)
                last = None
            elif plan is not None and key in (ord("x"), ord("X")):
                log.write("cancel", None, box_id=plan["box"]["id"], note="plan cancelled before placement")
                plan = None
            elif key == ord(" ") and plan is None:
                if fallen:
                    _, loose, _, _, shot, _ = read_scene(cap, detector, catalog, obj, K, dist, args.base_id, n=3)
                    still = [b for b in loose if b["id"] in fallen]
                    if still:                      # one reading, no retakes: the worker has to move the box
                        print(f"  [agent] {fallen_message([b['id'] for b in still])} "
                              f"(ID {still[0]['id']} is still in view, {still[0]['where']})")
                        log.write("wait_pickup", shot, box_ids=[b["id"] for b in still],
                                  where=[b["where"] for b in still])
                        continue
                if ev is not None and ev.trial is None:
                    print("  [eval] every trial is done. Press Q.")
                    continue
                stack, _, R0, t0, shot, _ = perceive(cap, detector, catalog, obj, K, dist, args.base_id, log,
                                                     "decision")
                if stack is None:
                    continue
                ids_now = [b["id"] for b in stack]
                if ev is not None:
                    what, info = ev.state(stack)
                    if what != "ready":
                        why = (f"ID {info[0]} must be at {info[1] * 100:+.0f} cm (now {info[2] * 100:+.1f} cm)"
                               if what == "shift" else f"it needs the stack {ev.needed_ids()}; the camera sees {ids_now}")
                        print(f"  [eval] {ev.trial['trial_id']} is not set up: {why}.")
                        log.write("eval_wrong_stack", shot, needed=ev.needed_ids(), stack=ids_now,
                                  setup_shift_cm=ev.setup_shifts(stack), why=why)
                        continue
                    expected = ids_now
                    offset = ev.trial["shift_cm"] / 100.0
                missing = [i for i in expected if i not in ids_now]
                if missing:                        # a box that was standing is gone: plan it again, in ID order
                    print(f"  [agent] stack changed: {', '.join(f'ID {i}' for i in missing)} "
                          f"{'is' if len(missing) == 1 else 'are'} missing from the stack.")
                    log.write("stack_changed", shot, missing=missing, expected=expected, stack=ids_now)
                back = [i for i in fallen if i in ids_now]
                if back:                           # a box counted as fallen is standing on the stack after all
                    print(f"  [agent] box {', '.join(f'ID {i}' for i in back)} is on the stack now.")
                    log.write("back_on_stack", shot, box_ids=back, stack=ids_now)
                    fallen = [i for i in fallen if i not in back]
                expected = ids_now
                nid = ev.trial["box_id"] if ev is not None else next_box_id(stack, catalog)
                if nid is None:
                    print("  [agent] every box in the catalogue is already on the stack.")
                    continue
                retry = nid in fallen
                if retry:
                    fallen.remove(nid)
                    stats["retry_after_fall"] += 1
                    print(f"  [agent] planning box ID {nid} again after it fell.")
                if args.aws:
                    print("  [agent] sending photos to AWS ...")
                    d, problem = decide_aws(args.aws, cap, shot, stack, nid, offset, catalog, settings)
                    if d is None:
                        print(f"  [agent] {problem}. Fix the stack or camera, then press SPACE again.")
                        log.write("retake", shot, reason="decision (AWS)", problem=problem)
                        continue
                else:
                    d = core.decide(stack, nid, offset, catalog, settings)
                    d["source"] = "laptop"
                d["retry_after_fall"] = retry
                stats["decisions"] += 1
                stats[d["zone"]] += 1
                print_decision(d)
                last = d
                snap = shot.copy()
                draw_box(snap, core.candidate_box(stack, nid, offset, catalog), catalog, R0, t0, K, dist, COLORS[d["zone"]], 3)
                outlined(snap, f"ID {nid} {d['overhang_pct']:+.0f}%: P(fall) {d['p']:.0%} {d['zone']} -> {d['action']}", (10, 30))
                cv2.imshow(WIN, snap)
                cv2.waitKey(1)
                if ev is not None:
                    approved, off, how = eval_decision(d, snap, log, args.supervisor, ev, stack)
                else:
                    approved, off, how = handle_decision(d, snap, log, args.supervisor)
                if how.startswith("override"):
                    stats["override"] += 1
                if approved:
                    box = core.candidate_box(stack, nid, off, catalog)
                    zone_now = d["zone"] if off == d["offset_m"] else "GREEN"
                    p_now = d["p"] if off == d["offset_m"] else d["alternative"]["p"]
                    plan = {"before": stack, "box": box, "how": how, "zone": zone_now, "p": p_now}
                    offset = off
                last = None if approved else d
            elif key == ord(" ") and plan is not None:
                stack, loose, R0, t0, shot, problem = perceive(cap, detector, catalog, obj, K, dist, args.base_id,
                                                                log, "check", allow_loose=True)
                if args.aws and (stack is not None or (problem and "not visible" in problem)):
                    print("  [agent] checking on AWS ...")
                    v, extra, src = verify_aws(args.aws, cap, shot, plan, catalog, settings, stack, loose)
                elif stack is None and problem and "not visible" in problem:
                    # base marker gone right after a placement: the stack may have fallen onto it
                    v = {"status": "FELL?", "message": "bottom box not visible after the placement", "deviation_m": None}
                elif stack is None:
                    continue                       # bad reading (box turned, shaky...): keep the plan, worker fixes it
                else:
                    v = core.verify(plan["before"], stack, plan["box"], catalog, loose=loose)
                print(f"\n[agent] check: {v['status']} - {v['message']}")
                answer = None
                if v["status"] == "FELL" and stack is not None and not_visible_only(plan, stack, loose):
                    # nothing on the floor and the stack below is intact: maybe SPACE came before the box did,
                    # or its marker was not read. The worker can see it; the camera cannot.
                    bid = plan["box"]["id"]
                    answer = ask(f"  box ID {bid} is not visible. f = it fell out of view, "
                                 "p = not placed yet (look again): ", "fp")
                    if answer == "p":
                        v = {"status": "NOT_PLACED", "deviation_m": None,
                             "message": f"box ID {bid} not visible; worker says not placed yet -> look again"}
                    else:
                        v = dict(v, message=v["message"] + " (confirmed by the worker)")
                    print(f"  [agent] {v['message']}")
                if not args.aws:
                    extra, src = {}, "laptop"
                    if v["status"] in ("OK", "OFF_PLAN") and stack is not None:
                        p, n, ci, z = core.stack_risk(stack, catalog, settings)
                        extra = {"p_now": p, "zone_now": z, "n": n}
                if extra:
                    print(f"  stack now: P(fall) {extra['p_now']:.0%} -> {extra['zone_now']}")
                    if extra["zone_now"] == "RED" or (v["status"] == "OFF_PLAN" and extra["zone_now"] != "GREEN"):
                        print("  [agent] WARNING: the stack is not safe now. Do not add boxes; "
                              "move the top box back into the wireframe, then press SPACE again.")
                    elif extra["zone_now"] == "YELLOW":
                        print(f"  [agent] CAUTION: the stack is borderline now (P(fall) {extra['p_now']:.0%}). "
                              "Ask the supervisor before adding another box.")
                fell_ids = []
                if v["status"].startswith("FELL"):
                    stats["fell"] += 1
                    on_stack = {b["id"] for b in stack} if stack is not None else set()
                    fell_ids = sorted({plan["box"]["id"]} | {b["id"] for b in plan["before"] if b["id"] not in on_stack
                                                             and b["id"] != args.base_id})
                log.write("check", shot, **v, planned_by=plan["how"], planned_zone=plan["zone"],
                          planned_p=plan["p"], checked_on=src, fell_ids=fell_ids, worker_answer=answer, **extra)
                if v["status"] == "NOT_PLACED":
                    continue                       # box not placed yet: keep the plan
                if ev is not None and ev.trial is not None:
                    fell_auto = v["status"].startswith("FELL")
                    tid = ev.trial["trial_id"]
                    ans = ask(f"  [eval] {tid}: the check says the box {'FELL' if fell_auto else 'STOOD'}. "
                              "Enter or y = confirm, n = the opposite: ", "yn", allow_empty=True)
                    fell = fell_auto if ans in ("", "y") else not fell_auto
                    ev.finish(v, fell_auto, fell, extra)
                    print(f"  [eval] {tid} done: {'fell' if fell else 'stood'}"
                          + (" (corrected by the worker)" if fell != fell_auto else "") + ".")
                    if ev.trial:
                        print(f"  [eval] next: {ev.describe()}. Take the boxes off and build that stack.")
                    else:
                        print("  [eval] every trial is done. Press Q.")
                    plan = None
                    last = None
                    fallen = []
                    continue
                if v["status"] == "OFF_PLAN" and extra.get("zone_now", "GREEN") != "GREEN":
                    continue                       # wait for the worker to fix it, then check again
                plan = None
                last = None
                if stack is not None:
                    expected = [b["id"] for b in stack]
                if fell_ids:
                    # the fallen boxes are "not placed" again; keep the requested shift so the new decision
                    # shows the same risk and its suggestion
                    fallen = sorted(set(fallen) | set(fell_ids))
                    print(f"  [agent] {fallen_message(fell_ids)}")
                else:
                    offset = 0.0
    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")
    cap.release()
    cv2.destroyAllWindows()
    log.write("end", None, stats=stats)
    print(f"\nSummary: {stats}")
    print(f"Log: {log.path}")


if __name__ == "__main__":
    main()
