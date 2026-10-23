"""Evaluation mode (agent.py --eval-plan) with a fake camera, then tools/eval_report.py on its log.

    python -m pytest tests/test_eval.py -q
"""
import csv
import json
import os
import sys

import pytest

import eval_report
import synth_scene as S
from test_agent_flow import NOTHING, SPACE, Y, events, run_agent, scene_base

H = [S.CATALOG[i]["H"] for i in range(3)]

PLAN = {"trials": [
    {"trial_id": "E1", "stack": [{"id": 0}], "box_id": 1, "shift_cm": 6, "expected_zone": "GREEN", "expected_p": 0.0},
    {"trial_id": "E2", "stack": [{"id": 0}, {"id": 1, "shift_cm": 0}], "box_id": 2, "shift_cm": 13,
     "expected_zone": "YELLOW", "expected_p": 0.27},
    {"trial_id": "E3", "stack": [{"id": 0}], "box_id": 1, "shift_cm": 16, "expected_zone": "RED", "expected_p": 0.73},
]}


def scenes():
    one_at = lambda x: scene_base() + [S.upright(1, x, y=Y[1])]             # noqa: E731
    fallen_1 = S.upright(1, 0.38, y=S.FLOOR_Y + H[1] / 2, z_front=-0.05)
    fallen_1["R"] = S.rot_y(20)
    return {"E1_PLACED": lambda: one_at(0.06),
            "E2_SETUP": lambda: one_at(0.0),
            "E2_PLACED": lambda: one_at(0.0) + [S.upright(2, 0.13, y=Y[2])],
            "E3_SETUP": scene_base,
            "E3_FELL": lambda: scene_base() + [fallen_1]}


KEYS = ([SPACE, NOTHING, "E1_PLACED", SPACE]          # E1: GREEN decision, placed, check, confirm
        + [SPACE]                                     # E2 before the setup: ID 1 still at +6 cm -> refused
        + ["E2_SETUP", SPACE, NOTHING, "E2_PLACED", SPACE]   # E2: YELLOW, evaluation override, stood
        + ["E3_SETUP", SPACE, NOTHING, "E3_FELL", SPACE]     # E3: RED, evaluation override, fell
        + [SPACE])                                    # after the last trial: nothing more to do


@pytest.mark.parametrize("use_aws", [False, True], ids=["laptop", "aws"])
def test_eval_mode_and_report(tmp_path, monkeypatch, capsys, use_aws):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(PLAN), encoding="utf-8")
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws, KEYS, scenes(), ["", "", ""],
                         extra_argv=["--eval-plan", str(plan_path), "--supervisor", "Tester"])
    start = events(log, "eval_start")[0]
    assert start["n_trials"] == 3 and len(start["plan_sha256"]) == 64
    results = events(log, "eval_result")
    assert [r["trial_id"] for r in results] == ["E1", "E2", "E3"]
    assert [r["zone"] for r in results] == ["GREEN", "YELLOW", "RED"]
    assert [r["fell"] for r in results] == [False, False, True]
    assert [r["check_status"] for r in results] == ["OK", "OK", "FELL"]
    assert results[1]["setup_shift_cm"] == pytest.approx([0.0], abs=0.6)
    # every decision is at the planned shift, YELLOW / RED as labelled evaluation overrides
    assert [round(e["offset_m"] * 100) for e in events(log, "decision")] == [6, 13, 16]
    overrides = events(log, "override")
    assert [(o["trial_id"], o["reason"], o["supervisor"], o["eval"]) for o in overrides] == \
           [("E2", "evaluation", "Tester", True), ("E3", "evaluation", "Tester", True)]
    # every event of a trial carries its trial_id; the refused SPACE is logged for E2
    wrong = events(log, "eval_wrong_stack")
    assert len(wrong) == 1 and wrong[0]["trial_id"] == "E2" and "must be at +0 cm" in wrong[0]["why"]
    assert all(e.get("trial_id") for e in log if e["event"] in ("decision", "check", "override"))
    assert "every trial is done" in out and log[-1]["stats"]["override"] == 2

    # report from this log
    report_dir = tmp_path / "report"
    monkeypatch.setattr(sys, "argv", ["eval_report.py", "--logs", str(tmp_path / "agent_*" / "log.jsonl"),
                                      "--plan", str(plan_path), "--out", str(report_dir)])
    s = eval_report.main()
    rows = list(csv.DictReader(open(report_dir / "trials.csv", encoding="utf-8")))
    assert [r["trial_id"] for r in rows] == ["E1", "E2", "E3"] and rows[2]["fell"] == "True"
    ps = [r["p"] for r in results]
    fells = [r["fell"] for r in results]
    assert s["n"] == 3 and s["green_falls"] == 0 and s["falls"] == 1
    assert s["accuracy"] == pytest.approx(sum((p >= 0.5) == f for p, f in zip(ps, fells)) / 3)
    assert s["brier"] == pytest.approx(sum((p - f) ** 2 for p, f in zip(ps, fells)) / 3)
    assert not s["passed"]                        # only 3 trials: the "at least 20 trials" criterion fails
    summary = (report_dir / "summary.md").read_text(encoding="utf-8")
    assert "Pass criteria" in summary and "Calibration" in summary and "Tester" not in summary


def test_summary_metrics_and_criteria():
    rows = [dict(trial_id=f"T{k:02d}", p=p, zone=z, fell=f, fell_auto=f, corrected=False, deviation_cm=d,
                 source="aws", aws_seconds=9.0, retakes=0, fp_question=0, wrong_stack=0, runs=1)
            for k, (p, z, f, d) in enumerate([(0.02, "GREEN", False, 0.4), (0.08, "GREEN", True, None),
                                              (0.30, "YELLOW", False, 1.2), (0.70, "RED", True, None),
                                              (0.90, "RED", False, 0.1)], start=1)]
    rows[4]["corrected"] = True
    plan = [{"trial_id": f"T{k:02d}"} for k in range(1, 7)]
    s = eval_report.summarise(rows, plan)
    assert s["n"] == 5 and s["missing"] == ["T06"]
    assert s["green_falls"] == 1 and s["accuracy"] == pytest.approx(3 / 5)
    assert s["brier"] == pytest.approx((0.02 ** 2 + 0.92 ** 2 + 0.3 ** 2 + 0.3 ** 2 + 0.9 ** 2) / 5)
    # clear trials: P 0.02, 0.08, 0.90 (0.70 is not > 70%) -> predictions stood, stood, fell; outcomes F, T, F -> 1/3
    assert s["clear"]["n"] == 3 and s["clear"]["accuracy"] == pytest.approx(1 / 3)
    # falls: sum of P 2.0, sd sqrt(0.6032) = 0.777 -> 90% interval 0.72..3.28 -> 1..3 falls; 2 observed
    assert (s["expected_falls"]["low"], s["expected_falls"]["high"]) == (1, 3) and s["falls"] == 2
    assert [c[0].split()[0] for c in s["criteria"]] == ["C1", "C2a", "C2b", "C3", "C4"]
    assert [c[3] for c in s["criteria"]] == [False, False, True, False, False] and not s["passed"]
    assert s["failure_cases"]["falls in GREEN"] == ["T02"]
    assert s["failure_cases"]["wrong prediction"] == ["T02", "T05"]
    assert s["failure_cases"]["outcome corrected by the worker"] == ["T05"]
    assert s["placement"]["max"] == pytest.approx(1.2) and s["placement"]["within_1cm"] == 2
    assert [b["n"] for b in s["bins"]] == [2, 0, 1, 0, 1, 1]      # 0.70 belongs to 70-90%


def test_summary_rebuilds_from_published_trials(tmp_path, monkeypatch, capsys):
    """--trials rebuilds the published summary.md from the published trials.csv (the logs are not in the repo)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report = os.path.join(root, "data", "eval_report")
    monkeypatch.setattr(sys, "argv", ["eval_report.py", "--trials", os.path.join(report, "trials.csv"),
                                      "--out", str(tmp_path)])
    eval_report.main()
    capsys.readouterr()
    with open(os.path.join(report, "summary.md"), encoding="utf-8") as f:
        published = f.read().splitlines()
    rebuilt = (tmp_path / "summary.md").read_text(encoding="utf-8").splitlines()
    assert published[2].startswith("Logs: ") and rebuilt[2].startswith("Trials: ")    # only the source line differs
    assert rebuilt[:2] + rebuilt[3:] == published[:2] + published[3:]
