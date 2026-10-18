r"""POST-HOC ANALYSIS, NOT USED BY THE SYSTEM. Nothing here changes a setting, a decision or a deployment.

After the locked evaluation (docs/EVAL_PROTOCOL.md) failed criterion C2b, this script recomputes P(fall) on the 25
stacks recorded in the evaluation log with other simulation settings (position and load-centre uncertainty,
friction) and scores each setting against the real outcomes. It reproduces the post-hoc table in docs/REPORT.md
section 6.4. With 25 trials, picking a setting from this table would overfit; the table is for follow-up work only.

    python tools/posthoc_sim_settings.py --log data/agent_20261018_152640/log.jsonl
    python tools/posthoc_sim_settings.py --log ... --margins      (static margin vs outcome, no simulation)
Runs on the laptop, about 7 minutes for the full table.
"""
import argparse
import json
import math
import os
import re
import time

import common
import drystone_core as core
from predict_test import load_catalog

GRID = [(1.0, 2.0, 0.5), (1.0, 3.0, 0.5), (1.0, 4.0, 0.5), (1.5, 2.0, 0.5), (2.0, 2.0, 0.5),
        (1.0, 2.0, 0.3), (1.0, 2.0, 0.8), (1.5, 3.0, 0.5), (2.0, 3.0, 0.5)]    # first row = the locked settings


def load_trials(path):
    with open(path, encoding="utf-8") as f:
        ev = [json.loads(line) for line in f if line.strip()]
    res = {e["trial_id"]: e for e in ev if e["event"] == "eval_result"}
    trials = []
    for d in (e for e in ev if e["event"] == "decision" and e.get("eval")):
        if d["trial_id"] not in res:
            continue
        stack = [{"id": b["id"], "x": b["x_cm"] / 100, "y": b["y_cm"] / 100, "z": b["z_cm"] / 100} for b in d["stack_cm"]]
        m = re.search(r"centre-of-mass margin ([+-][0-9.]+) cm", " ".join(d["trace"]))
        trials.append({"tid": d["trial_id"], "stack": stack, "box": d["box_id"], "off": d["offset_m"],
                       "p_log": d["p"], "zone": d["zone"], "fell": 1.0 if res[d["trial_id"]]["fell"] else 0.0,
                       "margin": float(m.group(1)) if m else None})
    return trials


def score(trials, catalog, pos, com, fric):
    ps = []
    for t in trials:
        c = core.candidate_box(t["stack"], t["box"], t["off"], catalog)
        p, _, _, _ = core.p_fall_adaptive(t["stack"] + [c], catalog, core.Settings(pos, com, fric, seed=0))
        ps.append(p)
    f = [t["fell"] for t in trials]
    brier = sum((a - b) ** 2 for a, b in zip(ps, f)) / len(f)
    ll = sum(math.log(max(1e-3, a) if b else max(1e-3, 1 - a)) for a, b in zip(ps, f))
    mu, sd = sum(ps), math.sqrt(sum(a * (1 - a) for a in ps))
    green_falls = sum(1 for a, b in zip(ps, f) if a < core.P_GREEN and b)
    return brier, ll, mu, sd, green_falls, ps


def main():
    ap = argparse.ArgumentParser(description="Post-hoc simulation settings check (not used by the system)")
    ap.add_argument("--log", default=os.path.join(common.DATA_DIR, "agent_20261018_152640", "log.jsonl"))
    ap.add_argument("--margins", action="store_true", help="only list static margin vs outcome")
    args = ap.parse_args()
    catalog = load_catalog(os.path.join(common.ROOT, "config", "boxes.json"))
    trials = load_trials(args.log)
    print(f"POST-HOC, not used by the system. {len(trials)} logged evaluation stacks, "
          f"{int(sum(t['fell'] for t in trials))} falls.")
    if args.margins:
        for t in sorted(trials, key=lambda t: t["margin"]):
            print(f"{t['tid']} margin {t['margin']:+.1f} cm  P {t['p_log']:.3f} {t['zone']:6s} "
                  f"{'FELL' if t['fell'] else 'stood'}")
        return
    print("pos_sd com_sd friction | Brier  logL   sum P (90% interval)      green<10% falls | seconds")
    for pos, com, fric in GRID:
        t0 = time.time()
        b, ll, mu, sd, gf, ps = score(trials, catalog, pos, com, fric)
        print(f"{pos:4.1f} {com:6.1f} {fric:6.1f}     | {b:.3f} {ll:6.2f}  {mu:5.2f} ({mu - 1.645 * sd:5.2f}-"
              f"{mu + 1.645 * sd:5.2f})   {gf}              | {time.time() - t0:.0f}", flush=True)
        if (pos, com, fric) == GRID[0]:
            diff = max(abs(a - t["p_log"]) for a, t in zip(ps, trials))
            print(f"   (locked settings recomputed from the logged stacks: max |P - logged P| = {diff:.3f})", flush=True)


if __name__ == "__main__":
    main()
