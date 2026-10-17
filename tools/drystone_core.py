"""Drystone decision core: stack + candidate placement -> zone, action, alternative.

No camera and no GUI here, so the same code runs on the laptop and on AWS.
Safety decisions are deterministic rules on top of a Monte Carlo physics estimate; no LLM decides anything.

Coordinates (metres), all in the frame of the base box marker:
x = right along the front face, y = up, z = toward the camera. A box is a dict {"id", "x", "y", "z"},
where (x, z) is the box centre in plan view and y is the height of its marker centre.
"""
import math

import numpy as np

from predict_test import simulate_once, static_check, zone

P_GREEN = 0.10           # below: guide the placement
P_RED = 0.50             # above: reject and suggest another position
BASE_SAMPLES = 150
MAX_SAMPLES = 600
SEARCH_STEP_M = 0.01     # alternative search: shift the candidate 1 cm at a time toward the box below
SEARCH_MAX_TRIES = 8
MIN_STATIC_MARGIN_M = 0.02   # skip alternatives whose centre of mass is within 2 cm of an edge (never green in Tes 2)

ACTIONS = {"HIJAU": "PANDU", "KUNING": "MINTA_PERSETUJUAN", "MERAH": "TOLAK"}


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
            trace.append(f"simulasi {len(falls)}x: P(roboh) = {p:.0%} +- {ci:.0%}")
        if not near or len(falls) >= max_n:
            if near and trace is not None:
                trace.append(f"masih dekat garis {near[0]:.0%} setelah {len(falls)} simulasi -> zona dipilih yang lebih aman")
            return p, len(falls), ci, bool(near)
        if trace is not None:
            trace.append(f"dekat garis {near[0]:.0%} -> tambah sampel")
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
        p, n, ci, near = p_fall_adaptive(stack + [cand], catalog, s, base=100, max_n=300)
        ok = zone_safe(p, ci, near) == "HIJAU"
        trace.append(f"coba {off * 100:+.0f} cm ({overhang_pct(stack, cand, catalog):+.0f}%): P = {p:.0%}"
                     + ("" if ok else (" (belum pasti hijau)" if p < P_GREEN else "")))
        if ok:
            return {"offset_m": off, "overhang_pct": overhang_pct(stack, cand, catalog), "p": p, "n": n}
        if tried >= SEARCH_MAX_TRIES:
            break
    trace.append("tidak ada posisi hijau dalam jangkauan pencarian -> jangan taruh kardus di tumpukan ini")
    return None


def decide(stack, box_id, offset_m, catalog, s):
    """Full decision for placing box_id at offset_m on top of the stack."""
    trace = []
    cand = candidate_box(stack, box_id, offset_m, catalog)
    boxes = stack + [cand]
    stable, margin = static_check(boxes, catalog)
    trace.append(f"kembaran digital: {len(stack)} kardus + calon ID {box_id} menjorok "
                 f"{overhang_pct(stack, cand, catalog):+.0f}% ({offset_m * 100:+.1f} cm)")
    trace.append(f"cek statis: {'berdiri' if stable else 'roboh'} (margin pusat massa {margin * 100:+.1f} cm)")
    p, n, ci, near = p_fall_adaptive(boxes, catalog, s, trace=trace)
    z = zone_safe(p, ci, near)
    out = {"box_id": box_id, "offset_m": offset_m, "overhang_pct": overhang_pct(stack, cand, catalog),
           "static_stable": bool(stable), "static_margin_m": float(margin), "p": p, "ci": ci, "n": n,
           "zone": z, "action": ACTIONS[z], "alternative": None, "trace": trace}
    if z != "HIJAU":
        trace.append("bukan hijau -> cari posisi aman terdekat")
        out["alternative"] = search_alternative(stack, box_id, offset_m, catalog, s, trace)
    return out


def stack_risk(stack, catalog, s):
    """P(fall) of the stack as it stands now (no candidate). Used after each placement."""
    if len(stack) < 2:
        return 0.0, 0, 0.0, "HIJAU"
    p, n, ci, near = p_fall_adaptive(stack, catalog, s)
    return p, n, ci, zone_safe(p, ci, near)


def verify(before, after, planned, catalog, tol_m=0.015):
    """Compare the stack after placement with the approved plan.

    before: stack before placement, after: stack seen now, planned: candidate box dict (or None).
    Returns {"status", "message", "deviation_m"}; status is OK, MELESET, ROBOH, BELUM, or BERUBAH."""
    ids_before = [b["id"] for b in before]
    ids_after = [b["id"] for b in after]
    lost = [i for i in ids_before if i not in ids_after]
    if lost:
        return {"status": "ROBOH", "message": f"kardus ID {lost} hilang dari tumpukan -> kemungkinan roboh",
                "deviation_m": None}
    for b0 in before:
        b1 = next(b for b in after if b["id"] == b0["id"])
        if b0["y"] - b1["y"] > 0.05 or math.hypot(b1["x"] - b0["x"], b1["z"] - b0["z"]) > 0.05:
            return {"status": "ROBOH", "message": f"kardus ID {b0['id']} bergeser/jatuh lebih dari 5 cm",
                    "deviation_m": None}
    if planned is None:
        return {"status": "BERUBAH" if ids_after != ids_before else "OK", "message": "", "deviation_m": None}
    new = next((b for b in after if b["id"] == planned["id"]), None)
    if new is None:
        return {"status": "BELUM", "message": f"kardus ID {planned['id']} belum terlihat", "deviation_m": None}
    if after[-1]["id"] != planned["id"]:
        return {"status": "MELESET", "message": f"kardus ID {planned['id']} tidak berada di paling atas",
                "deviation_m": None}
    dev = new["x"] - planned["x"]
    if abs(dev) > tol_m:
        return {"status": "MELESET", "deviation_m": dev,
                "message": f"kardus ID {planned['id']} ditaruh {dev * 100:+.1f} cm dari rencana -> dihitung ulang"}
    return {"status": "OK", "deviation_m": dev, "message": f"sesuai rencana ({dev * 100:+.1f} cm)"}
