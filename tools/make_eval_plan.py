r"""Fixed trial list for the evaluation on new trials (docs/EVAL_PROTOCOL.md), written BEFORE any data is taken.

Each trial: the stack to build first (box ID 0, optionally box ID 1 at a set shift), the box to decide on and its
shift (cm, relative to the box directly below). The expected zone and P(fall) are computed here with the locked
settings on ideal positions; the real decision is made from the camera reading during the trial. The order is
shuffled with a fixed seed so it can be reproduced.

    python tools/make_eval_plan.py                      -> config/eval_plan.json
"""
import argparse
import hashlib
import json
import os
import random

import common
import drystone_core as core
from predict_test import load_catalog

SEED = 20261021
# (stack shifts after ID 0, candidate shift); comments: expected zone on ideal positions
TRIALS = [
    # 2 boxes: ID 0 + candidate ID 1
    ([], +6),     # GREEN
    ([], -10),    # GREEN
    ([], +11),    # GREEN, near the 10% line
    ([], +12),    # YELLOW, near the 10% line
    ([], -13),    # YELLOW
    ([], +14),    # YELLOW
    ([], -14),    # YELLOW, near the 50% line
    ([], +15),    # RED
    ([], -16),    # RED
    ([], +18),    # RED
    # 3 boxes: ID 0 + ID 1 at a set shift + candidate ID 2
    ([0], +8),    # GREEN
    ([0], +10),   # GREEN
    ([5], -6),    # GREEN (back over the middle)
    ([5], +11),   # GREEN, near the 10% line
    ([-5], -10),  # GREEN
    ([0], -12),   # YELLOW
    ([0], +13),   # YELLOW
    ([5], +14),   # YELLOW, near the 50% line
    ([-5], -11),  # YELLOW, at the 10% line
    ([-5], +12),  # YELLOW
    ([0], +15),   # RED, near the 50% line
    ([0], -17),   # RED
    ([5], +16),   # RED
    ([-5], -15),  # RED
    ([5], +18),   # RED
]


def ideal_stack(shifts, catalog):
    boxes, x, y = [{"id": 0, "x": 0.0, "y": 0.0, "z": -catalog[0]["D"] / 2}], 0.0, 0.0
    for k, sh in enumerate(shifts, start=1):
        x += sh / 100
        y += (catalog[k - 1]["H"] + catalog[k]["H"]) / 2
        boxes.append({"id": k, "x": x, "y": y, "z": -catalog[k]["D"] / 2})
    return boxes


def build(catalog):
    trials = []
    for shifts, cand in TRIALS:
        st = ideal_stack(shifts, catalog)
        box_id = len(st)
        c = core.candidate_box(st, box_id, cand / 100, catalog)
        p, n, ci, near = core.p_fall_adaptive(st + [c], catalog, core.Settings(seed=0))
        trials.append({"stack": [{"id": 0}] + [{"id": k, "shift_cm": sh} for k, sh in enumerate(shifts, start=1)],
                       "box_id": box_id, "shift_cm": cand, "expected_zone": core.zone_safe(p, ci, near),
                       "expected_p": round(p, 3)})
    random.Random(SEED).shuffle(trials)
    for k, t in enumerate(trials, start=1):
        t["trial_id"] = f"T{k:02d}"
    return trials


def main():
    ap = argparse.ArgumentParser(description="Write the fixed evaluation trial list")
    ap.add_argument("--out", default=os.path.join(common.ROOT, "config", "eval_plan.json"))
    args = ap.parse_args()
    catalog = load_catalog(os.path.join(common.ROOT, "config", "boxes.json"))
    trials = build(catalog)
    plan = {"protocol": "docs/EVAL_PROTOCOL.md", "seed": SEED,
            "settings": {"pos_sd_cm": 1.0, "com_sd_cm": 2.0, "friction": 0.5, "p_green": core.P_GREEN,
                         "p_red": core.P_RED, "suggestion_margin_cm": 1},
            "trials": trials}
    text = json.dumps(plan, indent=1) + "\n"
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    zones = {z: sum(t["expected_zone"] == z for t in trials) for z in ("GREEN", "YELLOW", "RED")}
    print(f"{args.out}: {len(trials)} trials {zones}, sha256 {hashlib.sha256(text.encode()).hexdigest()[:12]}")
    for t in trials:
        base = " + ".join(f"ID {b['id']}" + (f" at {b['shift_cm']:+d} cm" if "shift_cm" in b else "") for b in t["stack"])
        print(f"  {t['trial_id']}: {base}; ID {t['box_id']} at {t['shift_cm']:+d} cm -> {t['expected_zone']} {t['expected_p']:.0%}")


if __name__ == "__main__":
    main()
