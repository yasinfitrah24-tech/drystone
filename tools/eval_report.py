r"""Evaluation report: agent logs from --eval-plan runs -> per-trial CSV + summary (metrics, calibration table,
pass criteria, failure-case candidates). See docs/EVAL_PROTOCOL.md.

    python tools/eval_report.py --logs "data/agent_*/log.jsonl"
    python tools/eval_report.py --logs data/agent_20261021_190000/log.jsonl data/agent_20261022_100000/log.jsonl
Writes data/eval_report/trials.csv and data/eval_report/summary.md (no photos, no names).
If a trial was run more than once (e.g. after a restart), its last result counts; earlier ones are listed.

Without the logs (they stay on our laptop), rebuild the summary from the published per-trial table:
    python tools/eval_report.py --trials data/eval_report/trials.csv
Writes data/eval_report/from_trials/summary.md and leaves the published files as they are.
"""
import argparse
import csv
import glob
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
# pass criteria, fixed in docs/EVAL_PROTOCOL.md before any data is taken
MAX_GREEN_FALLS = 0
CLEAR_LOW, CLEAR_HIGH = 0.10, 0.70     # clear trials: P < 10% or P > 70%
MIN_CLEAR_ACCURACY = 0.85
Z90 = 1.645                            # 90% interval of the number of falls
MAX_BRIER = 0.20
MIN_TRIALS = 20
FIELDS = ["trial_id", "n_boxes", "box_id", "shift_cm", "setup_shift_cm", "expected_zone", "expected_p", "p", "ci", "n",
          "zone", "action", "predicted_fall", "check_status", "fell_auto", "fell", "corrected", "deviation_cm",
          "source", "aws_seconds", "retakes", "fp_question", "wrong_stack", "runs"]


def read_logs(paths):
    events = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(dict(json.loads(line), _log=path))
    return events


def trial_rows(events):
    rows, counts = {}, {}
    for e in events:
        tid = e.get("trial_id")
        if not tid:
            continue
        c = counts.setdefault(tid, {"retakes": 0, "fp_question": 0, "wrong_stack": 0, "runs": 0})
        if e["event"] == "retake":
            c["retakes"] += 1
        elif e["event"] == "eval_wrong_stack":
            c["wrong_stack"] += 1
        elif e["event"] == "check" and e.get("worker_answer") is not None:
            c["fp_question"] += 1
        elif e["event"] == "eval_result":
            c["runs"] += 1
            rows[tid] = e
    out = []
    for tid in sorted(rows):
        e = rows[tid]
        r = {k: e.get(k) for k in FIELDS if k in e}
        r.update(trial_id=tid, predicted_fall=e["p"] is not None and e["p"] >= 0.5, **counts[tid])
        if isinstance(r.get("setup_shift_cm"), list):
            r["setup_shift_cm"] = " ".join(f"{v:+.1f}" for v in r["setup_shift_cm"])
        out.append(r)
    return out


INTS = ("n_boxes", "box_id", "n", "retakes", "fp_question", "wrong_stack", "runs")
FLOATS = ("shift_cm", "expected_p", "p", "ci", "deviation_cm", "aws_seconds")
BOOLS = ("predicted_fall", "fell_auto", "fell", "corrected")


def read_trials(path):
    """trials.csv (as written below) -> the same rows trial_rows() gives, with numbers and True/False back."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k, v in r.items():
                if v == "":
                    r[k] = None
                elif k in INTS:
                    r[k] = int(v)
                elif k in FLOATS:
                    r[k] = float(v)
                elif k in BOOLS:
                    r[k] = v == "True"
            rows.append(r)
    return rows


def summarise(rows, plan_trials):
    done = [r for r in rows if r.get("p") is not None and r.get("fell") is not None]
    n = len(done)
    s = {"n": n, "planned": len(plan_trials),
         "missing": [t["trial_id"] for t in plan_trials if t["trial_id"] not in {r["trial_id"] for r in rows}]}
    if not n:
        return s
    s["accuracy"] = sum((r["p"] >= 0.5) == r["fell"] for r in done) / n      # reported, not a criterion
    clear = [r for r in done if r["p"] < CLEAR_LOW or r["p"] > CLEAR_HIGH]
    s["clear"] = {"n": len(clear),
                  "accuracy": sum((r["p"] >= 0.5) == r["fell"] for r in clear) / len(clear) if clear else None}
    mu = sum(r["p"] for r in done)
    sd = math.sqrt(sum(r["p"] * (1 - r["p"]) for r in done))
    lo, hi = max(0, math.ceil(mu - Z90 * sd)), math.floor(mu + Z90 * sd)
    s["expected_falls"] = {"sum_p": mu, "sd": sd, "low": lo, "high": hi}
    s["brier"] = sum((r["p"] - (1.0 if r["fell"] else 0.0)) ** 2 for r in done) / n
    s["falls"] = sum(r["fell"] for r in done)
    s["zones"] = {}
    for z in ("GREEN", "YELLOW", "RED"):
        rz = [r for r in done if r["zone"] == z]
        s["zones"][z] = {"n": len(rz), "falls": sum(r["fell"] for r in rz),
                         "mean_p": statistics.mean(r["p"] for r in rz) if rz else None}
    s["green_falls"] = s["zones"]["GREEN"]["falls"]
    s["bins"] = []
    for lo, hi in BINS:
        rb = [r for r in done if lo <= r["p"] < hi]
        s["bins"].append({"range": f"{lo:.0%}-{min(hi, 1.0):.0%}", "n": len(rb),
                          "mean_p": statistics.mean(r["p"] for r in rb) if rb else None,
                          "observed": sum(r["fell"] for r in rb) / len(rb) if rb else None})
    devs = [abs(r["deviation_cm"]) for r in done if r.get("deviation_cm") is not None]
    s["placement"] = {"n": len(devs), "mean": statistics.mean(devs) if devs else None,
                      "median": statistics.median(devs) if devs else None, "max": max(devs) if devs else None,
                      "within_1cm": sum(d <= 1.0 for d in devs)}
    aws = [r["aws_seconds"] for r in done if r.get("source") == "aws" and r.get("aws_seconds") is not None]
    s["lambda"] = {"n": len(aws), "median": statistics.median(aws) if aws else None, "max": max(aws) if aws else None}
    s["fallbacks"] = sum(1 for r in done if r.get("source") and r["source"] != "aws" and "fallback" in r["source"])
    s["retakes"] = sum(r["retakes"] for r in rows)
    s["fp_questions"] = sum(r["fp_question"] for r in rows)
    s["corrected"] = sum(1 for r in done if r.get("corrected"))
    ef = s["expected_falls"]               # (lo / hi are reused by the calibration bins above)
    s["criteria"] = [("C1 falls in the GREEN zone", f"{s['green_falls']}", f"<= {MAX_GREEN_FALLS}",
                      s["green_falls"] <= MAX_GREEN_FALLS),
                     ("C2a accuracy on clear trials (P < 10% or > 70%)",
                      f"{pct(s['clear']['accuracy'])} of {s['clear']['n']}", f">= {MIN_CLEAR_ACCURACY:.0%}",
                      s["clear"]["accuracy"] is not None and s["clear"]["accuracy"] >= MIN_CLEAR_ACCURACY),
                     ("C2b falls inside the 90% interval of the predicted number", f"{s['falls']} falls",
                      f"{ef['low']}-{ef['high']} (sum of P {ef['sum_p']:.1f})", ef["low"] <= s["falls"] <= ef["high"]),
                     ("C3 Brier score", f"{s['brier']:.3f}", f"<= {MAX_BRIER}", s["brier"] <= MAX_BRIER),
                     ("C4 trials with an outcome", f"{n}", f">= {MIN_TRIALS}", n >= MIN_TRIALS)]
    s["passed"] = all(c[3] for c in s["criteria"])
    wrong = [r for r in done if (r["p"] >= 0.5) != r["fell"]]
    s["failure_cases"] = {
        "falls in GREEN": [r["trial_id"] for r in done if r["zone"] == "GREEN" and r["fell"]],
        "wrong prediction": [r["trial_id"] for r in wrong],
        "largest |P - outcome|": [r["trial_id"] for r in sorted(done, key=lambda r: -abs(r["p"] - r["fell"]))[:3]],
        "outcome corrected by the worker": [r["trial_id"] for r in done if r.get("corrected")],
        "placed > 1.5 cm off": [r["trial_id"] for r in done if r.get("deviation_cm") is not None
                                and abs(r["deviation_cm"]) > 1.5],
        "laptop fallback": [r["trial_id"] for r in done if r.get("source") and "fallback" in r["source"]],
        "retake or f/p question": [r["trial_id"] for r in rows if r["retakes"] or r["fp_question"]],
    }
    return s


def pct(v):
    return "-" if v is None else f"{v:.0%}"


def _rel(path):
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:                          # another drive (Windows)
        return path


def write_summary(path, s, logs, label="Logs"):
    L = ["# Evaluation report", "", f"{label}: {', '.join(_rel(p) for p in logs)}", "",
         f"Trials with an outcome: **{s['n']} of {s['planned']} planned**"
         + (f" (missing: {', '.join(s['missing'])})" if s["missing"] else ""), ""]
    if not s["n"]:
        L.append("No completed trial yet.")
    else:
        L += ["## Pass criteria (fixed before the data)", "", "| Criterion | Result | Target | |", "|---|---|---|---|"]
        L += [f"| {name} | {val} | {target} | {'PASS' if ok else 'FAIL'} |" for name, val, target, ok in s["criteria"]]
        L += ["", f"**Overall: {'PASS' if s['passed'] else 'FAIL'}**", "", "## Metrics", "",
              f"- Overall accuracy (P >= 50% predicts a fall; not a criterion, Test 2 had 82%): {s['accuracy']:.0%} "
              f"({s['n']} trials); Brier score: {s['brier']:.3f}",
              f"- Falls: {s['falls']} observed, {s['expected_falls']['sum_p']:.1f} predicted (sum of P), 90% interval "
              f"{s['expected_falls']['low']}-{s['expected_falls']['high']}",
              f"- Clear trials (P < 10% or > 70%): {s['clear']['n']}, accuracy {pct(s['clear']['accuracy'])}",
              "", "| Zone | Trials | Falls | Fall rate | Mean P(fall) |", "|---|---|---|---|---|"]
        for z, v in s["zones"].items():
            L.append(f"| {z} | {v['n']} | {v['falls']} | {pct(v['falls'] / v['n'] if v['n'] else None)} | "
                     f"{pct(v['mean_p'])} |")
        L += ["", "### Calibration", "", "| P(fall) range | Trials | Mean predicted | Observed fall rate |",
              "|---|---|---|---|"]
        L += [f"| {b['range']} | {b['n']} | {pct(b['mean_p'])} | {pct(b['observed'])} |" for b in s["bins"]]
        pl, la = s["placement"], s["lambda"]
        L += ["", "### Operations", ""]
        if pl["n"]:
            L.append(f"- Placement error (boxes that stood, |check deviation|): mean {pl['mean']:.1f} cm, median "
                     f"{pl['median']:.1f} cm, max {pl['max']:.1f} cm; {pl['within_1cm']}/{pl['n']} within 1 cm")
        if la["n"]:
            L.append(f"- Decision time on AWS Lambda (round trip): median {la['median']:.1f} s, max {la['max']:.1f} s "
                     f"({la['n']} decisions)")
        L += [f"- Retakes: {s['retakes']}; f/p questions: {s['fp_questions']}; laptop fallbacks: {s['fallbacks']}; "
              f"outcomes corrected by the worker: {s['corrected']}", "", "## Failure-case candidates", ""]
        L += [f"- {k}: {', '.join(v) if v else 'none'}" for k, v in s["failure_cases"].items()]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Evaluation report from --eval-plan agent logs")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--logs", nargs="+", help="log.jsonl files or patterns")
    src.add_argument("--trials", help="a trials.csv written by this tool (rebuilds summary.md only)")
    ap.add_argument("--plan", default=os.path.join(ROOT, "config", "eval_plan.json"))
    ap.add_argument("--out", default=None,
                    help="default data/eval_report (with --logs) or data/eval_report/from_trials (with --trials)")
    args = ap.parse_args()
    with open(args.plan, encoding="utf-8") as f:
        plan_trials = json.load(f)["trials"]
    if args.trials:
        out = args.out or os.path.join(ROOT, "data", "eval_report", "from_trials")
        s = summarise(read_trials(args.trials), plan_trials)
        os.makedirs(out, exist_ok=True)
        write_summary(os.path.join(out, "summary.md"), s, [args.trials], label="Trials")
        print(open(os.path.join(out, "summary.md"), encoding="utf-8").read())
        print(f"Saved in {out} (summary.md)")
        return s
    args.out = args.out or os.path.join(ROOT, "data", "eval_report")
    logs = sorted({p for pattern in args.logs for p in glob.glob(pattern)})
    events = read_logs(logs)
    logs = sorted({e["_log"] for e in events if e.get("event") == "eval_start"}) or logs
    events = [e for e in events if e["_log"] in logs]
    rows = trial_rows(events)
    s = summarise(rows, plan_trials)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "trials.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    write_summary(os.path.join(args.out, "summary.md"), s, logs)
    print(open(os.path.join(args.out, "summary.md"), encoding="utf-8").read())
    print(f"Saved in {args.out} (trials.csv, summary.md)")
    return s


if __name__ == "__main__":
    main()
