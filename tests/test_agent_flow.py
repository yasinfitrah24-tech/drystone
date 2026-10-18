"""Whole agent loop with a fake camera, once on the laptop and once through the Lambda handler (--aws):
- a fall: ID 1 GREEN -> ID 2 RED -> override -> falls -> FELL -> picked up -> ID 2 planned again -> suggestion -> OK
- SPACE before the box is placed: "not visible" -> worker answers p -> look again -> OK (no false FELL)
- a standing box taken off the stack: "stack changed: ID 1 is missing" -> ID 1 is planned again, not ID 2

    python -m pytest tests/test_agent_flow.py -q
"""
import base64
import builtins
import json
import os
import sys

import cv2
import pytest

import agent
import common
import service
import synth_scene as S

H = [S.CATALOG[i]["H"] for i in range(3)]
Y = [0.0, S.FLOOR_Y + H[0] + H[1] / 2, S.FLOOR_Y + H[0] + H[1] + H[2] / 2]
SPACE, NOTHING = ord(" "), 255          # NOTHING: the agent calls waitKey(1) once more after each decision


def scene_base():
    return [S.upright(0, 0.0, y=Y[0])]


def scene_two():
    return scene_base() + [S.upright(1, 0.0, y=Y[1])]


def scene_fallen():
    box = S.upright(2, 0.36, y=S.FLOOR_Y + H[2] / 2, z_front=-0.06)
    box["R"] = S.rot_y(-25)
    return scene_two() + [box]


def _log(tmp_path):
    (d,) = [p for p in tmp_path.iterdir() if p.name.startswith("agent_")]
    return [json.loads(line) for line in open(d / "log.jsonl", encoding="utf-8")]


def run_agent(tmp_path, monkeypatch, capsys, use_aws, keys, steps, answers):
    """keys: key codes, or names from steps (change what the camera sees). answers: terminal inputs in order."""
    state = {"img": S.render(scene_base())}
    keys = list(keys)

    def wait_key(*_):
        while keys:
            k = keys.pop(0)
            if isinstance(k, str):
                state["img"] = S.render(steps[k]())
                continue
            return k
        return ord("q")

    class Cap:
        def __init__(self, *_):
            pass

        def isOpened(self):
            return True

        def set(self, *_):
            pass

        def read(self):
            return True, state["img"].copy()

        def release(self):
            pass

    answers = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda prompt="": (print(prompt), next(answers))[1])
    for name, fn in (("VideoCapture", Cap), ("imshow", lambda *a: None), ("namedWindow", lambda *a: None),
                     ("resizeWindow", lambda *a: None), ("destroyAllWindows", lambda: None), ("waitKey", wait_key)):
        monkeypatch.setattr(cv2, name, fn)
    monkeypatch.setattr(common, "DATA_DIR", str(tmp_path))
    argv = ["agent.py", "--calib", os.path.join(S.ROOT, "data", "camera_laptop.yaml"), "--marker-mm", "80"]
    if use_aws:
        def fake_aws_call(url, body, cap, first):
            """Same request agent.aws_call sends, answered by the Lambda handler instead of the network."""
            frames = [first] + [f for ok, f in (cap.read() for _ in range(agent.AWS_FRAMES - 1)) if ok]
            body = dict(body, return_image=False, images=[
                base64.b64encode(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()).decode()
                for f in frames])
            return json.loads(service.lambda_handler(body)["body"]), 0.01
        monkeypatch.setattr(agent, "aws_call", fake_aws_call)
        argv += ["--aws", "http://lambda.test/"]
    monkeypatch.setattr(sys, "argv", argv)
    agent.main()
    return _log(tmp_path), capsys.readouterr().out


def events(log, name):
    return [e for e in log if e["event"] == name]


MODES = pytest.mark.parametrize("use_aws", [False, True], ids=["laptop", "aws"])


@MODES
def test_fall_then_plan_the_same_box_again(tmp_path, monkeypatch, capsys, use_aws):
    def suggestion_scene():
        sugg = events(_log(tmp_path), "use_suggestion")[-1]["offset_m"]
        return scene_two() + [S.upright(2, sugg, y=Y[2])]

    keys = ([SPACE, NOTHING, "PLACE_1", SPACE]                       # ID 1 at 0 cm: GREEN, placed, check OK
            + [ord("d")] * 18 + [SPACE, NOTHING, "FALL", SPACE]      # ID 2 at +18 cm: RED, override, falls
            + [SPACE]                                                # SPACE while ID 2 is still on the floor
            + ["PICK_UP", SPACE, NOTHING, "PLACE_SUGGESTION", SPACE])
    steps = {"PLACE_1": scene_two, "FALL": scene_fallen, "PICK_UP": scene_two, "PLACE_SUGGESTION": suggestion_scene}
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws, keys, steps, ["o", "Yasin", "Test Prediction", "s"])
    decisions = [(e["box_id"], e["zone"], e.get("retry_after_fall")) for e in events(log, "decision")]
    assert decisions == [(1, "GREEN", False), (2, "RED", False), (2, "RED", True)]
    assert {e["source"] for e in events(log, "decision")} == {"aws" if use_aws else "laptop"}
    assert [e["status"] for e in events(log, "check")] == ["OK", "FELL", "OK"]
    fell = events(log, "check")[1]
    assert fell["fell_ids"] == [2] and "box ID 2 is on the floor next to the stack" in fell["message"]
    assert fell["worker_answer"] is None                     # seen on the floor: FELL without asking
    assert len(events(log, "wait_pickup")) == 1 and not events(log, "retake")
    assert "box ID 2 fell. Pick it up and keep it out of the camera view, then press SPACE to plan ID 2 again." in out
    assert "every box in the catalogue is already on the stack" not in out
    assert [e["event"] for e in log if e["event"] in ("override", "use_suggestion")] == ["override", "use_suggestion"]
    assert log[-1]["stats"] == {"decisions": 3, "GREEN": 1, "YELLOW": 0, "RED": 2, "override": 1, "fell": 1,
                                "retry_after_fall": 1}


@MODES
def test_space_before_placing_asks_and_looks_again(tmp_path, monkeypatch, capsys, use_aws):
    keys = ([SPACE, NOTHING, "PLACE_1", SPACE]                       # ID 1 GREEN, check OK
            + [ord("d")] * 6 + [SPACE, NOTHING, SPACE]               # ID 2 at +6 cm GREEN, SPACE before placing
            + ["PLACE_2", SPACE])                                    # placed now, SPACE again
    steps = {"PLACE_1": scene_two, "PLACE_2": lambda: scene_two() + [S.upright(2, 0.06, y=Y[2])]}
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws, keys, steps, ["p"])
    checks = events(log, "check")
    assert [e["status"] for e in checks] == ["OK", "NOT_PLACED", "OK"]
    assert checks[1]["worker_answer"] == "p" and "not placed yet" in checks[1]["message"]
    assert "box ID 2 is not visible. f = it fell out of view, p = not placed yet (look again)" in out
    assert log[-1]["stats"]["fell"] == 0
    assert "every box in the catalogue is already on the stack" not in out


@MODES
def test_not_visible_answer_f_is_a_fall(tmp_path, monkeypatch, capsys, use_aws):
    keys = [SPACE, NOTHING, "PLACE_1", SPACE] + [ord("d")] * 6 + [SPACE, NOTHING, SPACE]
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws, keys, {"PLACE_1": scene_two}, ["f"])
    checks = events(log, "check")
    assert [e["status"] for e in checks] == ["OK", "FELL"]
    assert checks[1]["worker_answer"] == "f" and "confirmed by the worker" in checks[1]["message"]
    assert log[-1]["stats"]["fell"] == 1


@MODES
def test_missing_box_is_planned_again_first(tmp_path, monkeypatch, capsys, use_aws):
    keys = ([SPACE, NOTHING, "PLACE_1", SPACE]                       # ID 1 GREEN, check OK
            + ["TAKE_1_OFF", SPACE, NOTHING, "PLACE_1", SPACE])      # ID 1 taken off -> agent plans ID 1 again
    steps = {"PLACE_1": scene_two, "TAKE_1_OFF": scene_base}
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws, keys, steps, [])
    assert "stack changed: ID 1 is missing from the stack." in out
    changed = events(log, "stack_changed")
    assert len(changed) == 1 and changed[0]["missing"] == [1] and changed[0]["stack"] == [0]
    assert [e["box_id"] for e in events(log, "decision")] == [1, 1]   # not ID 2 on top of ID 0
    assert [e["status"] for e in events(log, "check")] == ["OK", "OK"]
