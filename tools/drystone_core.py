"""Drystone decision core: stack + candidate placement -> zone, action, alternative.

No camera and no GUI here, so the same code runs on the laptop and on AWS.
Safety decisions are deterministic rules on top of a Monte Carlo physics estimate; no LLM decides anything.

Coordinates (metres), all in the frame of the base box marker:
x = right along the front face, y = up, z = toward the camera. A box is a dict {"id", "x", "y", "z"},
where (x, z) is the box centre in plan view and y is the height of its marker centre.
"""
import math
import time

import numpy as np

import mujoco

from predict_test import FALL_DROP_M, FALL_TILT_DEG, SIM_SECONDS, static_check, zone

CHECK_EVERY = 10          # physics steps between early-exit checks (0.02 s)
SETTLE_AFTER_S = 0.25     # do not call a stack "at rest" before this
REST_SPEED = 0.002        # m/s and rad/s: every box slower than this = at rest


def _model_xml(boxes, catalog, rng, pos_sd, com_sd, friction):
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
    return ('<mujoco><option timestep="0.002"/><worldbody><geom type="plane" size="5 5 0.1" '
            f'friction="{friction} 0.005 0.0001"/>{"".join(bodies)}</worldbody></mujoco>')


def simulate_once(boxes, catalog, rng, pos_sd, com_sd, friction):
    """Same physics and same random draws as predict_test.simulate_once, but it stops as soon as a box has
    fallen (a fall never undoes itself) or every box is at rest (nothing more will happen)."""
    model = mujoco.MjModel.from_xml_string(_model_xml(boxes, catalog, rng, pos_sd, com_sd, friction))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    ids = [model.body(f"b{k}").id for k in range(len(boxes))]
    z0 = [float(data.xpos[i][2]) for i in ids]
    steps = int(SIM_SECONDS / model.opt.timestep)

    def fell():
        for k, i in enumerate(ids):
            q = data.xquat[i]
            tilt = np.degrees(2 * np.arccos(min(1.0, abs(float(q[0])))))
            if z0[k] - data.xpos[i][2] > FALL_DROP_M or tilt > FALL_TILT_DEG:
                return True
        return False

    for step in range(1, steps + 1):
        mujoco.mj_step(model, data)
        if step % CHECK_EVERY == 0:
            if fell():
                return True
            if step * model.opt.timestep >= SETTLE_AFTER_S and float(np.max(np.abs(data.qvel))) < REST_SPEED:
                return False
    return fell()

P_GREEN = 0.10           # below: guide the placement
P_RED = 0.50             # above: reject and suggest another position
BASE_SAMPLES = 150
MAX_SAMPLES = 600
SEARCH_STEP_M = 0.01     # alternative search: shift the candidate 1 cm at a time toward the box below
SEARCH_MAX_TRIES = 8
MIN_STATIC_MARGIN_M = 0.02   # skip alternatives whose centre of mass is within 2 cm of an edge (never green in Tes 2)

ACTIONS = {"GREEN": "GUIDE", "YELLOW": "ASK_SUPERVISOR", "RED": "REJECT"}


class Settings:
    def __init__(self, pos_sd_cm=1.0, com_sd_cm=2.0, friction=0.5, seed=0):
        self.pos_sd = pos_sd_cm / 100.0
        self.com_sd = com_sd_cm / 100.0
        self.friction = friction
        self.rng = np.random.default_rng(seed)


def candidate_box(stack, box_id, offset_m, catalog):
    """Next box on top of the stack, shifted offset_m to the right of the current top box."""
    top = stack[-1]
    return {"id": box_id, "x": top["x"] + offset_m, "z": top["z"],
            "y": top["y"] + (catalog[top["id"]]["H"] + catalog[box_id]["H"]) / 2.0}


def overhang_pct(stack, cand, catalog):
    return (cand["x"] - stack[-1]["x"]) / catalog[cand["id"]]["L"] * 100.0


def _ci95(p, n):
    if p in (0.0, 1.0):
        return 3.0 / n                      # rule of three: no events in n trials
    return 1.96 * math.sqrt(p * (1.0 - p) / n)


def p_fall_adaptive(boxes, catalog, s, base=BASE_SAMPLES, max_n=MAX_SAMPLES, trace=None):
    """Monte Carlo P(fall). If the 95% interval still crosses a zone line (10% or 50%), the agent doubles the samples."""
    falls = []
    n = base
    while True:
        falls += [simulate_once(boxes, catalog, s.rng, s.pos_sd, s.com_sd, s.friction) for _ in range(n - len(falls))]
        p = float(np.mean(falls))
        ci = _ci95(p, len(falls))
        near = [t for t in (P_GREEN, P_RED) if abs(p - t) < ci]
        if trace is not None:
            trace.append(f"{len(falls)} simulations: P(fall) = {p:.0%} +- {ci:.0%}")
        if not near or len(falls) >= max_n:
            if near and trace is not None:
                trace.append(f"still close to the {near[0]:.0%} line after {len(falls)} simulations -> taking the safer zone")
            return p, len(falls), ci, bool(near)
        if trace is not None:
            trace.append(f"close to the {near[0]:.0%} line -> more samples")
        n = min(max_n, len(falls) * 2)


def zone_safe(p, ci, near):
    """Zone with a safety bias: if the estimate is still ambiguous at a line, take the riskier zone."""
    return zone(p + ci if near else p)[0]


def search_alternative(stack, box_id, offset_m, catalog, s, trace):
    """Nearest HIJAU position to what the worker asked for, on a 1 cm grid, both directions.

    Positions whose static centre-of-mass margin is under 2 cm are skipped without simulating."""
    half = catalog[box_id]["L"] / 2.0
    grid = [k * SEARCH_STEP_M for k in range(-int(half / SEARCH_STEP_M), int(half / SEARCH_STEP_M) + 1)]
    grid = sorted((g for g in grid if abs(g - offset_m) > 0.005), key=lambda g: (abs(g - offset_m), abs(g)))
    tried = 0
    for off in grid:
        cand = candidate_box(stack, box_id, off, catalog)
        stable, margin = static_check(stack + [cand], catalog)
        if not stable or margin < MIN_STATIC_MARGIN_M:
            continue
        tried += 1
        p, n, ci, near = p_fall_adaptive(stack + [cand], catalog, s, base=60, max_n=300)
        ok = zone_safe(p, ci, near) == "GREEN"
        if ok and n < BASE_SAMPLES:
            # a quick screen said green: confirm with the full sample count before promising it to the worker
            p, n, ci, near = p_fall_adaptive(stack + [cand], catalog, s)
            ok = zone_safe(p, ci, near) == "GREEN"
            if not ok:
                trace.append(f"try {off * 100:+.0f} cm: confirmation with {n} simulations gave P = {p:.0%}, not green")
                tried += 1
                if tried >= SEARCH_MAX_TRIES:
                    break
                continue
        trace.append(f"try {off * 100:+.0f} cm ({overhang_pct(stack, cand, catalog):+.0f}%): P = {p:.0%}"
                     + ("" if ok else (" (not surely green yet)" if p < P_GREEN else "")))
        if ok:
            return {"offset_m": off, "overhang_pct": overhang_pct(stack, cand, catalog), "p": p, "n": n}
        if tried >= SEARCH_MAX_TRIES:
            break
    trace.append("no green position within the search range -> do not place a box on this stack")
    return None


def decide(stack, box_id, offset_m, catalog, s):
    """Full decision for placing box_id at offset_m on top of the stack."""
    trace, seconds = [], {}
    t = time.perf_counter()
    cand = candidate_box(stack, box_id, offset_m, catalog)
    boxes = stack + [cand]
    stable, margin = static_check(boxes, catalog)
    trace.append(f"digital twin: {len(stack)} box(es) + candidate ID {box_id} overhanging "
                 f"{overhang_pct(stack, cand, catalog):+.0f}% ({offset_m * 100:+.1f} cm)")
    trace.append(f"static check: {'stands' if stable else 'falls'} (centre-of-mass margin {margin * 100:+.1f} cm)")
    seconds["twin"], t = time.perf_counter() - t, time.perf_counter()
    stages = {"twin": len(trace)}
    p, n, ci, near = p_fall_adaptive(boxes, catalog, s, trace=trace)
    z = zone_safe(p, ci, near)
    seconds["simulation"], t = time.perf_counter() - t, time.perf_counter()
    stages["simulation"] = len(trace)
    out = {"box_id": box_id, "offset_m": offset_m, "overhang_pct": overhang_pct(stack, cand, catalog),
           "static_stable": bool(stable), "static_margin_m": float(margin), "p": p, "ci": ci, "n": n,
           "zone": z, "action": ACTIONS[z], "alternative": None, "trace": trace}
    if z != "GREEN":
        trace.append("not green -> searching the nearest safe position")
        out["alternative"] = search_alternative(stack, box_id, offset_m, catalog, s, trace)
    seconds["search"] = time.perf_counter() - t
    # where each stage ends in the trace, and how long it took (for the web page's numbered trace)
    out["stages"], out["seconds"] = stages, seconds
    return out


def stack_risk(stack, catalog, s):
    """P(fall) of the stack as it stands now (no candidate). Used after each placement."""
    if len(stack) < 2:
        return 0.0, 0, 0.0, "GREEN"
    p, n, ci, near = p_fall_adaptive(stack, catalog, s)
    return p, n, ci, zone_safe(p, ci, near)


def verify(before, after, planned, catalog, tol_m=0.015, loose=None):
    """Compare the stack after placement with the approved plan.

    before: stack before placement, after: stack seen now (built by contact, bottom first), planned: candidate box
    dict (or None), loose: visible boxes that are not on the stack, each with "where" (floor / beside / gap).
    Returns {"status", "message", "deviation_m"}; status is OK, OFF_PLAN, FELL, NOT_PLACED, or CHANGED.
    A planned box that is off the stack, or not visible at all while the rest is intact, counts as FELL: the check
    runs after the worker has let go of the box."""
    off_stack = {b["id"]: b["where"] for b in (loose or [])}
    place = {"floor": "on the floor next to the stack", "beside": "beside the stack",
             "gap": "above the stack but not resting on it"}

    def where(i):
        return place.get(off_stack.get(i), "not visible (off the stack)")

    ids_before = [b["id"] for b in before]
    ids_after = [b["id"] for b in after]
    lost = [i for i in ids_before if i not in ids_after]
    if lost:
        return {"status": "FELL", "deviation_m": None,
                "message": "; ".join(f"box ID {i} is {where(i)}" for i in lost) + " -> it fell"}
    for b0 in before:
        b1 = next(b for b in after if b["id"] == b0["id"])
        if b0["y"] - b1["y"] > 0.05 or math.hypot(b1["x"] - b0["x"], b1["z"] - b0["z"]) > 0.05:
            return {"status": "FELL", "message": f"box ID {b0['id']} moved or dropped more than 5 cm",
                    "deviation_m": None}
    if planned is None:
        return {"status": "CHANGED" if ids_after != ids_before else "OK", "message": "", "deviation_m": None}
    new = next((b for b in after if b["id"] == planned["id"]), None)
    if new is None:
        if planned["id"] in off_stack:
            return {"status": "FELL", "deviation_m": None,
                    "message": f"box ID {planned['id']} is {where(planned['id'])} -> it fell"}
        return {"status": "FELL", "deviation_m": None,
                "message": f"box ID {planned['id']} is not on the stack and not visible -> it likely fell out of view"}
    if after[-1]["id"] != planned["id"]:
        return {"status": "OFF_PLAN", "message": f"box ID {planned['id']} is not on top of the stack",
                "deviation_m": None}
    dev = new["x"] - planned["x"]
    if abs(dev) > tol_m:
        return {"status": "OFF_PLAN", "deviation_m": dev,
                "message": f"box ID {planned['id']} was placed {dev * 100:+.1f} cm from the plan -> risk recomputed"}
    return {"status": "OK", "deviation_m": dev, "message": f"as planned ({dev * 100:+.1f} cm)"}
