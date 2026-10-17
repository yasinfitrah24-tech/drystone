"""Whole agent loop with a fake camera: ID 1 GREEN -> ID 2 RED -> override -> falls -> FELL -> picked up ->
ID 2 planned again -> use suggestion -> OK. Once on the laptop, once through the Lambda handler (--aws).

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


def run_agent(tmp_path, monkeypatch, capsys, use_aws):
    state = {"img": S.render(scene_base())}

    def suggestion_scene():
        sugg = [e for e in _log(tmp_path) if e["event"] == "use_suggestion"][-1]["offset_m"]
        return scene_two() + [S.upright(2, sugg, y=Y[2])]

    steps = {"PLACE_1": lambda: scene_two(), "FALL": scene_fallen, "PICK_UP": scene_two,
             "PLACE_SUGGESTION": suggestion_scene}
    # 255 = nothing pressed: the agent calls waitKey(1) once more after each decision
    keys = ([ord(" "), 255, "PLACE_1", ord(" ")]                      # ID 1 at 0 cm: GREEN, placed, check OK
            + [ord("d")] * 18 + [ord(" "), 255, "FALL", ord(" ")]     # ID 2 at +18 cm: RED, override, falls
            + [ord(" ")]                                              # SPACE while ID 2 is still on the floor
            + ["PICK_UP", ord(" "), 255, "PLACE_SUGGESTION", ord(" "), ord("q")])

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

    answers = iter(["o", "Yasin", "Test Prediction", "s"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
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


@pytest.mark.parametrize("use_aws", [False, True], ids=["laptop", "aws"])
def test_fall_then_plan_the_same_box_again(tmp_path, monkeypatch, capsys, use_aws):
    log, out = run_agent(tmp_path, monkeypatch, capsys, use_aws)
    decisions = [(e["box_id"], e["zone"], e.get("retry_after_fall")) for e in log if e["event"] == "decision"]
    assert decisions == [(1, "GREEN", False), (2, "RED", False), (2, "RED", True)]
    assert {e["source"] for e in log if e["event"] == "decision"} == {"aws" if use_aws else "laptop"}
    checks = [e["status"] for e in log if e["event"] == "check"]
    assert checks == ["OK", "FELL", "OK"]
    fell = [e for e in log if e["event"] == "check" and e["status"] == "FELL"][0]
    assert fell["fell_ids"] == [2] and "box ID 2 is on the floor next to the stack" in fell["message"]
    # after the fall: one clear instruction, no automatic retake loop
    assert [e["event"] for e in log].count("wait_pickup") == 1
    assert not [e for e in log if e["event"] == "retake"]
    assert "box ID 2 fell. Pick it up and keep it out of the camera view, then press SPACE to plan ID 2 again." in out
    assert "every box in the catalogue is already on the stack" not in out
    # the re-planned box used the suggestion and was checked OK on top of the stack
    assert [e["event"] for e in log if e["event"] in ("override", "use_suggestion")] == ["override", "use_suggestion"]
    stats = log[-1]["stats"]
    assert stats == {"decisions": 3, "GREEN": 1, "YELLOW": 0, "RED": 2, "override": 1, "fell": 1,
                     "retry_after_fall": 1}
